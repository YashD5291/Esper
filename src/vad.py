"""VadThread: Silero VAD daemon thread for speech boundary detection.

Reads 512-sample audio frames from audio_q, scores each with the Silero VAD model,
accumulates speech into utterance buffers with pre/post padding, and emits complete
utterances (as float32 numpy arrays) to speech_q.
"""

import collections
import logging
import math
import queue
import threading

import numpy as np

from . import config
from .vad_model import SileroVadOnnx

log = logging.getLogger(__name__)

# ── Frame duration constant ────────────────────────────────────────────────────
# 512 samples at 16kHz = 32ms (hard Silero VAD requirement)
_FRAME_MS: int = 32


class VadThread:
    """Daemon thread that gates audio on speech boundaries using Silero VAD.

    State machine:
    - Idle: frames go into rolling pre-buffer; low-energy frames bypass VAD scoring.
    - Triggered: frames accumulate in speech_buf; silence frames count toward seal.
    - Seal: after VAD_SILENCE_THRESHOLD_MS of consecutive silence, post-buffer is
      collected, duration is checked, and utterance is emitted to speech_q.
    """

    def __init__(self, audio_q: queue.Queue, speech_q: queue.Queue) -> None:
        self._audio_q = audio_q
        self._speech_q = speech_q
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the VAD daemon thread."""
        self._thread = threading.Thread(target=self._run, daemon=True, name="vad")
        self._thread.start()

    def stop(self) -> None:
        """Signal the VAD thread to stop."""
        self._stop.set()

    def wait(self, timeout: float = 5.0) -> None:
        """Block until the VAD thread has exited."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        """Main VAD loop — scores frames, emits utterances to speech_q."""
        model = SileroVadOnnx(config.VAD_MODEL_PATH)

        # Derived constants — computed from config, not stored in config
        sil_frames = math.ceil(config.VAD_SILENCE_THRESHOLD_MS / _FRAME_MS)
        min_frames = math.ceil(config.VAD_MIN_SPEECH_DURATION_MS / _FRAME_MS)
        pre_frames = math.ceil(config.VAD_PRE_BUFFER_MS / _FRAME_MS)
        post_frames = math.ceil(config.VAD_POST_BUFFER_MS / _FRAME_MS)

        # Rolling pre-buffer (maxlen ensures only last ~300ms is kept)
        prebuf: collections.deque = collections.deque(maxlen=pre_frames)
        speech_buf: list = []
        triggered: bool = False
        silence_frames: int = 0
        speech_frame_count: int = 0  # count of frames with speech_prob >= threshold

        try:
            while not self._stop.is_set():
                try:
                    frame = self._audio_q.get(timeout=0.2)
                except queue.Empty:
                    continue

                if frame is None:
                    break  # sentinel from AudioCapture.stop()

                # CRITICAL (Pitfall 1): append to prebuf BEFORE the energy gate
                # so the audio is available for pre-buffer even if below energy threshold
                prebuf.append(frame)

                rms = float(np.sqrt(np.mean(frame ** 2)))

                if rms < config.VAD_MIN_ENERGY:
                    if not triggered:
                        # Skip VAD scoring; frame is already in prebuf
                        continue
                    # When triggered, low-energy frame still counts as non-speech silence
                    speech_buf.append(frame)
                    silence_frames += 1
                    if silence_frames >= sil_frames:
                        self._seal_utterance(
                            speech_buf, post_frames, min_frames, speech_frame_count, model
                        )
                        speech_buf = []
                        triggered = False
                        silence_frames = 0
                        speech_frame_count = 0
                    continue

                # Score frame with Silero VAD
                speech_prob = model(frame, config.SAMPLE_RATE)

                if not triggered:
                    if speech_prob >= config.VAD_SPEECH_THRESHOLD:
                        # Speech starts: prepend pre-buffer (already includes current frame)
                        triggered = True
                        silence_frames = 0
                        speech_frame_count = 1  # current frame is speech
                        speech_buf = list(prebuf)
                        prebuf.clear()
                else:
                    speech_buf.append(frame)
                    if speech_prob < config.VAD_SPEECH_THRESHOLD:
                        silence_frames += 1
                    else:
                        silence_frames = 0
                        speech_frame_count += 1

                    if silence_frames >= sil_frames:
                        self._seal_utterance(
                            speech_buf, post_frames, min_frames, speech_frame_count, model
                        )
                        speech_buf = []
                        triggered = False
                        silence_frames = 0
                        speech_frame_count = 0

        except Exception:
            log.error("Unexpected error in VadThread._run", exc_info=True)
            try:
                self._speech_q.put_nowait(None)
            except queue.Full:
                pass

    def _seal_utterance(
        self,
        speech_buf: list,
        post_frames: int,
        min_frames: int,
        speech_frame_count: int,
        model: object,
    ) -> None:
        """Collect post-buffer, check min speech duration, emit utterance if valid.

        min_frames applies to confirmed speech frames only — not the total buffer
        (which includes pre-buffer and silence frames).

        Calls model.reset_states() after sealing regardless of whether the
        utterance was emitted (Pitfall 2 prevention).
        """
        # Collect post-buffer frames without blocking the VAD thread
        for _ in range(post_frames):
            try:
                pf = self._audio_q.get(timeout=0.05)
                if pf is None:
                    break
                speech_buf.append(pf)
            except queue.Empty:
                break

        if speech_frame_count >= min_frames:
            utterance = np.concatenate(speech_buf).astype(np.float32)
            duration = len(utterance) / config.SAMPLE_RATE
            log.info("VAD: utterance sealed %.2fs (%d frames passed threshold)", duration, speech_frame_count)
            try:
                self._speech_q.put_nowait(utterance)  # non-blocking (Pitfall 3)
            except queue.Full:
                log.warning("speech_q full — utterance discarded")
        else:
            log.info(
                "VAD: utterance discarded: %d speech frames < %d minimum",
                speech_frame_count,
                min_frames,
            )

        # Reset LSTM state between utterances (Pitfall 2)
        model.reset_states()
