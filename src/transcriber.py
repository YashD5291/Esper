"""Whisper transcription engine — Phase 4 rewrite.

Replaces the Parakeet/CoreML StreamingTranscriber with a subprocess-isolated
WhisperTranscriber. MLX has an open thread-safety issue (GitHub #2133) that
causes Metal assertion failures under concurrent use. A spawn-context subprocess
gives Whisper its own clean Metal context.

Public API:
  WhisperTranscriber(on_update, on_status) — lifecycle: start() / stop() / wait()
  TranscriptionUpdate                       — per-utterance result dataclass
"""

from __future__ import annotations

import logging
import multiprocessing
import pathlib
import queue
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import config

log = logging.getLogger("esper.transcriber")


@dataclass
class TranscriptionUpdate:
    """Per-utterance transcription result from Whisper (Phase 4).

    Fields (D-01):
      text            — this utterance's transcript
      finalized_text  — session accumulator (all utterances joined)
      sentences       — list of utterance strings accumulated this session
      no_speech_prob  — average no_speech_prob across Whisper segments
      duration_s      — length of the audio utterance in seconds
    """

    text: str = ""
    finalized_text: str = ""
    sentences: list[str] = field(default_factory=list)
    no_speech_prob: float = 0.0
    duration_s: float = 0.0


def _whisper_worker_entry(audio_q, result_q) -> None:
    """Entry point for spawn-context subprocess.

    This wrapper is a module-level function so it can be pickled by the
    spawn context. It imports and calls the real worker from whisper_worker.py.
    """
    from src.whisper_worker import _whisper_worker
    _whisper_worker(audio_q, result_q)


class WhisperTranscriber:
    """Subprocess-isolated Whisper transcription engine.

    Lifecycle:
        wt = WhisperTranscriber(on_update=..., on_status=...)
        wt.start()                  # spawns subprocess, waits for ready
        for audio in utterances:
            update = wt.transcribe_utterance(audio)
        wt.stop()
        wt.wait()

    on_update: Callable[[TranscriptionUpdate], None]
        Called on every accepted utterance (hallucination-filtered).

    on_status: Callable[[str], None]
        Called with status strings:
          "downloading_model" — first run, model not in cache
          "loading_model"     — model cached, loading from disk
          "transcribing"      — utterance entered Whisper (D-02)
          "listening"         — utterance complete, back to idle (D-02)
          "error"             — worker timeout or inference error (D-06)
          "crashed"           — 3 consecutive failures (D-08)
    """

    def __init__(
        self,
        *,
        on_update: Callable[[TranscriptionUpdate], None],
        on_status: Callable[[str], None],
    ) -> None:
        self._on_update = on_update
        self._on_status = on_status

        self._sentences: list[str] = []
        self._finalized_text: str = ""
        self._generation_count: int = 0
        self._crash_count: int = 0
        self._stopped: bool = False

        self._proc = None
        self._audio_q = None
        self._result_q = None

    @property
    def stopped(self) -> bool:
        return self._stopped

    # ── public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the worker subprocess and wait for the ready sentinel.

        Emits "downloading_model" or "loading_model" status based on whether
        the model is already cached in ~/.cache/huggingface/hub/.

        Raises:
            RuntimeError: if the worker does not emit a ready sentinel within
                          config.MODEL_LOAD_TIMEOUT_S seconds (ARCH-03).
        """
        model_path = pathlib.Path(config.WHISPER_MODEL_REPO)
        if model_path.is_dir() and (model_path / "weights.safetensors").exists():
            self._on_status("loading_model")
        else:
            self._on_status("downloading_model")

        self._spawn_worker()

        # Wait for ready sentinel (covers model load + Metal shader compile)
        try:
            sentinel = self._result_q.get(timeout=config.MODEL_LOAD_TIMEOUT_S)
        except queue.Empty:
            if self._proc and self._proc.is_alive():
                self._proc.kill()
                self._proc.join(timeout=5)
            raise RuntimeError(
                f"Model load timed out after {config.MODEL_LOAD_TIMEOUT_S}s "
                f"(worker never emitted ready sentinel)"
            )

        if not (sentinel.get("ok") and sentinel.get("ready")):
            # Worker sent an error on startup
            error_msg = sentinel.get("error", "unknown error")
            raise RuntimeError(f"Worker startup failed: {error_msg}")

        log.info("Whisper worker ready.")

    def stop(self) -> None:
        """Send shutdown sentinel and kill the worker process."""
        if self._audio_q is not None:
            try:
                self._audio_q.put(None)
            except Exception:
                pass
        self._kill_worker()
        self._stopped = True

    def wait(self, timeout: float = 5.0) -> None:
        """Wait for the worker process to exit."""
        if self._proc is not None:
            self._proc.join(timeout=timeout)

    def transcribe_utterance(self, audio: np.ndarray) -> TranscriptionUpdate | None:
        """Send audio to the worker subprocess and return a TranscriptionUpdate.

        Args:
            audio: float32 numpy array at 16kHz (VAD-gated utterance).

        Returns:
            TranscriptionUpdate if accepted, None if filtered (hallucination,
            timeout, or worker error).

        D-06: On timeout, emits on_status("error") before failure handling.
        """
        if self._stopped:
            return None

        self._audio_q.put(audio)

        try:
            result = self._result_q.get(timeout=config.WHISPER_SUBPROCESS_TIMEOUT_S)
        except queue.Empty:
            log.warning("Whisper subprocess timed out after %ss", config.WHISPER_SUBPROCESS_TIMEOUT_S)
            self._kill_worker()
            self._on_status("error")  # D-06: emit error event before restart logic
            self._on_failure()
            return None

        if not result.get("ok"):
            log.error("Worker inference error: %s", result.get("error"))
            self._on_status("error")  # D-06: emit error event
            self._on_failure()
            return None

        raw = result["result"]
        if self._is_hallucination(raw):
            log.debug("Hallucination filtered: no_speech or compression_ratio exceeded threshold")
            return None

        # Success path: reset crash counter, build update
        self._crash_count = 0
        self._generation_count += 1

        update = self._build_update(raw, audio)
        self._on_update(update)

        # Recycle worker after N generations (PIPE-05: keep model warm but
        # prevent memory accumulation over long sessions)
        if self._generation_count >= config.WHISPER_MAX_GENERATIONS_BEFORE_RESTART:
            log.info("Recycling worker after %d generations", self._generation_count)
            self._generation_count = 0
            self._kill_worker()
            self._spawn_worker()
            # Wait for ready sentinel on recycled worker
            try:
                sentinel = self._result_q.get(timeout=config.MODEL_LOAD_TIMEOUT_S)
                if not (sentinel.get("ok") and sentinel.get("ready")):
                    log.error("Worker recycle failed: %s", sentinel.get("error"))
            except queue.Empty:
                log.error("Worker recycle timed out waiting for ready sentinel")

        return update

    # ── internals ─────────────────────────────────────────────────────────────

    def _spawn_worker(self) -> None:
        """Create and start a new worker subprocess using spawn context.

        Uses SimpleQueue for audio_q (parent→worker, no timeout needed) and
        Queue for result_q (worker→parent, needs .get(timeout=...) for watchdog).
        multiprocessing.Queue is safe here because the watchdog timeout kills
        the worker before queue state can deadlock.
        """
        ctx = multiprocessing.get_context("spawn")
        self._audio_q = ctx.SimpleQueue()
        self._result_q = ctx.Queue()
        self._proc = ctx.Process(
            target=_whisper_worker_entry,
            args=(self._audio_q, self._result_q),
            daemon=True,
            name="whisper-worker",
        )
        self._proc.start()

    def _kill_worker(self) -> None:
        """Kill and join the current worker process."""
        if self._proc is not None and self._proc.is_alive():
            self._proc.kill()
            self._proc.join(timeout=5)

    def _on_failure(self) -> None:
        """Increment crash counter; restart or stop after 3 consecutive failures."""
        self._crash_count += 1
        if self._crash_count >= 3:
            self._stopped = True
            self._on_status("crashed")
            log.error("WhisperTranscriber stopped after 3 consecutive failures")
        else:
            log.warning(
                "Worker failure #%d, restarting subprocess", self._crash_count
            )
            self._spawn_worker()
            # Consume the ready sentinel for the new worker
            try:
                sentinel = self._result_q.get(timeout=config.MODEL_LOAD_TIMEOUT_S)
                if not (sentinel.get("ok") and sentinel.get("ready")):
                    log.error("Restarted worker startup error: %s", sentinel.get("error"))
            except queue.Empty:
                log.error("Restarted worker timed out waiting for ready sentinel")

    def _is_hallucination(self, result: dict) -> bool:
        """Return True if the Whisper result should be silently discarded.

        Filters:
          - No segments (empty output)
          - Empty text after strip
          - Average no_speech_prob > config.WHISPER_NO_SPEECH_THRESHOLD
          - Average compression_ratio > config.WHISPER_COMPRESSION_RATIO_THRESHOLD
        """
        segments = result.get("segments", [])
        if not segments:
            return True

        text = result.get("text", "").strip()
        if not text:
            return True

        avg_no_speech = sum(s["no_speech_prob"] for s in segments) / len(segments)
        if avg_no_speech > config.WHISPER_NO_SPEECH_THRESHOLD:
            return True

        avg_compression = sum(s["compression_ratio"] for s in segments) / len(segments)
        if avg_compression > config.WHISPER_COMPRESSION_RATIO_THRESHOLD:
            return True

        return False

    def _build_update(self, result: dict, audio: np.ndarray) -> TranscriptionUpdate:
        """Build a TranscriptionUpdate from a successful Whisper result."""
        text = result["text"].strip()

        self._sentences.append(text)
        self._finalized_text = " ".join(self._sentences)

        segments = result.get("segments", [])
        avg_no_speech = (
            sum(s["no_speech_prob"] for s in segments) / len(segments)
            if segments else 0.0
        )

        duration_s = len(audio) / config.SAMPLE_RATE

        return TranscriptionUpdate(
            text=text,
            finalized_text=self._finalized_text,
            sentences=list(self._sentences),
            no_speech_prob=avg_no_speech,
            duration_s=duration_s,
        )
