#!/usr/bin/env python3
"""Esper: Real-time streaming transcription demo.

Supports two inference backends:
  - coreml (default): Runs on Apple Neural Engine via CoreML
  - mlx: Runs on GPU via Metal/MLX

Usage:
    python -m src.realtime_demo
    python -m src.realtime_demo --engine mlx
    python -m src.realtime_demo --telegram
    python -m src.realtime_demo --device 0
    python -m src.realtime_demo --list-devices
"""

import argparse
import os
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from . import config
from .audio_capture import AudioCapture, list_devices
from .transcriber import TranscriptionUpdate

# ANSI helpers
GRAY = "\033[90m"
WHITE = "\033[97m"
RESET = "\033[0m"
CLEAR_LINE = "\033[2K"
MOVE_UP = "\033[A"


class ConsoleRenderer:
    """Renders finalized + draft transcription to the terminal."""

    def __init__(self, *, show_sent: bool = False):
        self._lock = threading.Lock()
        self._prev_finalized_count = 0
        self._prev_draft_lines = 0
        self._show_sent = show_sent

    def on_update(self, update: TranscriptionUpdate):
        with self._lock:
            self._render(update)

    def _render(self, update: TranscriptionUpdate):
        # Erase previous draft lines
        if self._prev_draft_lines > 0:
            for _ in range(self._prev_draft_lines):
                sys.stdout.write(MOVE_UP + CLEAR_LINE + "\r")

        # Print any NEW finalized sentences (ones we haven't printed yet)
        fin = update.finalized_sentences
        new_fin = fin[self._prev_finalized_count:]
        sent_tag = f"  {GRAY}[sent]{RESET}" if self._show_sent else ""
        for s in new_fin:
            conf = f"({s.confidence:.0%})" if hasattr(s, "confidence") else ""
            sys.stdout.write(f"{CLEAR_LINE}  {WHITE}{s.text.strip()}  {GRAY}{conf}{RESET}{sent_tag}\n")
        self._prev_finalized_count = len(fin)

        # Print draft sentences (will be overwritten next cycle)
        draft_lines = 0
        for s in update.draft_sentences:
            text = s.text.strip() if hasattr(s, "text") else update.draft_text.strip()
            if text:
                sys.stdout.write(f"{CLEAR_LINE}  {GRAY}{text}{RESET}\n")
                draft_lines += 1

        # If no draft sentences but we have draft text, show it raw
        if not update.draft_sentences and update.draft_text.strip():
            sys.stdout.write(f"{CLEAR_LINE}  {GRAY}{update.draft_text.strip()}{RESET}\n")
            draft_lines = 1

        self._prev_draft_lines = draft_lines
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Esper — Real-Time Transcription")
    parser.add_argument("--device", type=int, default=None, help="Audio input device index")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    parser.add_argument("--engine", choices=["coreml", "mlx"], default="coreml", help="Inference backend (default: coreml)")
    parser.add_argument("--record", nargs="?", const="auto", default=None, metavar="PATH", help="Record audio to WAV file (auto-generates name if no path given)")
    parser.add_argument("--buffer", type=float, default=1.5, help="CoreML: seconds of audio to buffer (default: 1.5)")
    parser.add_argument("--feed-interval", type=float, default=0.4, help="MLX: seconds between model feeds (default: 0.4)")
    parser.add_argument("--context-size", type=int, nargs=2, default=[256, 256], metavar=("LEFT", "RIGHT"), help="MLX: streaming context window (default: 256 256)")
    parser.add_argument("--depth", type=int, default=1, help="MLX: encoder cache depth (default: 1)")
    parser.add_argument("--telegram", action="store_true", help="Send transcriptions to Telegram (requires .env with bot token)")
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
        config.TELEGRAM_BOT_TOKEN = bot_token
        config.TELEGRAM_CHAT_ID = chat_id
        from .telegram_sender import TelegramSender
        telegram_sender = TelegramSender(bot_token, chat_id)

    # -- banner --
    mode = args.engine.upper()
    if args.telegram:
        mode += "+TG"
    print()
    print("=" * 54)
    print(f"  ESPER — Real-Time Transcription  [{mode}]")

    # -- build callback (fan-out if Telegram is enabled) --
    renderer = ConsoleRenderer(show_sent=args.telegram)

    def on_update(update: TranscriptionUpdate):
        renderer.on_update(update)
        if telegram_sender is not None:
            telegram_sender.on_update(update)

    # -- load model --
    sys.stdout.write("  Loading model... ")
    sys.stdout.flush()

    if args.engine == "coreml":
        from .coreml_transcriber import CoreMLTranscriber, load_coreml_models

        models, vocab, load_time = load_coreml_models()
        print(f"done ({load_time:.1f}s)")

        # -- audio capture --
        capture = AudioCapture(device=args.device)
        capture.start()

        transcriber = CoreMLTranscriber(
            models,
            vocab,
            on_update=on_update,
            buffer_seconds=args.buffer,
        )
    else:
        from .transcriber import StreamingTranscriber, load_model

        model, load_time = load_model()
        print(f"done ({load_time:.1f}s)")

        # -- audio capture --
        capture = AudioCapture(device=args.device)
        capture.start()

        transcriber = StreamingTranscriber(
            model,
            on_update=on_update,
            feed_interval=args.feed_interval,
            context_size=tuple(args.context_size),
            depth=args.depth,
        )

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
        print(f"  Recording to: {record_path}")

    sys.stdout.write("  Warming up... ")
    sys.stdout.flush()
    transcriber.start()
    time.sleep(1.0)  # let warmup run
    print("done")

    print()
    print("  Listening. Press Ctrl+C to stop.")
    print("=" * 54)
    print()

    # -- pump audio from capture → transcriber --
    stop_event = threading.Event()

    def sigint_handler(sig, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, sigint_handler)

    try:
        while not stop_event.is_set():
            chunk = capture.get_chunk(timeout=0.2)
            if chunk is None:
                break  # sentinel — capture stopped
            if len(chunk) > 0:
                transcriber.push_audio(chunk)
                if record_path is not None:
                    record_chunks.append(chunk.copy())
    except KeyboardInterrupt:
        pass

    # -- shutdown --
    print(f"\n\n{GRAY}  Shutting down...{RESET}")
    capture.stop()
    transcriber.stop()
    transcriber.wait(timeout=5.0)
    if telegram_sender is not None:
        telegram_sender.stop()
        telegram_sender.wait(timeout=5.0)

    if record_path is not None and record_chunks:
        audio = np.concatenate(record_chunks)
        sf.write(str(record_path), audio, config.SAMPLE_RATE)
        duration = len(audio) / config.SAMPLE_RATE
        print(f"{GRAY}  Saved {duration:.1f}s of audio to {record_path}{RESET}")

    print(f"{GRAY}  Done.{RESET}\n")


if __name__ == "__main__":
    main()
