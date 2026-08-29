"""
downloader.py — YouTube 视频下载模块

封装 yt-dlp，实现：
- 多 player client fallback（android_vr → android → web_safari → web_creator）
- 多质量预设 fallback（1080p → 720p → 480p → best）
- Cookies 自动注入
- 下载重试 + 超时
- 元数据和缩略图一并下载
- 下载结果标准化输出

每个视频产出：
  {title} [{video_id}].{ext}        — 视频文件
  {title} [{video_id}].webp/jpg     — 封面
  {title} [{video_id}].info.json    — 原始元数据
"""

import subprocess
import json
import time
import shutil
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

from .config import DOWNLOAD, DIRS
from .cookie_extractor import get_yt_cookies

logger = logging.getLogger(__name__)

# 用 venv 里的 yt-dlp（新版，修复了 player client / PO token 问题），
# 而不是 PATH 里可能过时的版本。
# 用 `python -m yt_dlp` 而非 console 脚本：venv 的 python 是符号链接，
# site-packages 相对定位，项目移动后永不失效（console 脚本的 shebang 是硬编码绝对路径）。
PYTHON = str(DIRS["project"] / ".venv" / "bin" / "python")
YTDLP = [PYTHON, "-m", "yt_dlp"]


@dataclass
class DownloadResult:
    """下载结果"""
    success: bool
    video_id: str = ""
    url: str = ""
    title: str = ""
    video_file: str = ""          # 最终视频文件路径
    thumbnail_file: str = ""      # 封面文件路径
    info_file: str = ""           # info.json 路径
    quality_preset: str = ""      # 使用的质量预设名
    resolution: str = ""          # 实际分辨率
    duration: int = 0             # 秒
    file_size: int = 0            # 字节
    error: str = ""
    raw_metadata: Dict = field(default_factory=dict)


class VideoDownloader:
    def __init__(self, download_dir: Optional[Path] = None):
        self.download_dir = download_dir or DIRS["downloads"]
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def download(self, url: str, preferred_quality: Optional[str] = None) -> DownloadResult:
        """
        下载视频，自动 fallback。

        Args:
            url: YouTube URL
            preferred_quality: 指定质量预设名（如 "1080p_h264_aac"），None 则自动选择

        Returns:
            DownloadResult
        """
        # 提取 video_id
        video_id = self._extract_video_id(url)
        if not video_id:
            return DownloadResult(success=False, url=url, error=f"无法解析 video ID: {url}")

        logger.info(f"开始下载: {url} (ID: {video_id})")

        # 获取 cookies（但不一定用——android_vr 不带 cookies 反而更可靠）
        cookies_path = get_yt_cookies()

        # 先获取元数据
        metadata = self._fetch_metadata(url, cookies_path)
        if metadata is None:
            return DownloadResult(success=False, video_id=video_id, url=url,
                                  error="无法获取视频元数据")

        title = metadata.get("title", video_id)
        duration = metadata.get("duration", 0)
        logger.info(f"视频标题: {title}, 时长: {duration}s")

        # 确定质量预设列表
        presets = self._get_quality_presets(preferred_quality)

        # 尝试下载
        for client_idx, client_name in enumerate(DOWNLOAD.player_clients):
            # android_vr 不带 cookies 反而更可靠（SABR 限制不会触发）
            # 其他 client 需要登录态
            use_cookies = client_name != "android_vr"
            active_cookies = cookies_path if use_cookies else None

            for preset_name, format_str, codec_desc in presets:
                for attempt in range(1, DOWNLOAD.max_retries + 1):
                    logger.info(f"尝试: client={client_name}, preset={preset_name}, "
                                f"attempt={attempt}/{DOWNLOAD.max_retries}, "
                                f"cookies={'yes' if active_cookies else 'no'}")

                    result = self._attempt_download(
                        url=url,
                        video_id=video_id,
                        title=title,
                        duration=duration,
                        cookies_path=active_cookies,
                        client_name=client_name,
                        preset_name=preset_name,
                        format_str=format_str,
                        metadata=metadata,
                    )

                    if result.success:
                        logger.info(f"✅ 下载成功: {preset_name} via {client_name}")
                        return result

                    # 这些错误意味着该 client 下格式不可用，换格式即可（不换 client）
                    skip_format_errors = ["not available", "Requested format"]
                    # 这些错误意味着该 client 整体不可用，必须换 client
                    switch_client_errors = ["403", "SABR", "Forbidden", "sign in",
                                            "Only images are available",
                                            "This video is unavailable",
                                            "Error code: 152", "Error code: 150",
                                            "Video unavailable", "Sign in to confirm"]

                    should_switch_client = any(e in result.error for e in switch_client_errors)
                    should_skip_format = any(e in result.error for e in skip_format_errors)

                    if should_switch_client:
                        logger.warning(f"Client {client_name} 不可用，切换: {result.error[:100]}")
                        break  # 跳到下一个 client
                    elif should_skip_format:
                        logger.warning(f"格式 {preset_name} 在 {client_name} 下不可用，"
                                       f"尝试下一个格式")
                        break  # 跳到下一个 preset（break 内层 attempt 循环）
                    else:
                        # 其他错误 → 重试
                        if attempt < DOWNLOAD.max_retries:
                            delay = DOWNLOAD.retry_delay * attempt
                            logger.warning(f"重试中 ({attempt}/{DOWNLOAD.max_retries})，"
                                           f"等待 {delay}s... 错误: {result.error[:100]}")
                            time.sleep(delay)

        # 所有尝试失败
        logger.error(f"❌ 所有下载尝试失败: {url}")
        return DownloadResult(success=False, video_id=video_id, url=url,
                              title=title, error="所有下载策略均失败")

    def _extract_video_id(self, url: str) -> str:
        """从 URL 提取 video ID"""
        patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
            r"youtube\.com/watch.*[?&]v=([a-zA-Z0-9_-]{11})",
        ]
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        # 可能 URL 本身就是 ID
        if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
            return url
        return ""

    def _fetch_metadata(self, url: str, cookies_path: Optional[str]) -> Optional[Dict]:
        """用 yt-dlp 获取元数据（不下载视频）"""
        cmd = [
            *YTDLP, "--dump-json", "--no-warnings", "--no-progress",
        ]
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        cmd.append(url)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=60, check=False
            )
            if result.returncode != 0:
                # 不带 cookies 重试
                if cookies_path:
                    logger.debug("带 cookies 获取元数据失败，尝试不带 cookies")
                    result = subprocess.run(
                        [*YTDLP, "--dump-json", "--no-warnings", "--no-progress", url],
                        capture_output=True, text=True, timeout=60, check=False
                    )
                if result.returncode != 0:
                    logger.error(f"获取元数据失败: {result.stderr[:200]}")
                    return None

            return json.loads(result.stdout.strip())
        except subprocess.TimeoutExpired:
            logger.error("获取元数据超时")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"解析元数据 JSON 失败: {e}")
            return None

    def _get_quality_presets(self, preferred: Optional[str] = None) -> List[Tuple[str, str, str]]:
        """获取质量预设列表，如果指定了 preferred 则优先它"""
        all_presets = DOWNLOAD.quality_presets
        if preferred:
            # 找到指定的预设，放到最前面
            matched = [p for p in all_presets if p[0] == preferred]
            if matched:
                rest = [p for p in all_presets if p[0] != preferred]
                return matched + rest
        return all_presets

    def _attempt_download(self, **kwargs) -> DownloadResult:
        """单次下载尝试"""
        url = kwargs["url"]
        video_id = kwargs["video_id"]
        title = kwargs["title"]
        cookies_path = kwargs["cookies_path"]
        client_name = kwargs["client_name"]
        preset_name = kwargs["preset_name"]
        format_str = kwargs["format_str"]
        metadata = kwargs["metadata"]

        # 清理标题用于文件名
        safe_title = self._sanitize_filename(title)
        output_template = f"{safe_title} [{video_id}]"

        # 每个视频单独一个子文件夹，方便管理
        video_dir = self.download_dir / video_id
        video_dir.mkdir(parents=True, exist_ok=True)

        # 构建命令
        cmd = [
            *YTDLP,
            "--cookies-from-browser", DOWNLOAD.cookies_from_browser,
            "--remote-components", DOWNLOAD.remote_components,
            "--extractor-args", f"youtube:player_client={client_name}",
            "-f", format_str,
            "--merge-output-format", "mp4",
            "-o", str(video_dir / f"{output_template}.%(ext)s"),
            "--write-thumbnail",
            "--write-info-json",
            "--no-progress",
            "--no-warnings",
        ]

        if DOWNLOAD.rate_limit:
            cmd.extend(["--rate-limit", DOWNLOAD.rate_limit])

        cmd.append(url)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=DOWNLOAD.timeout, check=False, cwd=str(video_dir)
            )

            if result.returncode != 0:
                error = result.stderr.strip()
                return DownloadResult(
                    success=False, video_id=video_id, url=url, title=title,
                    quality_preset=preset_name, error=error
                )

            # 查找下载的文件
            video_file = self._find_file(video_id, [".mp4", ".mkv", ".webm"])
            thumbnail_file = self._find_file(video_id, [".webp", ".jpg", ".png"])
            info_file = self._find_file(video_id, [".info.json"])

            if not video_file:
                return DownloadResult(
                    success=False, video_id=video_id, url=url, title=title,
                    quality_preset=preset_name,
                    error="下载命令成功但找不到视频文件"
                )

            # 获取文件信息
            file_size = video_file.stat().st_size
            resolution = self._get_resolution(str(video_file))

            return DownloadResult(
                success=True,
                video_id=video_id,
                url=url,
                title=title,
                video_file=str(video_file),
                thumbnail_file=str(thumbnail_file) if thumbnail_file else "",
                info_file=str(info_file) if info_file else "",
                quality_preset=preset_name,
                resolution=resolution,
                duration=metadata.get("duration", 0),
                file_size=file_size,
                raw_metadata=metadata,
            )

        except subprocess.TimeoutExpired:
            return DownloadResult(
                success=False, video_id=video_id, url=url, title=title,
                quality_preset=preset_name, error=f"下载超时 ({DOWNLOAD.timeout}s)"
            )
        except Exception as e:
            return DownloadResult(
                success=False, video_id=video_id, url=url, title=title,
                quality_preset=preset_name, error=f"异常: {e}"
            )

    def _sanitize_filename(self, name: str) -> str:
        """清理文件名中的非法字符"""
        # 替换 Windows/macOS/Linux 都不允许的字符
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 去除首尾空格和点
        name = name.strip(". ")
        # 限制长度
        if len(name) > 100:
            name = name[:100]
        return name or "untitled"

    def _find_file(self, video_id: str, extensions: List[str]) -> Optional[Path]:
        """在视频子文件夹中查找指定 video_id 的文件"""
        video_dir = self.download_dir / video_id
        if not video_dir.exists():
            return None
        for ext in extensions:
            # 用字符串匹配而非 glob（避免 video_id 中的特殊字符被当 glob 语法）
            for f in video_dir.iterdir():
                # 精确后缀匹配（处理 .info.json 等多段扩展名）
                if f.name.endswith(ext) and video_id in f.name:
                    return f
        return None

    def _get_resolution(self, video_path: str) -> str:
        """用 ffprobe 获取视频分辨率"""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0",
                 video_path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip().replace(",", "x")
        except Exception:
            pass
        return "unknown"


# ── 便捷函数 ────────────────────────────────────────────────
def download_video(url: str, preferred_quality: Optional[str] = None) -> DownloadResult:
    """全局便捷函数：下载单个视频"""
    downloader = VideoDownloader()
    return downloader.download(url, preferred_quality=preferred_quality)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("用法: python -m src.downloader <URL> [quality_preset]")
        sys.exit(1)

    url = sys.argv[1]
    quality = sys.argv[2] if len(sys.argv) > 2 else None
    result = download_video(url, preferred_quality=quality)

    if result.success:
        print(f"\n✅ 下载成功!")
        print(f"   文件: {result.video_file}")
        print(f"   质量: {result.quality_preset}")
        print(f"   分辨率: {result.resolution}")
        print(f"   大小: {result.file_size / 1024 / 1024:.1f} MB")
    else:
        print(f"\n❌ 下载失败: {result.error}")