"""downloader.py 测试（纯逻辑，不联网）"""

from src.downloader import VideoDownloader


class TestExtractVideoId:
    def setup_method(self):
        self.d = VideoDownloader()

    def test_watch_url(self):
        assert self.d._extract_video_id("https://www.youtube.com/watch?v=9tKaCIuOggw") == "9tKaCIuOggw"

    def test_youtu_be(self):
        assert self.d._extract_video_id("https://youtu.be/9tKaCIuOggw") == "9tKaCIuOggw"

    def test_shorts(self):
        assert self.d._extract_video_id("https://www.youtube.com/shorts/9tKaCIuOggw") == "9tKaCIuOggw"

    def test_music_youtube(self):
        assert self.d._extract_video_id("https://music.youtube.com/watch?v=QN3IxW2uN8g") == "QN3IxW2uN8g"

    def test_embed(self):
        assert self.d._extract_video_id("https://www.youtube.com/embed/9tKaCIuOggw") == "9tKaCIuOggw"

    def test_plain_id(self):
        assert self.d._extract_video_id("9tKaCIuOggw") == "9tKaCIuOggw"

    def test_invalid(self):
        assert self.d._extract_video_id("https://example.com/not-youtube") == ""


class TestSanitizeFilename:
    def setup_method(self):
        self.d = VideoDownloader()

    def test_illegal_chars(self):
        assert self.d._sanitize_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"

    def test_strip_dots_spaces(self):
        assert self.d._sanitize_filename("  .hello.  ") == "hello"

    def test_empty(self):
        assert self.d._sanitize_filename("") == "untitled"

    def test_long(self):
        long = "x" * 200
        assert len(self.d._sanitize_filename(long)) == 100

    def test_unicode_kept(self):
        assert self.d._sanitize_filename("音乐 搬运") == "音乐 搬运"


class TestQualityPresets:
    def setup_method(self):
        self.d = VideoDownloader()

    def test_default_order(self):
        presets = self.d._get_quality_presets()
        # best_quality 应优先（画质优先）
        assert presets[0][0] == "best_quality"

    def test_preferred_first(self):
        presets = self.d._get_quality_presets("best_h264_aac")
        assert presets[0][0] == "best_h264_aac"

    def test_preferred_unknown(self):
        presets = self.d._get_quality_presets("nonexistent")
        assert presets[0][0] == "best_quality"
