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

import json
import logging
import pathlib
import struct
import sys

import numpy as np

# Add project root to sys.path so 'from . import config' works in spawn context.
_FROZEN = getattr(sys, '_MEIPASS', None)
_PROJECT_ROOT = _FROZEN if _FROZEN else str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Framed pipe protocol ─────────────────────────────────────────────────

_MSG_JSON = 0
_MSG_NUMPY = 1
_MSG_NONE = 2

def _send_msg(pipe, obj):
    """Write a typed, length-prefixed message to pipe."""
    if obj is None:
        pipe.write(struct.pack('>BI', _MSG_NONE, 0))
        pipe.flush()
        return
    if isinstance(obj, np.ndarray):
        dtype_bytes = str(obj.dtype).encode()
        shape_bytes = struct.pack(f'>{len(obj.shape)}Q', *obj.shape)
        header = struct.pack('>I', len(dtype_bytes)) + dtype_bytes + struct.pack('>I', len(obj.shape)) + shape_bytes
        raw = obj.tobytes()
        payload = header + raw
        pipe.write(struct.pack('>BI', _MSG_NUMPY, len(payload)))
        pipe.write(payload)
        pipe.flush()
        return
    payload = json.dumps(obj).encode()
    pipe.write(struct.pack('>BI', _MSG_JSON, len(payload)))
    pipe.write(payload)
    pipe.flush()

def _recv_msg(pipe):
    """Read a typed, length-prefixed message from pipe. Returns None on EOF."""
    hdr = pipe.read(5)
    if not hdr:
        return None  # clean EOF
    if len(hdr) < 5:
        raise RuntimeError(f"Truncated header: got {len(hdr)} bytes, expected 5")
    msg_type, length = struct.unpack('>BI', hdr)
    if msg_type == _MSG_NONE:
        return None
    if length == 0:
        return None
    data = pipe.read(length)
    if not data:
        return None  # clean EOF
    if len(data) < length:
        raise RuntimeError(f"Truncated payload: got {len(data)} bytes, expected {length}")
    if msg_type == _MSG_JSON:
        return json.loads(data)
    if msg_type == _MSG_NUMPY:
        off = 0
        if off + 4 > len(data):
            raise RuntimeError(f"Truncated numpy dtype length at offset {off}")
        dl = struct.unpack('>I', data[off:off+4])[0]; off += 4
        if off + dl > len(data):
            raise RuntimeError(f"Truncated numpy dtype: need {dl} bytes at offset {off}")
        dt = data[off:off+dl].decode(); off += dl
        if off + 4 > len(data):
            raise RuntimeError(f"Truncated numpy ndim at offset {off}")
        nd = struct.unpack('>I', data[off:off+4])[0]; off += 4
        if off + nd * 8 > len(data):
            raise RuntimeError(f"Truncated numpy shape: need {nd*8} bytes at offset {off}")
        shape = struct.unpack(f'>{nd}Q', data[off:off+nd*8]); off += nd*8
        return np.frombuffer(data[off:], dtype=np.dtype(dt)).reshape(shape).copy()
    return None


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
        try:
            _send_msg(stdout, {"ok": False, "error": f"ImportError: {exc}"})
        except Exception as send_exc:
            sys.stderr.write(f"FATAL: Could not send error response: {send_exc}\n")
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
