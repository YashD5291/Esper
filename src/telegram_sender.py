"""Per-utterance Telegram sender for Esper.

Sends one Telegram message per utterance using update.text directly (D-03).
The streaming/draft model is replaced by a simple queue of utterance strings.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

import httpx

from . import config
from .transcriber import TranscriptionUpdate

log = logging.getLogger(__name__)


class TelegramSender:
    """Send one Telegram message per utterance (D-03).

    Per the Phase 4 contract, on_update receives a TranscriptionUpdate where
    update.text contains the complete utterance transcript. Each non-empty
    utterance is sent as a separate Telegram message.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        on_sent: Callable[[str, int], None] | None = None,
        on_failed: Callable[[str, str], None] | None = None,
    ) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._chat_id = chat_id
        self._on_sent = on_sent
        self._on_failed = on_failed
        self._queue: queue.Queue[tuple[str, int] | None] = queue.Queue(maxsize=100)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telegram-sender")
        self._thread.start()

    # -- callback wired into the transcriber --

    def on_update(self, update: TranscriptionUpdate):
        """Enqueue utterance text for sending. One message per utterance (D-03)."""
        text = update.text.strip()
        if text:
            sentence_index = len(update.sentences) - 1 if update.sentences else 0
            try:
                self._queue.put_nowait((text, sentence_index))
            except queue.Full:
                log.warning("Telegram queue full — dropping message: %s", text[:60])

    # -- background sender --

    def _loop(self):
        client = httpx.Client(timeout=10.0)
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                text, sentence_index = item
                self._send_message(client, text, sentence_index)
        finally:
            client.close()

    def _send_message(self, client: httpx.Client, text: str, sentence_index: int = 0):
        if len(text) > 4096:
            log.warning("Truncating message from %d to 4096 chars", len(text))
            text = text[:4093] + "..."
        for attempt in range(config.TELEGRAM_MAX_RETRIES):
            try:
                resp = client.post(
                    f"{self._base_url}/sendMessage",
                    json={"chat_id": self._chat_id, "text": text},
                )
                if resp.status_code == 200:
                    try:
                        body = resp.json()
                        if body.get("ok"):
                            log.debug("Sent: %s", text[:40])
                            if self._on_sent:
                                self._on_sent(text, sentence_index)
                            return
                        log.warning("Telegram API returned ok=false: %s", body.get("description", "unknown"))
                    except (ValueError, KeyError):
                        log.debug("Sent (no body check): %s", text[:40])
                        if self._on_sent:
                            self._on_sent(text, sentence_index)
                        return
                if resp.status_code == 429:
                    try:
                        body = resp.json()
                        retry_after = body.get("parameters", {}).get("retry_after")
                    except (ValueError, KeyError):
                        retry_after = None
                    wait_time = retry_after or config.TELEGRAM_BACKOFF_BASE * (2 ** attempt)
                    log.warning(
                        "Telegram 429: retry after %ss (attempt %d)",
                        wait_time, attempt + 1,
                    )
                    time.sleep(wait_time)
                    continue
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    log.error(
                        "Telegram API %d (non-retryable): %s",
                        resp.status_code, resp.text[:200]
                    )
                    if self._on_failed:
                        self._on_failed(text, f"HTTP {resp.status_code}: {resp.text[:200]}")
                    return  # Don't retry 4xx errors
                log.warning(
                    "Telegram API %d: %s", resp.status_code, resp.text[:200]
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                log.warning(
                    "Telegram send error (attempt %d): %s", attempt + 1, exc
                )
            time.sleep(config.TELEGRAM_BACKOFF_BASE * (2**attempt))
        log.error("Failed to send after %d attempts: %s", config.TELEGRAM_MAX_RETRIES, text[:60])
        if self._on_failed:
            self._on_failed(text, f"Failed after {config.TELEGRAM_MAX_RETRIES} retries")

    # -- lifecycle --

    def stop(self):
        """Signal the background thread to drain and exit."""
        self._queue.put(None)

    def wait(self, timeout: float = 10.0) -> None:
        self._thread.join(timeout=timeout)
