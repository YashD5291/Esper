"""Unit tests for src/vad.py — VadThread state machine.

Covers requirements: PIPE-01 (silence/speech detection), PIPE-02 (pre/post buffer),
PIPE-03 (energy gate), D-08 (min duration discard).

All tests mock the Silero model so no GPU/MPS contention and deterministic control.
"""

import pathlib
import sys
import queue
import time
from unittest.mock import MagicMock, patch

import numpy as np

# Ensure project root on sys.path for direct invocation
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.vad import VadThread  # noqa: E402 — after sys.path setup


# ── helpers ────────────────────────────────────────────────────────────────────

RNG = np.random.default_rng(42)

def speech_frame() -> np.ndarray:
    """512-sample frame with RMS ~0.1 (well above 0.01 energy threshold)."""
    return RNG.normal(0, 0.1, 512).astype(np.float32)


def silence_frame() -> np.ndarray:
    """512-sample frame of zeros (RMS = 0.0, below energy threshold)."""
    return np.zeros(512, dtype=np.float32)


def make_mock_model(speech_prob: float = 0.9) -> MagicMock:
    """Return a mock Silero model that returns a fixed speech probability."""
    model = MagicMock()
    model.return_value = speech_prob
    model.reset_states = MagicMock()
    return model


def run_vad(frames: list[np.ndarray], mock_model: MagicMock, timeout: float = 2.0) -> queue.Queue:
    """
    Feed frames into a VadThread, let it process, return the speech_q.

    Sends a None sentinel at the end so VadThread exits cleanly.
    """
    audio_q: queue.Queue = queue.Queue()
    speech_q: queue.Queue = queue.Queue()

    for frame in frames:
        audio_q.put(frame)
    audio_q.put(None)  # sentinel

    with patch("src.vad.SileroVadOnnx", return_value=mock_model):
        vad = VadThread(audio_q=audio_q, speech_q=speech_q)
        vad.start()
        vad.wait(timeout=timeout)

    return speech_q


# ── PIPE-01 tests ──────────────────────────────────────────────────────────────

def test_silence_produces_no_utterance():
    """PIPE-01: 50 frames of zeros → speech_q remains empty."""
    frames = [silence_frame() for _ in range(50)]
    model = make_mock_model(speech_prob=0.1)

    speech_q = run_vad(frames, model)

    assert speech_q.empty(), "Expected no utterances from silence-only input"


def test_speech_then_silence_emits_utterance():
    """PIPE-01: 20 speech frames + 20 silence-VAD frames → exactly 1 utterance in speech_q."""
    # 20 high-energy frames with high speech prob
    speech_frames = [speech_frame() for _ in range(20)]
    # 20 frames that pass energy gate but VAD says no-speech (model returns 0.1)
    non_speech_frames = [speech_frame() for _ in range(20)]

    # Model alternates: high prob for first 20, low for next 20
    model = MagicMock()
    model.reset_states = MagicMock()

    call_count = [0]
    def side_effect(tensor, sample_rate):
        if call_count[0] < 20:
            call_count[0] += 1
            return 0.9
        call_count[0] += 1
        return 0.1

    model.side_effect = side_effect

    frames = speech_frames + non_speech_frames
    speech_q = run_vad(frames, model)

    assert not speech_q.empty(), "Expected an utterance to be emitted"
    utterance = speech_q.get_nowait()
    assert isinstance(utterance, np.ndarray), "Utterance must be a numpy array"
    assert utterance.dtype == np.float32, "Utterance must be float32"


# ── PIPE-02 tests ──────────────────────────────────────────────────────────────

def test_prebuffer_prepended_to_utterance():
    """PIPE-02: 15 ambient frames + 20 speech frames + 20 silence-VAD frames.

    Utterance length must be > 20 * 512 samples because the pre-buffer
    (up to 10 frames = 5120 samples) is prepended before the first speech frame.
    """
    # 15 ambient frames: energy > threshold, but VAD says no-speech
    ambient_frames = [speech_frame() for _ in range(15)]
    speech_frames_list = [speech_frame() for _ in range(20)]
    non_speech_frames = [speech_frame() for _ in range(20)]

    model = MagicMock()
    model.reset_states = MagicMock()

    call_count = [0]
    def side_effect(tensor, sample_rate):
        # Frames 0-14: ambient (low VAD prob)
        # Frames 15-34: speech (high VAD prob)
        # Frames 35+: silence (low VAD prob)
        if 15 <= call_count[0] < 35:
            call_count[0] += 1
            return 0.9
        call_count[0] += 1
        return 0.1

    model.side_effect = side_effect

    frames = ambient_frames + speech_frames_list + non_speech_frames
    speech_q = run_vad(frames, model)

    assert not speech_q.empty(), "Expected utterance after speech + silence"
    utterance = speech_q.get_nowait()
    # Pure speech frames alone = 20 * 512 = 10240 samples
    # With pre-buffer (up to 10 frames) prepended: should be > 10240
    assert len(utterance) > 20 * 512, (
        f"Expected utterance > {20 * 512} samples (pre-buffer should be prepended), "
        f"got {len(utterance)}"
    )


def test_postbuffer_appended_to_utterance():
    """PIPE-02: Post-buffer frames are appended after silence threshold is reached.

    After 16 silence frames trigger utterance seal, VadThread collects up to
    POST_FRAMES (7) additional frames. So utterance must be longer than
    (20 speech + 16 silence trigger) * 512 samples minimum.
    """
    speech_frames_list = [speech_frame() for _ in range(20)]
    # Need enough silence frames to trigger seal (16 frames = 500ms) plus post-buffer
    silence_vad_frames = [speech_frame() for _ in range(30)]

    model = MagicMock()
    model.reset_states = MagicMock()

    call_count = [0]
    def side_effect(tensor, sample_rate):
        if call_count[0] < 20:
            call_count[0] += 1
            return 0.9
        call_count[0] += 1
        return 0.1

    model.side_effect = side_effect

    frames = speech_frames_list + silence_vad_frames
    speech_q = run_vad(frames, model)

    assert not speech_q.empty(), "Expected utterance to be emitted"
    utterance = speech_q.get_nowait()
    # speech frames (20) + at least some silence trigger frames (16) + post-buffer
    # At minimum: 20 speech + 16 silence = 36 frames = 18432 samples
    # Post-buffer adds up to 7 more frames = up to 43 frames = 22016 samples
    assert len(utterance) > 20 * 512, (
        f"Utterance should include post-buffer, got {len(utterance)} samples"
    )


# ── PIPE-03 test ───────────────────────────────────────────────────────────────

def test_low_energy_frames_rejected():
    """PIPE-03: 30 zero-energy frames → model is never called, speech_q empty."""
    frames = [silence_frame() for _ in range(30)]
    model = make_mock_model(speech_prob=0.9)

    speech_q = run_vad(frames, model)

    model.assert_not_called()
    assert speech_q.empty(), "Low-energy frames must not produce utterances"


# ── D-08 test ──────────────────────────────────────────────────────────────────

def test_short_utterance_discarded():
    """D-08: 2 speech frames (64ms < 100ms minimum) + 20 silence-VAD frames.

    Utterance is too short — must be discarded, speech_q stays empty.
    """
    speech_frames_list = [speech_frame() for _ in range(2)]
    non_speech_frames = [speech_frame() for _ in range(20)]

    model = MagicMock()
    model.reset_states = MagicMock()

    call_count = [0]
    def side_effect(tensor, sample_rate):
        if call_count[0] < 2:
            call_count[0] += 1
            return 0.9
        call_count[0] += 1
        return 0.1

    model.side_effect = side_effect

    frames = speech_frames_list + non_speech_frames
    speech_q = run_vad(frames, model)

    assert speech_q.empty(), (
        "Short utterance (2 frames < 4 frame minimum) must be discarded"
    )
