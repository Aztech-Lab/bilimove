"""metadata_localizer.py 测试"""

from src.metadata_localizer import MetadataLocalizer


class TestDetermineTid:
    def setup_method(self):
        self.l = MetadataLocalizer()

    def test_music_keyword(self):
        assert self.l._determine_tid([], ["beat"], "Trap Beat", "") == 3

    def test_music_category(self):
        assert self.l._determine_tid(["Music"], [], "Song", "") == 3

    def test_tech(self):
        assert self.l._determine_tid([], ["programming"], "Python tutorial", "") == 95

    def test_default_music(self):
        assert self.l._determine_tid([], [], "Random video", "") == 3


class TestGenerateTitle:
    def setup_method(self):
        self.l = MetadataLocalizer()

    def test_chinese_kept(self):
        assert self.l._generate_title("中文标题", [], [], "", True) == "中文标题"

    def test_music_english_with_artist(self):
        t = self.l._generate_title("Uchiha Clan", [], ["Music"], "GRAVY BEATS", False)
        assert t == "【搬运】Uchiha Clan - GRAVY BEATS"

    def test_music_english_no_artist(self):
        t = self.l._generate_title("Some Song", [], ["Music"], "", False)
        assert t == "【搬运】Some Song"

    def test_non_music(self):
        t = self.l._generate_title("Tutorial", [], [], "Channel", False)
        assert t == "【搬运】Tutorial"


class TestLocalize:
    def setup_method(self):
        self.l = MetadataLocalizer()

    def test_localize_music(self):
        meta = {
            "title": "Uchiha Clan",
            "description": "A trap beat",
            "uploader": "GRAVY BEATS",
            "tags": ["trap", "beat"],
            "categories": ["Music"],
            "webpage_url": "https://youtu.be/abc",
            "duration": 180,
        }
        result = self.l.localize(meta, video_file_path="abc.mp4", thumbnail_file="abc.webp")
        assert result.title == "【搬运】Uchiha Clan - GRAVY BEATS"
        assert result.tid == 3
        assert result.source_url == "https://youtu.be/abc"
        assert result.cover_file == "abc.webp"
        assert result.video_file == "abc.mp4"
        assert "音乐搬运" in result.tags

    def test_localize_preserves_newlines(self):
        meta = {
            "title": "Song",
            "description": "第一行\n第二行\n第三行",
            "uploader": "Artist",
            "tags": [],
            "categories": ["Music"],
            "webpage_url": "https://youtu.be/abc",
            "duration": 100,
        }
        result = self.l.localize(meta)
        assert "\n" in result.description
