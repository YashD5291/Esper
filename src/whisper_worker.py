"""Subprocess worker for Whisper inference.

Two modes:
  1. multiprocessing (dev mode): _whisper_worker() — uses queues
  2. pipe-based (frozen/PyInstaller): run_pipe_worker() — uses stdin/stdout
     with length-prefixed pickle framing. This avoids all PyInstaller +
     multiprocessing issues (spawn can't load C extensions, fork deadlocks).

IMPORTANT: word_timestamps and clip_timestamps must NOT be passed to
mlx_whisper.transcribe() — they cause crashes on some audio inputs.
"""

from __future__ import annotations

import logging
import pathlib
import pickle
import struct
import sys

# Add project root to sys.path so 'from . import config' works in spawn context.
_FROZEN = getattr(sys, '_MEIPASS', None)
_PROJECT_ROOT = _FROZEN if _FROZEN else str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Framed pipe protocol ─────────────────────────────────────────────────

def _send_msg(pipe, obj):
    """Write a length-prefixed pickled message to pipe."""
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    pipe.write(struct.pack('>I', len(data)))
    pipe.write(data)
    pipe.flush()


def _recv_msg(pipe):
    """Read a length-prefixed pickled message from pipe. Returns None on EOF."""
    header = pipe.read(4)
    if not header or len(header) < 4:
        return None
    length = struct.unpack('>I', header)[0]
    data = pipe.read(length)
    if not data or len(data) < length:
        return None
    return pickle.loads(data)


# ── Pipe-based worker (frozen mode) ──────────────────────────────────────

def run_pipe_worker() -> None:
    """Entry point for --whisper-worker mode. Reads from stdin, writes to stdout."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s worker: %(message)s",
    )
    log = logging.getLogger("esper.whisper_worker")

    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    log.info("Pipe worker started, importing mlx_whisper...")
    try:
        import mlx_whisper
        from src import config
    except Exception as exc:
        log.error("Import failed: %s", exc, exc_info=True)
        _send_msg(stdout, {"ok": False, "error": f"ImportError: {exc}"})
        return

    log.info("Whisper ready. Model: %s", config.WHISPER_MODEL_REPO)
    _send_msg(stdout, {"ok": True, "ready": True})

    while True:
        audio = _recv_msg(stdin)
        if audio is None:
            log.debug("EOF/shutdown, exiting.")
            break

        try:
            raw = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=config.WHISPER_MODEL_REPO,
                language=config.WHISPER_LANGUAGE,
                word_timestamps=False,
                condition_on_previous_text=False,
                temperature=0.0,
                no_speech_threshold=None,
                compression_ratio_threshold=None,
            )
            _send_msg(stdout, {"ok": True, "result": raw})
        except Exception as exc:
            log.error("Inference error: %s", exc, exc_info=True)
            _send_msg(stdout, {"ok": False, "error": str(exc)})


# ── Multiprocessing worker (dev mode) ────────────────────────────────────

def _whisper_worker(audio_q, result_q) -> None:
    """Worker for multiprocessing.Process (spawn context, dev mode only)."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s worker: %(message)s",
    )
    log = logging.getLogger("esper.whisper_worker")

    try:
        import mlx_whisper
        from src import config
    except Exception as exc:
        log.error("Import failed: %s", exc, exc_info=True)
        result_q.put({"ok": False, "error": f"ImportError: {exc}"})
        return

    log.info("Whisper worker ready. Model: %s", config.WHISPER_MODEL_REPO)
    result_q.put({"ok": True, "ready": True})

    while True:
        audio = audio_q.get()
        if audio is None:
            break

        try:
            raw = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=config.WHISPER_MODEL_REPO,
                language=config.WHISPER_LANGUAGE,
                word_timestamps=False,
                condition_on_previous_text=False,
                temperature=0.0,
                no_speech_threshold=None,
                compression_ratio_threshold=None,
            )
            result_q.put({"ok": True, "result": raw})
        except Exception as exc:
            log.error("Inference error: %s", exc, exc_info=True)
            result_q.put({"ok": False, "error": str(exc)})
