"""共享数据模型（上传任务与结果）"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class UploadTask:
    """单个上传任务"""
    video_id: str = ""
    video_file: str = ""
    cover_file: str = ""
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    tid: int = 3
    source_url: str = ""  # 转载来源（原视频链接）
    status: str = "pending"
    bvid: str = ""
    error: str = ""
    confirmed_at: str = ""
    uploaded_at: str = ""


@dataclass
class UploadResult:
    """上传结果"""
    success: bool = False
    bvid: str = ""
    error: str = ""
    upload_time: str = ""
