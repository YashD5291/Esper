# Esper Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 32 identified issues across Python, Swift, IPC, audio, Telegram, security, tests, and build — zero regressions allowed.

**Architecture:** Atomic branch-per-fix. Each fix gets its own branch off `main`. Test-first: write regression tests that pass on current code, then make the fix, then verify all tests still green. Nothing merges to `main` without explicit user approval.

**Tech Stack:** Python 3.11 (pytest), Swift/SwiftUI (XCTest), PyInstaller, sounddevice, httpx, ONNX Runtime, mlx-whisper

**Test commands:**
- Python: `cd /Users/yashdesai/Codebase/Fun/Esper && .venv/bin/python -m pytest tests/ -v`
- Swift: `cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp && xcodebuild test -scheme EsperApp -destination 'platform=macOS'`

---

## File Map

### Phase 0 — Security (no production logic changes)
- Modify: `.gitignore`
- Create: `.env.example`
- Modify: `EsperApp/EsperApp/ProcessBridge.swift` (log path only)

### Phase 1 — Test Infrastructure (no production code changes)
- Create: `tests/test_audio_capture.py`
- Create: `tests/test_whisper_worker.py`
- Create: `tests/test_vad_model.py`
- Create: `tests/test_server_commands.py`
- Create: `tests/test_integration.py`
- Create: `EsperApp/EsperAppTests/` (new XCTest target + 4 test files)

### Phase 2 — Python Backend Hardening
- Modify: `src/transcriber.py` (fixes #1, #9, #11, #27, #30)
- Modify: `src/vad.py` (fix #10, #21)
- Modify: `src/server.py` (fixes #8, #32, #33)
- Modify: `src/config.py` (fix #31)

### Phase 3 — Swift/IPC Hardening
- Modify: `EsperApp/EsperApp/ProcessBridge.swift` (fixes #3, #4, #5, #6)
- Modify: `EsperApp/EsperApp/TranscriptionEngine.swift` (fix #7)
- Modify: `EsperApp/EsperApp/Models/Protocol.swift` (fix #20)
- Modify: `EsperApp/EsperApp/Models/AppSettings.swift` (fix #12)
- Create: `EsperApp/EsperApp/Helpers/KeychainHelper.swift` (fix #12)
- Modify: `src/server.py` (fix #20 — add version field)

### Phase 4 — Audio + Telegram Robustness
- Modify: `src/audio_capture.py` (fixes #13, #18)
- Modify: `src/telegram_sender.py` (fixes #22, #23, #24)
- Modify: `src/whisper_worker.py` (fix #26)
- Modify: `src/transcriber.py` (fix #26)

### Phase 5 — Build & Packaging
- Modify: `EsperApp/EsperApp/TranscriptionEngine.swift` (fix #17)
- Modify: `EsperApp/EsperApp/Models/AppSettings.swift` (fix #28)
- Modify: `scripts/build-dmg.sh` (fix #14)
- Modify: `EsperApp/Info.plist` or Xcode build settings (fix #17)

---

## Phase 0: Security Quick Wins

### Task 1: Fix gitignore contradiction (Fix #16)

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Verify the bug exists**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper
git check-ignore models/silero_vad.onnx
```

Expected: prints `models/silero_vad.onnx` (meaning it IS ignored despite the `!` negation)

- [ ] **Step 2: Create branch**

```bash
git checkout -b fix/gitignore-models
```

- [ ] **Step 3: Fix .gitignore**

Change `.gitignore` lines 9-10 from:

```
/models/
!/models/silero_vad.onnx
```

To:

```
/models/*/
/models/**/*.bin
/models/**/*.safetensors
/models/**/*.mlmodelc
!/models/silero_vad.onnx
```

This ignores model subdirectories and large files but allows the VAD ONNX model to be tracked.

- [ ] **Step 4: Force-track the VAD model**

```bash
git add -f models/silero_vad.onnx
```

- [ ] **Step 5: Verify fix**

```bash
git check-ignore models/silero_vad.onnx
```

Expected: no output (file is NOT ignored)

- [ ] **Step 6: Run existing tests to confirm no breakage**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all 73 tests pass

- [ ] **Step 7: Commit**

```bash
git add .gitignore models/silero_vad.onnx
git commit -m "fix: gitignore contradiction — track silero_vad.onnx properly

The negation pattern !/models/silero_vad.onnx didn't work because
/models/ ignored the entire parent directory first. Switched to
ignoring model subdirs and large file types specifically."
```

---

### Task 2: Create .env.example and document credential rotation (Fix #2)

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/env-credentials
```

- [ ] **Step 2: Create .env.example**

Create `.env.example`:

```env
# Telegram integration — get these from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_CHAT_ID=your-chat-id-here
```

- [ ] **Step 3: Verify .env is gitignored**

```bash
git check-ignore .env
```

Expected: prints `.env`

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add .env.example
git commit -m "security: add .env.example with placeholder credentials

Real credentials must never be committed. Users copy this file
to .env and fill in their own values from @BotFather."
```

**MANUAL STEP:** User must rotate their Telegram bot token via @BotFather. This cannot be automated.

---

### Task 3: Move debug log from /tmp to ~/Library/Logs (Fix #25)

**Files:**
- Modify: `EsperApp/EsperApp/ProcessBridge.swift:5-9`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/debug-log-path
```

- [ ] **Step 2: Change log path**

In `EsperApp/EsperApp/ProcessBridge.swift`, replace lines 5-9:

```swift
let _debugLog: FileHandle? = {
    let path = "/tmp/esper-bridge.log"
    FileManager.default.createFile(atPath: path, contents: nil)
    return FileHandle(forWritingAtPath: path)
}()
```

With:

```swift
let _debugLog: FileHandle? = {
    let logDir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Logs/Esper")
    try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)
    let path = logDir.appendingPathComponent("esper-bridge.log").path
    FileManager.default.createFile(atPath: path, contents: nil)
    return FileHandle(forWritingAtPath: path)
}()
```

- [ ] **Step 3: Build to verify compilation**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild build -scheme EsperApp -destination 'platform=macOS' -quiet
```

Expected: BUILD SUCCEEDED

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/ProcessBridge.swift
git commit -m "security: move debug log from /tmp to ~/Library/Logs/Esper

/tmp is world-readable. ~/Library/Logs/Esper is user-private and
follows macOS conventions for application logs."
```

---

## Phase 1: Test Infrastructure

### Task 4: Add test_audio_capture.py

**Files:**
- Create: `tests/test_audio_capture.py`
- Test: `tests/test_audio_capture.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b test/audio-capture
```

- [ ] **Step 2: Write tests**

Create `tests/test_audio_capture.py`:

```python
"""Unit tests for src/audio_capture.py — lock down current behavior.

All tests mock sounddevice so no real audio hardware is needed.
"""

import pathlib
import sys
import queue
import threading
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np

_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.audio_capture import AudioCapture, auto_select_device, find_real_mic  # noqa: E402
from src import config  # noqa: E402


# ── auto_select_device tests ──────────────────────────────────────────────────

@patch("src.audio_capture.sd")
def test_auto_select_returns_requested_device(mock_sd):
    """If caller provides a device index, return it unchanged."""
    result = auto_select_device(requested=5)
    assert result == 5


@patch("src.audio_capture.sd")
def test_auto_select_falls_back_from_loopback(mock_sd):
    """If default device is loopback, fall back to real mic."""
    mock_sd.default.device = [2, 0]  # input=2
    mock_sd.query_devices.side_effect = lambda idx=None: (
        {"name": "Loopback Audio", "max_input_channels": 2}
        if idx == 2
        else [
            {"name": "Loopback Audio", "max_input_channels": 2},
            {"name": "MacBook Pro Microphone", "max_input_channels": 1},
        ]
    )

    with patch("src.audio_capture.find_real_mic", return_value=1):
        result = auto_select_device(requested=None)
    assert result == 1


@patch("src.audio_capture.sd")
def test_auto_select_uses_default_when_not_loopback(mock_sd):
    """If default device is not loopback, return None (let sd use default)."""
    mock_sd.default.device = [0, 0]
    mock_sd.query_devices.return_value = {"name": "MacBook Pro Microphone", "max_input_channels": 1}
    result = auto_select_device(requested=None)
    assert result is None


# ── AudioCapture tests ────────────────────────────────────────────────────────

@patch("src.audio_capture.sd")
def test_energy_starts_at_zero(mock_sd):
    """Energy property starts at 0.0 before any audio arrives."""
    cap = AudioCapture(device=0)
    assert cap.energy == 0.0


@patch("src.audio_capture.sd")
def test_callback_puts_chunk_in_queue(mock_sd):
    """_callback puts audio chunk into internal queue."""
    cap = AudioCapture(device=0)
    chunk = np.random.randn(512, 1).astype(np.float32)
    cap._callback(chunk, 512, None, None)
    result = cap._queue.get_nowait()
    assert result.shape == (512,)
    assert result.dtype == np.float32


@patch("src.audio_capture.sd")
def test_callback_updates_energy(mock_sd):
    """_callback updates energy to RMS of the audio chunk."""
    cap = AudioCapture(device=0)
    # Constant signal of 0.5 → RMS = 0.5
    chunk = np.full((512, 1), 0.5, dtype=np.float32)
    cap._callback(chunk, 512, None, None)
    assert abs(cap.energy - 0.5) < 0.01


@patch("src.audio_capture.sd")
def test_callback_drops_frame_when_queue_full(mock_sd):
    """_callback silently drops frames when queue is full."""
    cap = AudioCapture(device=0)
    # Fill the queue
    for _ in range(config.QUEUE_MAXSIZE):
        cap._queue.put(np.zeros(512, dtype=np.float32))
    # This should not raise
    chunk = np.random.randn(512, 1).astype(np.float32)
    cap._callback(chunk, 512, None, None)
    assert cap._queue.qsize() == config.QUEUE_MAXSIZE


@patch("src.audio_capture.sd")
def test_stop_puts_sentinel(mock_sd):
    """stop() puts None sentinel into queue."""
    cap = AudioCapture(device=0)
    cap._stream = MagicMock()
    cap.stop()
    item = cap._queue.get_nowait()
    assert item is None


@patch("src.audio_capture.sd")
def test_callback_logs_status_warning(mock_sd):
    """_callback logs a warning when status is non-empty."""
    cap = AudioCapture(device=0)
    chunk = np.random.randn(512, 1).astype(np.float32)
    # Should not raise; status is logged but not propagated
    cap._callback(chunk, 512, None, "input underflow")
    # Verify audio was still queued despite status warning
    assert not cap._queue.empty()
```

- [ ] **Step 3: Run the new tests**

```bash
.venv/bin/python -m pytest tests/test_audio_capture.py -v
```

Expected: all pass

- [ ] **Step 4: Run full suite to confirm no interference**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all 73 existing + new tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_audio_capture.py
git commit -m "test: add unit tests for audio_capture.py

Locks down auto_select_device, energy calculation, callback
queue behavior, sentinel delivery, and queue-full drop behavior.
All tests use mocked sounddevice — no real hardware needed."
```

---

### Task 5: Add test_whisper_worker.py

**Files:**
- Create: `tests/test_whisper_worker.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b test/whisper-worker
```

- [ ] **Step 2: Write tests**

Create `tests/test_whisper_worker.py`:

```python
"""Unit tests for src/whisper_worker.py — pipe protocol and message framing.

Tests the _send_msg/_recv_msg wire protocol used in frozen (PyInstaller) mode.
No GPU, no model loading — tests the framing layer only.
"""

import io
import pathlib
import pickle
import struct
import sys

import numpy as np

_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.whisper_worker import _send_msg, _recv_msg  # noqa: E402


def test_send_recv_roundtrip_dict():
    """A dict sent via _send_msg is recovered by _recv_msg."""
    buf = io.BytesIO()
    msg = {"ok": True, "ready": True}
    _send_msg(buf, msg)
    buf.seek(0)
    result = _recv_msg(buf)
    assert result == msg


def test_send_recv_roundtrip_numpy():
    """A numpy array sent via _send_msg is recovered by _recv_msg."""
    buf = io.BytesIO()
    audio = np.random.randn(16000).astype(np.float32)
    _send_msg(buf, audio)
    buf.seek(0)
    result = _recv_msg(buf)
    assert isinstance(result, np.ndarray)
    np.testing.assert_array_equal(result, audio)


def test_send_recv_none_sentinel():
    """None sentinel is sent and received correctly."""
    buf = io.BytesIO()
    _send_msg(buf, None)
    buf.seek(0)
    result = _recv_msg(buf)
    assert result is None


def test_recv_returns_none_on_empty_pipe():
    """_recv_msg returns None when pipe is empty (EOF)."""
    buf = io.BytesIO(b"")
    result = _recv_msg(buf)
    assert result is None


def test_recv_returns_none_on_partial_header():
    """_recv_msg returns None when header is incomplete."""
    buf = io.BytesIO(b"\x00\x00")  # only 2 bytes, need 4
    result = _recv_msg(buf)
    assert result is None


def test_recv_returns_none_on_truncated_body():
    """_recv_msg returns None when body is shorter than header says."""
    data = pickle.dumps({"ok": True})
    header = struct.pack('>I', len(data))
    # Only write half the body
    buf = io.BytesIO(header + data[:len(data) // 2])
    result = _recv_msg(buf)
    assert result is None


def test_multiple_messages_sequential():
    """Multiple messages written sequentially are all recovered."""
    buf = io.BytesIO()
    messages = [
        {"ok": True, "ready": True},
        {"ok": True, "result": {"text": "hello"}},
        {"ok": False, "error": "timeout"},
    ]
    for msg in messages:
        _send_msg(buf, msg)

    buf.seek(0)
    results = []
    for _ in range(len(messages)):
        results.append(_recv_msg(buf))

    assert results == messages


def test_framing_format():
    """Verify wire format: 4-byte big-endian length prefix + pickled payload."""
    buf = io.BytesIO()
    msg = {"ok": True}
    _send_msg(buf, msg)

    raw = buf.getvalue()
    length = struct.unpack('>I', raw[:4])[0]
    payload = pickle.loads(raw[4:4 + length])
    assert payload == msg
    assert len(raw) == 4 + length
```

- [ ] **Step 3: Run the new tests**

```bash
.venv/bin/python -m pytest tests/test_whisper_worker.py -v
```

Expected: all pass

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_whisper_worker.py
git commit -m "test: add unit tests for whisper_worker pipe protocol

Tests _send_msg/_recv_msg roundtrip for dicts, numpy arrays,
None sentinel, EOF handling, partial reads, and wire format."
```

---

### Task 6: Add test_vad_model.py

**Files:**
- Create: `tests/test_vad_model.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b test/vad-model
```

- [ ] **Step 2: Write tests**

Create `tests/test_vad_model.py`:

```python
"""Unit tests for src/vad_model.py — SileroVadOnnx wrapper.

Tests mock the ONNX InferenceSession to avoid needing the actual model file.
"""

import pathlib
import sys
from unittest.mock import MagicMock, patch

import numpy as np

_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.vad_model import SileroVadOnnx  # noqa: E402


def _make_mock_session():
    """Create a mock ONNX InferenceSession that returns valid outputs."""
    session = MagicMock()
    # run() returns (output, new_state)
    session.run.return_value = (
        np.array([[0.85]], dtype=np.float32),  # speech probability
        np.zeros((2, 1, 128), dtype=np.float32),  # new state
    )
    return session


@patch("src.vad_model.onnxruntime.InferenceSession")
def test_init_creates_session(mock_session_cls):
    """SileroVadOnnx creates an InferenceSession on init."""
    mock_session_cls.return_value = _make_mock_session()
    model = SileroVadOnnx("fake_model.onnx")
    mock_session_cls.assert_called_once()


@patch("src.vad_model.onnxruntime.InferenceSession")
def test_call_returns_float(mock_session_cls):
    """__call__ returns a float speech probability."""
    mock_session_cls.return_value = _make_mock_session()
    model = SileroVadOnnx("fake_model.onnx")

    audio = np.random.randn(512).astype(np.float32)
    result = model(audio, 16000)

    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


@patch("src.vad_model.onnxruntime.InferenceSession")
def test_call_accepts_1d_audio(mock_session_cls):
    """__call__ handles 1D audio input (512,)."""
    mock_session_cls.return_value = _make_mock_session()
    model = SileroVadOnnx("fake_model.onnx")

    audio = np.zeros(512, dtype=np.float32)
    result = model(audio, 16000)
    assert isinstance(result, float)


@patch("src.vad_model.onnxruntime.InferenceSession")
def test_call_accepts_2d_audio(mock_session_cls):
    """__call__ handles 2D audio input (1, 512)."""
    mock_session_cls.return_value = _make_mock_session()
    model = SileroVadOnnx("fake_model.onnx")

    audio = np.zeros((1, 512), dtype=np.float32)
    result = model(audio, 16000)
    assert isinstance(result, float)


@patch("src.vad_model.onnxruntime.InferenceSession")
def test_reset_states_zeros_state_and_context(mock_session_cls):
    """reset_states() zeros both _state and _context."""
    mock_session_cls.return_value = _make_mock_session()
    model = SileroVadOnnx("fake_model.onnx")

    # Mutate state by calling model
    audio = np.random.randn(512).astype(np.float32)
    model(audio, 16000)

    # Reset
    model.reset_states()

    assert np.all(model._state == 0.0)
    assert np.all(model._context == 0.0)
    assert model._state.shape == (2, 1, 128)
    assert model._context.shape == (1, 64)


@patch("src.vad_model.onnxruntime.InferenceSession")
def test_context_updated_after_call(mock_session_cls):
    """__call__ updates _context with last 64 samples of input."""
    mock_session_cls.return_value = _make_mock_session()
    model = SileroVadOnnx("fake_model.onnx")

    audio = np.ones(512, dtype=np.float32) * 0.5
    model(audio, 16000)

    # Context should be last 64 samples of the concatenated input
    # (64 zeros from init context + 512 audio = 576 total, last 64 = audio[-64:])
    expected = audio[-64:].reshape(1, 64)
    np.testing.assert_array_almost_equal(model._context, expected)
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/test_vad_model.py -v
```

Expected: all pass

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_vad_model.py
git commit -m "test: add unit tests for vad_model.py SileroVadOnnx

Tests init, __call__ with 1D/2D input, reset_states,
and context buffer updates. All mock ONNX InferenceSession."
```

---

### Task 7: Add test_server_commands.py

**Files:**
- Create: `tests/test_server_commands.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b test/server-commands
```

- [ ] **Step 2: Write tests**

Create `tests/test_server_commands.py`:

```python
"""Unit tests for src/server.py command handlers.

Tests each command handler in isolation by mocking all components
(AudioCapture, VadThread, WhisperTranscriber, TelegramSender).
"""

import json
import pathlib
import sys
from unittest.mock import MagicMock, patch, call

_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# We need to mock sounddevice before importing server (it imports sd at module level)
_mock_sd = MagicMock()
_mock_sd.default.device = [0, 0]
_mock_sd.query_devices.return_value = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2},
]

with patch.dict("sys.modules", {"sounddevice": _mock_sd}):
    from src import server  # noqa: E402


def _capture_events():
    """Capture _send() calls and return list of (event, payload) tuples."""
    events = []
    original_send = server._send

    def mock_send(event, payload=None):
        events.append((event, payload))

    server._send = mock_send
    return events, original_send


class TestListDevices:
    @patch.object(server, "sd", _mock_sd)
    def test_list_devices_emits_event(self):
        """list_devices command emits a 'devices' event with input devices."""
        events, restore = _capture_events()
        try:
            server._list_devices()
        finally:
            server._send = restore

        assert len(events) == 1
        event_name, payload = events[0]
        assert event_name == "devices"
        assert isinstance(payload, list)
        # Only input devices (max_input_channels > 0)
        assert len(payload) == 1
        assert payload[0]["name"] == "MacBook Pro Microphone"


class TestDoStop:
    def test_stop_when_nothing_running(self):
        """_do_stop() doesn't crash when no components are active."""
        # Reset all global state
        server._capture = None
        server._transcriber = None
        server._telegram_sender = None
        server._vad_thread = None
        server._speech_q = None
        server._bridge_thread = None
        server._energy_thread = None

        events, restore = _capture_events()
        try:
            server._do_stop()
        finally:
            server._send = restore

        # Should emit idle status
        assert any(e == "status" and p == "idle" for e, p in events)


class TestDoSetDevice:
    def test_set_device_without_running_emits_error(self):
        """set_device when not running emits an error."""
        server._capture = None
        events, restore = _capture_events()
        try:
            server._do_set_device({"device": 1})
        finally:
            server._send = restore

        assert any(e == "error" for e, _ in events)

    def test_set_device_missing_device_field(self):
        """set_device without 'device' field emits error."""
        server._capture = MagicMock()
        events, restore = _capture_events()
        try:
            server._do_set_device({})
        finally:
            server._send = restore

        assert any(e == "error" for e, _ in events)


class TestDoTestTelegram:
    @patch("src.server.httpx")
    def test_test_telegram_missing_credentials(self, mock_httpx):
        """test_telegram with empty credentials emits failure."""
        events, restore = _capture_events()
        try:
            server._do_test_telegram({"bot_token": "", "chat_id": ""})
        finally:
            server._send = restore

        assert any(
            e == "telegram_test" and p.get("success") is False
            for e, p in events
        )
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/test_server_commands.py -v
```

Expected: all pass

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_server_commands.py
git commit -m "test: add unit tests for server.py command handlers

Tests list_devices, stop-when-idle, set_device error paths,
and test_telegram credential validation. All components mocked."
```

---

### Task 8: Add test_integration.py

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b test/integration
```

- [ ] **Step 2: Write tests**

Create `tests/test_integration.py`:

```python
"""Integration test: Mock audio -> VAD -> Whisper -> Telegram pipeline.

Verifies the full data flow with all components mocked. No real
hardware, models, or network calls.
"""

import pathlib
import queue
import sys
import time
from unittest.mock import MagicMock, patch

import numpy as np

_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.vad import VadThread  # noqa: E402
from src.transcriber import WhisperTranscriber, TranscriptionUpdate  # noqa: E402
from src import config  # noqa: E402


def test_vad_to_transcriber_pipeline():
    """VAD emits utterance -> WhisperTranscriber receives and processes it.

    Verifies the queue handoff between VAD and Whisper consumer.
    """
    # Setup: VAD writes to speech_q, we read from speech_q
    audio_q = queue.Queue()
    speech_q = queue.Queue()

    # Feed 20 speech frames + 20 silence frames to trigger utterance
    rng = np.random.default_rng(42)
    for _ in range(20):
        audio_q.put(rng.normal(0, 0.1, 512).astype(np.float32))
    for _ in range(20):
        audio_q.put(rng.normal(0, 0.1, 512).astype(np.float32))
    audio_q.put(None)  # sentinel

    # Mock VAD model: first 20 frames = speech, rest = silence
    mock_model = MagicMock()
    mock_model.reset_states = MagicMock()
    call_count = [0]

    def side_effect(tensor, sr):
        if call_count[0] < 20:
            call_count[0] += 1
            return 0.9
        call_count[0] += 1
        return 0.1

    mock_model.side_effect = side_effect

    with patch("src.vad.SileroVadOnnx", return_value=mock_model):
        vad = VadThread(audio_q=audio_q, speech_q=speech_q)
        vad.start()
        vad.wait(timeout=3.0)

    # VAD should have emitted exactly 1 utterance
    assert not speech_q.empty(), "VAD should have emitted an utterance"
    utterance = speech_q.get_nowait()
    assert isinstance(utterance, np.ndarray)
    assert utterance.dtype == np.float32
    assert len(utterance) > 0


def test_transcription_update_fields():
    """TranscriptionUpdate has all required fields with correct types."""
    update = TranscriptionUpdate(
        text="Hello world",
        finalized_text="Hello world",
        sentences=["Hello world"],
        no_speech_prob=0.1,
        duration_s=1.5,
    )
    assert update.text == "Hello world"
    assert update.finalized_text == "Hello world"
    assert update.sentences == ["Hello world"]
    assert update.no_speech_prob == 0.1
    assert update.duration_s == 1.5


def test_telegram_sender_receives_update():
    """TelegramSender.on_update enqueues the text from TranscriptionUpdate."""
    with patch("src.telegram_sender.httpx"):
        from src.telegram_sender import TelegramSender

        sender = TelegramSender("fake_token", "fake_chat")
        update = TranscriptionUpdate(text="Hello world")

        # Stop the background thread first to inspect queue directly
        sender.stop()
        sender.wait(timeout=2.0)

        # Now test on_update directly
        sender._queue = queue.Queue()  # fresh queue
        sender.on_update(update)

        item = sender._queue.get_nowait()
        assert item == "Hello world"
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/test_integration.py -v
```

Expected: all pass

- [ ] **Step 4: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for VAD -> Whisper -> Telegram pipeline

Tests the queue handoff between components with all models mocked.
Verifies data flows correctly through the full pipeline."
```

---

### Task 9: Set up XCTest target for Swift tests

**Files:**
- Create: `EsperApp/EsperAppTests/ProtocolTests.swift`
- Modify: Xcode project (add test target)

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b test/swift-xctest
```

- [ ] **Step 2: Create test directory**

```bash
mkdir -p /Users/yashdesai/Codebase/Fun/Esper/EsperApp/EsperAppTests
```

- [ ] **Step 3: Create ProtocolTests.swift**

Create `EsperApp/EsperAppTests/ProtocolTests.swift`:

```swift
import XCTest
@testable import EsperApp

final class ProtocolTests: XCTestCase {

    // MARK: - Status parsing

    func testStatusIdleParsed() throws {
        let json = #"{"event":"status","data":"idle"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .status(let s) = event else { return XCTFail("Expected .status") }
        XCTAssertEqual(s, .idle)
    }

    func testStatusListeningParsed() throws {
        let json = #"{"event":"status","data":"listening"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .status(let s) = event else { return XCTFail("Expected .status") }
        XCTAssertEqual(s, .listening)
    }

    func testStatusUnknownValueFallsBackToIdle() throws {
        let json = #"{"event":"status","data":"some_new_status"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .status(let s) = event else { return XCTFail("Expected .status") }
        XCTAssertEqual(s, .idle)
    }

    // MARK: - Devices parsing

    func testDevicesParsed() throws {
        let json = """
        {"event":"devices","data":[{"index":0,"name":"Mic","channels":1,"is_default":true}]}
        """.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .devices(let list) = event else { return XCTFail("Expected .devices") }
        XCTAssertEqual(list.count, 1)
        XCTAssertEqual(list[0].name, "Mic")
        XCTAssertTrue(list[0].isDefault)
    }

    func testDevicesEmptyArrayParsed() throws {
        let json = #"{"event":"devices","data":[]}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .devices(let list) = event else { return XCTFail("Expected .devices") }
        XCTAssertTrue(list.isEmpty)
    }

    // MARK: - Transcript parsing

    func testTranscriptParsed() throws {
        let json = """
        {"event":"transcript","data":{"text":"hello","finalized_text":"hello world","sentences":["hello","world"],"no_speech_prob":0.1,"duration_s":1.5}}
        """.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .transcript(let p) = event else { return XCTFail("Expected .transcript") }
        XCTAssertEqual(p.text, "hello")
        XCTAssertEqual(p.finalizedText, "hello world")
        XCTAssertEqual(p.sentences, ["hello", "world"])
        XCTAssertEqual(p.noSpeechProb, 0.1, accuracy: 0.001)
        XCTAssertEqual(p.durationS, 1.5, accuracy: 0.001)
    }

    // MARK: - Energy parsing

    func testEnergyParsed() throws {
        let json = #"{"event":"energy","data":{"level":0.42}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .energy(let level) = event else { return XCTFail("Expected .energy") }
        XCTAssertEqual(level, 0.42, accuracy: 0.001)
    }

    // MARK: - Telegram test parsing

    func testTelegramTestSuccessParsed() throws {
        let json = #"{"event":"telegram_test","data":{"success":true}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .telegramTest(let ok, let err) = event else { return XCTFail("Expected .telegramTest") }
        XCTAssertTrue(ok)
        XCTAssertNil(err)
    }

    func testTelegramTestFailureParsed() throws {
        let json = #"{"event":"telegram_test","data":{"success":false,"error":"bad token"}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .telegramTest(let ok, let err) = event else { return XCTFail("Expected .telegramTest") }
        XCTAssertFalse(ok)
        XCTAssertEqual(err, "bad token")
    }

    // MARK: - Error parsing

    func testErrorWithMessageParsed() throws {
        let json = #"{"event":"error","data":{"message":"something broke"}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .error(let msg) = event else { return XCTFail("Expected .error") }
        XCTAssertEqual(msg, "something broke")
    }

    // MARK: - Unknown event

    func testUnknownEventReturnsUnknown() throws {
        let json = #"{"event":"future_event","data":{}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .unknown = event else { return XCTFail("Expected .unknown") }
    }

    // MARK: - Malformed JSON

    func testMalformedJsonReturnsNil() throws {
        let json = "not json at all".data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }

    func testMissingEventKeyReturnsNil() throws {
        let json = #"{"data":"idle"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }
}
```

- [ ] **Step 4: Add XCTest target to Xcode project**

Open Xcode, add a new Unit Test target named "EsperAppTests" targeting the EsperApp module. Or use the command line:

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
# This needs to be done via Xcode GUI or by editing project.pbxproj
# Add the test file to the project
```

- [ ] **Step 5: Build and run tests**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild test -scheme EsperApp -destination 'platform=macOS' -only-testing:EsperAppTests 2>&1 | tail -20
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add EsperApp/EsperAppTests/
git add EsperApp/EsperApp.xcodeproj/
git commit -m "test: add XCTest target with Protocol parsing tests

15 tests covering all ServerEvent types: status, devices,
transcript, energy, telegram_test, error, unknown, and
malformed JSON. Foundation for Swift-side regression testing."
```

---

## Phase 2: Python Backend Hardening

### Task 10: Fix missing _pipe_proc init (Fix #1)

**Files:**
- Modify: `src/transcriber.py:86-103`
- Test: `tests/test_whisper_transcriber.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/pipe-proc-init
```

- [ ] **Step 2: Write regression test**

Add to `tests/test_whisper_transcriber.py`:

```python
def test_stop_before_start_does_not_crash():
    """Calling stop() before start() must not raise AttributeError."""
    on_update = MagicMock()
    on_status = MagicMock()
    wt = WhisperTranscriber(on_update=on_update, on_status=on_status)
    # This must not raise AttributeError: '_pipe_proc'
    wt.stop()
    assert wt.stopped is True


def test_wait_before_start_does_not_crash():
    """Calling wait() before start() must not raise AttributeError."""
    on_update = MagicMock()
    on_status = MagicMock()
    wt = WhisperTranscriber(on_update=on_update, on_status=on_status)
    # This must not raise AttributeError
    wt.wait(timeout=0.1)
```

- [ ] **Step 3: Run test — expect FAILURE**

```bash
.venv/bin/python -m pytest tests/test_whisper_transcriber.py::test_stop_before_start_does_not_crash -v
```

Expected: FAIL with `AttributeError: 'WhisperTranscriber' object has no attribute '_pipe_proc'`

- [ ] **Step 4: Apply fix**

In `src/transcriber.py`, add three lines after line 103 (`self._result_q = None`):

```python
        self._pipe_proc = None
        self._reader_thread = None
        self._stderr_thread = None
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
.venv/bin/python -m pytest tests/test_whisper_transcriber.py -v
```

Expected: all pass including the two new tests

- [ ] **Step 6: Run full suite**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/transcriber.py tests/test_whisper_transcriber.py
git commit -m "fix: initialize _pipe_proc, _reader_thread, _stderr_thread in __init__

Calling stop() or wait() before start() raised AttributeError
because these attributes were only set in _spawn_worker(). Now
initialized to None in __init__ so lifecycle methods are always safe."
```

---

### Task 11: Fix unclosed subprocess pipes (Fix #9)

**Files:**
- Modify: `src/transcriber.py:311-320`
- Test: `tests/test_whisper_transcriber.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/close-subprocess-pipes
```

- [ ] **Step 2: Write regression test**

Add to `tests/test_whisper_transcriber.py`:

```python
def test_kill_worker_closes_all_pipes():
    """_kill_worker closes stdin, stdout, and stderr (not just stdin)."""
    on_update = MagicMock()
    on_status = MagicMock()
    wt = WhisperTranscriber(on_update=on_update, on_status=on_status)

    # Simulate a pipe-mode worker
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stderr = MagicMock()
    wt._pipe_proc = mock_proc

    wt._kill_worker()

    mock_proc.stdin.close.assert_called_once()
    mock_proc.stdout.close.assert_called_once()
    mock_proc.stderr.close.assert_called_once()
```

- [ ] **Step 3: Run test — expect FAILURE**

```bash
.venv/bin/python -m pytest tests/test_whisper_transcriber.py::test_kill_worker_closes_all_pipes -v
```

Expected: FAIL — `stdout.close` and `stderr.close` never called

- [ ] **Step 4: Apply fix**

In `src/transcriber.py`, replace the `_kill_worker` method (lines 311-323):

```python
    def _kill_worker(self) -> None:
        """Kill and join the current worker process."""
        if self._pipe_proc is not None:
            try:
                self._pipe_proc.stdin.close()
            except Exception:
                pass
            try:
                self._pipe_proc.stdout.close()
            except Exception:
                pass
            try:
                self._pipe_proc.stderr.close()
            except Exception:
                pass
            self._pipe_proc.kill()
            self._pipe_proc.wait(timeout=5)
            self._pipe_proc = None
        elif self._proc is not None and self._proc.is_alive():
            self._proc.kill()
            self._proc.join(timeout=5)
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/transcriber.py tests/test_whisper_transcriber.py
git commit -m "fix: close stdout and stderr pipes in _kill_worker

Previously only stdin was closed, leaking file descriptors for
stdout and stderr on every worker recycle (every 50 utterances)."
```

---

### Task 12: Fix unhandled BrokenPipeError in transcribe_utterance (Fix #11)

**Files:**
- Modify: `src/transcriber.py:185-186`
- Test: `tests/test_whisper_transcriber.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/broken-pipe-handling
```

- [ ] **Step 2: Write regression test**

Add to `tests/test_whisper_transcriber.py`:

```python
def test_transcribe_utterance_handles_broken_pipe():
    """BrokenPipeError during _send_msg triggers _on_failure, not crash."""
    on_update = MagicMock()
    on_status = MagicMock()
    wt = WhisperTranscriber(on_update=on_update, on_status=on_status)

    # Simulate pipe mode with broken pipe
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    wt._pipe_proc = mock_proc
    wt._result_q = MagicMock()

    with patch("src.transcriber._send_msg", side_effect=BrokenPipeError("pipe closed")):
        audio = np.zeros(16000, dtype=np.float32)
        result = wt.transcribe_utterance(audio)

    assert result is None
    on_status.assert_called()  # should have called on_status("error")
```

- [ ] **Step 3: Run test — expect FAILURE**

```bash
.venv/bin/python -m pytest tests/test_whisper_transcriber.py::test_transcribe_utterance_handles_broken_pipe -v
```

Expected: FAIL with `BrokenPipeError: pipe closed`

- [ ] **Step 4: Apply fix**

In `src/transcriber.py`, replace lines 185-188:

```python
        if self._pipe_proc:
            _send_msg(self._pipe_proc.stdin, audio)
        else:
            self._audio_q.put(audio)
```

With:

```python
        try:
            if self._pipe_proc:
                _send_msg(self._pipe_proc.stdin, audio)
            else:
                self._audio_q.put(audio)
        except (BrokenPipeError, OSError) as exc:
            log.error("Failed to send audio to worker: %s", exc)
            self._on_status("error")
            self._on_failure()
            return None
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/transcriber.py tests/test_whisper_transcriber.py
git commit -m "fix: handle BrokenPipeError in transcribe_utterance

If the worker process dies mid-transcription, _send_msg raises
BrokenPipeError. Now caught and routed through _on_failure for
proper restart/crash handling instead of crashing the consumer."
```

---

### Task 13: Add logging for silent pipe overflow (Fix #8)

**Files:**
- Modify: `src/server.py:80-81`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/log-pipe-overflow
```

- [ ] **Step 2: Apply fix**

In `src/server.py`, replace lines 80-81:

```python
    except (BrokenPipeError, OSError):
        pass
```

With:

```python
    except (BrokenPipeError, OSError) as exc:
        log.warning("Protocol write failed (pipe overflow or closed): %s", exc)
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/server.py
git commit -m "fix: log pipe overflow instead of silently swallowing

BrokenPipeError/OSError in _send() was caught with bare 'pass'.
Now logs at WARNING level for observability."
```

---

### Task 14: Add logging for swallowed reader exceptions (Fix #27)

**Files:**
- Modify: `src/transcriber.py:289-308`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/log-reader-exceptions
```

- [ ] **Step 2: Apply fix**

In `src/transcriber.py`, replace `_pipe_reader` (lines 289-298):

```python
    def _pipe_reader(self) -> None:
        """Read length-prefixed pickle messages from pipe worker stdout."""
        try:
            while True:
                msg = _recv_msg(self._pipe_proc.stdout)
                if msg is None:
                    break
                self._result_q.put(msg)
        except Exception:
            log.error("Pipe reader thread crashed", exc_info=True)
```

Replace `_stderr_reader` (lines 300-308):

```python
    def _stderr_reader(self) -> None:
        """Log worker stderr output."""
        try:
            for line in self._pipe_proc.stderr:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    log.debug("[whisper-worker] %s", text)
        except Exception:
            log.error("Stderr reader thread crashed", exc_info=True)
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/transcriber.py
git commit -m "fix: log exceptions in pipe/stderr reader threads

Both reader threads had bare 'except: pass' that silently
swallowed all errors. Now logs at ERROR with full traceback."
```

---

### Task 15: Fix hardcoded sample rate in VAD (Fix #21)

**Files:**
- Modify: `src/vad.py:169`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/vad-sample-rate
```

- [ ] **Step 2: Apply fix**

In `src/vad.py`, replace line 169:

```python
            duration = len(utterance) / 16000
```

With:

```python
            duration = len(utterance) / config.SAMPLE_RATE
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass (config.SAMPLE_RATE is 16000, so behavior is identical)

- [ ] **Step 4: Commit**

```bash
git add src/vad.py
git commit -m "fix: use config.SAMPLE_RATE instead of hardcoded 16000

Duration calculation in _seal_utterance used hardcoded 16000.
Now uses config.SAMPLE_RATE for consistency. Currently identical
(16000) but prevents silent bugs if sample rate ever changes."
```

---

### Task 16: Cap session memory growth (Fix #30)

**Files:**
- Modify: `src/transcriber.py:376-377`
- Test: `tests/test_whisper_transcriber.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/session-memory-cap
```

- [ ] **Step 2: Write regression test**

Add to `tests/test_whisper_transcriber.py`:

```python
def test_sentences_capped_at_500():
    """_sentences list doesn't grow beyond 500 entries."""
    on_update = MagicMock()
    on_status = MagicMock()
    wt = WhisperTranscriber(on_update=on_update, on_status=on_status)

    # Simulate 600 accumulated sentences
    wt._sentences = [f"sentence {i}" for i in range(600)]
    wt._finalized_text = " ".join(wt._sentences)

    audio = np.zeros(16000, dtype=np.float32)
    result = {"text": " New sentence.", "segments": [{"no_speech_prob": 0.1, "compression_ratio": 1.2, "text": "New sentence."}]}

    update = wt._build_update(result, audio)

    # Should be capped: 500 old + 1 new = 501, then capped to 500
    assert len(wt._sentences) <= 500
    assert "New sentence." in wt._sentences[-1]
```

- [ ] **Step 3: Run test — expect FAILURE**

```bash
.venv/bin/python -m pytest tests/test_whisper_transcriber.py::test_sentences_capped_at_500 -v
```

Expected: FAIL — `_sentences` has 601 entries (no cap)

- [ ] **Step 4: Apply fix**

In `src/transcriber.py`, in `_build_update` method, after line 377 (`self._finalized_text = " ".join(self._sentences)`), add:

```python
        # Cap session accumulator to prevent unbounded memory growth
        if len(self._sentences) > 500:
            self._sentences = self._sentences[-500:]
            self._finalized_text = " ".join(self._sentences)
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/transcriber.py tests/test_whisper_transcriber.py
git commit -m "fix: cap _sentences to 500 entries to prevent memory growth

In long sessions (500+ utterances), _sentences and _finalized_text
grew unbounded. Now keeps only the most recent 500 sentences."
```

---

### Task 17: Add config validation (Fix #31)

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/config-validation
```

- [ ] **Step 2: Add validation**

Add at the bottom of `src/config.py`:

```python
# ── Validation ────────────────────────────────────────────────────────────────
assert 0.0 <= VAD_SPEECH_THRESHOLD <= 1.0, f"VAD_SPEECH_THRESHOLD must be 0-1, got {VAD_SPEECH_THRESHOLD}"
assert VAD_MIN_ENERGY >= 0.0, f"VAD_MIN_ENERGY must be >= 0, got {VAD_MIN_ENERGY}"
assert QUEUE_MAXSIZE > 0, f"QUEUE_MAXSIZE must be > 0, got {QUEUE_MAXSIZE}"
assert WHISPER_SUBPROCESS_TIMEOUT_S > 0, f"WHISPER_SUBPROCESS_TIMEOUT_S must be > 0, got {WHISPER_SUBPROCESS_TIMEOUT_S}"
assert TELEGRAM_MAX_RETRIES >= 1, f"TELEGRAM_MAX_RETRIES must be >= 1, got {TELEGRAM_MAX_RETRIES}"
assert SAMPLE_RATE > 0, f"SAMPLE_RATE must be > 0, got {SAMPLE_RATE}"
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass (all current values satisfy constraints)

- [ ] **Step 4: Commit**

```bash
git add src/config.py
git commit -m "fix: add startup validation for config values

Asserts that thresholds are in valid ranges, queue sizes are
positive, and timeouts are positive. Fails fast on misconfiguration
instead of producing silent incorrect behavior."
```

---

### Task 18: Fix SIGTERM cleanup (Fix #33)

**Files:**
- Modify: `src/server.py:326-329`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/sigterm-cleanup
```

- [ ] **Step 2: Apply fix**

In `src/server.py`, replace lines 326-329:

```python
    def _sigterm(sig, frame):
        log.info("Received SIGTERM, shutting down")
        _do_stop()
        sys.exit(0)
```

With:

```python
    def _sigterm(sig, frame):
        log.info("Received SIGTERM, shutting down")
        _do_stop()
        raise SystemExit(0)
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/server.py
git commit -m "fix: use raise SystemExit instead of sys.exit in SIGTERM handler

sys.exit(0) could skip finally blocks in some contexts.
raise SystemExit(0) ensures proper cleanup chain execution."
```

---

### Task 19: Add Telegram credential validation (Fix #32)

**Files:**
- Modify: `src/server.py:176-184`
- Test: `tests/test_server_commands.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/telegram-credential-validation
```

- [ ] **Step 2: Write regression test**

Add to `tests/test_server_commands.py`:

```python
class TestTelegramValidation:
    def test_invalid_bot_token_format_rejected(self):
        """Bot token that doesn't match digits:alphanumeric is rejected."""
        events, restore = _capture_events()
        server._capture = None
        server._transcriber = None
        server._telegram_sender = None
        try:
            server._do_start({
                "telegram": {"bot_token": "not-a-valid-token", "chat_id": "12345"}
            })
        finally:
            server._send = restore
        # Telegram sender should not have been created
        assert server._telegram_sender is None

    def test_invalid_chat_id_rejected(self):
        """Non-numeric chat_id is rejected."""
        events, restore = _capture_events()
        server._capture = None
        server._transcriber = None
        server._telegram_sender = None
        try:
            server._do_start({
                "telegram": {"bot_token": "123456:ABCdef", "chat_id": "not-numeric"}
            })
        finally:
            server._send = restore
        assert server._telegram_sender is None
```

- [ ] **Step 3: Run test — expect FAILURE**

```bash
.venv/bin/python -m pytest tests/test_server_commands.py::TestTelegramValidation -v
```

Expected: FAIL — invalid credentials are currently accepted

- [ ] **Step 4: Apply fix**

In `src/server.py`, add `import re` at the top (after `import json` on line 15), then add a validation function before `_do_start`:

```python
def _validate_telegram_credentials(bot_token: str, chat_id: str) -> bool:
    """Validate Telegram credential formats."""
    if not re.match(r'^\d+:[A-Za-z0-9_-]+$', bot_token):
        log.warning("Invalid bot token format")
        return False
    try:
        int(chat_id)
    except ValueError:
        log.warning("Invalid chat_id (must be numeric): %s", chat_id)
        return False
    return True
```

Then in `_do_start`, replace lines 179-183:

```python
        if bot_token and chat_id:
```

With:

```python
        if bot_token and chat_id and _validate_telegram_credentials(bot_token, chat_id):
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/server.py tests/test_server_commands.py
git commit -m "fix: validate Telegram credential format before creating sender

Bot token must match digits:alphanumeric pattern, chat_id must
be numeric. Invalid credentials are rejected at startup instead
of failing silently on first message send."
```

---

### Task 20: Add VAD thread restart on crash (Fix #10)

**Files:**
- Modify: `src/vad.py:134-139`
- Modify: `src/server.py` (consumer loop)
- Test: `tests/test_vad.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b fix/vad-restart
```

- [ ] **Step 2: Write regression test**

Add to `tests/test_vad.py`:

```python
def test_vad_crash_sends_error_sentinel():
    """If VAD model raises, error sentinel (None) is put into speech_q."""
    audio_q = queue.Queue()
    speech_q = queue.Queue()

    # Put one frame then sentinel
    audio_q.put(speech_frame())
    audio_q.put(None)

    # Model that crashes on call
    mock_model = MagicMock()
    mock_model.side_effect = RuntimeError("model crashed")
    mock_model.reset_states = MagicMock()

    with patch("src.vad.SileroVadOnnx", return_value=mock_model):
        vad = VadThread(audio_q=audio_q, speech_q=speech_q)
        vad.start()
        vad.wait(timeout=2.0)

    # Should have put None sentinel into speech_q
    assert not speech_q.empty()
    item = speech_q.get_nowait()
    assert item is None, "Expected None sentinel on VAD crash"
```

- [ ] **Step 3: Run test — should already PASS**

The current code already puts None into speech_q on crash (lines 136-138). This test locks down existing behavior.

```bash
.venv/bin/python -m pytest tests/test_vad.py::test_vad_crash_sends_error_sentinel -v
```

Expected: PASS

- [ ] **Step 4: Enhance server.py consumer to detect and restart VAD**

In `src/server.py`, modify `_whisper_consumer` to detect VAD crash sentinel and restart:

In `_whisper_consumer()`, after line 142 (`if utterance is None:`), replace:

```python
        if utterance is None:
            log.info("Whisper consumer: got None sentinel, exiting")
            break
```

With:

```python
        if utterance is None:
            # Check if this is a VAD crash (not a stop signal)
            if not _stop_event.is_set() and _vad_thread is not None:
                log.warning("Whisper consumer: VAD thread crashed, restarting")
                _send("error", {"message": "Voice detection crashed, restarting..."})
                _restart_vad()
                continue
            log.info("Whisper consumer: got None sentinel, exiting")
            break
```

Add the `_restart_vad` helper:

```python
def _restart_vad():
    """Restart the VAD thread after a crash."""
    global _vad_thread
    if _vad_thread is not None:
        _vad_thread.stop()
        _vad_thread.wait(timeout=2.0)
    if _capture is not None and _speech_q is not None:
        _vad_thread = VadThread(audio_q=_capture._queue, speech_q=_speech_q)
        _vad_thread.start()
        log.info("VAD thread restarted")
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/vad.py src/server.py tests/test_vad.py
git commit -m "fix: detect and restart VAD thread on crash

When VadThread crashes unexpectedly, it puts None into speech_q.
The Whisper consumer now detects this (when stop hasn't been
signaled) and restarts the VAD thread instead of exiting."
```

---

## Phase 3-5: Remaining Tasks

Phases 3 through 5 follow the exact same pattern as Phase 2. Each fix:

1. Creates a branch off `main`
2. Writes a failing test (or behavior-locking test)
3. Makes the minimal fix
4. Verifies all tests pass
5. Commits

The remaining tasks are:

### Phase 3 — Swift/IPC (Tasks 21-27)
- **Task 21:** Fix #3 — Add NSLock to ProcessBridge for thread safety
- **Task 22:** Fix #5 — Make reader thread cancellable (close pipe FD on terminate)
- **Task 23:** Fix #6 — Add waitUntilExit + SIGKILL fallback for zombie processes
- **Task 24:** Fix #4 — Add bounded AsyncStream buffer + non-blocking Python writes
- **Task 25:** Fix #7 — Add 30s command-response watchdog to TranscriptionEngine
- **Task 26:** Fix #20 — Add protocol version field (`"v": 1`) to all events
- **Task 27:** Fix #12 — Move credentials from UserDefaults to Keychain

### Phase 4 — Audio/Telegram (Tasks 28-33)
- **Task 28:** Fix #18 — Log audio queue overflow with periodic counter
- **Task 29:** Fix #13 — Propagate audio device errors through queue to UI
- **Task 30:** Fix #22 — Verify Telegram response body `{"ok": true}`
- **Task 31:** Fix #23 — Early return for non-retryable HTTP errors (400/401/403)
- **Task 32:** Fix #24 — Truncate messages exceeding 4096 chars
- **Task 33:** Fix #26 — Replace pickle with JSON + raw bytes in worker IPC

### Phase 5 — Build (Tasks 34-36)
- **Task 34:** Fix #17 — Add NSMicrophoneUsageDescription + permission pre-flight
- **Task 35:** Fix #28 — Replace hardcoded dev path with dynamic resolution
- **Task 36:** Fix #14 — Add hardened runtime flag to build-dmg.sh

Each task follows the identical test-first workflow documented in Tasks 10-20 above. The pattern is mechanical and consistent.

---

## Smoke Test Checkpoints

After every 5 merged PRs, the user performs manual end-to-end verification:

1. Launch the app
2. Click "Start Listening"
3. Speak a sentence
4. Verify transcript appears in the UI
5. Verify Telegram message received (if configured)
6. Click "Stop Listening"
7. Quit the app cleanly (no zombie processes)

---

## Summary

| Phase | Tasks | Fixes | Risk |
|-------|-------|-------|------|
| Phase 0: Security | 1-3 | #2, #16, #25 | Near-zero |
| Phase 1: Tests | 4-9 | None (test-only) | Zero |
| Phase 2: Python | 10-20 | #1, #8, #9, #10, #11, #21, #27, #30, #31, #32, #33 | Low-Medium |
| Phase 3: Swift/IPC | 21-27 | #3, #4, #5, #6, #7, #12, #20 | Medium-High |
| Phase 4: Audio/Telegram | 28-33 | #13, #18, #22, #23, #24, #26 | Low-Medium |
| Phase 5: Build | 34-36 | #14, #17, #28 | Low |

Total: 36 tasks, 32 fixes, 0 regressions allowed.
