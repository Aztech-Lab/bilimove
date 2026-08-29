"""biliup_uploader.py 测试（纯逻辑，不实际上传）"""

import json
from pathlib import Path

from src.biliup_uploader import BiliupUploader
from src.models import UploadTask


class TestExtractBvid:
    def setup_method(self):
        self.u = BiliupUploader()

    def test_extract_bvid(self):
        out = '{"bvid": "BV1zZ426PEr4", "code": 0}'
        assert self.u._extract_bvid(out) == "BV1zZ426PEr4"

    def test_no_bvid(self):
        assert self.u._extract_bvid("no bvid here") == ""


class TestExtractError:
    def setup_method(self):
        self.u = BiliupUploader()

    def test_message_field(self):
        out = '{"message": "稿件类型为转载时，转载来源不能为空", "code": 21021}'
        assert "转载来源不能为空" in self.u._extract_error(out)

    def test_error_line(self):
        out = "ERROR: something went wrong\nmore"
        assert "ERROR" in self.u._extract_error(out)

    def test_fallback(self):
        out = "plain output"
        assert self.u._extract_error(out) == "plain output"


class TestBiliupCmd:
    def test_uses_cookies_file(self):
        u = BiliupUploader()
        cmd = u._biliup_cmd("list")
        # 应包含 biliup 二进制 + cookies 文件
        assert cmd[0].endswith("biliup")
        assert "-u" in cmd
        assert str(u.cookies_file) in cmd

    def test_upload_command_has_copyright_and_source(self, tmp_path):
        u = BiliupUploader()
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x")
        task = UploadTask(
            video_id="abc",
            video_file=str(video),
            title="标题",
            description="简介\n第二行",
            tags=["音乐", "搬运"],
            tid=3,
            source_url="https://youtu.be/abc",
        )
        cmd = u._biliup_cmd(
            "upload", task.video_file,
            "--title", task.title,
            "--desc", task.description,
            "--tag", ",".join(task.tags),
            "--tid", str(task.tid),
            "--copyright", "2",
            "--is-only-self", "1",
            "--source", task.source_url,
        )
        joined = " ".join(cmd)
        assert "--copyright 2" in joined
        assert "--is-only-self 1" in joined
        assert "--source https://youtu.be/abc" in joined
        assert "--desc" in joined


class TestLoadTask:
    def test_load_task(self, tmp_path):
        u = BiliupUploader()
        video = tmp_path / "abc.mp4"
        video.write_bytes(b"x")
        meta = {
            "video_file": "abc.mp4",
            "bili_title": "标题",
            "bili_description": "简介\n第二行",
            "bili_tags": ["音乐", "搬运"],
            "bili_tid": 3,
            "source_url": "https://youtu.be/abc",
        }
        (tmp_path / "abc_upload_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        task = u.load_task(tmp_path)
        assert task is not None
        assert task.video_id == "abc"
        assert task.title == "标题"
        assert task.source_url == "https://youtu.be/abc"
        assert "\n" in task.description

    def test_load_task_missing_meta(self, tmp_path):
        u = BiliupUploader()
        assert u.load_task(tmp_path) is None
