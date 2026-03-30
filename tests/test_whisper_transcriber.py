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
from unittest.mock import MagicMock, patch

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


def _make_mock_proc():
    """Return a mock subprocess Process."""
    p = MagicMock()
    p.is_alive.return_value = True
    return p


def _make_ctx(audio_q, result_q, proc):
    """Return a mock multiprocessing context."""
    ctx = MagicMock()
    ctx.SimpleQueue.return_value = audio_q
    ctx.Queue.return_value = result_q
    ctx.Process.return_value = proc
    return ctx


# ── ARCH-04: TranscriptionUpdate contract ─────────────────────────────────────

def test_transcription_update_fields():
    """ARCH-04: TranscriptionUpdate has all required fields."""
    from src.transcriber import TranscriptionUpdate

    t = TranscriptionUpdate()
    field_names = {f.name for f in dc_fields(t)}

    # Required fields (per D-01)
    assert "text" in field_names, "Missing field: text"
    assert "finalized_text" in field_names, "Missing field: finalized_text"
    assert "sentences" in field_names, "Missing field: sentences"
    assert "no_speech_prob" in field_names, "Missing field: no_speech_prob"
    assert "duration_s" in field_names, "Missing field: duration_s"

    # Default values
    assert t.text == ""
    assert t.finalized_text == ""
    assert t.sentences == []
    assert t.no_speech_prob == 0.0
    assert t.duration_s == 0.0


# ── config hallucination thresholds ───────────────────────────────────────────

def test_config_hallucination_thresholds():
    """config.py must have the hallucination filter thresholds."""
    assert hasattr(config, "WHISPER_NO_SPEECH_THRESHOLD"), "Missing WHISPER_NO_SPEECH_THRESHOLD"
    assert hasattr(config, "WHISPER_COMPRESSION_RATIO_THRESHOLD"), "Missing WHISPER_COMPRESSION_RATIO_THRESHOLD"
    assert config.WHISPER_NO_SPEECH_THRESHOLD == 0.8
    assert config.WHISPER_COMPRESSION_RATIO_THRESHOLD == 3.0


# ── PIPE-05: spawn context ─────────────────────────────────────────────────────

def test_spawn_context():
    """PIPE-05: _spawn_worker uses mp.get_context('spawn'), not fork."""
    from src.transcriber import WhisperTranscriber

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.return_value = {"ok": True, "ready": True}

    mock_ctx = _make_ctx(mock_audio_q, mock_result_q, mock_proc)

    wt = WhisperTranscriber(on_update=MagicMock(), on_status=MagicMock())
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx) as mock_get_ctx:
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()

    mock_get_ctx.assert_called_once_with("spawn")


# ── PIPE-04: transcribe returns TranscriptionUpdate ───────────────────────────

def test_transcribe_returns_update():
    """PIPE-04: transcribe_utterance returns a TranscriptionUpdate on success."""
    from src.transcriber import TranscriptionUpdate, WhisperTranscriber

    ready = {"ok": True, "ready": True}
    good_result = _make_good_result(" Hello world.")

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [ready, good_result]

    mock_ctx = _make_ctx(mock_audio_q, mock_result_q, mock_proc)

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())

    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
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

    ready = {"ok": True, "ready": True}
    bad_result = _make_good_result(no_speech_prob=0.9)

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [ready, bad_result]

    mock_ctx = _make_ctx(mock_audio_q, mock_result_q, mock_proc)

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()
            audio = np.zeros(16000, dtype=np.float32)
            result = wt.transcribe_utterance(audio)

    assert result is None, "High no_speech_prob should be filtered"
    assert len(updates) == 0, "No update should be emitted for hallucination"


def test_hallucination_filter_compression():
    """PIPE-06: compression_ratio > 3.0 → transcribe_utterance returns None."""
    from src.transcriber import WhisperTranscriber

    ready = {"ok": True, "ready": True}
    bad_result = _make_good_result(compression_ratio=3.5)

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [ready, bad_result]

    mock_ctx = _make_ctx(mock_audio_q, mock_result_q, mock_proc)

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()
            audio = np.zeros(16000, dtype=np.float32)
            result = wt.transcribe_utterance(audio)

    assert result is None, "High compression_ratio should be filtered"


def test_hallucination_filter_empty_text():
    """PIPE-06: empty text → transcribe_utterance returns None."""
    from src.transcriber import WhisperTranscriber

    ready = {"ok": True, "ready": True}
    empty_result = _make_good_result(text="")

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [ready, empty_result]

    mock_ctx = _make_ctx(mock_audio_q, mock_result_q, mock_proc)

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()
            audio = np.zeros(16000, dtype=np.float32)
            result = wt.transcribe_utterance(audio)

    assert result is None, "Empty text should be filtered"


def test_hallucination_filter_passes_good_result():
    """PIPE-06: valid result (low no_speech_prob, normal compression, non-empty) passes through."""
    from src.transcriber import WhisperTranscriber

    ready = {"ok": True, "ready": True}
    good_result = _make_good_result(text=" hello", no_speech_prob=0.2, compression_ratio=1.5)

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [ready, good_result]

    mock_ctx = _make_ctx(mock_audio_q, mock_result_q, mock_proc)

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
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

    ready = {"ok": True, "ready": True}

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()

    # First result_q used for initial start + first utterance (times out)
    mock_result_q_1 = MagicMock()
    mock_result_q_1.get.side_effect = [ready, queue.Empty()]

    # Second result_q for the restart after timeout
    mock_result_q_2 = MagicMock()
    mock_result_q_2.get.return_value = ready

    mock_ctx = MagicMock()
    # Each _spawn_worker call gets a new audio_q + result_q pair
    mock_ctx.SimpleQueue.return_value = mock_audio_q
    mock_ctx.Queue.side_effect = [mock_result_q_1, mock_result_q_2]
    mock_ctx.Process.return_value = mock_proc

    statuses: list = []
    wt = WhisperTranscriber(on_update=MagicMock(), on_status=statuses.append)
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()
            audio = np.zeros(16000, dtype=np.float32)
            result = wt.transcribe_utterance(audio)

    assert result is None, "Timeout should return None"
    mock_proc.kill.assert_called()


def test_watchdog_timeout_emits_error_event():
    """ARCH-03 + D-06: timeout path emits on_status('error') before failure handling."""
    from src.transcriber import WhisperTranscriber

    ready = {"ok": True, "ready": True}

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()

    mock_result_q_1 = MagicMock()
    mock_result_q_1.get.side_effect = [ready, queue.Empty()]

    mock_result_q_2 = MagicMock()
    mock_result_q_2.get.return_value = ready

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.return_value = mock_audio_q
    mock_ctx.Queue.side_effect = [mock_result_q_1, mock_result_q_2]
    mock_ctx.Process.return_value = mock_proc

    statuses: list = []
    wt = WhisperTranscriber(on_update=MagicMock(), on_status=statuses.append)
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
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

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    # Simulate timeout waiting for ready sentinel
    mock_result_q.get.side_effect = queue.Empty()

    mock_ctx = _make_ctx(mock_audio_q, mock_result_q, mock_proc)

    wt = WhisperTranscriber(on_update=MagicMock(), on_status=MagicMock())

    import pytest
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises((RuntimeError, TimeoutError)):
                wt.start()


# ── ARCH-03: crash restart ─────────────────────────────────────────────────────

def test_crash_restart():
    """ARCH-03: consecutive worker failures up to 3 → stopped=True after 3rd."""
    from src.transcriber import WhisperTranscriber

    ready = {"ok": True, "ready": True}

    # We need enough result_qs:
    # - start() uses rq_1: returns ready
    # - utterance 1 → queue.Empty on rq_1 → _on_failure → _spawn_worker → rq_2 returns ready
    # - utterance 2 → queue.Empty on rq_2 → _on_failure → _spawn_worker → rq_3 returns ready
    # - utterance 3 → queue.Empty on rq_3 → _on_failure → crash_count=3, stopped=True

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()

    rq_1 = MagicMock()
    rq_1.get.side_effect = [ready, queue.Empty()]

    rq_2 = MagicMock()
    rq_2.get.side_effect = [ready, queue.Empty()]

    rq_3 = MagicMock()
    rq_3.get.side_effect = [ready, queue.Empty()]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.return_value = mock_audio_q
    mock_ctx.Queue.side_effect = [rq_1, rq_2, rq_3]
    mock_ctx.Process.return_value = mock_proc

    statuses: list = []
    wt = WhisperTranscriber(on_update=MagicMock(), on_status=statuses.append)

    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()
            audio = np.zeros(16000, dtype=np.float32)
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

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()

    # Sequence:
    # start()       rq_1: ready
    # utterance 1   rq_1: Empty → crash_count=1 → restart, rq_2: ready
    # utterance 2   rq_2: good  → crash_count=0
    # utterance 3   rq_2: Empty → crash_count=1 (not 2) → restart, rq_3: ready
    # utterance 4   rq_3: good  → crash_count=0

    rq_1 = MagicMock()
    rq_1.get.side_effect = [ready, queue.Empty()]

    rq_2 = MagicMock()
    rq_2.get.side_effect = [ready, good, queue.Empty()]

    rq_3 = MagicMock()
    rq_3.get.side_effect = [ready, good2]

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.return_value = mock_audio_q
    mock_ctx.Queue.side_effect = [rq_1, rq_2, rq_3]
    mock_ctx.Process.return_value = mock_proc

    statuses: list = []
    wt = WhisperTranscriber(on_update=MagicMock(), on_status=statuses.append)
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
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

    ready = {"ok": True, "ready": True}
    good = _make_good_result(" x.")

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()

    # rq_1: ready + max_gen successful results
    # rq_2: ready (after recycle)
    # rq_1 also handles the (max_gen+1)th call which triggers recycle
    # After recycle, rq_2 handles ready sentinel
    rq_1 = MagicMock()
    rq_1.get.side_effect = [ready] + [good] * max_gen

    rq_2 = MagicMock()
    rq_2.get.side_effect = [ready, good]  # ready for recycle + one more utterance

    mock_ctx = MagicMock()
    mock_ctx.SimpleQueue.return_value = mock_audio_q
    mock_ctx.Queue.side_effect = [rq_1, rq_2]

    procs_created = []
    def make_proc(**kwargs):
        p = _make_mock_proc()
        procs_created.append(p)
        return p

    mock_ctx.Process.side_effect = make_proc

    wt = WhisperTranscriber(on_update=MagicMock(), on_status=MagicMock())
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
        with patch("pathlib.Path.exists", return_value=True):
            wt.start()
            audio = np.zeros(16000, dtype=np.float32)
            # max_gen utterances → triggers recycle on the max_gen-th
            for _ in range(max_gen):
                wt.transcribe_utterance(audio)

    # Should have spawned 2 processes: initial + recycle
    assert len(procs_created) >= 2, (
        f"Expected subprocess recycle after {max_gen} generations, got {len(procs_created)} procs"
    )


# ── session accumulator ────────────────────────────────────────────────────────

def test_session_accumulator():
    """Second transcribe_utterance appends text to finalized_text and sentences list."""
    from src.transcriber import WhisperTranscriber

    ready = {"ok": True, "ready": True}
    result1 = _make_good_result(" First sentence.")
    result2 = _make_good_result(" Second sentence.")

    mock_proc = _make_mock_proc()
    mock_audio_q = MagicMock()
    mock_result_q = MagicMock()
    mock_result_q.get.side_effect = [ready, result1, result2]

    mock_ctx = _make_ctx(mock_audio_q, mock_result_q, mock_proc)

    updates: list = []
    wt = WhisperTranscriber(on_update=updates.append, on_status=MagicMock())
    with patch("src.transcriber.multiprocessing.get_context", return_value=mock_ctx):
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


# ── session memory cap ────────────────────────────────────────────────────────

def test_sentences_capped_at_500():
    """_sentences list doesn't grow beyond 500 entries."""
    from src.transcriber import WhisperTranscriber

    wt = WhisperTranscriber(on_update=MagicMock(), on_status=MagicMock())
    wt._sentences = [f"sentence {i}" for i in range(600)]
    wt._finalized_text = " ".join(wt._sentences)

    audio = np.zeros(16000, dtype=np.float32)
    result = {
        "text": " New sentence.",
        "segments": [{"no_speech_prob": 0.1, "compression_ratio": 1.2, "text": "New sentence."}],
    }
    update = wt._build_update(result, audio)

    assert len(wt._sentences) <= 500
    assert "New sentence." in wt._sentences[-1]
