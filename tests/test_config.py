"""Tests for src/config.py — single source of truth for all Esper tunables."""

import importlib
import pathlib
import sys

# Ensure project root is on sys.path so `from src import config` works
# when running tests directly (e.g., python tests/test_config.py)
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def get_config():
    """Import config fresh (handles module reload in test runs)."""
    if "src.config" in sys.modules:
        return sys.modules["src.config"]
    return importlib.import_module("src.config")


# ── Audio section ──────────────────────────────────────────────────────────────

def test_sample_rate():
    config = get_config()
    assert config.SAMPLE_RATE == 16000


def test_channels():
    config = get_config()
    assert config.CHANNELS == 1


def test_chunk_duration():
    config = get_config()
    assert config.CHUNK_DURATION == 0.1


def test_chunk_samples():
    config = get_config()
    assert config.CHUNK_SAMPLES == 1600


def test_queue_maxsize():
    config = get_config()
    assert config.QUEUE_MAXSIZE == 300


# ── VAD section ───────────────────────────────────────────────────────────────

def test_vad_frame_size():
    config = get_config()
    assert config.VAD_FRAME_SIZE == 512


def test_vad_speech_threshold():
    config = get_config()
    assert config.VAD_SPEECH_THRESHOLD == 0.5


def test_vad_silence_threshold_ms():
    config = get_config()
    assert config.VAD_SILENCE_THRESHOLD_MS == 500


def test_vad_min_speech_duration_ms():
    config = get_config()
    assert config.VAD_MIN_SPEECH_DURATION_MS == 500


def test_vad_min_energy():
    config = get_config()
    assert config.VAD_MIN_ENERGY == 0.01


# ── Whisper section ───────────────────────────────────────────────────────────

def test_whisper_model_repo():
    config = get_config()
    assert config.WHISPER_MODEL_REPO == "mlx-community/whisper-large-v3-turbo"


def test_whisper_language():
    config = get_config()
    assert config.WHISPER_LANGUAGE == "en"


def test_whisper_max_generations_before_restart():
    config = get_config()
    assert config.WHISPER_MAX_GENERATIONS_BEFORE_RESTART == 50


def test_whisper_subprocess_timeout_s():
    config = get_config()
    assert config.WHISPER_SUBPROCESS_TIMEOUT_S == 15.0


# ── Telegram section ──────────────────────────────────────────────────────────

def test_telegram_bot_token_default_empty():
    config = get_config()
    assert config.TELEGRAM_BOT_TOKEN == ""


def test_telegram_chat_id_default_empty():
    config = get_config()
    assert config.TELEGRAM_CHAT_ID == ""


def test_telegram_stream_default_true():
    config = get_config()
    assert config.TELEGRAM_STREAM is True


def test_telegram_max_retries():
    config = get_config()
    assert config.TELEGRAM_MAX_RETRIES == 3


def test_telegram_backoff_base():
    config = get_config()
    assert config.TELEGRAM_BACKOFF_BASE == 1.0


def test_telegram_draft_interval():
    config = get_config()
    assert config.TELEGRAM_DRAFT_INTERVAL == 0.5


# ── IPC section ───────────────────────────────────────────────────────────────

def test_energy_emit_interval_s():
    config = get_config()
    assert config.ENERGY_EMIT_INTERVAL_S == 0.1


def test_model_load_timeout_s():
    config = get_config()
    assert config.MODEL_LOAD_TIMEOUT_S == 120.0


def test_default_engine():
    config = get_config()
    assert config.DEFAULT_ENGINE == "coreml"


# ── Structural checks ─────────────────────────────────────────────────────────

def test_no_internal_imports():
    """config.py must have zero internal (src.*) imports to prevent circular deps."""
    import inspect
    import ast
    import pathlib

    config_path = pathlib.Path(__file__).parent.parent / "src" / "config.py"
    tree = ast.parse(config_path.read_text())

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("src."), (
                f"config.py must not import from src.*: found 'from {module} import ...'"
            )
            assert not module.startswith("."), (
                f"config.py must not use relative imports: found 'from {module} import ...'"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("src."), (
                    f"config.py must not import src.*: found 'import {alias.name}'"
                )


def test_chunk_samples_derived_correctly():
    """CHUNK_SAMPLES must equal int(SAMPLE_RATE * CHUNK_DURATION)."""
    config = get_config()
    expected = int(config.SAMPLE_RATE * config.CHUNK_DURATION)
    assert config.CHUNK_SAMPLES == expected, (
        f"CHUNK_SAMPLES={config.CHUNK_SAMPLES} but int(SAMPLE_RATE * CHUNK_DURATION)={expected}"
    )


if __name__ == "__main__":
    # Allow running directly: python tests/test_config.py
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
