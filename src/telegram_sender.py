"""Per-utterance Telegram sender for Esper.

Sends one Telegram message per utterance using update.text directly (D-03).
The streaming/draft model is replaced by a simple queue of utterance strings.
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
    """Send one Telegram message per utterance (D-03).

    Per the Phase 4 contract, on_update receives a TranscriptionUpdate where
    update.text contains the complete utterance transcript. Each non-empty
    utterance is sent as a separate Telegram message.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._chat_id = chat_id
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telegram-sender")
        self._thread.start()

    # -- callback wired into the transcriber --

    def on_update(self, update: TranscriptionUpdate):
        """Enqueue utterance text for sending. One message per utterance (D-03)."""
        text = update.text.strip()
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
                self._send_message(client, item)
        finally:
            client.close()

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

    def wait(self, timeout: float = 10.0) -> None:
        self._thread.join(timeout=timeout)
