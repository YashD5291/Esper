"""Cleanup assertions for Phase 6: verify all dead Parakeet/CoreML code is removed.

These tests assert the ABSENCE of dead code and files. All tests pass once the
cleanup is complete.
"""

from __future__ import annotations

import importlib
import pathlib
import sys

_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SRC_DIR = pathlib.Path(_PROJECT_ROOT) / "src"
_TESTS_DIR = pathlib.Path(_PROJECT_ROOT) / "tests"
_MODELS_DIR = pathlib.Path(_PROJECT_ROOT) / "models"
_REQUIREMENTS = pathlib.Path(_PROJECT_ROOT) / "requirements.txt"


def test_no_coreml_transcriber_file():
    """src/coreml_transcriber.py must not exist on disk."""
    assert not (_SRC_DIR / "coreml_transcriber.py").exists(), (
        "src/coreml_transcriber.py still exists — delete it"
    )


def test_no_coreml_models_dir():
    """models/coreml/ directory must not exist."""
    assert not (_MODELS_DIR / "coreml").exists(), (
        "models/coreml/ directory still exists — delete it with git rm -r"
    )


def test_no_test_stt_file():
    """tests/test_stt.py must not exist on disk."""
    assert not (_TESTS_DIR / "test_stt.py").exists(), (
        "tests/test_stt.py still exists — delete it"
    )


def test_no_coreml_imports():
    """No .py file under src/ may import or reference coreml_transcriber."""
    matches = []
    for py_file in _SRC_DIR.rglob("*.py"):
        if "coreml_transcriber" in py_file.read_text():
            matches.append(str(py_file.relative_to(_PROJECT_ROOT)))
    assert matches == [], (
        f"coreml_transcriber still referenced in: {matches}"
    )


def test_no_default_engine_in_config():
    """src.config must have no DEFAULT_ENGINE attribute."""
    # Force fresh import
    if "src.config" in sys.modules:
        del sys.modules["src.config"]
    cfg = importlib.import_module("src.config")
    assert not hasattr(cfg, "DEFAULT_ENGINE"), (
        "config.DEFAULT_ENGINE still exists — remove it from config.py"
    )


def test_no_engine_name_in_server():
    """src/server.py must not contain '_engine_name'."""
    server_py = _SRC_DIR / "server.py"
    assert "_engine_name" not in server_py.read_text(), (
        "src/server.py still contains _engine_name — remove engine selection remnants"
    )


def test_no_backward_compat_fields():
    """TranscriptionUpdate must have no draft_text, finalized_sentences, or draft_sentences fields."""
    # Force fresh import
    for mod_name in list(sys.modules):
        if "src.transcriber" in mod_name:
            del sys.modules[mod_name]
    from src.transcriber import TranscriptionUpdate  # noqa: E402
    from dataclasses import fields as dc_fields

    field_names = {f.name for f in dc_fields(TranscriptionUpdate)}
    assert "draft_text" not in field_names, "draft_text is still in TranscriptionUpdate"
    assert "finalized_sentences" not in field_names, "finalized_sentences is still in TranscriptionUpdate"
    assert "draft_sentences" not in field_names, "draft_sentences is still in TranscriptionUpdate"


def test_no_parakeet_in_requirements():
    """requirements.txt must not contain 'parakeet-mlx'."""
    text = _REQUIREMENTS.read_text()
    assert "parakeet-mlx" not in text, (
        "parakeet-mlx still in requirements.txt — remove it"
    )


def test_no_coremltools_in_requirements():
    """requirements.txt must not contain 'coremltools'."""
    text = _REQUIREMENTS.read_text()
    assert "coremltools" not in text, (
        "coremltools still in requirements.txt — remove it"
    )


def test_no_scipy_in_requirements():
    """requirements.txt must not contain 'scipy'."""
    text = _REQUIREMENTS.read_text()
    assert "scipy" not in text, (
        "scipy still in requirements.txt — remove it"
    )


def test_existing_tests_pass():
    """Full test suite runs without failures (excluding test_cleanup.py itself)."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "-q",
         "--ignore=tests/test_cleanup.py"],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
    )
    assert result.returncode == 0, (
        f"Existing tests failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
