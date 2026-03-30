"""Tests for src/server.py command handlers.

Mocks sounddevice at module level (it's imported at line 26 of server.py)
so the server module can be loaded without actual audio hardware.
"""

import sys
from unittest.mock import MagicMock, patch

# sounddevice must be mocked BEFORE importing src.server
_mock_sd = MagicMock()
_mock_sd.default.device = [0, 0]
_mock_sd.query_devices.return_value = [
    {"name": "MacBook Pro Microphone", "max_input_channels": 1, "max_output_channels": 0},
    {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2},
]

with patch.dict("sys.modules", {"sounddevice": _mock_sd}):
    from src import server


def _capture_events():
    """Swap server._send with a capturing mock; returns (events_list, original_send)."""
    events = []
    original_send = server._send

    def mock_send(event, payload=None):
        events.append((event, payload))

    server._send = mock_send
    return events, original_send


# ── Tests ────────────────────────────────────────────────────────────────────


def test_list_devices_emits_event():
    """_list_devices emits a 'devices' event with input-only devices."""
    events, original = _capture_events()
    try:
        server._list_devices()

        assert len(events) == 1
        event_name, payload = events[0]
        assert event_name == "devices"

        # Only the microphone (max_input_channels > 0) should appear
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["name"] == "MacBook Pro Microphone"
        assert payload[0]["index"] == 0
        assert payload[0]["channels"] == 1
        assert payload[0]["is_default"] is True
    finally:
        server._send = original


def test_stop_when_nothing_running():
    """_do_stop doesn't crash when no components are active, emits 'idle'."""
    events, original = _capture_events()
    try:
        # Ensure globals are None (default state)
        server._capture = None
        server._transcriber = None
        server._telegram_sender = None
        server._vad_thread = None
        server._speech_q = None
        server._bridge_thread = None
        server._energy_thread = None

        server._do_stop()

        event_names = [e[0] for e in events]
        assert "status" in event_names
        status_events = [(e, p) for e, p in events if e == "status"]
        assert any(p == "idle" for _, p in status_events)
    finally:
        server._send = original


def test_set_device_without_running_emits_error():
    """set_device when _capture is None emits an error event."""
    events, original = _capture_events()
    try:
        server._capture = None
        server._do_set_device({"device": 1})

        assert len(events) == 1
        event_name, payload = events[0]
        assert event_name == "error"
        assert "not running" in payload["message"].lower()
    finally:
        server._send = original


def test_set_device_missing_device_field():
    """set_device({}) emits an error about missing 'device' field."""
    events, original = _capture_events()
    try:
        server._do_set_device({})

        assert len(events) == 1
        event_name, payload = events[0]
        assert event_name == "error"
        assert "device" in payload["message"].lower()
    finally:
        server._send = original


def test_test_telegram_missing_credentials():
    """test_telegram with empty creds emits a failure telegram_test event."""
    events, original = _capture_events()
    try:
        server._do_test_telegram({})

        assert len(events) == 1
        event_name, payload = events[0]
        assert event_name == "telegram_test"
        assert payload["success"] is False
        assert "required" in payload["error"].lower()
    finally:
        server._send = original


# ── Telegram credential validation ──────────────────────────────────────


class TestTelegramValidation:
    def test_valid_credentials(self):
        """Valid bot token and chat_id pass validation."""
        assert server._validate_telegram_credentials("123456:ABC-DEF_ghi", "12345") is True

    def test_valid_negative_chat_id(self):
        """Negative chat_id (group chats) passes validation."""
        assert server._validate_telegram_credentials("123456:ABCdef", "-100123456") is True

    def test_invalid_bot_token_rejected(self):
        """Invalid bot token format doesn't create sender."""
        # Reset state
        server._telegram_sender = None
        server._transcriber = None
        server._capture = None
        events, restore = _capture_events()
        try:
            # Mock WhisperTranscriber to prevent actual startup
            with patch.object(server, "WhisperTranscriber") as mock_wt:
                mock_wt.side_effect = Exception("should not reach here")
                server._do_start({"telegram": {"bot_token": "not-valid", "chat_id": "12345"}})
        except Exception:
            pass
        finally:
            server._send = restore
        assert server._telegram_sender is None

    def test_invalid_bot_token_format(self):
        """Bot token without colon-separated numeric prefix is rejected."""
        assert server._validate_telegram_credentials("not-valid", "12345") is False

    def test_invalid_chat_id_non_numeric(self):
        """Non-numeric chat_id is rejected."""
        assert server._validate_telegram_credentials("123456:ABCdef", "not-a-number") is False

    def test_empty_bot_token(self):
        """Empty bot token is rejected."""
        assert server._validate_telegram_credentials("", "12345") is False


# ── VAD restart ─────────────────────────────────────────────────────────


class TestVadRestart:
    def test_restart_vad_creates_new_thread(self):
        """_restart_vad stops old thread and creates a new VadThread."""
        mock_old_vad = MagicMock()
        mock_capture = MagicMock()
        mock_capture._queue = MagicMock()
        mock_speech_q = MagicMock()

        server._vad_thread = mock_old_vad
        server._capture = mock_capture
        server._speech_q = mock_speech_q

        try:
            with patch.object(server, "VadThread") as mock_vt:
                mock_new_vad = MagicMock()
                mock_vt.return_value = mock_new_vad
                server._restart_vad()

                mock_old_vad.stop.assert_called_once()
                mock_old_vad.wait.assert_called_once_with(timeout=2.0)
                mock_vt.assert_called_once_with(audio_q=mock_capture._queue, speech_q=mock_speech_q)
                mock_new_vad.start.assert_called_once()
        finally:
            server._vad_thread = None
            server._capture = None
            server._speech_q = None

    def test_restart_vad_noop_without_capture(self):
        """_restart_vad does nothing when _capture is None."""
        mock_old_vad = MagicMock()
        server._vad_thread = mock_old_vad
        server._capture = None
        server._speech_q = MagicMock()

        try:
            with patch.object(server, "VadThread") as mock_vt:
                server._restart_vad()
                mock_vt.assert_not_called()
        finally:
            server._vad_thread = None
            server._speech_q = None
