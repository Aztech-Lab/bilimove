"""
config.py — 全局配置管理

项目路径、下载策略、转码参数、B站参数、日志等配置。
所有模块从这里读取配置，不硬编码路径。
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import json
import os

# ── 项目根目录 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # video_moving/

# ── 目录结构 ────────────────────────────────────────────────
# 生成数据统一收进 data/，保持根目录清爽
DIRS = {
    "project":     PROJECT_ROOT,                # 项目根目录
    "data":        PROJECT_ROOT / "data",       # 生成数据根目录
    "downloads":   PROJECT_ROOT / "data" / "downloads",
    "logs":        PROJECT_ROOT / "data" / "logs",
    "config":      PROJECT_ROOT / "config",
    "src":         PROJECT_ROOT / "src",
    "output":      PROJECT_ROOT / "data" / "output",       # 转码后的最终上传就绪文件
    "archive":     PROJECT_ROOT / "data" / "archive",      # 已处理完成的原始文件归档
    "failed":      PROJECT_ROOT / "data" / "failed",       # 处理失败的文件
}

def ensure_dirs():
    """创建所有必要的目录"""
    for d in DIRS.values():
        d.mkdir(parents=True, exist_ok=True)

# ── 下载策略 ────────────────────────────────────────────────
@dataclass
class DownloadConfig:
    # yt-dlp player client fallback 链（按优先级尝试）
    player_clients: list = field(default_factory=lambda: [
        "web_embedded",    # 最可靠，带 cookies 能拿 1080p
        "android_vr",      # 备选，不需要 cookies
        "android",         # 备选
        "web_safari",      # Safari web client
        "web_creator",     # 需要登录 cookies
    ])
    
    # Chrome cookies 提取
    cookies_from_browser: str = "chrome"  # 从浏览器自动提取 cookies
    remote_components: str = "ejs:github"  # JS challenge solver

    # 视频质量优先级（按优先级尝试，第一个成功的就用）
    # 用 yt-dlp 智能格式串（而非固定 format_id），画质优先且避免空转：
    #   - 一上来就用 best_quality（bestvideo+bestaudio），拿最高画质+音质，
    #     转码器会转成 H.264+AAC 给 B 站，无需先试特定编码白费功夫
    #   - 若 best_quality 失败，再退到 H.264+AAC（B站兼容，无需转码）
    # 格式串里的 "/" 是 yt-dlp 的 fallback 链，一个命令内自动降级。
    quality_presets: list = field(default_factory=lambda: [
        # 最高质量任意编码（需转码，但画质/音质最好）
        ("best_quality", "bestvideo+bestaudio/best", "any"),
        # 兜底：最高质量 H.264 + AAC（B站兼容，无需转码）
        ("best_h264_aac", "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]", "h264+aac"),
    ])

    # 下载选项
    max_retries: int = 3
    retry_delay: float = 2.0
    write_thumbnail: bool = True
    write_info_json: bool = True
    rate_limit: str = ""  # e.g. "5M" — 留空不限速
    timeout: int = 300    # 单次下载超时（秒）

    # Cookies
    cookie_file: str = "/tmp/yt_cookies.txt"
    cookie_max_age: int = 3600  # cookies 缓存有效期（秒），1小时
    chrome_cdp_port: int = 9222  # Chrome remote debugging 端口

# ── 转码策略 ────────────────────────────────────────────────
@dataclass
class TranscodeConfig:
    # 目标格式：B站友好的 H.264 + AAC
    video_codec: str = "libx264"
    video_crf: int = 18           # 18 = 视觉无损，质量很好
    video_preset: str = "slow"    # 编码速度（slow = 质量更好）
    video_pix_fmt: str = "yuv420p"

    audio_codec: str = "aac"
    audio_bitrate: str = "320k"  # 最高目标码率（源低于此值时不拉高）
    audio_sample_rate: int = 48000

    # 输出容器
    output_format: str = "mp4"
    faststart: bool = True        # moov atom 前置，网页播放更快加载

    # 如果源已经是 H.264 + AAC 且质量达标，是否跳过转码
    skip_if_compatible: bool = True
    min_video_bitrate: int = 200_000   # 低于此码率才考虑转码提升
    min_audio_bitrate: int = 128_000

    # ffmpeg 路径（空则用 PATH 中的）
    ffmpeg_path: str = ""

# ── 元数据汉化策略 ──────────────────────────────────────────
@dataclass
class MetadataConfig:
    # B站分区 ID（3 = 音乐区）
    default_tid: int = 3
    # 标签数量上限
    max_tags: int = 10
    # 标题最大长度（B站限制 80 字符）
    max_title_length: int = 80
    # 简介最大长度
    max_desc_length: int = 2000
    # 是否添加版权声明
    add_copyright_notice: bool = True
    # 默认标签（会加到每个视频）
    base_tags: list = field(default_factory=lambda: ["音乐搬运"])

# ── 日志 ────────────────────────────────────────────────────
@dataclass
class LogConfig:
    level: str = "INFO"
    log_file: Optional[str] = None  # None = 自动生成到 logs/

    def get_log_file(self):
        if self.log_file:
            return Path(self.log_file)
        return DIRS["logs"] / f"pipeline_{self._get_date()}.log"

    @staticmethod
    def _get_date():
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d")

# ── 全局实例 ────────────────────────────────────────────────
DOWNLOAD = DownloadConfig()
TRANSCODE = TranscodeConfig()
METADATA = MetadataConfig()
LOG = LogConfig()

def load_config(config_path: Optional[str] = None):
    """从 JSON 文件加载配置覆盖默认值"""
    if config_path is None:
        config_path = str(DIRS["config"] / "settings.json")
    path = Path(config_path)
    if not path.exists():
        return

    with open(path) as f:
        data = json.load(f)

    global DOWNLOAD, TRANSCODE, METADATA, LOG
    if "download" in data:
        for k, v in data["download"].items():
            if hasattr(DOWNLOAD, k):
                setattr(DOWNLOAD, k, v)
    if "transcode" in data:
        for k, v in data["transcode"].items():
            if hasattr(TRANSCODE, k):
                setattr(TRANSCODE, k, v)
    if "metadata" in data:
        for k, v in data["metadata"].items():
            if hasattr(METADATA, k):
                setattr(METADATA, k, v)
    if "log" in data:
        for k, v in data["log"].items():
            if hasattr(LOG, k):
                setattr(LOG, k, v)

# 初始化
ensure_dirs()