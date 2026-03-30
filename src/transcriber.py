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
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import config
from .whisper_worker import _send_msg, _recv_msg

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
        self._pipe_proc = None
        self._reader_thread = None
        self._stderr_thread = None

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
        if self._pipe_proc is not None:
            try:
                _send_msg(self._pipe_proc.stdin, None)
            except Exception:
                pass
        elif self._audio_q is not None:
            try:
                self._audio_q.put(None)
            except Exception:
                pass
        self._kill_worker()
        self._stopped = True

    def wait(self, timeout: float = 5.0) -> None:
        """Wait for the worker process to exit."""
        if self._pipe_proc is not None:
            self._pipe_proc.wait(timeout=timeout)
        elif self._proc is not None:
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

        if self._pipe_proc:
            _send_msg(self._pipe_proc.stdin, audio)
        else:
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
        """Create and start a new worker subprocess.

        In frozen mode (PyInstaller): uses subprocess.Popen to launch a
        second instance of the frozen binary with --whisper-worker flag.
        Communication via length-prefixed pickle on stdin/stdout.
        This avoids all PyInstaller + multiprocessing issues.

        In dev mode: uses multiprocessing spawn context with queues.
        """
        self._result_q = queue.Queue()

        if getattr(sys, '_MEIPASS', None):
            # Frozen: launch self with --whisper-worker flag
            self._pipe_proc = subprocess.Popen(
                [sys.executable, "--whisper-worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._audio_q = None  # not used in pipe mode
            self._proc = None     # not a multiprocessing.Process
            self._result_q = queue.Queue()

            # Background thread reads results from worker stdout → result_q
            self._reader_thread = threading.Thread(
                target=self._pipe_reader,
                daemon=True,
                name="whisper-pipe-reader",
            )
            self._reader_thread.start()

            # Background thread captures worker stderr for logging
            self._stderr_thread = threading.Thread(
                target=self._stderr_reader,
                daemon=True,
                name="whisper-stderr-reader",
            )
            self._stderr_thread.start()
        else:
            # Dev mode: use multiprocessing spawn (queues directly)
            self._pipe_proc = None
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

    def _pipe_reader(self) -> None:
        """Read length-prefixed pickle messages from pipe worker stdout."""
        try:
            while True:
                msg = _recv_msg(self._pipe_proc.stdout)
                if msg is None:
                    break
                self._result_q.put(msg)
        except Exception:
            pass

    def _stderr_reader(self) -> None:
        """Log worker stderr output."""
        try:
            for line in self._pipe_proc.stderr:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    log.debug("[whisper-worker] %s", text)
        except Exception:
            pass


    def _kill_worker(self) -> None:
        """Kill and join the current worker process."""
        if self._pipe_proc is not None:
            try:
                self._pipe_proc.stdin.close()
            except Exception:
                pass
            self._pipe_proc.kill()
            self._pipe_proc.wait(timeout=5)
            self._pipe_proc = None
        elif self._proc is not None and self._proc.is_alive():
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
