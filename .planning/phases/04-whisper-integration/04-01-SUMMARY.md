---
phase: 04-whisper-integration
plan: "01"
subsystem: transcription-engine
tags: [whisper, mlx, subprocess, tdd, hallucination-filter, watchdog]
dependency_graph:
  requires: [Phase 1 config.py, Phase 3 VadThread (speech_q)]
  provides: [WhisperTranscriber, TranscriptionUpdate, whisper_worker]
  affects: [server.py, telegram_sender.py, realtime_demo.py, coreml_transcriber.py]
tech_stack:
  added: [mlx-whisper==0.4.3]
  patterns:
    - spawn-context subprocess isolation for MLX thread safety
    - multiprocessing.Queue with timeout for result_q watchdog
    - hallucination filtering in parent process (D-07)
    - crash counter with 3-strike and success-reset (D-08)
    - generation-based subprocess recycle after 50 utterances
key_files:
  created:
    - src/whisper_worker.py
    - tests/test_whisper_transcriber.py
  modified:
    - src/transcriber.py
    - src/config.py
    - requirements.txt
decisions:
  - "Use multiprocessing.Queue (not SimpleQueue) for result_q — Queue supports get(timeout=...) needed for 15s watchdog; SimpleQueue does not. Deadlock risk mitigated by watchdog kill before shutdown."
  - "Patch src.transcriber.multiprocessing.get_context at module level in tests (not contextual) — ensures _spawn_worker calls inside transcribe_utterance are also mocked."
  - "clip_timestamps mentioned only in module docstring warning, not passed to mlx_whisper.transcribe() — compliant with plan anti-pattern requirement."
metrics:
  duration: 8min
  completed_date: "2026-03-27"
  tasks_completed: 1
  files_changed: 5
---

# Phase 4 Plan 1: Whisper Transcription Engine Summary

WhisperTranscriber subprocess-isolated transcription with hallucination filter, 15s watchdog, crash counter, and backward-compatible TranscriptionUpdate dataclass.

## What Was Built

**src/transcriber.py** — Complete rewrite. New `TranscriptionUpdate` dataclass adds `text`, `finalized_text`, `sentences`, `no_speech_prob`, `duration_s` (D-01). Old fields `draft_text`, `finalized_sentences`, `draft_sentences` kept for `coreml_transcriber.py` backward compat until Phase 6. New `WhisperTranscriber` class handles the full subprocess lifecycle:
- `start()`: spawns worker, waits for ready sentinel up to 120s (MODEL_LOAD_TIMEOUT_S), emits `downloading_model` or `loading_model` status
- `transcribe_utterance()`: sends audio to worker, waits up to 15s, applies hallucination filter, emits `error` event on timeout (D-06), resets crash counter on success, recycles subprocess at 50 generations
- `_on_failure()`: crash counter increments, restarts worker, emits `crashed` + stops at 3 consecutive failures (D-08)

**src/whisper_worker.py** — New file. `_whisper_worker(audio_q, result_q)` runs in spawn-context child. Imports `mlx_whisper`, calls `transcribe()` with `word_timestamps=False`, no `clip_timestamps`, `no_speech_threshold=None`, `compression_ratio_threshold=None` (filtering in parent per D-07). Emits `{"ok": True, "ready": True}` sentinel after import, `{"ok": True, "result": raw}` on success, `{"ok": False, "error": ...}` on exception.

**src/config.py** — Added `WHISPER_NO_SPEECH_THRESHOLD: float = 0.6` and `WHISPER_COMPRESSION_RATIO_THRESHOLD: float = 2.4`.

**requirements.txt** — Added `mlx-whisper==0.4.3`.

**tests/test_whisper_transcriber.py** — 16 TDD tests covering all plan requirements.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] multiprocessing.SimpleQueue lacks timeout support**
- **Found during:** Task 1 (GREEN phase, first test run)
- **Issue:** Plan specified `ctx.SimpleQueue()` for result_q, but `multiprocessing.SimpleQueue.get()` does not accept a `timeout` argument, breaking the 15s watchdog pattern
- **Fix:** Used `ctx.Queue()` for result_q only (Queue supports `get(timeout=...)`); kept `ctx.SimpleQueue()` for audio_q (parent→worker, no timeout needed). Queue's background feeder thread deadlock risk is mitigated by watchdog kill before any shutdown drain.
- **Files modified:** `src/transcriber.py`, `tests/test_whisper_transcriber.py`

**2. [Rule 1 - Bug] Test patches scoped too narrowly for _on_failure restart**
- **Found during:** Task 1 (GREEN phase, watchdog timeout test)
- **Issue:** Initial tests patched `multiprocessing.get_context` in a `with` block only wrapping `wt.start()`. When `wt.transcribe_utterance()` triggered `_on_failure()` → `_spawn_worker()`, the patch was no longer active, causing real `multiprocessing.get_context("spawn")` to be called.
- **Fix:** Updated all tests to patch `src.transcriber.multiprocessing.get_context` at module level, wrapping both `start()` and `transcribe_utterance()` calls.
- **Files modified:** `tests/test_whisper_transcriber.py`

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| multiprocessing.Queue for result_q (not SimpleQueue) | SimpleQueue.get() has no timeout; Queue.get(timeout=...) needed for 15s watchdog. Deadlock risk negligible with watchdog kill. |
| Module-level patch for multiprocessing.get_context in tests | _spawn_worker called from both start() and _on_failure() inside transcribe_utterance(); patch must cover entire test scope |

## Verification Results

```
python -m pytest tests/test_whisper_transcriber.py -x -v    → 16/16 PASSED
python -m pytest tests/test_config.py -x                    → 25/25 PASSED
python -c "from src.transcriber import TranscriptionUpdate; ..." → OK (backward compat)
grep -c 'class StreamingTranscriber' src/transcriber.py     → 0
grep -c 'def load_model' src/transcriber.py                 → 0
grep 'class WhisperTranscriber' src/transcriber.py          → 1 match
grep 'def _whisper_worker' src/whisper_worker.py            → 1 match
grep 'clip_timestamps' src/whisper_worker.py (in call)      → 0 (comment only)
```

## Known Stubs

None — all plan requirements implemented and tested.

## Self-Check: PASSED
