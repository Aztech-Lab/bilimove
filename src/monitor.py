"""
monitor.py — YouTube 频道/播放列表监控

定时检查监控目标，发现新视频自动走 pipeline 全流程（下载 → 转码 → 汉化 → 上传）。

用法：
  # 用默认配置 config/monitors.yaml 监控一轮
  python -m src.monitor

  # 指定配置文件
  python -m src.monitor --config my_monitors.yaml

  # 只检查不处理（dry-run，列出会处理哪些新视频）
  python -m src.monitor --dry-run

  # 监控 + 自动上传（跳过确认）
  python -m src.monitor --upload --auto

配置文件格式（config/monitors.yaml）：
  monitors:
    - name: "示例频道"
      url: "https://www.youtube.com/@Channel/videos"
      # 可选：只处理最近 N 个视频（默认 10）
      limit: 10
      # 可选：过滤关键词（标题包含任一关键词才处理，留空=全部）
      title_filter: []
      # 可选：排除关键词
      exclude: [" Shorts", "#short"]
      # 可选：跳过超过多少分钟的视频（0=不限制）
      max_duration_min: 0
"""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field

from .config import DIRS, ensure_dirs

logger = logging.getLogger(__name__)


@dataclass
class MonitorTarget:
    """单个监控目标"""
    name: str
    url: str
    limit: int = 10
    title_filter: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    max_duration_min: int = 0


@dataclass
class VideoEntry:
    """从列表里拉到的一条视频"""
    video_id: str
    url: str
    title: str
    duration: int = 0
    channel: str = ""
    upload_date: str = ""


class ChannelMonitor:
    """YouTube 频道/播放列表监控器"""

    def __init__(self, config_path: Optional[Path] = None,
                 state_file: Optional[Path] = None):
        self.config_path = config_path or (DIRS["config"] / "monitors.yaml")
        self.state_file = state_file or (DIRS["config"] / "processed.json")
        self._ensure_state_file()

    def _ensure_state_file(self):
        """确保状态文件存在"""
        if not self.state_file.exists():
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self._save_processed({})

    # ── 配置加载 ────────────────────────────────────────────

    def load_config(self) -> List[MonitorTarget]:
        """加载监控配置"""
        if not self.config_path.exists():
            logger.error(f"配置文件不存在：{self.config_path}")
            logger.error("请复制 config/monitors.yaml.example 为 config/monitors.yaml 并编辑")
            return []

        import yaml  # venv 里有 PyYAML
        with open(self.config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "monitors" not in data:
            logger.warning("配置文件为空或没有 monitors 段")
            return []

        targets = []
        for item in data["monitors"]:
            targets.append(MonitorTarget(
                name=item.get("name", item.get("url", "unnamed")),
                url=item["url"],
                limit=item.get("limit", 10),
                title_filter=item.get("title_filter", []) or [],
                exclude=item.get("exclude", []) or [],
                max_duration_min=item.get("max_duration_min", 0),
            ))

        logger.info(f"加载了 {len(targets)} 个监控目标")
        return targets

    # ── 频道列表（根目录 channels.txt，每行一个）──────────────

    def channels_file(self) -> Path:
        """根目录 channels.txt 路径"""
        return DIRS["project"] / "channels.txt"

    def load_channels(self) -> List[str]:
        """从根目录 channels.txt 加载频道 URL 列表（每行一个，忽略 # 注释和空行）"""
        path = self.channels_file()
        if not path.exists():
            return []
        urls = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                urls.append(line)
        return urls

    def save_channels(self, urls: List[str]):
        """保存频道 URL 到根目录 channels.txt"""
        path = self.channels_file()
        with open(path, "w", encoding="utf-8") as f:
            f.write("# 每行一个 YouTube 频道/播放列表 URL，复制粘贴即可\n")
            f.write("# 支持多个频道，每行一个\n")
            for u in urls:
                f.write(u + "\n")
        logger.info(f"已保存 {len(urls)} 个频道到 {path}")

    def prompt_channels(self) -> List[str]:
        """首次运行提示用户输入频道 URL"""
        print("\n📺 还没有配置监控频道。")
        print("请输入要监控的 YouTube 频道/播放列表 URL，每行一个，输入空行结束：")
        urls = []
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                break
            urls.append(line)
        if urls:
            self.save_channels(urls)
        return urls

    def resolve_targets(self) -> List[MonitorTarget]:
        """解析监控目标：优先 channels.txt，其次 monitors.yaml"""
        # 显式指定了 --config 则用 monitors.yaml
        if self.config_path and self.config_path != (DIRS["config"] / "monitors.yaml"):
            return self.load_config()

        # 默认用根目录 channels.txt
        urls = self.load_channels()
        if not urls:
            # 首次运行，交互式提示输入
            if sys.stdin.isatty():
                urls = self.prompt_channels()
            if not urls:
                logger.warning("未配置监控频道，请编辑根目录 channels.txt（每行一个 URL）")
                return []
        return [MonitorTarget(name=u, url=u) for u in urls]

    # ── 已处理记录管理 ────────────────────────────────────────

    def load_processed(self) -> Dict[str, Dict]:
        """读取已处理记录 {video_id: {status, time, title, ...}}"""
        try:
            with open(self.state_file, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_processed(self, data: Dict):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def mark_processed(self, video_id: str, status: str, title: str = "",
                       bvid: str = "", error: str = "", source_url: str = ""):
        """标记一个视频为已处理（按 YouTube video_id 去重，video_id 是 URL 的稳定部分）"""
        data = self.load_processed()
        data[video_id] = {
            "status": status,
            "title": title,
            "bvid": bvid,
            "error": error,
            "source_url": source_url,  # 原 YouTube 地址，用于去重核对
            "time": datetime.now().isoformat(),
        }
        self._save_processed(data)

    # ── 拉取频道视频列表 ────────────────────────────────────

    def fetch_entries(self, target: MonitorTarget) -> List[VideoEntry]:
        """用 yt-dlp 拉取频道/播放列表的视频列表（不下载）"""
        logger.info(f"📋 拉取列表：{target.name} ({target.url})")

        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--no-progress",
            "--playlist-end", str(target.limit),
        ]
        cmd.append(target.url)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, check=False
            )
        except subprocess.TimeoutExpired:
            logger.error(f"⏱️  拉取超时：{target.name}")
            return []

        if result.returncode != 0:
            logger.error(f"❌ 拉取失败：{result.stderr[:300]}")
            return []

        entries = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            vid = item.get("id", "")
            if not vid:
                continue

            entries.append(VideoEntry(
                video_id=vid,
                url=item.get("url", f"https://www.youtube.com/watch?v={vid}"),
                title=item.get("title", ""),
                duration=item.get("duration", 0) or 0,
                channel=item.get("channel", item.get("uploader", "")),
                upload_date=item.get("upload_date", ""),
            ))

        logger.info(f"   拉到 {len(entries)} 条视频")
        return entries

    # ── 过滤 ────────────────────────────────────────────────

    def should_process(self, entry: VideoEntry, target: MonitorTarget,
                       processed: Dict) -> bool:
        """判断这条视频是否应该处理"""
        # 已处理过
        if entry.video_id in processed:
            return False

        # 关键词过滤
        if target.title_filter:
            if not any(kw.lower() in entry.title.lower() for kw in target.title_filter):
                return False

        # 排除关键词
        if target.exclude:
            if any(kw.lower() in entry.title.lower() for kw in target.exclude):
                return False

        # 时长过滤
        if target.max_duration_min > 0 and entry.duration > 0:
            if entry.duration > target.max_duration_min * 60:
                return False

        return True

    # ── 主流程 ────────────────────────────────────────────────

    def run_once(self, upload: bool = False, auto_upload: bool = False,
                 dry_run: bool = False) -> Dict[str, int]:
        """跑一轮监控"""
        from .pipeline import Pipeline

        targets = self.resolve_targets()
        if not targets:
            return {"checked": 0, "new": 0, "processed": 0, "failed": 0}

        processed = self.load_processed()
        stats = {"checked": 0, "new": 0, "processed": 0, "failed": 0}

        pipeline = Pipeline(
            output_dir=DIRS["output"] / f"monitor_{datetime.now().strftime('%Y%m%d')}",
            interactive=upload,
            auto_upload=auto_upload,
        )

        for target in targets:
            logger.info(f"\n{'='*60}")
            logger.info(f"🔍 检查：{target.name}")
            logger.info(f"{'='*60}")

            entries = self.fetch_entries(target)
            stats["checked"] += len(entries)

            new_videos = [e for e in entries if self.should_process(e, target, processed)]

            if not new_videos:
                logger.info("   没有新视频")
                continue

            logger.info(f"🆓 发现 {len(new_videos)} 个新视频")
            stats["new"] += len(new_videos)

            for entry in new_videos:
                logger.info(f"\n▶ 处理：{entry.title} ({entry.video_id})")

                if dry_run:
                    logger.info("   [dry-run] 跳过实际处理")
                    continue

                try:
                    job = pipeline.process_single(entry.url)

                    if job.status in ("done", "uploaded"):
                        stats["processed"] += 1
                        self.mark_processed(
                            entry.video_id,
                            status=job.status,
                            title=entry.title,
                            bvid=job.bvid,
                            source_url=entry.url,
                        )
                    else:
                        stats["failed"] += 1
                        self.mark_processed(
                            entry.video_id,
                            status="failed",
                            title=entry.title,
                            error=job.error,
                            source_url=entry.url,
                        )

                except Exception as e:
                    logger.error(f"❌ 处理异常：{e}")
                    stats["failed"] += 1
                    self.mark_processed(
                        entry.video_id, status="failed",
                        title=entry.title, error=str(e), source_url=entry.url
                    )

                    # 失败后等一会再继续
                    time.sleep(3)

        logger.info(f"\n{'='*60}")
        logger.info(f"📊 监控完成：检查 {stats['checked']}，"
                    f"新发现 {stats['new']}，"
                    f"成功 {stats['processed']}，"
                    f"失败 {stats['failed']}")
        logger.info(f"{'='*60}")

        return stats


# ── CLI ─────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(description="YouTube 频道监控 + 自动搬运")
    parser.add_argument("--config", "-c", help="监控配置文件路径",
                        default=None)
    parser.add_argument("--upload", "-u", action="store_true",
                        help="处理完自动上传到 B 站")
    parser.add_argument("--auto", "-a", action="store_true",
                        help="自动上传模式（跳过确认，配合 --upload 用）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只检查列出新视频，不实际处理")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="详细日志")
    parser.add_argument("--login", action="store_true",
                        help="仅执行 B 站登录")

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    ensure_dirs()

    if args.login:
        from .biliup_uploader import BiliupUploader
        uploader = BiliupUploader()
        uploader.login()
        return

    config_path = Path(args.config) if args.config else None
    monitor = ChannelMonitor(config_path=config_path)

    stats = monitor.run_once(
        upload=args.upload,
        auto_upload=args.auto,
        dry_run=args.dry_run,
    )

    # 非 0 退出码表示有失败
    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()