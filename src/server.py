#!/usr/bin/env python3
"""Esper headless JSON server — bridges Python STT to the SwiftUI app.

Communicates via newline-delimited JSON. In SwiftUI mode, pass --protocol-fd N
to write events to a dedicated file descriptor. In CLI mode (no flag), events
go to stdout.

Usage:
    python -m src.server                    # CLI mode (stdout)
    python -m src.server --protocol-fd 5    # SwiftUI mode (fd 5)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue as _queue
import signal
import sys
import threading
import time
from typing import TextIO

import sounddevice as sd

from . import config
from .audio_capture import AudioCapture
from .transcriber import TranscriptionUpdate, WhisperTranscriber
from .vad import VadThread


def _parse_protocol_fd() -> int | None:
    """Parse --protocol-fd from argv, returning the int fd or None."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--protocol-fd", type=int, default=None)
    args, _ = parser.parse_known_args()
    return args.protocol_fd


_protocol_fd = _parse_protocol_fd()

_proto_out: TextIO

if _protocol_fd is not None:
    try:
        _proto_out = os.fdopen(_protocol_fd, "w", buffering=1)
    except OSError as exc:
        sys.stderr.write(f"FATAL: --protocol-fd {_protocol_fd} not accessible: {exc}\n")
        sys.exit(1)
else:
    _proto_out = sys.stdout

# ── Logging setup (to stderr) ──────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("esper.server")


_write_lock = threading.Lock()


def _send(event: str, payload=None):
    """Write one JSON event to the protocol stream.

    Thread-safe: multiple threads (_whisper_consumer, _emit_energy, main)
    may call _send concurrently. The lock ensures complete JSON lines.
    """
    obj = {"event": event}
    if payload is not None:
        obj["data"] = payload
    try:
        with _write_lock:
            _proto_out.write(json.dumps(obj) + "\n")
            _proto_out.flush()
    except (BrokenPipeError, OSError):
        pass


def _send_error(message: str):
    log.error("Sending error event: %s", message)
    _send("error", {"message": message})


# ── State ──────────────────────────────────────────────────────────
_capture: AudioCapture | None = None
_transcriber = None
_telegram_sender = None
_vad_thread: VadThread | None = None
_speech_q: _queue.Queue | None = None
_bridge_thread: threading.Thread | None = None
_energy_thread: threading.Thread | None = None
_stop_event = threading.Event()


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
        "text": update.text,
        "finalized_text": update.finalized_text,
        "sentences": update.sentences,
        "no_speech_prob": update.no_speech_prob,
        "duration_s": update.duration_s,
    })
    if _telegram_sender is not None:
        _telegram_sender.on_update(update)


def _on_status(status_str: str):
    """Forward WhisperTranscriber status events to protocol stream."""
    _send("status", status_str)


def _whisper_consumer():
    """Read utterances from speech_q and transcribe via WhisperTranscriber."""
    log.info("Whisper consumer thread started")
    while not _stop_event.is_set():
        try:
            utterance = _speech_q.get(timeout=0.2)
        except _queue.Empty:
            continue
        if utterance is None:
            log.info("Whisper consumer: got None sentinel, exiting")
            break
        if _transcriber is None or _transcriber.stopped:
            log.info("Whisper consumer: transcriber gone/stopped, exiting")
            break
        duration = len(utterance) / config.SAMPLE_RATE
        log.info("Whisper consumer: got utterance %.2fs (%d samples)", duration, len(utterance))
        _send("status", "transcribing")  # D-02: processing indicator
        _transcriber.transcribe_utterance(utterance)  # on_update callback fires inside
        if not _transcriber.stopped:
            _send("status", "listening")  # D-02: back to listening


def _emit_energy():
    """Emit energy events at ~10 Hz."""
    while not _stop_event.is_set():
        if _capture is not None:
            _send("energy", {"level": _capture.energy})
        time.sleep(config.ENERGY_EMIT_INTERVAL_S)


def _do_start(data: dict):
    """Handle the 'start' command: spawn WhisperTranscriber, start capture + VAD."""
    global _capture, _transcriber, _telegram_sender, _vad_thread, _speech_q, _bridge_thread
    global _energy_thread, _stop_event

    device = data.get("device")
    telegram_cfg = data.get("telegram")

    _stop_event.clear()
    log.info("Starting: device=%s", device)

    # Telegram setup (unchanged)
    if telegram_cfg:
        bot_token = telegram_cfg.get("bot_token", "")
        chat_id = telegram_cfg.get("chat_id", "")
        if bot_token and chat_id:
            from .telegram_sender import TelegramSender
            config.TELEGRAM_BOT_TOKEN = bot_token
            config.TELEGRAM_CHAT_ID = chat_id
            _telegram_sender = TelegramSender(bot_token, chat_id)
            log.info("Telegram sender configured")

    # Create WhisperTranscriber — subprocess handles model loading and ready signaling
    try:
        _transcriber = WhisperTranscriber(on_update=_on_update, on_status=_on_status)
        _transcriber.start()  # spawns subprocess, emits status events, waits for ready
    except Exception as exc:
        _send_error(f"Failed to start Whisper: {exc}")
        log.error("Whisper start failed", exc_info=True)
        if _telegram_sender is not None:
            _telegram_sender.stop()
            _telegram_sender = None
        return

    # Audio capture (unchanged)
    try:
        _capture = AudioCapture(device=device)
        _capture.start()
        log.info("Audio capture started (device=%s)", device)
    except Exception as exc:
        _send_error(f"Failed to start audio capture: {exc}")
        log.error("Audio capture failed", exc_info=True)
        if _transcriber is not None:
            _transcriber.stop()
            _transcriber.wait(timeout=5.0)
            _transcriber = None
        if _telegram_sender is not None:
            _telegram_sender.stop()
            _telegram_sender = None
        return

    # VAD + whisper consumer (replaces _bridge_speech_q)
    _speech_q = _queue.Queue(maxsize=10)
    _vad_thread = VadThread(audio_q=_capture._queue, speech_q=_speech_q)
    _vad_thread.start()

    _bridge_thread = threading.Thread(target=_whisper_consumer, daemon=True, name="whisper-consumer")
    _bridge_thread.start()

    _energy_thread = threading.Thread(target=_emit_energy, daemon=True, name="energy-emitter")
    _energy_thread.start()

    _send("status", "listening")
    log.info("Now listening")


def _do_stop():
    """Handle the 'stop' command: shut down capture + transcriber + telegram."""
    global _capture, _transcriber, _telegram_sender, _vad_thread, _speech_q
    global _bridge_thread, _energy_thread

    log.info("Stopping")
    _stop_event.set()

    if _capture is not None:
        _capture.stop()
        _capture = None

    if _vad_thread is not None:
        _vad_thread.stop()
        _vad_thread.wait(timeout=5.0)
        _vad_thread = None

    if _transcriber is not None:
        _transcriber.stop()
        _transcriber.wait(timeout=5.0)
        _transcriber = None

    if _telegram_sender is not None:
        _telegram_sender.stop()
        _telegram_sender.wait(timeout=10.0)
        _telegram_sender = None

    if _bridge_thread is not None:
        _bridge_thread.join(timeout=2.0)
        _bridge_thread = None

    if _energy_thread is not None:
        _energy_thread.join(timeout=2.0)
        _energy_thread = None

    _speech_q = None

    _send("status", "idle")
    log.info("Stopped")


def _do_set_device(data: dict):
    """Handle 'set_device' — hot-swap audio input without full restart."""
    global _capture, _vad_thread
    device = data.get("device")
    if device is None:
        _send_error("set_device requires a 'device' field")
        return
    if _capture is not None:
        # Stop VAD (reads from old capture queue)
        if _vad_thread is not None:
            _vad_thread.stop()
            _vad_thread.wait(timeout=2.0)
        _capture.stop()
        _capture = AudioCapture(device=device)
        _capture.start()
        # Restart VAD with new capture queue
        if _speech_q is not None:
            _vad_thread = VadThread(audio_q=_capture._queue, speech_q=_speech_q)
            _vad_thread.start()
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
        raise SystemExit(0)

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
