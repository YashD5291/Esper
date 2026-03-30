"""Unit tests for src/whisper_worker.py — pipe protocol (_send_msg / _recv_msg).

Tests the length-prefixed pickle framing used for Swift↔Python IPC in frozen
(PyInstaller) mode. All tests use io.BytesIO as the pipe mock — no real
subprocesses needed.
"""

import io
import pathlib
import pickle
import struct
import sys

import numpy as np

# Ensure project root on sys.path for direct invocation
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.whisper_worker import _send_msg, _recv_msg  # noqa: E402


# ── roundtrip tests ───────────────────────────────────────────────────────────


def test_send_recv_roundtrip_dict():
    """Dict sent via _send_msg is recovered identically by _recv_msg."""
    buf = io.BytesIO()
    obj = {"ok": True, "result": {"text": "hello world"}, "count": 42}
    _send_msg(buf, obj)
    buf.seek(0)
    assert _recv_msg(buf) == obj


def test_send_recv_roundtrip_numpy():
    """Numpy array survives the pickle roundtrip through the pipe protocol."""
    buf = io.BytesIO()
    arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    _send_msg(buf, arr)
    buf.seek(0)
    result = _recv_msg(buf)
    np.testing.assert_array_equal(result, arr)
    assert result.dtype == np.float32


def test_send_recv_none_sentinel():
    """None sentinel (used for shutdown) roundtrips correctly."""
    buf = io.BytesIO()
    _send_msg(buf, None)
    buf.seek(0)
    result = _recv_msg(buf)
    assert result is None


# ── EOF / partial-read edge cases ─────────────────────────────────────────────


def test_recv_returns_none_on_empty_pipe():
    """Empty BytesIO (EOF immediately) returns None."""
    buf = io.BytesIO(b"")
    assert _recv_msg(buf) is None


def test_recv_returns_none_on_partial_header():
    """Only 2 bytes available (incomplete 4-byte header) returns None."""
    buf = io.BytesIO(b"\x00\x00")
    assert _recv_msg(buf) is None


def test_recv_returns_none_on_truncated_body():
    """Header claims N bytes but only half the body is present — returns None."""
    payload = pickle.dumps({"hello": "world"}, protocol=pickle.HIGHEST_PROTOCOL)
    header = struct.pack(">I", len(payload))
    # Write header + only half the payload
    buf = io.BytesIO(header + payload[: len(payload) // 2])
    assert _recv_msg(buf) is None


# ── sequential / multi-message ────────────────────────────────────────────────


def test_multiple_messages_sequential():
    """Three messages written sequentially are all read back in order."""
    buf = io.BytesIO()
    messages = [
        {"type": "ready", "ok": True},
        {"type": "result", "text": "test"},
        {"type": "error", "msg": "fail"},
    ]
    for msg in messages:
        _send_msg(buf, msg)

    buf.seek(0)
    for expected in messages:
        assert _recv_msg(buf) == expected

    # After all messages consumed, next read returns None (EOF)
    assert _recv_msg(buf) is None


# ── framing format ────────────────────────────────────────────────────────────


def test_framing_format():
    """Wire format is 4-byte big-endian length prefix followed by pickle payload."""
    buf = io.BytesIO()
    obj = {"key": "value"}
    _send_msg(buf, obj)

    raw = buf.getvalue()

    # First 4 bytes are the big-endian length prefix
    length_prefix = raw[:4]
    body = raw[4:]

    expected_body = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    expected_length = struct.pack(">I", len(expected_body))

    assert length_prefix == expected_length
    assert body == expected_body
    assert pickle.loads(body) == obj
