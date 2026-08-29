"""
pipeline.py — 主调度器

串联全流程：下载 → 转码 → 元数据汉化 → 产出 upload-ready 包
支持批量处理、状态追踪、失败恢复、文件整理。

用法：
  # 单视频
  python -m src.pipeline https://youtu.be/XXXXX

  # 批量（从文件读取 URL 列表）
  python -m src.pipeline --batch urls.txt

  # 指定输出目录
  python -m src.pipeline https://youtu.be/XXXXX --output ./my_batch
"""

import json
import time
import logging
import shutil
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

from .config import DIRS, DOWNLOAD, TRANSCODE, METADATA, LOG, ensure_dirs
from .downloader import VideoDownloader, DownloadResult
from .transcoder import VideoTranscoder, TranscodeResult
from .metadata_localizer import MetadataLocalizer, LocalizedMetadata
from .models import UploadResult, UploadTask
from .biliup_uploader import BiliupUploader

logger = logging.getLogger(__name__)


@dataclass
class VideoJob:
    """单个视频的处理任务"""
    url: str
    status: str = "pending"        # pending → downloading → transcoding → localizing → done / failed
    video_id: str = ""
    error: str = ""
    download_result: Optional[Dict] = None
    transcode_result: Optional[Dict] = None
    metadata_result: Optional[Dict] = None
    upload_result: Optional[Dict] = None
    bvid: str = ""                 # B 站 BV 号
    output_dir: str = ""
    started_at: str = ""
    completed_at: str = ""


@dataclass
class BatchResult:
    """批量处理结果"""
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    uploaded: int = 0  # 已上传到 B 站的数量
    jobs: List[VideoJob] = field(default_factory=list)
    output_dir: str = ""

    def summary(self) -> str:
        return (f"总计: {self.total}, 成功: {self.success}, "
                f"失败: {self.failed}, 跳过: {self.skipped}")


class Pipeline:
    def __init__(self, output_dir: Optional[Path] = None, interactive: bool = False,
                 auto_upload: bool = False):
        self.output_dir = output_dir or DIRS["output"]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.interactive = interactive    # 是否启用上传
        self.auto_upload = auto_upload    # 是否跳过确认直接上传

        self.downloader = VideoDownloader()
        self.transcoder = VideoTranscoder(output_dir=self.output_dir)
        self.localizer = MetadataLocalizer()
        self.uploader = BiliupUploader()  # 基于 biliup CLI，可靠全自动

        # 状态文件（用于恢复）
        self.state_file = self.output_dir / "pipeline_state.json"

    def process_single(self, url: str, job_output_dir: Optional[Path] = None) -> VideoJob:
        """
        处理单个视频：下载 → 转码 → 汉化 → 产出

        Args:
            url: YouTube URL
            job_output_dir: 指定输出目录，None 则用全局 output/

        Returns:
            VideoJob with final status
        """
        job = VideoJob(url=url, started_at=datetime.now().isoformat())
        out_dir = job_output_dir or self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        job.output_dir = str(out_dir)

        logger.info(f"{'='*60}")
        logger.info(f"开始处理: {url}")
        logger.info(f"输出目录: {out_dir}")
        logger.info(f"{'='*60}")

        # ── Step 1: 下载 ──────────────────────────────
        job.status = "downloading"
        self._save_state(job)

        dl_result = self.downloader.download(url)
        job.download_result = asdict(dl_result)

        if not dl_result.success:
            job.status = "failed"
            job.error = f"下载失败: {dl_result.error}"
            job.completed_at = datetime.now().isoformat()
            logger.error(f"❌ 下载失败: {job.error}")
            self._save_state(job)
            self._move_to_failed(dl_result, out_dir)
            return job

        job.video_id = dl_result.video_id
        logger.info(f"📦 下载完成: {dl_result.quality_preset} {dl_result.resolution}")

        # ── Step 2: 转码 ──────────────────────────────
        job.status = "transcoding"
        self._save_state(job)

        tc_result = self.transcoder.transcode(
            dl_result.video_file,
            output_name=f"{dl_result.video_id}"  # 用 video_id 作为输出名，简洁
        )
        job.transcode_result = asdict(tc_result)

        if not tc_result.success:
            job.status = "failed"
            job.error = f"转码失败: {tc_result.error}"
            job.completed_at = datetime.now().isoformat()
            logger.error(f"❌ 转码失败: {job.error}")
            self._save_state(job)
            return job

        if tc_result.skipped:
            logger.info(f"✅ 转码跳过（源文件已兼容）")
        else:
            logger.info(f"🎬 转码完成: {tc_result.output_file}")

        # ── Step 3: 元数据汉化 ────────────────────────
        job.status = "localizing"
        self._save_state(job)

        # 读取 info.json
        metadata = dl_result.raw_metadata
        if not metadata and dl_result.info_file:
            try:
                with open(dl_result.info_file, encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception as e:
                logger.warning(f"读取 info.json 失败: {e}")

        meta_result = self.localizer.localize(
            metadata=metadata,
            video_file=Path(tc_result.output_file).name,
            thumbnail_file=Path(dl_result.thumbnail_file).name if dl_result.thumbnail_file else "",
            video_file_path=tc_result.output_file,
        )

        # 写入 upload_meta.json 到输出目录
        meta_path = out_dir / f"{dl_result.video_id}_upload_meta.json"
        meta_result.to_json(str(meta_path))
        job.metadata_result = meta_result.to_dict()
        job.metadata_result["meta_file"] = str(meta_path)

        logger.info(f"📝 元数据汉化完成: {meta_result.title}")

        # ── Step 4: 整理输出文件 ──────────────────────
        # 将封面复制到输出目录，统一命名为 {video_id}_cover{ext}
        if dl_result.thumbnail_file:
            thumb_path = Path(dl_result.thumbnail_file)
            if thumb_path.exists():
                thumb_dest = out_dir / f"{dl_result.video_id}_cover{thumb_path.suffix}"
                if thumb_path.resolve() != thumb_dest.resolve():
                    shutil.copy2(thumb_path, thumb_dest)
                # 更新 meta_result 的封面文件名并重写 upload_meta.json
                meta_result.cover_file = thumb_dest.name
                meta_result.to_json(str(meta_path))
                job.metadata_result = meta_result.to_dict()
                job.metadata_result["meta_file"] = str(meta_path)
                job.metadata_result["cover_file"] = str(thumb_dest)

        # 生成 README.txt（人工上传指引）
        self._write_readme(out_dir, dl_result, tc_result, meta_result)

        # ── Step 5: B 站自动上传（可选） ────────────────
        if self.interactive:
            logger.info("📤 开始自动上传到 B 站...")
            try:
                upload_task = UploadTask(
                    video_id=dl_result.video_id,
                    video_file=str(Path(tc_result.output_file).absolute()),
                    cover_file=str(out_dir / meta_result.cover_file) if meta_result.cover_file else "",
                    title=meta_result.title,
                    description=meta_result.description,
                    tags=meta_result.tags,
                    tid=meta_result.tid,
                    source_url=url,  # 转载来源（原视频链接）
                )

                # 检查登录状态
                if not self.uploader.login_check():
                    logger.warning("⚠️  未登录 B 站，需要先登录")
                    if sys.stdin.isatty():
                        self.uploader.login()
                    else:
                        logger.error("非交互式终端，无法执行登录，跳过上传")

                if self.uploader.login_check():
                    # 确认模式：显示预览 + 等待用户确认
                    if not self.auto_upload:
                        self.uploader.show_preview(upload_task)
                        if not self.uploader.confirm_upload(upload_task):
                            logger.info("⏭️  用户取消上传")
                            job.upload_result = {"success": False, "error": "用户取消"}
                            job.status = "done"  # 视频处理成功，只是没上传
                            self._save_state(job)
                            return job
                    else:
                        logger.info("🤖 自动模式，跳过确认直接上传")

                    # 执行上传
                    result = self.uploader.upload(upload_task)
                    job.upload_result = {
                        "success": result.success,
                        "bvid": result.bvid,
                        "error": result.error,
                    }
                    if result.success:
                        job.status = "uploaded"
                        job.bvid = result.bvid
                        self.uploader.save_result(out_dir, upload_task, result)
                else:
                    job.upload_result = {"success": False, "error": "未登录 B 站"}

            except Exception as e:
                logger.error(f"❌ 上传过程出错: {e}")
                job.upload_result = {"success": False, "error": str(e)}
                # 上传失败不标记为 failed，视频处理本身是成功的

        # ── 完成 ──────────────────────────────────────
        job.status = "done"
        job.completed_at = datetime.now().isoformat()
        logger.info(f"✅ 全流程完成: {url}")
        logger.info(f"   输出: {tc_result.output_file}")
        logger.info(f"   标题: {meta_result.title}")
        logger.info(f"   大小: {tc_result.file_size / 1024 / 1024:.1f} MB")

        self._save_state(job)
        return job

    def process_batch(self, urls: List[str], batch_name: Optional[str] = None) -> BatchResult:
        """
        批量处理多个视频

        Args:
            urls: URL 列表
            batch_name: 批次名称（用于输出目录名）

        Returns:
            BatchResult
        """
        if not urls:
            return BatchResult()

        # 创建批次输出目录
        if not batch_name:
            batch_name = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        batch_dir = self.output_dir / batch_name
        batch_dir.mkdir(parents=True, exist_ok=True)

        result = BatchResult(total=len(urls), output_dir=str(batch_dir))
        logger.info(f"{'='*60}")
        logger.info(f"批次处理: {batch_name}")
        logger.info(f"视频数量: {len(urls)}")
        logger.info(f"输出目录: {batch_dir}")
        logger.info(f"{'='*60}")

        for i, url in enumerate(urls, 1):
            url = url.strip()
            if not url or url.startswith("#"):
                result.skipped += 1
                continue

            logger.info(f"\n[{i}/{len(urls)}] 处理: {url}")

            # 每个视频一个子目录
            video_id_hint = url.split("v=")[-1].split("/")[-1][:11] if "youtu" in url else f"video_{i}"
            job_dir = batch_dir / video_id_hint

            job = self.process_single(url, job_output_dir=job_dir)
            result.jobs.append(job)

            if job.status == "done":
                result.success += 1
            else:
                result.failed += 1

            # 批次状态文件
            self._save_batch_state(batch_dir, result)

        logger.info(f"\n{'='*60}")
        logger.info(f"批次完成: {result.summary()}")
        logger.info(f"{'='*60}")

        return result

    def _write_readme(self, out_dir: Path, dl: DownloadResult,
                      tc: TranscodeResult, meta: LocalizedMetadata):
        """写人工上传指引"""
        readme_path = out_dir / f"{dl.video_id}_README.txt"
        lines = [
            f"{'='*50}",
            f"  视频上传指引 — {dl.video_id}",
            f"{'='*50}",
            "",
            f"视频文件: {Path(tc.output_file).name}",
            f"封面文件: {Path(meta.cover_file).name if meta.cover_file else '无'}",
            "",
            f"── B站标题 ──",
            f"{meta.title}",
            "",
            f"── B站简介 ──",
            f"{meta.description}",
            "",
            f"── B站标签 ──",
            f"{', '.join(meta.tags)}",
            "",
            f"── 分区 ──",
            f"分区 ID: {meta.tid} ({'音乐' if meta.tid == 3 else '其他'})",
            "",
            f"── 源信息 ──",
            f"原标题: {meta.source_title}",
            f"原作者: {meta.source_uploader}",
            f"源链接: {meta.source_url}",
            f"分辨率: {tc.resolution}",
            f"时长: {dl.duration}s ({dl.duration//60}:{dl.duration%60:02d})",
            f"质量: {dl.quality_preset}",
            "",
            f"{'='*50}",
        ]
        readme_path.write_text("\n".join(lines), encoding="utf-8")

    def _save_state(self, job: VideoJob):
        """保存单个 job 状态"""
        state_path = Path(job.output_dir) / f"{job.video_id or 'pending'}_state.json"
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(asdict(job), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存状态失败: {e}")

    def _save_batch_state(self, batch_dir: Path, result: BatchResult):
        """保存批次状态"""
        state = {
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
            "skipped": result.skipped,
            "updated_at": datetime.now().isoformat(),
            "jobs": [asdict(j) for j in result.jobs],
        }
        state_path = batch_dir / "batch_state.json"
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _move_to_failed(self, dl_result: DownloadResult, out_dir: Path):
        """将失败任务的元数据移到 failed 目录"""
        failed_dir = DIRS["failed"]
        failed_dir.mkdir(parents=True, exist_ok=True)
        # 如果有 info.json，复制过去以备后用
        if dl_result.info_file and Path(dl_result.info_file).exists():
            shutil.copy2(dl_result.info_file, failed_dir)


# ── CLI ─────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(description="YouTube → B站 视频搬运流水线")
    parser.add_argument("urls", nargs="*", help="YouTube URL(s)")
    parser.add_argument("--batch", "-b", help="批量处理：从文件读取 URL 列表")
    parser.add_argument("--output", "-o", help="输出目录", default=None)
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    parser.add_argument("--upload", "-u", action="store_true", help="启用 B 站上传")
    parser.add_argument("--auto", "-a", action="store_true", help="自动上传（跳过确认，慎用）")

    args = parser.parse_args()

    # 日志设置
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    ensure_dirs()
    pipeline = Pipeline(
        output_dir=Path(args.output) if args.output else None,
        interactive=args.upload,
        auto_upload=args.auto
    )

    # 批量模式
    if args.batch:
        with open(args.batch) as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        result = pipeline.process_batch(urls)
        print(f"\n{result.summary()}")
        sys.exit(0 if result.failed == 0 else 1)

    # 单视频模式
    if not args.urls:
        parser.print_help()
        sys.exit(1)

    for url in args.urls:
        job = pipeline.process_single(url)
        if job.status != "done":
            sys.exit(1)


if __name__ == "__main__":
    main()