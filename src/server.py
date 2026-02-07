#!/usr/bin/env python3
"""Esper headless JSON server — bridges Python STT to the SwiftUI app.

Communicates via newline-delimited JSON over stdin (commands) / stdout (events).
All print() calls from existing modules are redirected to stderr so they
never corrupt the protocol stream.

Usage:
    python -m src.server
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import traceback

# ── Stdout isolation ────────────────────────────────────────────────
# Must happen BEFORE any import that might call print().
_proto_fd = os.dup(1)          # save real stdout file descriptor
os.dup2(2, 1)                  # redirect fd 1 → stderr (catches C-level prints too)
_proto_out = os.fdopen(_proto_fd, "w", buffering=1)  # line-buffered protocol writer


def _send(event: str, payload=None):
    """Write one JSON event to the protocol stream (original stdout)."""
    obj = {"event": event}
    if payload is not None:
        obj["data"] = payload
    try:
        _proto_out.write(json.dumps(obj) + "\n")
        _proto_out.flush()
    except (BrokenPipeError, OSError):
        pass


def _send_error(message: str):
    _send("error", {"message": message})


# ── Imports (after stdout redirect) ────────────────────────────────
import numpy as np
import sounddevice as sd

from .audio_capture import AudioCapture, SAMPLE_RATE
from .transcriber import TranscriptionUpdate


# ── State ──────────────────────────────────────────────────────────
_capture: AudioCapture | None = None
_transcriber = None
_telegram_sender = None
_pump_thread: threading.Thread | None = None
_energy_thread: threading.Thread | None = None
_stop_event = threading.Event()
_engine_name: str = "coreml"


def _list_devices():
    """Query sounddevice and emit a devices event."""
    devices = []
    default_idx = sd.default.device[0]
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            devices.append({
                "index": i,
                "name": dev["name"],
                "channels": dev["max_input_channels"],
                "is_default": i == default_idx,
            })
    _send("devices", devices)


def _on_update(update: TranscriptionUpdate):
    """Fan-out callback: emit transcript event + forward to Telegram."""
    _send("transcript", {
        "finalized_text": update.finalized_text,
        "draft_text": update.draft_text,
        "finalized_sentences": [
            {"text": s.text.strip(), "confidence": getattr(s, "confidence", 1.0)}
            for s in update.finalized_sentences
        ],
    })
    if _telegram_sender is not None:
        _telegram_sender.on_update(update)


def _pump_audio():
    """Pump audio chunks from capture → transcriber until stopped."""
    global _capture, _transcriber
    while not _stop_event.is_set():
        if _capture is None:
            break
        chunk = _capture.get_chunk(timeout=0.2)
        if chunk is None:
            break
        if len(chunk) > 0 and _transcriber is not None:
            _transcriber.push_audio(chunk)


def _emit_energy():
    """Emit energy events at ~10 Hz."""
    while not _stop_event.is_set():
        if _capture is not None:
            _send("energy", {"level": _capture.energy})
        time.sleep(0.1)


def _do_start(data: dict):
    """Handle the 'start' command: load model, start capture + transcriber."""
    global _capture, _transcriber, _telegram_sender, _pump_thread, _energy_thread
    global _stop_event, _engine_name

    engine = data.get("engine", "coreml")
    device = data.get("device")  # int or None
    buffer_seconds = data.get("buffer", 5.0)
    telegram_cfg = data.get("telegram")  # {bot_token, chat_id} or None

    _engine_name = engine
    _stop_event.clear()

    # Telegram setup
    if telegram_cfg:
        bot_token = telegram_cfg.get("bot_token", "")
        chat_id = telegram_cfg.get("chat_id", "")
        if bot_token and chat_id:
            from .telegram_sender import TelegramSender
            _telegram_sender = TelegramSender(bot_token, chat_id)

    # Load model
    _send("status", "loading_model")
    try:
        if engine == "coreml":
            from .coreml_transcriber import CoreMLTranscriber, load_coreml_models
            models, vocab, load_time = load_coreml_models()
            _transcriber = CoreMLTranscriber(
                models, vocab,
                on_update=_on_update,
                buffer_seconds=buffer_seconds,
            )
        else:
            from .transcriber import StreamingTranscriber, load_model
            model, load_time = load_model()
            _transcriber = StreamingTranscriber(
                model,
                on_update=_on_update,
                feed_interval=data.get("feed_interval", 0.4),
            )
    except Exception as exc:
        _send_error(f"Failed to load model: {exc}")
        traceback.print_exc(file=sys.stderr)
        return

    # Audio capture
    try:
        _capture = AudioCapture(device=device)
        _capture.start()
    except Exception as exc:
        _send_error(f"Failed to start audio capture: {exc}")
        traceback.print_exc(file=sys.stderr)
        return

    # Start transcriber
    _transcriber.start()

    # Pump and energy threads
    _pump_thread = threading.Thread(target=_pump_audio, daemon=True, name="audio-pump")
    _pump_thread.start()

    _energy_thread = threading.Thread(target=_emit_energy, daemon=True, name="energy-emitter")
    _energy_thread.start()

    _send("status", "listening")


def _do_stop():
    """Handle the 'stop' command: shut down capture + transcriber + telegram."""
    global _capture, _transcriber, _telegram_sender, _pump_thread, _energy_thread

    _stop_event.set()

    if _capture is not None:
        _capture.stop()
        _capture = None

    if _transcriber is not None:
        _transcriber.stop()
        _transcriber.wait(timeout=5.0)
        _transcriber = None

    if _telegram_sender is not None:
        _telegram_sender.stop()
        _telegram_sender.wait(timeout=5.0)
        _telegram_sender = None

    if _pump_thread is not None:
        _pump_thread.join(timeout=2.0)
        _pump_thread = None

    if _energy_thread is not None:
        _energy_thread.join(timeout=2.0)
        _energy_thread = None

    _send("status", "idle")


def _do_set_device(data: dict):
    """Handle 'set_device' — hot-swap audio input without full restart."""
    global _capture
    device = data.get("device")
    if device is None:
        _send_error("set_device requires a 'device' field")
        return
    if _capture is not None:
        _capture.stop()
        _capture = AudioCapture(device=device)
        _capture.start()
        _send("status", "listening")
    else:
        _send_error("Cannot set device: not running")


# ── Main loop ──────────────────────────────────────────────────────

def main():
    # Graceful shutdown on SIGTERM
    def _sigterm(sig, frame):
        _do_stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)

    _send("status", "idle")

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                _send_error(f"Invalid JSON: {exc}")
                continue

            cmd = msg.get("cmd", "")
            data = msg.get("data", {})

            try:
                if cmd == "list_devices":
                    _list_devices()
                elif cmd == "start":
                    _do_start(data)
                elif cmd == "stop":
                    _do_stop()
                elif cmd == "set_device":
                    _do_set_device(data)
                else:
                    _send_error(f"Unknown command: {cmd}")
            except Exception as exc:
                _send_error(str(exc))
                traceback.print_exc(file=sys.stderr)

    except (EOFError, BrokenPipeError):
        pass
    finally:
        _do_stop()


if __name__ == "__main__":
    main()
