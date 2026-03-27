"""Silero VAD v5 via ONNX runtime -- no PyTorch dependency.

Drop-in replacement for the torch-based Silero model. Implements the same
__call__ and reset_states interface used by VadThread.
"""

from __future__ import annotations

import numpy as np
import onnxruntime


class SileroVadOnnx:
    """Silero VAD running on ONNX runtime (CPU only, ~2MB model)."""

    def __init__(self, model_path: str) -> None:
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)

    def reset_states(self) -> None:
        """Zero RNN state and context buffer between utterances."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)

    def __call__(self, audio: np.ndarray, sr: int) -> float:
        """Score a 512-sample audio chunk. Returns speech probability [0, 1].

        Args:
            audio: float32 array, shape (1, 512) or (512,).
            sr: sample rate, must be 16000.
        """
        if audio.ndim == 1:
            audio = audio[np.newaxis, :]

        # Prepend 64-sample context for temporal continuity
        x = np.concatenate([self._context, audio], axis=1)  # (1, 576)

        ort_inputs = {
            "input": x,
            "state": self._state,
            "sr": np.array(sr, dtype=np.int64),
        }
        out, self._state = self._session.run(None, ort_inputs)

        # Save last 64 samples as context for next call
        self._context = x[:, -64:]

        return float(out[0, 0])
