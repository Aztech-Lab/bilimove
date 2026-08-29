"""monitor.py 测试（去重逻辑，不联网）"""

import json
from pathlib import Path

from src.monitor import ChannelMonitor, MonitorTarget, VideoEntry


def make_monitor(tmp_path):
    """用临时 state 文件创建 monitor，避免污染真实 processed.json"""
    state = tmp_path / "processed.json"
    return ChannelMonitor(state_file=state)


class TestShouldProcess:
    def test_new_video(self, tmp_path):
        m = make_monitor(tmp_path)
        entry = VideoEntry(video_id="abc", url="https://youtu.be/abc", title="Song")
        target = MonitorTarget(name="t", url="https://youtube.com")
        assert m.should_process(entry, target, {}) is True

    def test_already_processed(self, tmp_path):
        m = make_monitor(tmp_path)
        entry = VideoEntry(video_id="abc", url="https://youtu.be/abc", title="Song")
        target = MonitorTarget(name="t", url="https://youtube.com")
        assert m.should_process(entry, target, {"abc": {}}) is False

    def test_exclude_keyword(self, tmp_path):
        m = make_monitor(tmp_path)
        entry = VideoEntry(video_id="abc", url="https://youtu.be/abc", title="Song #short")
        target = MonitorTarget(name="t", url="https://youtube.com", exclude=["#short"])
        assert m.should_process(entry, target, {}) is False

    def test_title_filter(self, tmp_path):
        m = make_monitor(tmp_path)
        entry = VideoEntry(video_id="abc", url="https://youtu.be/abc", title="Other")
        target = MonitorTarget(name="t", url="https://youtube.com", title_filter=["music"])
        assert m.should_process(entry, target, {}) is False

    def test_duration_limit(self, tmp_path):
        m = make_monitor(tmp_path)
        entry = VideoEntry(video_id="abc", url="https://youtu.be/abc", title="Song", duration=300)
        target = MonitorTarget(name="t", url="https://youtube.com", max_duration_min=2)
        assert m.should_process(entry, target, {}) is False


class TestMarkProcessed:
    def test_mark_stores_source_url(self, tmp_path):
        m = make_monitor(tmp_path)
        m.mark_processed("abc", status="done", title="Song",
                         bvid="BV1xx", source_url="https://youtu.be/abc")
        data = m.load_processed()
        assert "abc" in data
        assert data["abc"]["source_url"] == "https://youtu.be/abc"
        assert data["abc"]["bvid"] == "BV1xx"
        assert data["abc"]["status"] == "done"

    def test_mark_failed(self, tmp_path):
        m = make_monitor(tmp_path)
        m.mark_processed("abc", status="failed", title="Song", error="boom")
        data = m.load_processed()
        assert data["abc"]["status"] == "failed"
        assert data["abc"]["error"] == "boom"

    def test_persists_to_disk(self, tmp_path):
        m = make_monitor(tmp_path)
        m.mark_processed("abc", status="done", title="Song")
        # 重新加载应读到
        m2 = ChannelMonitor(state_file=tmp_path / "processed.json")
        assert "abc" in m2.load_processed()
