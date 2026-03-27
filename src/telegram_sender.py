"""Streaming Telegram sender for Esper.

Streams transcription to Telegram in real-time:
  - sendMessageDraft: live-updates partial text as it's transcribed
  - sendMessage: finalizes complete sentences as permanent messages

Set stream=False for legacy sentence-by-sentence mode (no drafts).
"""

from __future__ import annotations

import logging
import queue
import threading
import time

import httpx

from . import config
from .transcriber import TranscriptionUpdate

log = logging.getLogger(__name__)


class TelegramSender:
    """Stream transcription to Telegram via sendMessageDraft + sendMessage."""

    def __init__(self, bot_token: str, chat_id: str, *, stream: bool = True):
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._chat_id = chat_id
        self._stream = stream
        self._queue: queue.Queue[TranscriptionUpdate | str | None] = queue.Queue()

        # Streaming state
        self._processed_chars = 0
        self._draft_buf = ""
        self._draft_id = int(time.time()) & 0x7FFFFFFF or 1  # non-zero int32
        self._last_draft_t = 0.0

        # Legacy state (stream=False)
        self._prev_sentence_count = 0

        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="telegram-sender"
        )
        self._thread.start()

    # -- callback wired into the transcriber --

    def on_update(self, update: TranscriptionUpdate):
        """Fast callback — enqueues update for background processing."""
        if self._stream:
            self._queue.put(update)
        else:
            sentences = update.finalized_sentences
            new = sentences[self._prev_sentence_count :]
            self._prev_sentence_count = len(sentences)
            for s in new:
                text = s.text.strip() if hasattr(s, "text") else ""
                if text:
                    self._queue.put(text)

    # -- background sender --

    def _loop(self):
        client = httpx.Client(timeout=10.0)
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                if isinstance(item, TranscriptionUpdate):
                    self._process_streaming(client, item)
                elif isinstance(item, str):
                    self._send_message(client, item)
        finally:
            if self._stream and self._draft_buf.strip():
                self._send_message(client, self._draft_buf.strip())
            client.close()

    def _process_streaming(self, client: httpx.Client, update: TranscriptionUpdate):
        full = update.finalized_text
        new_text = full[self._processed_chars :]
        if not new_text.strip():
            return
        self._processed_chars = len(full)

        self._draft_buf += new_text

        # Scan for sentence-ending punctuation
        last_end = -1
        for i, ch in enumerate(self._draft_buf):
            if ch in ".!?":
                last_end = i

        if last_end >= 0:
            to_send = self._draft_buf[: last_end + 1].strip()
            self._draft_buf = self._draft_buf[last_end + 1 :]
            if to_send:
                self._send_message(client, to_send)
                self._draft_id = (self._draft_id + 1) | 1  # keep non-zero

        # Stream remaining draft
        draft = self._draft_buf.strip()
        if draft:
            self._send_draft(client, draft)

    def _send_draft(self, client: httpx.Client, text: str):
        now = time.monotonic()
        if now - self._last_draft_t < config.TELEGRAM_DRAFT_INTERVAL:
            return
        self._last_draft_t = now
        try:
            resp = client.post(
                f"{self._base_url}/sendMessageDraft",
                json={
                    "chat_id": self._chat_id,
                    "draft_id": self._draft_id,
                    "text": text,
                },
            )
            if resp.status_code == 200:
                log.debug("Draft: %s", text[:40])
            else:
                log.warning("Draft API %d: %s", resp.status_code, resp.text[:200])
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            log.warning("Draft send failed: %s", exc)

    def _send_message(self, client: httpx.Client, text: str):
        for attempt in range(config.TELEGRAM_MAX_RETRIES):
            try:
                resp = client.post(
                    f"{self._base_url}/sendMessage",
                    json={"chat_id": self._chat_id, "text": text},
                )
                if resp.status_code == 200:
                    log.debug("Sent: %s", text[:40])
                    return
                log.warning(
                    "Telegram API %d: %s", resp.status_code, resp.text[:200]
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                log.warning(
                    "Telegram send error (attempt %d): %s", attempt + 1, exc
                )
            time.sleep(config.TELEGRAM_BACKOFF_BASE * (2**attempt))
        log.error("Failed to send after %d attempts: %s", config.TELEGRAM_MAX_RETRIES, text[:60])

    # -- lifecycle --

    def stop(self):
        """Signal the background thread to drain and exit."""
        self._queue.put(None)

    def wait(self, timeout: float = 5.0):
        self._thread.join(timeout=timeout)
