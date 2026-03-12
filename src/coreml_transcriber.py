"""CoreML transcription engine using Parakeet TDT v3 on Apple Neural Engine.

Replaces the MLX backend with CoreML inference.  The heavy mel-spectrogram
and encoder stages run on ANE; the lightweight decoder LSTM and joint
decision run on CPU/ANE as CoreML sees fit.

The public API mirrors StreamingTranscriber so that realtime_demo.py can
swap engines with a single flag.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import coremltools as ct
import numpy as np

from .audio_capture import SAMPLE_RATE
from .transcriber import TranscriptionUpdate

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "coreml"

# TDT v3 constants
BLANK_ID = 8192
DURATION_BINS = [0, 1, 2, 3, 4]
MAX_SYMBOLS_PER_STEP = 10
MAX_AUDIO_SAMPLES = 240_000  # 15s at 16kHz
OVERLAP_SAMPLES = SAMPLE_RATE  # 1s default overlap (overridden per-instance)


@dataclass
class _Sentence:
    """Lightweight container matching the sentence interface ConsoleRenderer expects."""
    text: str
    confidence: float = 1.0
    start: float = 0.0
    end: float = 0.0


def load_coreml_models() -> dict:
    """Load all CoreML model components and return them in a dict."""
    t0 = time.time()

    models = {
        "mel_encoder": ct.models.CompiledMLModel(
            str(MODEL_DIR / "MelEncoder.mlmodelc"), ct.ComputeUnit.ALL
        ),
        "decoder": ct.models.CompiledMLModel(
            str(MODEL_DIR / "Decoder.mlmodelc"), ct.ComputeUnit.ALL
        ),
        "joint_decision": ct.models.CompiledMLModel(
            str(MODEL_DIR / "JointDecision.mlmodelc"), ct.ComputeUnit.ALL
        ),
    }

    # Load vocabulary: { "0": "<unk>", "1": "<|nospeech|>", ... }
    with open(MODEL_DIR / "parakeet_v3_vocab.json") as f:
        raw = json.load(f)
    vocab = {int(k): v for k, v in raw.items()}

    elapsed = time.time() - t0
    return models, vocab, elapsed


def _run_decoder(model, token_id: int, h: np.ndarray, c: np.ndarray):
    """Run one decoder LSTM step. Returns (decoder_output, h_out, c_out)."""
    result = model.predict({
        "targets": np.array([[token_id]], dtype=np.int32),
        "target_length": np.array([1], dtype=np.int32),
        "h_in": h,
        "c_in": c,
    })
    return result["decoder"], result["h_out"], result["c_out"]


def _run_joint(model, encoder_step: np.ndarray, decoder_step: np.ndarray):
    """Run one joint decision step. Returns (token_id, token_prob, duration_bin)."""
    result = model.predict({
        "encoder_step": encoder_step,
        "decoder_step": decoder_step,
    })
    token_id = int(result["token_id"].flat[0])
    token_prob = float(result["token_prob"].flat[0])
    duration = int(result["duration"].flat[0])
    return token_id, token_prob, duration


def _tdt_greedy_decode(
    encoder_out: np.ndarray,
    encoder_length: int,
    decoder_model,
    joint_model,
) -> list[tuple[int, float]]:
    """TDT greedy decoding loop.

    Args:
        encoder_out: [1, 1024, T] float32 — encoder output
        encoder_length: number of valid encoder frames
        decoder_model: CoreML decoder (LSTM predictor)
        joint_model: CoreML joint decision network

    Returns:
        List of (token_id, token_prob) for non-blank tokens.
    """
    T = encoder_length

    # Initialize LSTM state
    h = np.zeros((2, 1, 640), dtype=np.float32)
    c = np.zeros((2, 1, 640), dtype=np.float32)

    # Prime decoder with blank (SOS)
    dec_out, h, c = _run_decoder(decoder_model, BLANK_ID, h, c)

    tokens: list[tuple[int, float]] = []
    time_idx = 0

    while time_idx < T:
        # Extract encoder frame at current time index: [1, 1024, 1]
        enc_step = encoder_out[:, :, time_idx:time_idx + 1]

        # Run joint decision
        token_id, token_prob, dur_bin = _run_joint(joint_model, enc_step, dec_out)
        duration = DURATION_BINS[min(dur_bin, len(DURATION_BINS) - 1)]

        if token_id == BLANK_ID:
            # Blank — advance by duration, reuse decoder output
            if duration == 0:
                duration = 1  # prevent infinite loop
            time_idx += duration

            # Inner blank loop: keep advancing while blank, reusing decoder
            while time_idx < T:
                enc_step = encoder_out[:, :, time_idx:time_idx + 1]
                token_id, token_prob, dur_bin = _run_joint(joint_model, enc_step, dec_out)
                duration = DURATION_BINS[min(dur_bin, len(DURATION_BINS) - 1)]

                if token_id != BLANK_ID:
                    break  # exit inner loop — non-blank found

                if duration == 0:
                    duration = 1
                time_idx += duration
            else:
                break  # exhausted all frames

        # Non-blank token found
        if token_id != BLANK_ID and time_idx < T:
            tokens.append((token_id, token_prob))

            # Update decoder LSTM with the new token
            dec_out, h, c = _run_decoder(decoder_model, token_id, h, c)

            # Advance by duration
            time_idx += max(duration, 1)

            # Guard against stuck emission at same timestep
            symbols_at_step = 1
            while time_idx < T and symbols_at_step < MAX_SYMBOLS_PER_STEP:
                enc_step = encoder_out[:, :, time_idx:time_idx + 1]
                token_id, token_prob, dur_bin = _run_joint(joint_model, enc_step, dec_out)
                duration = DURATION_BINS[min(dur_bin, len(DURATION_BINS) - 1)]

                if token_id == BLANK_ID:
                    if duration == 0:
                        duration = 1
                    time_idx += duration
                    break  # back to outer loop

                tokens.append((token_id, token_prob))
                dec_out, h, c = _run_decoder(decoder_model, token_id, h, c)
                time_idx += max(duration, 1)
                symbols_at_step += 1

    return tokens


def _tokens_to_text(tokens: list[tuple[int, float]], vocab: dict) -> str:
    """Convert token IDs to text using vocabulary."""
    parts = []
    for tid, _ in tokens:
        tok = vocab.get(tid, "")
        if tok.startswith("\u2581"):  # SentencePiece space marker ▁
            parts.append(" " + tok[1:])
        else:
            parts.append(tok)
    return "".join(parts).strip()


class CoreMLTranscriber:
    """Consume audio chunks and produce transcription updates via CoreML.

    Buffers audio into chunks up to 15s (the model's maximum), runs
    mel-spectrogram + encoder on ANE, then decodes tokens with TDT greedy
    search.

    Public API matches StreamingTranscriber.
    """

    def __init__(
        self,
        models: dict,
        vocab: dict,
        *,
        on_update: Callable[[TranscriptionUpdate], None] | None = None,
        buffer_seconds: float = 1.5,
    ):
        self.mel_encoder = models["mel_encoder"]
        self.decoder = models["decoder"]
        self.joint_decision = models["joint_decision"]
        self.vocab = vocab
        self.on_update = on_update
        self.buffer_seconds = min(buffer_seconds, 15.0)

        # Scale overlap with buffer: ~33% of buffer, capped at 1s
        self._overlap_samples = int(
            SAMPLE_RATE * min(self.buffer_seconds * 0.33, 1.0)
        )

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._audio_queue: list[np.ndarray] = []
        self._queue_lock = threading.Lock()

        self._all_text: list[str] = []
        self._prev_tail: str = ""

    # -- public API --

    def push_audio(self, chunk: np.ndarray):
        """Thread-safe: enqueue a numpy audio chunk for transcription."""
        with self._queue_lock:
            self._audio_queue.append(chunk)

    def start(self):
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="coreml-transcriber"
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

    def wait(self, timeout: float = 5.0):
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # -- internals --

    def _drain_queue(self) -> np.ndarray | None:
        with self._queue_lock:
            if not self._audio_queue:
                return None
            chunks = self._audio_queue
            self._audio_queue = []
        return np.concatenate(chunks)

    def _transcribe_chunk(self, audio: np.ndarray) -> str:
        """Run CoreML inference on an audio chunk (up to 15s / 240000 samples)."""
        n_samples = len(audio)

        # Pad to exactly 240000 samples (15s) — model expects fixed size
        padded = np.zeros(MAX_AUDIO_SAMPLES, dtype=np.float32)
        padded[:n_samples] = audio

        audio_signal = padded.reshape(1, -1)  # [1, 240000]
        audio_length = np.array([n_samples], dtype=np.int32)

        # Fused mel-spectrogram + encoder
        enc_result = self.mel_encoder.predict({
            "audio_signal": audio_signal,
            "audio_length": audio_length,
        })
        encoder_out = enc_result["encoder"]       # [1, 1024, T]
        encoder_len = int(enc_result["encoder_length"].flat[0])

        # TDT greedy decode
        tokens = _tdt_greedy_decode(
            encoder_out, encoder_len, self.decoder, self.joint_decision,
        )

        return _tokens_to_text(tokens, self.vocab)

    def _emit_update(self, text: str):
        """Deduplicate against previous chunk and emit a TranscriptionUpdate."""
        text = text.strip()
        if not text:
            return

        # Deduplicate overlap: if the new text starts with words that
        # match the end of the previous text, skip the overlapping part.
        # Uses case-insensitive + punctuation-stripped comparison since the
        # model may capitalize or punctuate differently at chunk boundaries.
        if self._all_text and self._prev_tail:
            tail = self._prev_tail
            words_new = text.split()
            words_tail = tail.split()
            strip_tbl = str.maketrans("", "", ".,!?;:\"'")
            norm = lambda w: w.lower().translate(strip_tbl)
            best = 0
            for n in range(min(len(words_tail), len(words_new)), 0, -1):
                if [norm(w) for w in words_new[:n]] == [norm(w) for w in words_tail[-n:]]:
                    best = n
                    break
            if best > 0:
                text = " ".join(words_new[best:])
                if not text:
                    return

        self._all_text.append(text)

        full_text = " ".join(self._all_text)
        sentences = [_Sentence(text=t) for t in self._all_text]
        update = TranscriptionUpdate(
            finalized_text=full_text,
            draft_text="",
            finalized_sentences=sentences,
            draft_sentences=[],
        )
        if self.on_update:
            self.on_update(update)

    def _run(self):
        """Background thread: accumulate audio, transcribe in overlapping chunks.

        Each chunk overlaps the previous by OVERLAP_SAMPLES (1s) so that
        words at the boundary always have encoder context on both sides.
        The overlap region is transcribed twice; _emit_update deduplicates
        by matching the trailing words of the previous chunk against the
        leading words of the new one.
        """
        import sys
        import traceback

        buffer = np.array([], dtype=np.float32)
        chunk_samples = int(self.buffer_seconds * SAMPLE_RATE)
        self._prev_tail = ""

        try:
            # Warmup: run a silent chunk to trigger CoreML compilation
            silence = np.zeros(SAMPLE_RATE, dtype=np.float32)  # 1s silence
            self._transcribe_chunk(silence)

            while not self._stop.is_set():
                self._stop.wait(0.1)

                audio = self._drain_queue()
                if audio is not None:
                    buffer = np.concatenate([buffer, audio])

                # Process when we have enough audio
                while len(buffer) >= chunk_samples:
                    take = min(len(buffer), MAX_AUDIO_SAMPLES)
                    chunk = buffer[:take]
                    # Keep overlap in the buffer for next chunk
                    advance = take - self._overlap_samples
                    buffer = buffer[advance:]

                    text = self._transcribe_chunk(chunk)
                    self._emit_update(text)
                    # Set tail AFTER emit so dedup compares against the
                    # previous chunk, not the current one.
                    words = text.strip().split()
                    if words:
                        self._prev_tail = " ".join(words[-12:])

            # Flush remaining buffer on stop
            if len(buffer) > SAMPLE_RATE * 0.3:
                text = self._transcribe_chunk(buffer)
                buffer = np.array([], dtype=np.float32)
                self._emit_update(text)

        except Exception:
            print(
                f"\n\033[91m  [CoreML thread crashed]\033[0m",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)
