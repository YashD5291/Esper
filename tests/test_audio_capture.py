"""Unit tests for src/audio_capture.py — device selection and AudioCapture.

All tests mock sounddevice so no real hardware is needed.
"""

import logging
import math
import pathlib
import sys
import queue
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np

# Ensure project root on sys.path for direct invocation
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.audio_capture import auto_select_device, AudioCapture  # noqa: E402


# ── device selection tests ────────────────────────────────────────────────────


@patch("src.audio_capture.sd")
def test_auto_select_returns_requested_device(mock_sd):
    """If caller gives device index, return it directly — no queries."""
    result = auto_select_device(requested=7)
    assert result == 7


@patch("src.audio_capture.sd")
def test_auto_select_falls_back_from_loopback(mock_sd):
    """If default device is loopback, fall back to first real mic."""
    mock_sd.default.device = (2, 0)
    mock_sd.query_devices.side_effect = lambda *args: (
        # Called with index → return device info for the default
        {"name": "Loopback Audio", "max_input_channels": 2}
        if args == (2,)
        else [
            {"name": "Loopback Audio", "max_input_channels": 2},
            {"name": "Speaker Output", "max_input_channels": 0},
            {"name": "MacBook Pro Microphone", "max_input_channels": 1},
        ]
    )

    result = auto_select_device()
    assert result == 2  # index of "MacBook Pro Microphone" in the device list


@patch("src.audio_capture.sd")
def test_auto_select_uses_default_when_not_loopback(mock_sd):
    """If default device is not loopback, return None (let sd pick)."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "MacBook Pro Microphone", "max_input_channels": 1}

    result = auto_select_device()
    assert result is None


# ── AudioCapture tests ────────────────────────────────────────────────────────


@patch("src.audio_capture.sd")
def test_energy_starts_at_zero(mock_sd):
    """energy property is 0.0 before any audio callback fires."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "Built-in Mic", "max_input_channels": 1}

    cap = AudioCapture(device=0)
    assert cap.energy == 0.0


@patch("src.audio_capture.sd")
def test_callback_puts_chunk_in_queue(mock_sd):
    """_callback puts a (512,) float32 array into the queue."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "Built-in Mic", "max_input_channels": 1}

    cap = AudioCapture(device=0)
    indata = np.random.default_rng(0).normal(0, 0.1, (512, 1)).astype(np.float32)

    cap._callback(indata, 512, None, None)

    chunk = cap._queue.get_nowait()
    assert chunk.shape == (512,)
    assert chunk.dtype == np.float32


@patch("src.audio_capture.sd")
def test_callback_updates_energy(mock_sd):
    """_callback updates energy to RMS of the chunk."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "Built-in Mic", "max_input_channels": 1}

    cap = AudioCapture(device=0)
    indata = np.full((512, 1), 0.5, dtype=np.float32)

    cap._callback(indata, 512, None, None)

    expected_rms = math.sqrt(float(np.mean(indata[:, 0] ** 2)))
    assert cap.energy == expected_rms


@patch("src.audio_capture.sd")
def test_callback_drops_frame_when_queue_full(mock_sd):
    """Full queue doesn't raise — frame is silently dropped."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "Built-in Mic", "max_input_channels": 1}

    cap = AudioCapture(device=0)
    # Fill the queue to capacity
    for _ in range(cap._queue.maxsize):
        cap._queue.put(np.zeros(512, dtype=np.float32))

    indata = np.ones((512, 1), dtype=np.float32)

    # Must not raise
    cap._callback(indata, 512, None, None)

    # Queue size unchanged (frame dropped)
    assert cap._queue.qsize() == cap._queue.maxsize


@patch("src.audio_capture.sd")
def test_stop_puts_sentinel(mock_sd):
    """stop() puts None sentinel into the queue."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "Built-in Mic", "max_input_channels": 1}

    cap = AudioCapture(device=0)
    cap._stream = None  # no real stream to stop

    cap.stop()

    sentinel = cap._queue.get_nowait()
    assert sentinel is None


@patch("src.audio_capture.sd")
def test_callback_counts_dropped_frames(mock_sd):
    """Drop counter increments when queue is full."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "Built-in Mic", "max_input_channels": 1}

    cap = AudioCapture(device=0)
    for _ in range(cap._queue.maxsize):
        cap._queue.put(np.zeros(512, dtype=np.float32))

    chunk = np.random.default_rng(0).normal(0, 0.1, (512, 1)).astype(np.float32)
    cap._callback(chunk, 512, None, None)
    assert cap._drop_count == 1

    cap._callback(chunk, 512, None, None)
    assert cap._drop_count == 2


@patch("src.audio_capture.sd")
def test_callback_logs_error_for_overflow_status(mock_sd, caplog):
    """Status containing 'overflow' logs at ERROR level."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "Built-in Mic", "max_input_channels": 1}

    cap = AudioCapture(device=0)
    indata = np.random.default_rng(1).normal(0, 0.1, (512, 1)).astype(np.float32)

    with caplog.at_level(logging.DEBUG, logger="src.audio_capture"):
        cap._callback(indata, 512, None, "input overflow")

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("input overflow" in r.message for r in error_records)
    # Audio still queued despite the error
    chunk = cap._queue.get_nowait()
    assert chunk.shape == (512,)


@patch("src.audio_capture.sd")
def test_callback_logs_warning_for_non_error_status(mock_sd, caplog):
    """Status without 'error'/'overflow' logs at WARNING level."""
    mock_sd.default.device = (0, 0)
    mock_sd.query_devices.return_value = {"name": "Built-in Mic", "max_input_channels": 1}

    cap = AudioCapture(device=0)
    indata = np.random.default_rng(1).normal(0, 0.1, (512, 1)).astype(np.float32)

    with caplog.at_level(logging.WARNING, logger="src.audio_capture"):
        cap._callback(indata, 512, None, "input underflow")

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("input underflow" in r.message for r in warning_records)
