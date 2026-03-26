"""Streaming transcription engine wrapping parakeet-mlx."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import mlx.core as mx
import numpy as np

from . import config

MODEL_NAME = "mlx-community/parakeet-tdt-0.6b-v3"


@dataclass
class TranscriptionUpdate:
    """Snapshot of the current transcription state pushed to the callback."""

    finalized_text: str = ""
    draft_text: str = ""
    finalized_sentences: list = field(default_factory=list)
    draft_sentences: list = field(default_factory=list)


def load_model():
    """Load the Parakeet TDT v3 model and return it."""
    from parakeet_mlx import from_pretrained

    t0 = time.time()
    model = from_pretrained(MODEL_NAME)
    elapsed = time.time() - t0
    return model, elapsed


class StreamingTranscriber:
    """Consume audio chunks and produce streaming transcription updates.

    Runs its own background thread that:
      1. Accumulates audio for *feed_interval* seconds.
      2. Feeds the batch to parakeet-mlx's streaming context.
      3. Reads finalized / draft tokens and fires *on_update*.
    """

    def __init__(
        self,
        model,
        *,
        on_update: Callable[[TranscriptionUpdate], None] | None = None,
        feed_interval: float = 0.4,
        context_size: tuple[int, int] = (256, 256),
        depth: int = 1,
    ):
        self.model = model
        self.on_update = on_update
        self.feed_interval = feed_interval
        self.context_size = context_size
        self.depth = depth

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._audio_queue: list[np.ndarray] = []
        self._queue_lock = threading.Lock()

    # -- public API --

    def push_audio(self, chunk: np.ndarray):
        """Thread-safe: enqueue a numpy audio chunk for the transcription loop."""
        with self._queue_lock:
            self._audio_queue.append(chunk)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="transcriber")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def wait(self, timeout: float = 5.0):
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # -- internals --

    def _drain_queue(self) -> np.ndarray | None:
        """Pop all queued chunks and concatenate into one array."""
        with self._queue_lock:
            if not self._audio_queue:
                return None
            chunks = self._audio_queue
            self._audio_queue = []
        return np.concatenate(chunks)

    def _run(self):
        with self.model.transcribe_stream(
            context_size=self.context_size,
            depth=self.depth,
        ) as streamer:
            # Warmup: feed 0.5 s of silence so MLX compiles its graphs
            silence = mx.zeros((int(config.SAMPLE_RATE * 0.5),))
            streamer.add_audio(silence)
            mx.eval(streamer.audio_buffer)  # force compilation

            while not self._stop.is_set():
                self._stop.wait(self.feed_interval)

                audio = self._drain_queue()
                if audio is None or len(audio) == 0:
                    continue

                streamer.add_audio(mx.array(audio))

                # Build update from token lists
                finalized = streamer.finalized_tokens
                draft = streamer.draft_tokens

                fin_text = "".join(t.text for t in finalized)
                dft_text = "".join(t.text for t in draft)

                # Split sentences into finalized vs draft.
                # result.sentences is built from finalized + draft in order.
                # A sentence is finalized if its last token's end time is
                # within the finalized region.
                result = streamer.result
                fin_boundary = finalized[-1].end if finalized else 0.0
                fin_sentences = []
                dft_sentences = []
                for s in result.sentences:
                    if s.end <= fin_boundary:
                        fin_sentences.append(s)
                    else:
                        dft_sentences.append(s)

                update = TranscriptionUpdate(
                    finalized_text=fin_text,
                    draft_text=dft_text,
                    finalized_sentences=fin_sentences,
                    draft_sentences=dft_sentences,
                )

                if self.on_update:
                    self.on_update(update)

        # Context manager __exit__ calls mx.clear_cache()
