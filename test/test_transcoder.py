"""transcoder.py 测试（纯逻辑）"""

from src.transcoder import VideoTranscoder


class TestIsCompatible:
    def setup_method(self):
        self.t = VideoTranscoder()

    def test_compatible_h264_aac(self):
        assert self.t._is_compatible("h264", "aac", ".mp4", 500_000, 160_000) is True

    def test_avc1_mp4a(self):
        assert self.t._is_compatible("avc1", "mp4a", ".mp4", 500_000, 160_000) is True

    def test_wrong_container(self):
        assert self.t._is_compatible("h264", "aac", ".mkv", 500_000, 160_000) is False

    def test_wrong_video_codec(self):
        assert self.t._is_compatible("av1", "aac", ".mp4", 500_000, 160_000) is False

    def test_wrong_audio_codec(self):
        assert self.t._is_compatible("h264", "opus", ".mp4", 500_000, 160_000) is False

    def test_low_video_bitrate(self):
        assert self.t._is_compatible("h264", "aac", ".mp4", 50_000, 160_000) is False

    def test_low_audio_bitrate(self):
        assert self.t._is_compatible("h264", "aac", ".mp4", 500_000, 50_000) is False


class TestBuildFfmpegCommand:
    def setup_method(self):
        self.t = VideoTranscoder()

    def test_command_has_codecs(self):
        cmd = self.t._build_ffmpeg_command("/in.mp4", "/out.mp4")
        joined = " ".join(cmd)
        assert "libx264" in joined
        assert "aac" in joined
        assert "yuv420p" in joined
        assert "/in.mp4" in joined
        assert "/out.mp4" in joined
