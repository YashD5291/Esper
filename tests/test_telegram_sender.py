"""Tests for TelegramSender per-utterance model (D-03).

Per-utterance semantics: one Telegram message per utterance, using update.text
directly. No _processed_chars tracking, no draft/streaming logic.
"""

from __future__ import annotations

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

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
