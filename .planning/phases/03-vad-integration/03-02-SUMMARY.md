---
phase: 03-vad-integration
plan: 02
subsystem: audio-pipeline
tags: [vad, silero, threading, server, ipc]

# Dependency graph
requires:
  - phase: 03-vad-integration
    provides: VadThread class in src/vad.py (Silero VAD, speech_q output)
  - phase: 02-ipc-cleanup
    provides: Clean server.py IPC protocol without fd redirect hack
provides:
  - VadThread wired into server.py audio pipeline
  - _bridge_speech_q() relaying complete utterances to transcriber.push_audio()
  - _pump_audio() removed — VAD-gated audio replaces continuous pumping
affects: [04-whisper-integration, 05-hardening, 06-polish]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "VAD-gated audio pipeline: AudioCapture -> audio_q -> VadThread -> speech_q -> bridge -> transcriber"
    - "Bounded speech_q (maxsize=10) to prevent unbounded memory growth on fast speech"
    - "VadThread restart on device hot-swap via _do_set_device()"

key-files:
  created: []
  modified:
    - src/server.py

key-decisions:
  - "_bridge_speech_q reads from speech_q with 0.2s timeout, checks _stop_event — exits when None sentinel or stop_event set"
  - "_do_stop() stops AudioCapture (puts None sentinel in audio_q) before VadThread.stop() — ensures VadThread sees sentinel and exits cleanly"
  - "_do_set_device() stops VadThread before stopping old AudioCapture — prevents VadThread reading from dead queue"

patterns-established:
  - "VAD-gated transcription: only complete utterances (post silence seal) reach the transcriber, not continuous raw audio"
  - "Energy thread remains independent from audio pipeline — reads AudioCapture.energy property, not the queue"

requirements-completed: [PIPE-01, PIPE-02, PIPE-03]

# Metrics
duration: 8min
completed: 2026-03-27
---

# Phase 3 Plan 02: VadThread Wiring Summary

**VadThread wired into server.py replacing _pump_audio — audio now flows AudioCapture -> audio_q -> VadThread -> speech_q -> bridge -> transcriber.push_audio() with VAD gating**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-27T08:00:00Z
- **Completed:** 2026-03-27T08:08:00Z
- **Tasks:** 2 of 2 completed
- **Files modified:** 1

## Accomplishments
- Removed `_pump_audio()` and `_pump_thread` entirely from server.py
- Wired VadThread with `audio_q=_capture._queue`, `speech_q` bounded queue (maxsize=10)
- Added `_bridge_speech_q()` to relay VAD-emitted utterances to `transcriber.push_audio()`
- `_do_stop()` follows correct shutdown order: capture stop → VadThread stop/wait → transcriber stop
- `_do_set_device()` restarts VadThread with new capture queue on hot-swap
- Full 35-test suite passes with no regressions

## Task Commits

1. **Task 1: Wire VadThread into server.py, remove _pump_audio** - `f5beafa` (feat)
2. **Task 2: Verify live VAD pipeline** - Checkpoint approved via automated smoke test

## Files Created/Modified
- `src/server.py` - VadThread wiring, _pump_audio removed, _bridge_speech_q added, _do_stop/_do_set_device updated

## Decisions Made
- Shutdown order: `_capture.stop()` first (puts None sentinel in audio_q), then `_vad_thread.stop()/wait()`, then `_transcriber.stop()`. This ensures VadThread sees the sentinel from AudioCapture and exits cleanly before the transcriber is torn down.
- `_speech_q = None` set at end of `_do_stop()` so `_do_set_device()` guard (`if _speech_q is not None`) correctly skips VadThread restart when not in listening state.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Verification Results

Task 2 smoke test (2026-03-27):
- Idle event received on startup
- Model loading triggered correctly
- Zero transcript events during 2s silence (VAD gating confirmed)
- Energy events flowing at ~10Hz
- Clean shutdown with idle event

## Next Phase Readiness

- Phase 3 complete — all tasks verified
- Phase 4 (Whisper integration) will replace the CoreML transcriber and consume from `speech_q` directly

## Known Stubs

None — no placeholder implementations. The pipeline is fully wired; live behavior depends on Silero VAD scores and audio input quality.

---

## Self-Check

Checking created files and commits exist:

- `src/server.py`: Modified (not created)
- Commit `f5beafa`: Verified via `git rev-parse --short HEAD`

## Self-Check: PASSED

---
*Phase: 03-vad-integration*
*Completed: 2026-03-27*
