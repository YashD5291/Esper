---
phase: 03-vad-integration
plan: 01
subsystem: audio-pipeline
tags: [silero-vad, torch, torchaudio, vad, threading, state-machine, tdd]

# Dependency graph
requires:
  - phase: 01-config-consolidation
    provides: "src/config.py with VAD constants (VAD_FRAME_SIZE, VAD_SPEECH_THRESHOLD, VAD_SILENCE_THRESHOLD_MS, VAD_MIN_SPEECH_DURATION_MS, VAD_MIN_ENERGY)"
  - phase: 02-ipc-cleanup
    provides: "clean server.py structure with daemon thread patterns"
provides:
  - VadThread class in src/vad.py — Silero VAD state machine with pre/post buffer and energy gate
  - 6 unit tests in tests/test_vad.py covering PIPE-01, PIPE-02, PIPE-03, D-08
  - Config updated: CHUNK_DURATION=0.032, CHUNK_SAMPLES=512 (512-sample Silero frames)
  - silero-vad, torch, torchaudio added to requirements.txt
affects: [04-whisper-integration, 03-02-server-wiring]

# Tech tracking
tech-stack:
  added:
    - silero-vad 6.2.1 (Silero VAD model, JIT-bundled, CPU-only)
    - torch 2.11.0 (PyTorch runtime for Silero)
    - torchaudio 2.11.0 (required silero-vad dep)
  patterns:
    - Daemon thread state machine with threading.Event stop signal
    - Pre-buffer via collections.deque(maxlen=N) for O(1) rolling window
    - Energy gate (RMS check) before VAD model scoring — reduces compute on silence
    - put_nowait on bounded speech_q to avoid blocking VAD thread
    - model.reset_states() after each utterance (Silero LSTM state management)
    - Speech frame count tracked separately from total buffer for min-duration check

key-files:
  created:
    - src/vad.py (VadThread class, 182 lines)
    - tests/test_vad.py (6 unit tests, 240 lines)
  modified:
    - src/config.py (CHUNK_DURATION 0.1→0.032, CHUNK_SAMPLES 1600→512)
    - tests/test_config.py (updated chunk duration/samples assertions)
    - requirements.txt (added silero-vad, torch, torchaudio)

key-decisions:
  - "min_frames check uses speech_frame_count (frames with prob >= threshold), not total speech_buf length — silence frames in buffer would inflate count and let short utterances pass the D-08 filter"
  - "prebuf.append(frame) placed BEFORE energy gate — low-energy frames still enter pre-buffer so audio is available when speech starts (Pitfall 1 prevention)"
  - "CHUNK_DURATION=0.032 derived via int(SAMPLE_RATE * CHUNK_DURATION) expression — derivation stays correct at 512"

patterns-established:
  - "Pattern: Append to prebuf first, then apply energy gate — ensures no gaps in pre-buffer"
  - "Pattern: Track speech_frame_count separately for min-duration filtering, not len(speech_buf)"
  - "Pattern: model.reset_states() in _seal_utterance regardless of emit/discard decision"

requirements-completed: [PIPE-01, PIPE-02, PIPE-03]

# Metrics
duration: 7min
completed: 2026-03-27
---

# Phase 3 Plan 1: VAD Integration — VadThread Summary

**Silero VAD daemon thread with 300ms pre-buffer, 200ms post-buffer, energy gate, and min-duration filter emitting float32 utterances to speech_q**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-27T06:54:42Z
- **Completed:** 2026-03-27T07:01:20Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- VadThread state machine: Silero VAD scoring per 512-sample frame, pre-buffer prepend, post-buffer append, energy gate, min-duration discard, non-blocking speech_q put
- 6 unit tests covering all PIPE requirements — all pass with mocked Silero model
- Config chunk constants updated (CHUNK_DURATION=0.032, CHUNK_SAMPLES=512) — AudioCapture automatically picks up change via config reference
- silero-vad 6.2.1, torch 2.11.0, torchaudio 2.11.0 installed and added to requirements.txt

## Task Commits

1. **Task 1: Install deps, update config, write failing VAD tests (TDD RED)** - `104a16c` (test)
2. **Task 2: Implement VadThread (TDD GREEN)** - `195957d` (feat)

**Plan metadata:** (docs commit — see below)

_Note: TDD RED committed first as test-only, then GREEN as feat._

## Files Created/Modified

- `src/vad.py` — VadThread daemon thread, full Silero VAD state machine
- `tests/test_vad.py` — 6 unit tests with mocked Silero model; covers PIPE-01/02/03 + D-08
- `src/config.py` — CHUNK_DURATION changed 0.1→0.032, CHUNK_SAMPLES 1600→512, QUEUE_MAXSIZE comment updated
- `tests/test_config.py` — Updated chunk_duration and chunk_samples assertions
- `requirements.txt` — Added silero-vad, torch, torchaudio

## Decisions Made

- **speech_frame_count separate from speech_buf length:** The total buffer includes pre-buffer and silence frames. If `len(speech_buf)` was used for the min-duration check, a 5-frame speech utterance accumulating 16 silence frames before sealing would have `len(speech_buf)=21 >= 16` and pass incorrectly. Tracking only frames where `speech_prob >= threshold` correctly implements D-08.
- **prebuf.append before energy gate:** Per Pitfall 1 in RESEARCH.md — ensures quiet frames at utterance onset are preserved in pre-buffer so the first phoneme isn't clipped.
- **CHUNK_DURATION kept as derived expression:** `int(SAMPLE_RATE * CHUNK_DURATION)` still evaluates to exactly 512 at 0.032, keeping the `test_chunk_samples_derived_correctly` test passing without special-casing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed speech_frame_count logic for min-duration check**

- **Found during:** Task 2 (VadThread implementation, TDD GREEN attempt)
- **Issue:** `len(speech_buf)` includes pre-buffer frames and silence frames. With 5 speech frames followed by 16 silence frames, `speech_buf` had 21 total frames (> 16 minimum), causing the short utterance to be emitted instead of discarded.
- **Fix:** Added `speech_frame_count` state variable tracking only frames with `speech_prob >= VAD_SPEECH_THRESHOLD`. Used `speech_frame_count >= min_frames` in `_seal_utterance` instead of `len(speech_buf)`.
- **Files modified:** src/vad.py
- **Verification:** `test_short_utterance_discarded` passes; all 6 VAD tests green
- **Committed in:** `195957d` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — logic bug)
**Impact on plan:** Required fix for correct D-08 behavior. No scope creep.

## Issues Encountered

- First TDD GREEN run: `test_short_utterance_discarded` failed — traced to `len(speech_buf)` including silence frames inflating the count past `min_frames`. Diagnosed via manual trace, fixed with `speech_frame_count` counter tracking confirmed speech frames only.

## User Setup Required

None — silero-vad is installed in `.venv` via pip.

## Next Phase Readiness

- VadThread API (`start()`, `stop()`, `wait()`) ready for server.py wiring (Plan 03-02)
- AudioCapture will automatically use 512-sample blocks via `config.CHUNK_SAMPLES`
- speech_q interface: `queue.Queue`, each item is `np.ndarray` of shape `(N,)` dtype float32
- Full test suite (35 tests) green — no regressions from config change

## Self-Check: PASSED

- FOUND: src/vad.py
- FOUND: tests/test_vad.py
- FOUND: 03-01-SUMMARY.md
- FOUND: commit 104a16c (test: install deps, update config, failing VAD tests)
- FOUND: commit 195957d (feat: VadThread implementation)

---
*Phase: 03-vad-integration*
*Completed: 2026-03-27*
