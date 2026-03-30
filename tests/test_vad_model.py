"""Unit tests for src/vad_model.py — SileroVadOnnx ONNX wrapper.

Tests mock onnxruntime.InferenceSession so no actual model file is needed.
"""

import pathlib
import sys
from unittest.mock import MagicMock, patch

import numpy as np

# Ensure project root on sys.path for direct invocation
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.vad_model import SileroVadOnnx  # noqa: E402 — after sys.path setup


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_run(_output_names, inputs):
    """Simulate InferenceSession.run() returning (prob, state)."""
    return (
        np.array([[0.85]], dtype=np.float32),
        np.zeros((2, 1, 128), dtype=np.float32),
    )


def _make_model() -> SileroVadOnnx:
    """Create a SileroVadOnnx with a mocked InferenceSession."""
    with patch("src.vad_model.onnxruntime.InferenceSession") as MockSession:
        MockSession.return_value.run = MagicMock(side_effect=_mock_run)
        model = SileroVadOnnx("fake_model.onnx")
    return model


# ── tests ──────────────────────────────────────────────────────────────────────

@patch("src.vad_model.onnxruntime.InferenceSession")
def test_init_creates_session(MockSession):
    """InferenceSession is created on init with CPUExecutionProvider."""
    SileroVadOnnx("fake_model.onnx")

    MockSession.assert_called_once()
    args, kwargs = MockSession.call_args
    assert args[0] == "fake_model.onnx"
    assert kwargs["providers"] == ["CPUExecutionProvider"]


def test_call_returns_float():
    """__call__ returns a float in [0, 1]."""
    model = _make_model()
    audio = np.random.default_rng(0).normal(0, 0.1, 512).astype(np.float32)

    prob = model(audio, sr=16000)

    assert isinstance(prob, float)
    assert 0.0 <= prob <= 1.0


def test_call_accepts_1d_audio():
    """__call__ handles (512,) shaped input without error."""
    model = _make_model()
    audio = np.zeros(512, dtype=np.float32)

    assert audio.ndim == 1
    prob = model(audio, sr=16000)
    assert isinstance(prob, float)


def test_call_accepts_2d_audio():
    """__call__ handles (1, 512) shaped input without error."""
    model = _make_model()
    audio = np.zeros((1, 512), dtype=np.float32)

    assert audio.ndim == 2
    prob = model(audio, sr=16000)
    assert isinstance(prob, float)


def test_reset_states_zeros_state_and_context():
    """reset_states zeroes _state (2,1,128) and _context (1,64)."""
    model = _make_model()

    # Dirty the internal state
    model._state = np.ones((2, 1, 128), dtype=np.float32)
    model._context = np.ones((1, 64), dtype=np.float32)

    model.reset_states()

    assert model._state.shape == (2, 1, 128)
    assert model._context.shape == (1, 64)
    np.testing.assert_array_equal(model._state, np.zeros((2, 1, 128), dtype=np.float32))
    np.testing.assert_array_equal(model._context, np.zeros((1, 64), dtype=np.float32))


def test_context_updated_after_call():
    """_context is updated with the last 64 samples of the input after __call__."""
    model = _make_model()

    # Create audio with a known pattern in the last 64 samples
    rng = np.random.default_rng(99)
    audio = rng.normal(0, 0.1, 512).astype(np.float32)

    model(audio, sr=16000)

    expected_tail = audio[-64:]
    actual_context = model._context[0]  # shape (1, 64) → take first row
    np.testing.assert_array_almost_equal(actual_context, expected_tail)
