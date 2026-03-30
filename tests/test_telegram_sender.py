"""Tests for TelegramSender per-utterance model (D-03).

Per-utterance semantics: one Telegram message per utterance, using update.text
directly. No _processed_chars tracking, no draft/streaming logic.
"""

from __future__ import annotations

import inspect
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src import config
from src.transcriber import TranscriptionUpdate
from src.telegram_sender import TelegramSender


def _make_sender(bot_token: str = "fake-token", chat_id: str = "12345") -> TelegramSender:
    """Build a TelegramSender with a mocked httpx.Client."""
    return TelegramSender(bot_token, chat_id)


def _drain(sender: TelegramSender, mock_client: MagicMock, timeout: float = 1.0) -> list[str]:
    """Stop the sender and collect what was sent via the mock client."""
    sender.stop()
    sender.wait(timeout=timeout)
    calls = mock_client.post.call_args_list
    sent = []
    for call in calls:
        kwargs = call.kwargs or {}
        args = call.args
        # json= kwarg or second positional
        json_body = kwargs.get("json") or (args[1] if len(args) > 1 else None)
        if json_body and "text" in json_body:
            sent.append(json_body["text"])
    return sent


class TestPerUtteranceSend:
    """test_per_utterance_send: on_update enqueues update.text for sending."""

    def test_per_utterance_send(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client_instance):
            sender = _make_sender()
            sender.on_update(TranscriptionUpdate(text="Hello world."))
            sent = _drain(sender, mock_client_instance)

        assert sent == ["Hello world."], f"Expected ['Hello world.'], got {sent}"

    def test_empty_text_not_sent(self):
        """TranscriptionUpdate with text='' must not enqueue anything."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client_instance):
            sender = _make_sender()
            sender.on_update(TranscriptionUpdate(text=""))
            sent = _drain(sender, mock_client_instance)

        assert sent == [], f"Expected no messages sent, got {sent}"

    def test_whitespace_only_not_sent(self):
        """TranscriptionUpdate with text='   ' must not enqueue anything."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client_instance):
            sender = _make_sender()
            sender.on_update(TranscriptionUpdate(text="   "))
            sent = _drain(sender, mock_client_instance)

        assert sent == [], f"Expected no messages sent, got {sent}"

    def test_stop_flushes_nothing_extra(self):
        """After on_update(text='Hi.') + stop(), only 'Hi.' is sent — no leftover draft."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client_instance):
            sender = _make_sender()
            sender.on_update(TranscriptionUpdate(text="Hi."))
            sent = _drain(sender, mock_client_instance)

        assert sent == ["Hi."], f"Expected exactly ['Hi.'], got {sent}"
        # Exactly one post call (no draft or extra messages)
        assert mock_client_instance.post.call_count == 1, (
            f"Expected 1 post call, got {mock_client_instance.post.call_count}"
        )

    def test_multiple_utterances_sent_independently(self):
        """Multiple on_update calls produce one message each."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client_instance):
            sender = _make_sender()
            sender.on_update(TranscriptionUpdate(text="First utterance."))
            sender.on_update(TranscriptionUpdate(text="Second utterance."))
            sender.on_update(TranscriptionUpdate(text="Third utterance."))
            sent = _drain(sender, mock_client_instance)

        assert sent == [
            "First utterance.",
            "Second utterance.",
            "Third utterance.",
        ], f"Unexpected sent messages: {sent}"

    def test_text_is_stripped(self):
        """update.text is stripped before sending (no leading/trailing whitespace in message)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client_instance):
            sender = _make_sender()
            sender.on_update(TranscriptionUpdate(text="  hello there  "))
            sent = _drain(sender, mock_client_instance)

        assert sent == ["hello there"], f"Expected ['hello there'], got {sent}"

    def test_queue_type_annotation_is_str(self):
        """TelegramSender._queue holds str items (not TranscriptionUpdate)."""
        with patch("src.telegram_sender.httpx.Client"):
            sender = _make_sender()

        # The queue should be Queue[str | None], not Queue[TranscriptionUpdate | ...]
        # We verify by checking that on_update puts a str into the queue
        sender.on_update(TranscriptionUpdate(text="test"))
        try:
            item = sender._queue.get(timeout=0.5)
            assert isinstance(item, str), f"Expected str item in queue, got {type(item)}: {item!r}"
        finally:
            sender.stop()
            sender.wait(timeout=1.0)


class TestHardening:
    """Hardening tests: 429 handling, shutdown drain, timeout, no stream param."""

    def test_429_respects_retry_after(self):
        """429 response with retry_after sleeps exactly retry_after seconds (D-06)."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.json.return_value = {
            "ok": False,
            "error_code": 429,
            "parameters": {"retry_after": 1},
        }

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}

        mock_client = MagicMock()
        mock_client.post.side_effect = [resp_429, resp_200]

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client):
            with patch("src.telegram_sender.time.sleep") as mock_sleep:
                sender = _make_sender()
                sender.on_update(TranscriptionUpdate(text="Hi"))
                sender.stop()
                sender.wait(timeout=15)

        assert mock_client.post.call_count == 2, (
            f"Expected 2 post calls (retry succeeded), got {mock_client.post.call_count}"
        )
        mock_sleep.assert_called_with(1)

    def test_429_falls_back_to_backoff(self):
        """429 response without parameters field falls back to exponential backoff (D-06)."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.json.return_value = {"ok": False, "error_code": 429}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}

        mock_client = MagicMock()
        mock_client.post.side_effect = [resp_429, resp_200]

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client):
            with patch("src.telegram_sender.time.sleep") as mock_sleep:
                sender = _make_sender()
                sender.on_update(TranscriptionUpdate(text="Hi"))
                sender.stop()
                sender.wait(timeout=15)

        expected_sleep = config.TELEGRAM_BACKOFF_BASE * (2 ** 0)
        mock_sleep.assert_called_with(expected_sleep)

    def test_max_retries_drops_message(self):
        """After max retries all fail, message is dropped and pipeline continues (D-07)."""
        resp_500 = MagicMock()
        resp_500.status_code = 500
        resp_500.text = "Internal Server Error"

        mock_client = MagicMock()
        mock_client.post.return_value = resp_500

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client):
            with patch("src.telegram_sender.time.sleep"):
                sender = _make_sender()
                sender.on_update(TranscriptionUpdate(text="fail"))
                sender.stop()
                sender.wait(timeout=10)

        assert mock_client.post.call_count == config.TELEGRAM_MAX_RETRIES, (
            f"Expected {config.TELEGRAM_MAX_RETRIES} post calls, got {mock_client.post.call_count}"
        )

    def test_shutdown_drains_queue(self):
        """stop() + wait(10s) sends all queued messages before exiting (INTG-02, D-04)."""
        send_times = []

        def slow_post(*args, **kwargs):
            time.sleep(0.3)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"ok": True}
            return resp

        mock_client = MagicMock()
        mock_client.post.side_effect = slow_post

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client):
            sender = _make_sender()
            sender.on_update(TranscriptionUpdate(text="msg1"))
            sender.on_update(TranscriptionUpdate(text="msg2"))
            sender.on_update(TranscriptionUpdate(text="msg3"))
            sender.stop()
            sender.wait(timeout=10.0)

        assert mock_client.post.call_count == 3, (
            f"Expected 3 post calls (all messages drained), got {mock_client.post.call_count}"
        )

    def test_wait_default_timeout_is_10(self):
        """TelegramSender.wait() default timeout must be 10.0 seconds (INTG-02, D-05)."""
        sig = inspect.signature(TelegramSender.wait)
        timeout_param = sig.parameters.get("timeout")
        assert timeout_param is not None, "wait() must have a 'timeout' parameter"
        assert timeout_param.default == 10.0, (
            f"Expected wait() default timeout=10.0, got {timeout_param.default}"
        )

    def test_no_stream_param(self):
        """TelegramSender.__init__ must not accept a 'stream' parameter (D-02)."""
        sig = inspect.signature(TelegramSender.__init__)
        assert "stream" not in sig.parameters, (
            f"TelegramSender.__init__ must not have 'stream' parameter, found: {list(sig.parameters)}"
        )

    def test_non_retryable_error_not_retried(self):
        """HTTP 401 should not be retried — only 1 request made."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client):
            with patch("src.telegram_sender.time.sleep"):
                sender = _make_sender()
                sender.on_update(TranscriptionUpdate(text="test"))
                sender.stop()
                sender.wait(timeout=5)

        assert mock_client.post.call_count == 1, (
            f"Expected 1 post call (no retries for 401), got {mock_client.post.call_count}"
        )

    def test_long_message_truncated(self):
        """Messages > 4096 chars are truncated with ellipsis."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("src.telegram_sender.httpx.Client", return_value=mock_client):
            sender = _make_sender()
            sender.on_update(TranscriptionUpdate(text="a" * 5000))
            sent = _drain(sender, mock_client)

        assert len(sent) == 1, f"Expected 1 message, got {len(sent)}"
        assert len(sent[0]) == 4096, f"Expected 4096 chars, got {len(sent[0])}"
        assert sent[0].endswith("..."), "Truncated message should end with '...'"
