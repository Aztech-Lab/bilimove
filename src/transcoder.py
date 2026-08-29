"""
transcoder.py — ffmpeg 视频转码模块

将下载的各种格式/编码统一转为 B站友好的：
  H.264 (libx264) + AAC, MP4 容器, faststart

功能：
- 自动检测源编码，如果已经是 H.264+AAC MP4 且质量达标则跳过
- CRF 18 视觉无损质量
- 192kbps AAC 音频（48kHz）
- faststart 优化网页播放
- 转码进度日志
- 输出到 output/ 目录
"""

import subprocess
import json
import os
import shutil
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from .config import TRANSCODE, DIRS

logger = logging.getLogger(__name__)


@dataclass
class TranscodeResult:
    """转码结果"""
    success: bool
    input_file: str = ""
    output_file: str = ""
    skipped: bool = False           # 是否跳过了转码（源已兼容）
    video_codec: str = ""
    audio_codec: str = ""
    resolution: str = ""
    duration: float = 0.0
    file_size: int = 0
    error: str = ""


class VideoTranscoder:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or DIRS["output"]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = TRANSCODE.ffmpeg_path or self._find_ffmpeg()

    def _find_ffmpeg(self) -> str:
        """查找 ffmpeg 路径"""
        path = shutil.which("ffmpeg")
        if not path:
            # macOS homebrew 默认路径
            for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
                if os.path.isfile(p):
                    return p
            raise RuntimeError("找不到 ffmpeg，请安装或配置 ffmpeg_path")
        return path

    def transcode(self, input_path: str, output_name: Optional[str] = None) -> TranscodeResult:
        """
        转码视频为 B站友好的 H.264+AAC MP4。

        Args:
            input_path: 输入视频文件路径
            output_name: 输出文件名（不含扩展名），None 则用输入文件名

        Returns:
            TranscodeResult
        """
        input_file = Path(input_path)
        if not input_file.exists():
            return TranscodeResult(success=False, input_file=input_path,
                                   error="输入文件不存在")

        # 探测源文件信息
        probe = self._probe(input_path)
        if probe is None:
            return TranscodeResult(success=False, input_file=input_path,
                                   error="无法探测文件信息")

        v_codec = probe.get("v_codec", "")
        a_codec = probe.get("a_codec", "")
        resolution = probe.get("resolution", "")
        duration = probe.get("duration", 0.0)
        v_bitrate = probe.get("v_bitrate", 0)
        a_bitrate = probe.get("a_bitrate", 0)
        container = input_file.suffix.lower()

        logger.info(f"源文件: {input_file.name}")
        logger.info(f"  视频: {v_codec} {resolution} {v_bitrate//1000}kbps")
        logger.info(f"  音频: {a_codec} {a_bitrate//1000}kbps")
        logger.info(f"  容器: {container}, 时长: {duration:.1f}s")

        # 检查是否可以跳过转码
        if TRANSCODE.skip_if_compatible and self._is_compatible(
            v_codec, a_codec, container, v_bitrate, a_bitrate
        ):
            logger.info("✅ 源文件已兼容 B站，跳过转码")
            output_path = self.output_dir / input_file.name
            if input_file.resolve() != output_path.resolve():
                shutil.copy2(input_file, output_path)
            return TranscodeResult(
                success=True,
                input_file=input_path,
                output_file=str(output_path),
                skipped=True,
                video_codec=v_codec,
                audio_codec=a_codec,
                resolution=resolution,
                duration=duration,
                file_size=output_path.stat().st_size,
            )

        # 确定输出文件名
        if output_name is None:
            output_name = input_file.stem
        output_path = self.output_dir / f"{output_name}.{TRANSCODE.output_format}"

        # 如果输出文件已存在，删除
        if output_path.exists():
            output_path.unlink()

        # 构建 ffmpeg 命令
        cmd = self._build_ffmpeg_command(input_path, str(output_path))

        logger.info(f"开始转码: {input_file.name} → {output_path.name}")
        logger.debug(f"ffmpeg 命令: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=max(600, int(duration * 3)),  # 至少10分钟，或3倍视频时长
                check=False
            )

            if result.returncode != 0:
                error = result.stderr[-500:] if result.stderr else "未知错误"
                logger.error(f"转码失败: {error}")
                return TranscodeResult(
                    success=False, input_file=input_path,
                    output_file=str(output_path), error=error
                )

            if not output_path.exists():
                return TranscodeResult(
                    success=False, input_file=input_path, error="转码完成但输出文件不存在"
                )

            file_size = output_path.stat().st_size

            # 验证输出
            out_probe = self._probe(str(output_path))
            out_v_codec = out_probe.get("v_codec", "") if out_probe else ""
            out_a_codec = out_probe.get("a_codec", "") if out_probe else ""

            logger.info(f"✅ 转码完成: {output_path.name} ({file_size/1024/1024:.1f} MB)")
            logger.info(f"  视频: {out_v_codec} {out_probe.get('resolution', '')}")
            logger.info(f"  音频: {out_a_codec} {out_probe.get('a_bitrate', 0)//1000}kbps")

            return TranscodeResult(
                success=True,
                input_file=input_path,
                output_file=str(output_path),
                skipped=False,
                video_codec=out_v_codec,
                audio_codec=out_a_codec,
                resolution=out_probe.get("resolution", "") if out_probe else "",
                duration=duration,
                file_size=file_size,
            )

        except subprocess.TimeoutExpired:
            return TranscodeResult(
                success=False, input_file=input_path,
                error=f"转码超时 (视频时长 {duration:.0f}s)"
            )
        except Exception as e:
            return TranscodeResult(
                success=False, input_file=input_path, error=f"异常: {e}"
            )

    def _is_compatible(self, v_codec: str, a_codec: str, container: str,
                       v_bitrate: int, a_bitrate: int) -> bool:
        """检查源文件是否已经是 B站兼容的格式"""
        # 容器必须是 mp4
        if container not in (".mp4", ".flv"):
            return False

        # 视频必须是 H.264
        if not v_codec.startswith("h264") and not v_codec.startswith("avc1"):
            return False

        # 音频必须是 AAC
        if not a_codec.startswith("aac") and not a_codec.startswith("mp4a"):
            return False

        # 码率检查
        if v_bitrate > 0 and v_bitrate < TRANSCODE.min_video_bitrate:
            return False
        if a_bitrate > 0 and a_bitrate < TRANSCODE.min_audio_bitrate:
            return False

        return True

    def _probe(self, file_path: str) -> Optional[Dict[str, Any]]:
        """用 ffprobe 探测文件信息"""
        ffprobe = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
        cmd = [
            ffprobe, "-v", "error", "-show_format", "-show_streams",
            "-of", "json", file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=10, check=False)
            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
            format_info = data.get("format", {})

            duration = float(format_info.get("duration", 0))

            v_codec = v_stream.get("codec_name", "") if v_stream else ""
            a_codec = a_stream.get("codec_name", "") if a_stream else ""

            width = int(v_stream.get("width", 0)) if v_stream else 0
            height = int(v_stream.get("height", 0)) if v_stream else 0
            resolution = f"{width}x{height}" if width and height else ""

            v_bitrate = int(v_stream.get("bit_rate", 0)) if v_stream else 0
            a_bitrate = int(a_stream.get("bit_rate", 0)) if a_stream else 0

            # 如果 stream 级没有 bitrate，用 format 级
            if v_bitrate == 0 and a_bitrate == 0:
                total_bitrate = int(format_info.get("bit_rate", 0))
                # 粗略分配
                if total_bitrate > 0:
                    v_bitrate = int(total_bitrate * 0.8)
                    a_bitrate = int(total_bitrate * 0.2)

            return {
                "v_codec": v_codec,
                "a_codec": a_codec,
                "resolution": resolution,
                "width": width,
                "height": height,
                "duration": duration,
                "v_bitrate": v_bitrate,
                "a_bitrate": a_bitrate,
            }
        except Exception as e:
            logger.error(f"ffprobe 失败: {e}")
            return None

    def _build_ffmpeg_command(self, input_path: str, output_path: str) -> list:
        """构建 ffmpeg 转码命令"""
        # 先 probe 源文件获取音频码率
        probe = self._probe(input_path)
        
        cmd = [self.ffmpeg, "-i", input_path, "-y"]

        # 视频：H.264 高质量
        cmd.extend([
            "-c:v", TRANSCODE.video_codec,
            "-crf", str(TRANSCODE.video_crf),
            "-preset", TRANSCODE.video_preset,
            "-pix_fmt", TRANSCODE.video_pix_fmt,
        ])

        # 音频：AAC，智能匹配源码率（不拉高低质量源）
        source_audio_bitrate = probe.get("a_bitrate", 0) if probe else 0
        target_bitrate = int(TRANSCODE.audio_bitrate.replace("k", "")) * 1000
        
        if source_audio_bitrate > 0 and source_audio_bitrate < target_bitrate:
            # 源码率低于目标，用源码率 + 20% 余量（避免再压缩损失）
            smart_bitrate = min(int(source_audio_bitrate * 1.2), target_bitrate)
            smart_bitrate_k = f"{smart_bitrate // 1000}k"
            logger.info(f"  音频智能码率: 源 {source_audio_bitrate//1000}k → 目标 {smart_bitrate_k}（不拉高）")
        else:
            smart_bitrate_k = TRANSCODE.audio_bitrate
            logger.info(f"  音频码率: {smart_bitrate_k}")
        
        cmd.extend([
            "-c:a", TRANSCODE.audio_codec,
            "-b:a", smart_bitrate_k,
            "-ar", str(TRANSCODE.audio_sample_rate),
        ])

        # faststart（网页播放优化）
        if TRANSCODE.faststart:
            cmd.extend(["-movflags", "+faststart"])

        # 输出
        cmd.append(output_path)

        return cmd


# ── 便捷函数 ────────────────────────────────────────────────
def transcode_video(input_path: str, output_name: Optional[str] = None) -> TranscodeResult:
    """全局便捷函数：转码单个视频"""
    transcoder = VideoTranscoder()
    return transcoder.transcode(input_path, output_name=output_name)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("用法: python -m src.transcoder <input_file> [output_name]")
        sys.exit(1)

    inp = sys.argv[1]
    out_name = sys.argv[2] if len(sys.argv) > 2 else None
    result = transcode_video(inp, output_name=out_name)

    if result.success:
        status = "跳过（已兼容）" if result.skipped else "转码完成"
        print(f"\n✅ {status}!")
        print(f"   输出: {result.output_file}")
        print(f"   大小: {result.file_size / 1024 / 1024:.1f} MB")
    else:
        print(f"\n❌ 失败: {result.error}")