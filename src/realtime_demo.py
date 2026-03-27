#!/usr/bin/env python3
"""Esper: Real-time transcription via Whisper + Silero VAD.

Captures microphone audio, gates on speech with Silero VAD, and transcribes
each utterance with Whisper large-v3-turbo via mlx-whisper.

Usage:
    python -m src.realtime_demo
    python -m src.realtime_demo --telegram
    python -m src.realtime_demo --device 0
    python -m src.realtime_demo --list-devices
    python -m src.realtime_demo --record
"""

import argparse
import os
import queue as _queue
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from . import config
from .audio_capture import AudioCapture, list_devices
from .transcriber import TranscriptionUpdate, WhisperTranscriber
from .vad import VadThread

# ANSI helpers
GRAY = "\033[90m"
WHITE = "\033[97m"
RESET = "\033[0m"
CLEAR_LINE = "\033[2K"


class ConsoleRenderer:
    """Renders per-utterance transcription to the terminal."""

    def __init__(self, *, show_sent: bool = False):
        self._lock = threading.Lock()
        self._show_sent = show_sent

    def on_update(self, update: TranscriptionUpdate):
        with self._lock:
            self._render(update)

    def _render(self, update: TranscriptionUpdate):
        text = update.text.strip()
        if not text:
            return
        sent_tag = f"  {GRAY}[sent]{RESET}" if self._show_sent else ""
        sys.stdout.write(f"{CLEAR_LINE}  {WHITE}{text}{RESET}{sent_tag}\n")
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Esper — Real-Time Transcription")
    parser.add_argument("--device", type=int, default=None, help="Audio input device index")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    parser.add_argument("--record", nargs="?", const="auto", default=None, metavar="PATH",
                        help="Record utterance audio (speech-only) to WAV file (auto-generates name if no path given)")
    parser.add_argument("--telegram", action="store_true",
                        help="Send transcriptions to Telegram (requires .env with bot token)")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        sys.exit(0)

    # -- Telegram setup --
    telegram_sender = None
    if args.telegram:
        from dotenv import load_dotenv
        load_dotenv()
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id or "your-" in bot_token:
            print("Error: --telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
            sys.exit(1)
        from .telegram_sender import TelegramSender
        telegram_sender = TelegramSender(bot_token, chat_id)

    # -- recording setup --
    record_chunks: list[np.ndarray] = []
    record_path = None
    if args.record is not None:
        if args.record == "auto":
            rec_dir = Path("recordings")
            rec_dir.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            record_path = rec_dir / f"session_{stamp}.wav"
        else:
            record_path = Path(args.record)
            record_path.parent.mkdir(parents=True, exist_ok=True)

    # -- banner --
    mode = "WHISPER"
    if args.telegram:
        mode += "+TG"
    print()
    print("=" * 54)
    print(f"  ESPER — Real-Time Transcription  [{mode}]")
    if record_path:
        print(f"  Recording to: {record_path}  (speech-only)")

    # -- build callback (fan-out if Telegram is enabled) --
    renderer = ConsoleRenderer(show_sent=args.telegram)

    def on_update(update: TranscriptionUpdate):
        renderer.on_update(update)
        if telegram_sender is not None:
            telegram_sender.on_update(update)

    # -- status display --
    def _cli_status(status_str: str):
        if status_str == "downloading_model":
            sys.stdout.write("\r  Downloading model... ")
        elif status_str in ("loading_model", "compiling_shaders"):
            sys.stdout.write(f"\r  {status_str.replace('_', ' ').title()}... ")
        sys.stdout.flush()

    # -- load model --
    sys.stdout.write("  Loading model... ")
    sys.stdout.flush()

    transcriber = WhisperTranscriber(on_update=on_update, on_status=_cli_status)
    transcriber.start()
    print("done")

    # -- audio capture --
    capture = AudioCapture(device=args.device)
    capture.start()

    # -- VAD + consumer thread --
    stop_event = threading.Event()
    speech_q = _queue.Queue(maxsize=10)
    vad = VadThread(audio_q=capture._queue, speech_q=speech_q)
    vad.start()

    def _consumer():
        while not stop_event.is_set():
            try:
                utterance = speech_q.get(timeout=0.2)
            except _queue.Empty:
                continue
            if utterance is None:
                break
            if record_path is not None:
                record_chunks.append(utterance.copy())
            if transcriber.stopped:
                break
            transcriber.transcribe_utterance(utterance)

    consumer_thread = threading.Thread(target=_consumer, daemon=True, name="cli-consumer")
    consumer_thread.start()

    print()
    print("  Listening. Press Ctrl+C to stop.")
    print("=" * 54)
    print()

    # -- main thread waits for Ctrl+C --
    def sigint_handler(sig, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, sigint_handler)

    try:
        while not stop_event.is_set():
            stop_event.wait(0.5)
    except KeyboardInterrupt:
        pass

    # -- shutdown --
    print(f"\n\n{GRAY}  Shutting down...{RESET}")
    capture.stop()
    vad.stop()
    vad.wait(timeout=5.0)
    transcriber.stop()
    transcriber.wait(timeout=5.0)
    if telegram_sender is not None:
        telegram_sender.stop()
        telegram_sender.wait(timeout=5.0)

    if record_path is not None and record_chunks:
        audio = np.concatenate(record_chunks)
        sf.write(str(record_path), audio, config.SAMPLE_RATE)
        duration = len(audio) / config.SAMPLE_RATE
        print(f"{GRAY}  Saved {duration:.1f}s of speech audio to {record_path}{RESET}")

    print(f"{GRAY}  Done.{RESET}\n")


if __name__ == "__main__":
    main()
