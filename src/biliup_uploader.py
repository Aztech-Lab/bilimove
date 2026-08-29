"""
biliup_uploader.py — B 站上传（基于 biliup CLI，可靠、全自动）

用 biliup CLI 上传，替代脆弱的浏览器自动化。支持：
- 仅自己可见（--is-only-self 1），方便在手机上核实后再改公开
- 转载（--copyright 2）+ 转载来源（--source）
- 封面、简介（保留换行）、标签、分区
- 自动解析 BV 号

用法：
  python -m src.biliup_uploader ./output/VIDEO_ID/ --auto
"""

import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import asdict
from datetime import datetime

from .config import DIRS
from .models import UploadTask, UploadResult

logger = logging.getLogger(__name__)


class BiliupUploader:
    """基于 biliup CLI 的 B 站上传器"""

    def __init__(self, cookies_file: Optional[Path] = None):
        # biliup 默认读当前目录的 cookies.json；这里固定用 config/cookies.json
        self.cookies_file = cookies_file or (DIRS["config"] / "cookies.json")
        # biliup 二进制在 venv 里，不在 PATH，用完整路径
        self.biliup_bin = str(DIRS["project"] / ".venv" / "bin" / "biliup")

    def _biliup_cmd(self, *args) -> List[str]:
        """构造 biliup 命令（带 cookies 文件）"""
        return [self.biliup_bin, "-u", str(self.cookies_file), *args]

    def login_check(self) -> bool:
        """检查 cookie 是否有效（biliup list 能列出视频即有效）"""
        try:
            result = subprocess.run(
                self._biliup_cmd("list"),
                capture_output=True, text=True, timeout=60, check=False,
                cwd=str(DIRS["project"]),
            )
            # 输出里包含 "user: xxx" 或 BV 号即登录有效
            return "user:" in result.stdout or "BV" in result.stdout
        except Exception as e:
            logger.error(f"检查登录失败: {e}")
            return False

    def login(self):
        """登录 B 站（biliup login，需要交互扫码）"""
        logger.info("🔐 启动 biliup 登录...")
        try:
            subprocess.run(
                self._biliup_cmd("login"),
                cwd=str(DIRS["project"]),
            )
            return True
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False

    def show_preview(self, task: UploadTask):
        """显示上传预览"""
        print("\n" + "=" * 70)
        print("📺 B 站上传预览（biliup）")
        print("=" * 70)
        print(f"🆔 Video ID: {task.video_id}")
        print(f"📁 视频文件：{Path(task.video_file).name}")
        print(f"📝 标    题：{task.title}")
        print(f"📄 简    介：{task.description[:100]}...")
        print(f"🏷️  标    签：{', '.join(task.tags)}")
        print(f"📂 分    区：ID {task.tid}")
        print(f"🔗 转载来源：{task.source_url}")
        print(f"👁  可见性：仅自己可见")
        print("=" * 70)

    def confirm_upload(self, task: UploadTask) -> bool:
        """等待用户确认"""
        print("\n操作选项:")
        print("  [1] ✅ 直接上传")
        print("  [2] ❌ 取消")
        while True:
            choice = input("\n请选择 (1/2): ").strip()
            if choice == "1":
                return True
            elif choice == "2":
                print("❌ 已取消上传")
                return False
            else:
                print("无效选择，请重试")

    def upload(self, task: UploadTask) -> UploadResult:
        """通过 biliup CLI 上传视频（仅自己可见 + 转载）"""
        if not Path(task.video_file).exists():
            return UploadResult(success=False, error=f"视频文件不存在：{task.video_file}")

        # 封面：biliup 不接受 webp，转成 png
        cover_file = task.cover_file
        if cover_file and Path(cover_file).exists():
            if Path(cover_file).suffix.lower() == ".webp":
                png_path = str(Path(cover_file).with_suffix(".png"))
                if not Path(png_path).exists():
                    import subprocess as sp
                    sp.run(
                        ["ffmpeg", "-y", "-i", cover_file, "-frames:v", "1", png_path],
                        capture_output=True, timeout=30,
                    )
                if Path(png_path).exists():
                    cover_file = png_path
                else:
                    cover_file = ""
            else:
                cover_file = str(Path(cover_file).absolute())

        # 构造 biliup 命令
        cmd = self._biliup_cmd(
            "upload", task.video_file,
            "--title", task.title,
            "--desc", task.description,          # 保留换行
            "--tag", ",".join(task.tags),
            "--tid", str(task.tid),
            "--copyright", "2",                  # 转载
            "--is-only-self", "1",               # 仅自己可见
        )
        if cover_file:
            cmd.extend(["--cover", cover_file])
        if task.source_url:
            cmd.extend(["--source", task.source_url])

        logger.info(f"🚀 开始上传（biliup）：{task.title}")
        logger.info(f"   命令: {' '.join(cmd[:6])} ...")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, check=False,
                cwd=str(DIRS["project"]),
            )
            output = result.stdout + result.stderr

            # 解析 BV 号
            bvid = self._extract_bvid(output)
            # 判断成功：输出含 "投稿成功" 或 BV 号
            success = bool(bvid) or "投稿成功" in output or "code: 0" in output

            if success:
                logger.info(f"✅ 上传成功：{task.title} (BV: {bvid})")
                return UploadResult(
                    success=True,
                    bvid=bvid,
                    upload_time=datetime.now().isoformat(),
                )
            else:
                # 提取错误信息
                error = self._extract_error(output)
                logger.error(f"❌ 上传失败：{error}")
                return UploadResult(success=False, error=error)

        except subprocess.TimeoutExpired:
            return UploadResult(success=False, error="上传超时")
        except Exception as e:
            logger.error(f"❌ 上传异常: {e}")
            return UploadResult(success=False, error=str(e))

    def _extract_bvid(self, output: str) -> str:
        """从输出中提取 BV 号"""
        m = re.search(r'(BV[0-9a-zA-Z]{10})', output)
        return m.group(1) if m else ""

    def _extract_error(self, output: str) -> str:
        """从输出中提取错误信息"""
        # 找 message 字段
        m = re.search(r'"message":\s*"([^"]+)"', output)
        if m:
            return m.group(1)
        # 找 ERROR 行
        for line in output.splitlines():
            if "ERROR" in line or "error" in line.lower():
                return line.strip()[:200]
        return output.strip()[-200:]

    def save_result(self, output_dir: Path, task: UploadTask, result: UploadResult):
        """保存上传结果"""
        result_file = output_dir / f"{task.video_id}_upload_result.json"
        data = {
            "video_id": task.video_id,
            "title": task.title,
            "status": "done" if result.success else "failed",
            "bvid": result.bvid,
            "upload_time": result.upload_time,
            "error": result.error,
        }
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已保存：{result_file}")

    def upload_single(self, output_dir: Path, auto: bool = False) -> Optional[UploadResult]:
        """上传单个视频"""
        task = self.load_task(output_dir)
        if not task or task.error:
            return None

        if not self.login_check():
            print("\n⚠️  需要先登录 B 站")
            if sys.stdin.isatty():
                if input("现在登录？(y/n): ").strip().lower() == "y":
                    self.login()
                else:
                    return None
            else:
                logger.error("非交互式终端，无法登录")
                return None

        self.show_preview(task)

        if not auto:
            if not self.confirm_upload(task):
                task.status = "skipped"
                return None

        result = self.upload(task)

        if result:
            task.status = "done" if result.success else "failed"
            task.bvid = result.bvid
            task.error = result.error
            task.uploaded_at = result.upload_time
            self.save_result(output_dir, task, result)

        return result

    def load_task(self, output_dir: Path) -> Optional[UploadTask]:
        """从输出目录加载上传任务"""
        meta_files = list(output_dir.glob("*_upload_meta.json"))
        if not meta_files:
            logger.error(f"未找到元数据文件：{output_dir}/*_upload_meta.json")
            return None

        meta_file = meta_files[0]
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            video_id = meta_file.stem.replace("_upload_meta", "")
            task = UploadTask(
                video_id=video_id,
                video_file=meta.get("video_file", ""),
                cover_file=meta.get("bili_cover", ""),
                title=meta.get("bili_title", ""),
                description=meta.get("bili_description", ""),
                tags=meta.get("bili_tags", []),
                tid=meta.get("bili_tid", 3),
                source_url=meta.get("source_url", ""),
            )

            video_path = output_dir / task.video_file
            if not video_path.exists():
                logger.error(f"视频文件不存在：{video_path}")
                task.error = f"视频文件缺失：{task.video_file}"
                return task
            task.video_file = str(video_path.absolute())

            if task.cover_file:
                cover_path = output_dir / task.cover_file
                if cover_path.exists():
                    task.cover_file = str(cover_path.absolute())
                else:
                    task.cover_file = ""

            return task
        except Exception as e:
            logger.error(f"读取元数据失败: {e}")
            return None


# ── CLI ─────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(description="B 站上传（biliup）")
    parser.add_argument("output_dir", nargs="?", help="视频输出目录")
    parser.add_argument("--auto", action="store_true", help="自动模式（跳过确认）")
    parser.add_argument("--login", action="store_true", help="登录 B 站")
    parser.add_argument("--check", action="store_true", help="检查登录状态")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    uploader = BiliupUploader()

    if args.login:
        uploader.login()
        return
    if args.check:
        print(f"登录状态：{'✅ 已登录' if uploader.login_check() else '❌ 未登录'}")
        return
    if not args.output_dir:
        parser.print_help()
        sys.exit(1)

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        logger.error(f"目录不存在：{output_dir}")
        sys.exit(1)

    result = uploader.upload_single(output_dir, auto=args.auto)
    if not result or not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
