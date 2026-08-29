"""models.py 数据模型测试"""

from src.models import UploadTask, UploadResult


class TestUploadTask:
    def test_defaults(self):
        task = UploadTask()
        assert task.video_id == ""
        assert task.tid == 3
        assert task.tags == []
        assert task.status == "pending"

    def test_full_fields(self):
        task = UploadTask(
            video_id="abc123",
            video_file="/tmp/v.mp4",
            cover_file="/tmp/c.png",
            title="标题",
            description="简介\n第二行",
            tags=["音乐", "搬运"],
            tid=3,
            source_url="https://youtu.be/abc123",
        )
        assert task.video_id == "abc123"
        assert task.source_url == "https://youtu.be/abc123"
        assert task.tags == ["音乐", "搬运"]
        assert "\n" in task.description

    def test_mutable_defaults_isolated(self):
        """每个实例的 tags 列表应独立，不共享"""
        a = UploadTask()
        b = UploadTask()
        a.tags.append("x")
        assert b.tags == []


class TestUploadResult:
    def test_defaults(self):
        r = UploadResult()
        assert r.success is False
        assert r.bvid == ""
        assert r.error == ""

    def test_success(self):
        r = UploadResult(success=True, bvid="BV1xx", upload_time="2026-01-01")
        assert r.success is True
        assert r.bvid == "BV1xx"
