"""Unit tests for src/transcriber.py (WhisperTranscriber) and src/whisper_worker.py.

Covers requirements:
  PIPE-04 — Whisper large-v3-turbo transcribes VAD-gated utterances
  PIPE-05 — Whisper runs in spawn-context subprocess
  PIPE-06 — Hallucination guard filters no_speech_prob and compression_ratio
  ARCH-03 — Cascading watchdog timeouts
  ARCH-04 — TranscriptionUpdate contract

All tests mock subprocess/multiprocessing — no GPU required.
"""

from __future__ import annotations

import pathlib
import queue
import sys
from dataclasses import fields as dc_fields
from unittest.mock import MagicMock, call, patch

import numpy as np

# Ensure project root on sys.path for direct invocation
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src import config  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_good_result(text: str = " Hello world.", no_speech_prob: float = 0.1,
                      compression_ratio: float = 1.2) -> dict:
    """Return a mock mlx_whisper.transcribe()-shaped result dict."""
    return {
        "ok": True,
        "result": {
            "text": text,
            "segments": [
                {
                    "no_speech_prob": no_speech_prob,
                    "compression_ratio": compression_ratio,
                    "text": text,
                }
            ],
        },
    }


def _make_transcriber(result_q_items: list | None = None, *, on_update=None, on_status=None):
    """Build a WhisperTranscriber with fully mocked subprocess infrastructure.

    Patches multiprocessing.get_context so no real process is spawned.
    Pre-loads result_q with items from result_q_items list (if provided).
    """
    from src.transcriber import WhisperTranscriber

    updates: list = []
    statuses: list = []
    if on_update is None:
        on_update = updates.append
    if on_status is None:
        on_status = statuses.append

    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()

    if result_q_items is not None:
        # Simulate queue.get(timeout=...) returning items in order, then raising Empty
        side_effects: list = list(result_q_items) + [queue.Empty()]
        mock_result_q.get.side_effect = side_effects

    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    return (
        WhisperTranscriber(on_update=on_update, on_status=on_status),
        mock_ctx,
        mock_audio_q,
        mock_result_q,
        mock_proc,
        updates,
        statuses,
    )


# ── ARCH-04: TranscriptionUpdate contract ─────────────────────────────────────

def test_transcription_update_fields():
    """ARCH-04: TranscriptionUpdate has all required new and backward-compat fields."""
    from src.transcriber import TranscriptionUpdate

    t = TranscriptionUpdate()
    field_names = {f.name for f in dc_fields(t)}

    # New fields (per D-01)
    assert "text" in field_names, "Missing field: text"
    assert "finalized_text" in field_names, "Missing field: finalized_text"
    assert "sentences" in field_names, "Missing field: sentences"
    assert "no_speech_prob" in field_names, "Missing field: no_speech_prob"
    assert "duration_s" in field_names, "Missing field: duration_s"

    # Backward-compat fields (for coreml_transcriber.py — removed in Phase 6)
    assert "draft_text" in field_names, "Missing backward-compat field: draft_text"
    assert "finalized_sentences" in field_names, "Missing backward-compat field: finalized_sentences"
    assert "draft_sentences" in field_names, "Missing backward-compat field: draft_sentences"

    # Default values
    assert t.text == ""
    assert t.finalized_text == ""
    assert t.sentences == []
    assert t.no_speech_prob == 0.0
    assert t.duration_s == 0.0
    assert t.draft_text == ""
    assert t.finalized_sentences == []
    assert t.draft_sentences == []


def test_transcription_update_backward_compat():
    """ARCH-04: coreml_transcriber.py construction style still works."""
    from src.transcriber import TranscriptionUpdate

    t = TranscriptionUpdate(
        finalized_text="hello world",
        draft_text="draft",
        finalized_sentences=[],
        draft_sentences=[],
    )
    assert t.finalized_text == "hello world"
    assert t.draft_text == "draft"
    assert t.finalized_sentences == []
    assert t.draft_sentences == []


# ── config hallucination thresholds ───────────────────────────────────────────

def test_config_hallucination_thresholds():
    """config.py must have the hallucination filter thresholds."""
    assert hasattr(config, "WHISPER_NO_SPEECH_THRESHOLD"), "Missing WHISPER_NO_SPEECH_THRESHOLD"
    assert hasattr(config, "WHISPER_COMPRESSION_RATIO_THRESHOLD"), "Missing WHISPER_COMPRESSION_RATIO_THRESHOLD"
    assert config.WHISPER_NO_SPEECH_THRESHOLD == 0.6
    assert config.WHISPER_COMPRESSION_RATIO_THRESHOLD == 2.4


# ── PIPE-05: spawn context ─────────────────────────────────────────────────────

def test_spawn_context():
    """PIPE-05: _spawn_worker uses mp.get_context('spawn'), not fork."""
    from src.transcriber import WhisperTranscriber

    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True

    # Capture the ready sentinel on result_q
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.return_value = {"ok": True, "ready": True}

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    wt = WhisperTranscriber(on_update=MagicMock(), on_status=MagicMock())
    with patch("multiprocessing.get_context", return_value=mock_ctx) as mock_get_ctx:
        # Check ~/.cache for model to avoid waiting
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    mock_get_ctx.assert_called_once_with("spawn")


# ── PIPE-04: transcribe returns TranscriptionUpdate ───────────────────────────

def test_transcribe_returns_update():
    """PIPE-04: transcribe_utterance returns a TranscriptionUpdate on success."""
    from src.transcriber import TranscriptionUpdate, WhisperTranscriber

    good_result = _make_good_result(" Hello world.")
    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    # First call is for start() ready sentinel, second is for the utterance
    mock_result_q.get.side_effect = [{"ok": True, "ready": True}, good_result]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())

    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    result = wt.transcribe_utterance(audio)

    assert result is not None, "Expected TranscriptionUpdate, got None"
    assert isinstance(result, TranscriptionUpdate)
    assert result.text == "Hello world."
    assert len(updates) == 1
    assert updates[0].text == "Hello world."


# ── PIPE-06: hallucination filter ─────────────────────────────────────────────

def test_hallucination_filter_no_speech():
    """PIPE-06: no_speech_prob > 0.6 → transcribe_utterance returns None."""
    from src.transcriber import WhisperTranscriber

    bad_result = _make_good_result(no_speech_prob=0.8)
    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [{"ok": True, "ready": True}, bad_result]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    result = wt.transcribe_utterance(audio)

    assert result is None, "High no_speech_prob should be filtered"
    assert len(updates) == 0, "No update should be emitted for hallucination"


def test_hallucination_filter_compression():
    """PIPE-06: compression_ratio > 2.4 → transcribe_utterance returns None."""
    from src.transcriber import WhisperTranscriber

    bad_result = _make_good_result(compression_ratio=3.0)
    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [{"ok": True, "ready": True}, bad_result]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    result = wt.transcribe_utterance(audio)

    assert result is None, "High compression_ratio should be filtered"


def test_hallucination_filter_empty_text():
    """PIPE-06: empty text → transcribe_utterance returns None."""
    from src.transcriber import WhisperTranscriber

    empty_result = _make_good_result(text="")
    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [{"ok": True, "ready": True}, empty_result]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    result = wt.transcribe_utterance(audio)

    assert result is None, "Empty text should be filtered"


def test_hallucination_filter_passes_good_result():
    """PIPE-06: valid result (low no_speech_prob, normal compression, non-empty) passes through."""
    from src.transcriber import WhisperTranscriber

    good_result = _make_good_result(text=" hello", no_speech_prob=0.2, compression_ratio=1.5)
    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [{"ok": True, "ready": True}, good_result]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    result = wt.transcribe_utterance(audio)

    assert result is not None, "Good result should pass the hallucination filter"
    assert result.text == "hello"


# ── ARCH-03: watchdog timeout ──────────────────────────────────────────────────

def test_watchdog_timeout():
    """ARCH-03: result_q.get() timeout → worker killed, transcribe_utterance returns None."""
    from src.transcriber import WhisperTranscriber

    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    # Ready sentinel succeeds; utterance call times out
    mock_result_q.get.side_effect = [{"ok": True, "ready": True}, queue.Empty()]

    mock_ctx = MagicMock()
    # Provide two rounds of SimpleQueue (initial start + respawn after crash)
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q,
                                         MagicMock(), MagicMock()]
    mock_ctx.Process.return_value = mock_proc

    statuses: list = []
    wt = WhisperTranscriber(on_update=MagicMock(), on_status=statuses.append)
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    result = wt.transcribe_utterance(audio)

    assert result is None, "Timeout should return None"
    mock_proc.kill.assert_called()


def test_watchdog_timeout_emits_error_event():
    """ARCH-03 + D-06: timeout path emits on_status('error') before failure handling."""
    from src.transcriber import WhisperTranscriber

    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [{"ok": True, "ready": True}, queue.Empty()]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q,
                                         MagicMock(), MagicMock()]
    mock_ctx.Process.return_value = mock_proc

    statuses: list = []
    wt = WhisperTranscriber(on_update=MagicMock(), on_status=statuses.append)
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    wt.transcribe_utterance(audio)

    assert "error" in statuses, f"Expected 'error' status event, got: {statuses}"
    # 'error' must appear before 'crashed' (if any)
    if "crashed" in statuses:
        assert statuses.index("error") < statuses.index("crashed")


# ── ARCH-03: model load timeout ───────────────────────────────────────────────

def test_model_load_timeout():
    """ARCH-03: if worker never sends ready sentinel, start() raises RuntimeError."""
    from src.transcriber import WhisperTranscriber

    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    # Simulate timeout waiting for ready sentinel
    mock_result_q.get.side_effect = queue.Empty()

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    wt = WhisperTranscriber(on_update=MagicMock(), on_status=MagicMock())

    import pytest
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises((RuntimeError, TimeoutError)):
                wt.start()


# ── ARCH-03: crash restart ─────────────────────────────────────────────────────

def test_crash_restart():
    """ARCH-03: consecutive worker failures up to 3 → stopped=True after 3rd."""
    from src.transcriber import WhisperTranscriber

    # We'll track how many times Process is created (each restart = new process)
    procs_created = []

    def make_mock_proc():
        p = MagicMock()
        p.is_alive.return_value = True
        procs_created.append(p)
        return p

    ready = {"ok": True, "ready": True}
    # Four ready sentinels (one per spawn: initial + 2 restarts, then crashed on 3rd failure)
    # Four utterances all fail with queue.Empty
    ready_sentinel_count = [0]

    mock_audio_q = MagicMock()

    def make_result_q():
        rq = MagicMock()
        call_count = [0]

        def get_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call per queue: ready sentinel
                return ready
            # Subsequent calls: timeout
            raise queue.Empty()

        rq.get.side_effect = lambda **kwargs: get_side_effect(**kwargs)
        return rq

    mock_ctx = MagicMock()

    # Provide enough SimpleQueues for multiple spawns
    queues_provided = [MagicMock() for _ in range(20)]
    result_qs = []
    audio_qs = []

    def make_simple_q():
        # Alternate: audio_q, result_q, audio_q, result_q, ...
        if len(audio_qs) <= len(result_qs):
            q = MagicMock()
            audio_qs.append(q)
            return q
        else:
            rq = make_result_q()
            result_qs.append(rq)
            return rq

    mock_ctx.SimpleQueue.side_effect = make_simple_q
    mock_ctx.Process.side_effect = lambda **kwargs: make_mock_proc()

    statuses: list = []
    wt = WhisperTranscriber(on_update=MagicMock(), on_status=statuses.append)

    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()
            audio = np.zeros(16000, dtype=np.float32)
            # Each call fails with timeout → increments crash_count
            wt.transcribe_utterance(audio)  # crash 1 → restart
            wt.transcribe_utterance(audio)  # crash 2 → restart
            wt.transcribe_utterance(audio)  # crash 3 → stopped

    assert wt.stopped, "After 3 consecutive failures, transcriber should be stopped"
    assert "crashed" in statuses, f"Expected 'crashed' event, got: {statuses}"


def test_crash_counter_reset():
    """ARCH-03 + D-08: crash counter resets to 0 after a successful transcription."""
    from src.transcriber import WhisperTranscriber

    ready = {"ok": True, "ready": True}
    good = _make_good_result(" Good.")
    good2 = _make_good_result(" Also good.")

    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()

    # Sequence: ready, fail, ready (restart), succeed, fail, ready (restart), succeed
    # After failure+success: crash_count should be 0; second failure should not crash
    mock_result_q.get.side_effect = [
        ready,          # start() sentinel
        queue.Empty(),  # first utterance fails (crash_count → 1)
        ready,          # restart ready sentinel
        good,           # second utterance succeeds (crash_count → 0)
        queue.Empty(),  # third utterance fails (crash_count → 1, not 2)
        ready,          # restart ready sentinel
        good2,          # fourth utterance succeeds
    ]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = lambda: mock_audio_q if not mock_ctx._result_q_given else mock_result_q

    # Simpler approach: just return mock_result_q always
    audio_qs_given = [0]
    result_qs_given = [0]

    def sq_factory():
        # Odd calls → audio_q, even calls → result_q
        total = audio_qs_given[0] + result_qs_given[0]
        if total % 2 == 0:
            audio_qs_given[0] += 1
            return mock_audio_q
        else:
            result_qs_given[0] += 1
            return mock_result_q

    mock_ctx.SimpleQueue.side_effect = sq_factory
    mock_ctx.Process.return_value = mock_proc

    statuses: list = []
    wt = WhisperTranscriber(on_update=MagicMock(), on_status=statuses.append)
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    wt.transcribe_utterance(audio)  # fails, crash_count=1, restart
    wt.transcribe_utterance(audio)  # succeeds, crash_count=0
    wt.transcribe_utterance(audio)  # fails, crash_count=1 (not 2)
    wt.transcribe_utterance(audio)  # succeeds, crash_count=0

    assert not wt.stopped, "Should not be stopped — crash counter should have reset"
    assert "crashed" not in statuses, f"Unexpected 'crashed' event: {statuses}"


# ── generation-based restart ───────────────────────────────────────────────────

def test_generation_restart():
    """WhisperTranscriber recycles subprocess after WHISPER_MAX_GENERATIONS_BEFORE_RESTART."""
    from src.transcriber import WhisperTranscriber

    max_gen = config.WHISPER_MAX_GENERATIONS_BEFORE_RESTART  # 50

    procs = []

    def make_proc(**kwargs):
        p = MagicMock()
        p.is_alive.return_value = True
        procs.append(p)
        return p

    ready = {"ok": True, "ready": True}
    good = _make_good_result(" x.")

    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    # ready + max_gen successful results + ready (after restart)
    mock_result_q.get.side_effect = [ready] + [good] * (max_gen + 1) + [ready]

    mock_ctx = MagicMock()
    total_sq_calls = [0]

    def sq_factory():
        total_sq_calls[0] += 1
        if total_sq_calls[0] % 2 == 1:
            return mock_audio_q
        return mock_result_q

    mock_ctx.SimpleQueue.side_effect = sq_factory
    mock_ctx.Process.side_effect = make_proc

    wt = WhisperTranscriber(on_update=MagicMock(), on_status=MagicMock())
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    for _ in range(max_gen + 1):
        wt.transcribe_utterance(audio)

    # Should have spawned 2 processes: initial + recycle after max_gen
    assert len(procs) >= 2, (
        f"Expected subprocess recycle after {max_gen} generations, got {len(procs)} procs"
    )


# ── session accumulator ────────────────────────────────────────────────────────

def test_session_accumulator():
    """Second transcribe_utterance appends text to finalized_text and sentences list."""
    from src.transcriber import WhisperTranscriber

    ready = {"ok": True, "ready": True}
    result1 = _make_good_result(" First sentence.")
    result2 = _make_good_result(" Second sentence.")

    mock_proc = MagicMock()
    mock_proc.is_alive.return_value = True
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [ready, result1, result2]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.side_effect = [mock_audio_q, mock_result_q]
    mock_ctx.Process.return_value = mock_proc

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    audio = np.zeros(16000, dtype=np.float32)
    r1 = wt.transcribe_utterance(audio)
    r2 = wt.transcribe_utterance(audio)

    assert r1 is not None
    assert r2 is not None

    assert r1.text == "First sentence."
    assert r2.text == "Second sentence."

    # finalized_text accumulates
    assert "First sentence." in r2.finalized_text
    assert "Second sentence." in r2.finalized_text

    # sentences list grows
    assert len(r2.sentences) == 2
    assert r2.sentences[0] == "First sentence."
    assert r2.sentences[1] == "Second sentence."
