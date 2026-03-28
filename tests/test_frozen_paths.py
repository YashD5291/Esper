"""Tests for frozen (PyInstaller) vs dev mode path resolution."""

import pathlib
import sys
from unittest import mock


def test_config_uses_meipass_when_frozen():
    """When sys._MEIPASS is set, _PROJECT_ROOT should point to it."""
    fake_meipass = "/tmp/fake_meipass"
    with mock.patch.dict(sys.__dict__, {"_MEIPASS": fake_meipass}):
        import importlib
        from src import config
        importlib.reload(config)

        assert config._PROJECT_ROOT == pathlib.Path(fake_meipass)
        assert config.VAD_MODEL_PATH == str(pathlib.Path(fake_meipass) / "models" / "silero_vad.onnx")
        assert config.WHISPER_MODEL_REPO == str(pathlib.Path(fake_meipass) / "models" / "whisper")

    importlib.reload(config)


def test_config_uses_file_path_when_not_frozen():
    """In dev mode, _PROJECT_ROOT should be based on __file__."""
    from src import config
    expected = pathlib.Path(__file__).resolve().parent.parent
    assert config._PROJECT_ROOT == expected
