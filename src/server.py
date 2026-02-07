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
import logging
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

# ── Logging setup (to stderr) ──────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("esper.server")


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
    log.error("Sending error event: %s", message)
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

_MODEL_LOAD_TIMEOUT = 30  # seconds


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
    log.info("Listed %d input devices", len(devices))
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
        try:
            chunk = _capture.get_chunk(timeout=0.2)
        except Exception as exc:
            log.error("Audio pump error: %s", exc, exc_info=True)
            _send_error(f"Audio stream error: {exc}")
            break
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


def _load_model_with_timeout(engine: str, data: dict):
    """Load the STT model in a thread with a timeout. Returns (transcriber, load_time) or raises."""
    result = [None]
    error = [None]

    def _load():
        try:
            if engine == "coreml":
                from .coreml_transcriber import CoreMLTranscriber, load_coreml_models
                models, vocab, load_time = load_coreml_models()
                result[0] = CoreMLTranscriber(
                    models, vocab,
                    on_update=_on_update,
                    buffer_seconds=data.get("buffer", 5.0),
                )
            else:
                from .transcriber import StreamingTranscriber, load_model
                model, load_time = load_model()
                result[0] = StreamingTranscriber(
                    model,
                    on_update=_on_update,
                    feed_interval=data.get("feed_interval", 0.4),
                )
            log.info("Model loaded in %.2fs (%s engine)", load_time, engine)
        except Exception as exc:
            error[0] = exc

    thread = threading.Thread(target=_load, name="model-loader")
    thread.start()
    thread.join(timeout=_MODEL_LOAD_TIMEOUT)

    if thread.is_alive():
        raise TimeoutError(f"Model loading timed out after {_MODEL_LOAD_TIMEOUT}s")
    if error[0] is not None:
        raise error[0]
    return result[0]


def _do_start(data: dict):
    """Handle the 'start' command: load model, start capture + transcriber."""
    global _capture, _transcriber, _telegram_sender, _pump_thread, _energy_thread
    global _stop_event, _engine_name

    engine = data.get("engine", "coreml")
    device = data.get("device")  # int or None
    telegram_cfg = data.get("telegram")  # {bot_token, chat_id} or None

    _engine_name = engine
    _stop_event.clear()
    log.info("Starting: engine=%s, device=%s", engine, device)

    # Telegram setup
    if telegram_cfg:
        bot_token = telegram_cfg.get("bot_token", "")
        chat_id = telegram_cfg.get("chat_id", "")
        if bot_token and chat_id:
            from .telegram_sender import TelegramSender
            _telegram_sender = TelegramSender(bot_token, chat_id)
            log.info("Telegram sender configured")

    # Load model
    _send("status", "loading_model")
    try:
        _transcriber = _load_model_with_timeout(engine, data)
    except Exception as exc:
        _send_error(f"Failed to load model: {exc}")
        log.error("Model load failed", exc_info=True)
        # Clean up telegram if we started it
        if _telegram_sender is not None:
            _telegram_sender.stop()
            _telegram_sender = None
        return

    # Audio capture
    try:
        _capture = AudioCapture(device=device)
        _capture.start()
        log.info("Audio capture started (device=%s)", device)
    except Exception as exc:
        _send_error(f"Failed to start audio capture: {exc}")
        log.error("Audio capture failed", exc_info=True)
        # Clean up model + telegram
        if _transcriber is not None:
            _transcriber.stop()
            _transcriber.wait(timeout=5.0)
            _transcriber = None
        if _telegram_sender is not None:
            _telegram_sender.stop()
            _telegram_sender = None
        return

    # Start transcriber
    _transcriber.start()

    # Pump and energy threads
    _pump_thread = threading.Thread(target=_pump_audio, daemon=True, name="audio-pump")
    _pump_thread.start()

    _energy_thread = threading.Thread(target=_emit_energy, daemon=True, name="energy-emitter")
    _energy_thread.start()

    _send("status", "listening")
    log.info("Now listening")


def _do_stop():
    """Handle the 'stop' command: shut down capture + transcriber + telegram."""
    global _capture, _transcriber, _telegram_sender, _pump_thread, _energy_thread

    log.info("Stopping")
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
    log.info("Stopped")


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
        log.info("Switched audio device to %s", device)
        _send("status", "listening")
    else:
        _send_error("Cannot set device: not running")


def _do_test_telegram(data: dict):
    """Handle 'test_telegram' — send a test message and report result."""
    bot_token = data.get("bot_token", "")
    chat_id = data.get("chat_id", "")

    if not bot_token or not chat_id:
        _send("telegram_test", {"success": False, "error": "Bot token and chat ID are required"})
        return

    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json={"chat_id": chat_id, "text": "Esper connected"})
            if resp.status_code == 200:
                log.info("Telegram test message sent successfully")
                _send("telegram_test", {"success": True})
            else:
                error_msg = resp.json().get("description", resp.text[:200])
                log.warning("Telegram test failed: %s", error_msg)
                _send("telegram_test", {"success": False, "error": error_msg})
    except Exception as exc:
        log.error("Telegram test error: %s", exc)
        _send("telegram_test", {"success": False, "error": str(exc)})


# ── Main loop ──────────────────────────────────────────────────────

def main():
    # Graceful shutdown on SIGTERM
    def _sigterm(sig, frame):
        log.info("Received SIGTERM, shutting down")
        _do_stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)

    log.info("Esper server started")
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
            log.info("Command received: %s", cmd)

            try:
                if cmd == "list_devices":
                    _list_devices()
                elif cmd == "start":
                    _do_start(data)
                elif cmd == "stop":
                    _do_stop()
                elif cmd == "set_device":
                    _do_set_device(data)
                elif cmd == "test_telegram":
                    _do_test_telegram(data)
                else:
                    _send_error(f"Unknown command: {cmd}")
            except Exception as exc:
                _send_error(str(exc))
                log.error("Command %s failed", cmd, exc_info=True)

    except (EOFError, BrokenPipeError):
        log.info("Stdin closed (EOF/BrokenPipe)")
    finally:
        log.info("Main loop exited, cleaning up")
        _do_stop()


if __name__ == "__main__":
    main()
