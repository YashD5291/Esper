"""Integration tests for the VAD -> Whisper -> Telegram pipeline.

Verifies handoff between components: VadThread emits utterances that
TranscriptionUpdate can carry, and TelegramSender receives them via on_update.

All models mocked — no real hardware or network.
"""

import pathlib
import queue
import sys
from unittest.mock import MagicMock, patch

import numpy as np

# Ensure project root on sys.path for direct invocation
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.vad import VadThread  # noqa: E402
from src.transcriber import TranscriptionUpdate  # noqa: E402
from src.telegram_sender import TelegramSender  # noqa: E402


# -- helpers ------------------------------------------------------------------

RNG = np.random.default_rng(42)


def speech_frame() -> np.ndarray:
    """512-sample frame with RMS ~0.1 (well above energy threshold)."""
    return RNG.normal(0, 0.1, 512).astype(np.float32)


# -- Test 1: VAD -> Transcriber pipeline --------------------------------------

def test_vad_to_transcriber_pipeline():
    """VadThread emits exactly 1 utterance (float32 numpy array) from speech + silence."""
    audio_q: queue.Queue = queue.Queue()
    speech_q: queue.Queue = queue.Queue()

    # 20 speech frames + 20 silence-VAD frames + sentinel
    for _ in range(40):
        audio_q.put(speech_frame())
    audio_q.put(None)

    # Mock Silero: first 20 calls return 0.9 (speech), rest return 0.1 (silence)
    model = MagicMock()
    model.reset_states = MagicMock()
    call_count = [0]

    def side_effect(tensor, sample_rate):
        idx = call_count[0]
        call_count[0] += 1
        return 0.9 if idx < 20 else 0.1

    model.side_effect = side_effect

    with patch("src.vad.SileroVadOnnx", return_value=model):
        vad = VadThread(audio_q=audio_q, speech_q=speech_q)
        vad.start()
        vad.wait(timeout=5.0)

    assert not speech_q.empty(), "Expected VadThread to emit an utterance"
    utterance = speech_q.get_nowait()
    assert isinstance(utterance, np.ndarray), f"Expected numpy array, got {type(utterance)}"
    assert utterance.dtype == np.float32, f"Expected float32, got {utterance.dtype}"

    # Should be exactly 1 utterance
    assert speech_q.empty(), "Expected exactly 1 utterance, but speech_q has more"


# -- Test 2: TranscriptionUpdate fields --------------------------------------

def test_transcription_update_fields():
    """TranscriptionUpdate carries all expected fields with correct types."""
    update = TranscriptionUpdate(
        text="Hello world.",
        finalized_text="Hello world.",
        sentences=["Hello world."],
        no_speech_prob=0.05,
        duration_s=2.5,
    )

    assert update.text == "Hello world."
    assert update.finalized_text == "Hello world."
    assert update.sentences == ["Hello world."]
    assert isinstance(update.sentences, list)
    assert isinstance(update.no_speech_prob, float)
    assert update.no_speech_prob == 0.05
    assert isinstance(update.duration_s, float)
    assert update.duration_s == 2.5


# -- Test 3: Telegram sender receives update ---------------------------------

def test_telegram_sender_receives_update():
    """TelegramSender.on_update enqueues update.text as a string."""
    with patch("src.telegram_sender.httpx.Client"):
        sender = TelegramSender("fake-token", "12345")
        sender.stop()
        sender.wait(timeout=2.0)

    # Create a fresh queue so we can inspect without the background thread
    sender._queue = queue.Queue()
    sender.on_update(TranscriptionUpdate(text="Hello world"))

    assert not sender._queue.empty(), "Expected on_update to enqueue text"
    item = sender._queue.get_nowait()
    assert item == "Hello world", f"Expected 'Hello world', got {item!r}"
