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
