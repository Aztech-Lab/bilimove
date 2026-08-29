"""config.py 配置测试"""

from src.config import DIRS, ensure_dirs, PROJECT_ROOT


class TestDirs:
    def test_project_root(self):
        assert PROJECT_ROOT.name == "video_moving"

    def test_data_subdirs(self):
        """生成数据统一在 data/ 下"""
        assert DIRS["downloads"].parent == DIRS["data"]
        assert DIRS["output"].parent == DIRS["data"]
        assert DIRS["logs"].parent == DIRS["data"]
        assert DIRS["archive"].parent == DIRS["data"]
        assert DIRS["failed"].parent == DIRS["data"]

    def test_config_in_root(self):
        assert DIRS["config"].parent == PROJECT_ROOT

    def test_ensure_dirs_creates(self, tmp_path):
        """ensure_dirs 应创建所有目录"""
        # 用临时目录模拟，避免污染真实目录
        import src.config as cfg
        orig = cfg.DIRS
        cfg.DIRS = {k: tmp_path / k for k in orig}
        try:
            cfg.ensure_dirs()
            for d in cfg.DIRS.values():
                assert d.exists()
        finally:
            cfg.DIRS = orig
