---
phase: 03-vad-integration
verified: 2026-03-27T09:00:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
---

# Phase 3: VAD Integration Verification Report

**Phase Goal:** Silero VAD owns the audio loop and emits complete utterance buffers to speech_q, so Whisper is never called on silence or sub-threshold fragments
**Verified:** 2026-03-27T09:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from Plan 03-01 must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Silence frames fed to VadThread produce zero entries in speech_q | VERIFIED | `test_silence_produces_no_utterance` passes; energy gate (`rms < VAD_MIN_ENERGY`) skips VAD scoring and never triggers on zero frames |
| 2 | Speech frames followed by 500ms silence emit a concatenated utterance to speech_q | VERIFIED | `test_speech_then_silence_emits_utterance` passes; `sil_frames = ceil(500/32) = 16`; `_seal_utterance` fires and puts float32 ndarray via `put_nowait` |
| 3 | Emitted utterance includes 300ms pre-buffer audio prepended before first speech frame | VERIFIED | `test_prebuffer_prepended_to_utterance` passes; `pre_frames = ceil(300/32) = 10`; `speech_buf = list(prebuf)` at trigger; utterance length > 20*512 confirmed |
| 4 | Emitted utterance includes 200ms post-buffer audio appended after silence detection | VERIFIED | `test_postbuffer_appended_to_utterance` passes; `_seal_utterance` collects up to `post_frames=7` additional frames after seal threshold |
| 5 | Frames with RMS below VAD_MIN_ENERGY (0.01) are not scored by the VAD model | VERIFIED | `test_low_energy_frames_rejected` passes; energy gate `continue` before `model(tensor, ...)` call; `model.assert_not_called()` confirmed |
| 6 | Utterances shorter than 500ms of speech frames are discarded | VERIFIED | `test_short_utterance_discarded` passes; `speech_frame_count` (not `len(speech_buf)`) checked against `min_frames=16`; 5-frame utterance discarded |

**Plan 03-01 score:** 6/6 truths verified

### Observable Truths (from Plan 03-02 must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 7 | VadThread replaces _pump_audio as the audio consumer in server.py | VERIFIED | `grep -c '_pump_audio' src/server.py` = 0; VadThread imported and instantiated at lines 33, 246 |
| 8 | speech_q bridges VadThread output to the existing transcriber via push_audio() | VERIFIED | `_bridge_speech_q()` at line 125 reads from `_speech_q`, calls `_transcriber.push_audio(utterance)` at line 135 |
| 9 | Stopping the pipeline cleanly shuts down VadThread before AudioCapture | VERIFIED | `_do_stop()`: `_capture.stop()` first (sends None sentinel to audio_q), then `_vad_thread.stop()` + `_vad_thread.wait(timeout=5.0)` |
| 10 | Energy emission thread is unchanged and still runs independently | VERIFIED | `_emit_energy()` reads `_capture.energy` property directly, not from the audio queue; started independently in `_do_start()` at line 252 |

**Plan 03-02 score:** 4/4 truths verified

**Overall score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | Expected | Lines | Status | Details |
|----------|----------|-------|--------|---------|
| `src/vad.py` | VadThread class with state machine | 182 | VERIFIED | Exports `VadThread`; min_lines=80 satisfied; `from . import config` present |
| `tests/test_vad.py` | Unit tests for VadThread — PIPE requirements | 238 | VERIFIED | 6 tests covering PIPE-01/02/03/D-08; min_lines=60 satisfied |
| `src/config.py` | CHUNK_DURATION=0.032, CHUNK_SAMPLES=512 | 40 | VERIFIED | `CHUNK_DURATION: float = 0.032`; `CHUNK_SAMPLES: int = int(SAMPLE_RATE * CHUNK_DURATION)` = 512 |
| `src/server.py` | VadThread wiring, speech_q bridge, _pump_audio removed | 406 | VERIFIED | `VadThread` referenced 4 times; `_pump_audio` references = 0; `_bridge_speech_q` defined |
| `requirements.txt` | silero-vad, torch, torchaudio entries | 11 | VERIFIED | All three entries present |

---

### Key Link Verification

**Plan 03-01 links:**

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/vad.py` | `src/config.py` | `from . import config` | WIRED | Line 19; `config.VAD_*` used at lines 65-68, 93, 112, 115 |
| `src/vad.py` | `silero_vad` | `load_silero_vad()` | WIRED | Line 17 import; line 61 call inside `_run()` |
| `tests/test_vad.py` | `src/vad.py` | `from src.vad import VadThread` | WIRED | Line 22; VadThread instantiated in `run_vad()` helper |

**Plan 03-02 links:**

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/server.py` | `src/vad.py` | `from .vad import VadThread` | WIRED | Line 33 import; lines 87, 246, 317 usage |
| `src/server.py` | `queue.Queue (speech_q)` | `_speech_q = queue.Queue(maxsize=10)` | WIRED | Line 245 in `_do_start()`; `_speech_q` referenced at lines 88, 129, 245, 294, 316 |
| `_bridge_speech_q` | `transcriber.push_audio` | `_transcriber.push_audio(utterance)` | WIRED | Line 135 in `_bridge_speech_q()`; `utterance` comes from `_speech_q.get()` at line 129 |

---

### Data-Flow Trace (Level 4)

VadThread is a processing thread, not a UI component. Data flow is through queues, not state rendering — Level 4 applies as a pipeline trace rather than a render check.

| Stage | Data Variable | Source | Produces Real Data | Status |
|-------|---------------|--------|--------------------|--------|
| AudioCapture -> audio_q | `frame: np.ndarray` | `sounddevice` callback writing 512-sample blocks | Yes — hardware mic audio | FLOWING |
| audio_q -> VadThread | `self._audio_q.get()` | AudioCapture._queue (same object, passed by reference at line 246) | Yes | FLOWING |
| VadThread -> speech_q | `utterance = np.concatenate(speech_buf)` | Accumulated real audio frames, not synthetic | Yes | FLOWING |
| speech_q -> transcriber | `_transcriber.push_audio(utterance)` | `_bridge_speech_q()` reads from `_speech_q` | Yes | FLOWING |

---

### Behavioral Spot-Checks

Server requires running audio hardware; full pipeline spot-check is a human verification item. Module-level checks:

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| VadThread importable | `python -c "from src.vad import VadThread; print('OK')"` | `VadThread importable: OK` | PASS |
| config.CHUNK_SAMPLES == 512 | `python -c "from src.config import CHUNK_SAMPLES; assert CHUNK_SAMPLES == 512"` | exit 0 | PASS |
| config.CHUNK_DURATION == 0.032 | `python -c "from src.config import CHUNK_DURATION; assert CHUNK_DURATION == 0.032"` | exit 0 | PASS |
| Full test suite | `python -m pytest tests/ -q` | `35 passed in 9.01s` | PASS |
| VAD tests (6) | `python -m pytest tests/test_vad.py -v` | `6 passed in 6.77s` (partial run) | PASS |
| _pump_audio absent from server.py | `grep -c '_pump_audio' src/server.py` | `0` | PASS |
| VadThread referenced >= 3 times in server.py | `grep -c 'VadThread' src/server.py` | `4` | PASS |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| PIPE-01 | 03-01, 03-02 | VAD detects speech boundaries using Silero VAD with configurable silence threshold | SATISFIED | VadThread state machine: `sil_frames` derived from `VAD_SILENCE_THRESHOLD_MS`; truths 1 & 2 verified by passing tests |
| PIPE-02 | 03-01, 03-02 | VAD applies 150-300ms silence padding before/after utterances to prevent word clipping | SATISFIED | 300ms pre-buffer (`pre_frames=10`) prepended at trigger; 200ms post-buffer (`post_frames=7`) collected in `_seal_utterance`; truths 3 & 4 verified by passing tests |
| PIPE-03 | 03-01, 03-02 | VAD rejects low-energy chunks below configurable noise floor | SATISFIED | Energy gate at line 93 checks `rms < config.VAD_MIN_ENERGY`; truth 5 verified by `test_low_energy_frames_rejected` with `model.assert_not_called()` |

**REQUIREMENTS.md traceability check:** All three IDs (PIPE-01, PIPE-02, PIPE-03) are marked `[x]` and mapped to Phase 3 in the traceability table. No orphaned requirements for this phase.

---

### Anti-Patterns Found

No anti-patterns detected. Scanned `src/vad.py`, `src/server.py`, `tests/test_vad.py` for:
- TODO/FIXME/HACK comments: none
- Empty implementations (`return null`, `return {}`, `return []`): none
- Placeholder text: none
- Console.log-only handlers: none (Python; no `print()` calls, all logging via `log.*`)

One notable observation (not a blocker): `src/server.py` still imports and uses `CoreMLTranscriber` / `StreamingTranscriber` (the old Parakeet transcriber) in `_load_model_with_timeout`. This is Phase 6 cleanup scope (CLEAN-01), not Phase 3. The VAD integration correctly feeds utterances to whichever transcriber is loaded — the pipeline contract is honored.

---

### Human Verification Required

#### 1. Live VAD Gating End-to-End

**Test:** Activate venv, run `python -m src.server`, send `{"cmd": "start", "data": {"engine": "coreml"}}`, speak one sentence, pause 2 seconds, speak a second sentence.
**Expected:** Two separate `transcript` events (one per utterance). Zero transcript events during the 2-second silence gap. No Python errors in stderr.
**Why human:** Requires live audio hardware, real Silero scoring (not mocked), and real-time observation of event timing. Cannot be verified without running the process with a microphone.

#### 2. Clean Shutdown with No Hanging Threads

**Test:** After verifying live transcription in item 1, send `{"cmd": "stop"}` and observe.
**Expected:** `{"event": "status", "data": "idle"}` emitted; process exits without hanging; no thread join timeouts logged to stderr.
**Why human:** Requires live process observation; automated checks cannot verify thread lifecycle at runtime.

---

### Gaps Summary

No gaps. All 10 must-have truths are verified, all 5 required artifacts pass all four levels (exist, substantive, wired, data-flowing), and all 6 key links are confirmed wired. The full test suite (35 tests) passes with no regressions. PIPE-01, PIPE-02, and PIPE-03 are satisfied.

---

_Verified: 2026-03-27T09:00:00Z_
_Verifier: Claude (gsd-verifier)_
