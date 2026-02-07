"""Queue-based Telegram sender for Esper.

Receives TranscriptionUpdate callbacks and sends only *new* finalized
sentences to a Telegram chat via the Bot API.  Runs a background daemon
thread so that HTTP calls never block the transcriber.
"""

from __future__ import annotations

import logging
import queue
import threading
import time

import httpx

from .transcriber import TranscriptionUpdate

log = logging.getLogger(__name__)

# Retry config
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds; doubles each retry


class TelegramSender:
    """Enqueue new sentences and POST them to Telegram in the background."""

    def __init__(self, bot_token: str, chat_id: str):
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._send_queue: queue.Queue[str | None] = queue.Queue()
        self._prev_sentence_count = 0
        self._thread = threading.Thread(
            target=self._sender_loop, daemon=True, name="telegram-sender"
        )
        self._thread.start()

    # -- callback wired into the transcriber --

    def on_update(self, update: TranscriptionUpdate):
        """Fast callback — just enqueues new sentences."""
        sentences = update.finalized_sentences
        new = sentences[self._prev_sentence_count:]
        self._prev_sentence_count = len(sentences)
        for s in new:
            text = s.text.strip() if hasattr(s, "text") else ""
            if text:
                self._send_queue.put(text)

    # -- background sender --

    def _sender_loop(self):
        client = httpx.Client(timeout=10.0)
        try:
            while True:
                msg = self._send_queue.get()
                if msg is None:
                    break  # shutdown sentinel
                self._send_with_retry(client, msg)
        finally:
            client.close()

    def _send_with_retry(self, client: httpx.Client, text: str):
        for attempt in range(_MAX_RETRIES):
            try:
                resp = client.post(
                    self._url,
                    json={"chat_id": self._chat_id, "text": text},
                )
                if resp.status_code == 200:
                    log.debug("Sent: %s", text[:40])
                    return
                log.warning(
                    "Telegram API %d: %s", resp.status_code, resp.text[:200]
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                log.warning("Telegram send error (attempt %d): %s", attempt + 1, exc)
            backoff = _BACKOFF_BASE * (2 ** attempt)
            time.sleep(backoff)
        log.error("Failed to send after %d attempts: %s", _MAX_RETRIES, text[:60])

    # -- lifecycle --

    def stop(self):
        """Signal the background thread to drain and exit."""
        self._send_queue.put(None)

    def wait(self, timeout: float = 5.0):
        self._thread.join(timeout=timeout)
