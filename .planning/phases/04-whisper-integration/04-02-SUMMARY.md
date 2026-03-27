---
phase: 04-whisper-integration
plan: "02"
subsystem: transcription-engine
tags: [whisper, vad, telegram, ipc, per-utterance, subprocess]

requires:
  - phase: 04-01
    provides: "WhisperTranscriber, TranscriptionUpdate with per-utterance shape"
  - phase: 03-vad-integration
    provides: "VadThread (speech_q interface)"
  - phase: 02-ipc-cleanup
    provides: "protocol-fd IPC for server.py"
  - phase: 01-config-consolidation
    provides: "config.py with SAMPLE_RATE, MODEL_LOAD_TIMEOUT_S, WHISPER_* constants"
provides:
  - "server.py wired to WhisperTranscriber with per-utterance transcript event shape"
  - "telegram_sender.py simplified to one message per utterance (D-03)"
  - "realtime_demo.py using WhisperTranscriber + VadThread pipeline"
  - "tests/test_telegram_sender.py with 7 TDD tests covering per-utterance model"
affects: [04-03, 05-telegram-hardening, 06-cleanup]

tech-stack:
  added: []
  patterns:
    - _whisper_consumer thread in server.py: reads speech_q, calls transcribe_utterance, emits transcribing/listening status (D-02)
    - per-utterance Telegram sending: on_update enqueues update.text.strip() directly, one message per utterance (D-03)
    - SimplerConsoleRenderer: no draft/finalized tracking, single write per utterance
    - VadThread + WhisperTranscriber consumer thread: canonical pipeline pattern for both server.py and realtime_demo.py

key-files:
  created:
    - tests/test_telegram_sender.py
  modified:
    - src/server.py
    - src/telegram_sender.py
    - src/realtime_demo.py

key-decisions:
  - "_whisper_consumer replaces _bridge_speech_q — emits transcribing/listening status events flanking each transcribe_utterance call (D-02)"
  - "TelegramSender stream parameter kept for API compat but ignored — per-utterance is always used now (D-03)"
  - "realtime_demo --record saves speech-only utterances from speech_q (not full raw audio stream) — simpler and more useful"
  - "SAMPLE_RATE imported from config (not audio_capture) — audio_capture.py no longer exports this constant"

patterns-established:
  - "Per-utterance transcript shape: {text, finalized_text, sentences, no_speech_prob, duration_s}"
  - "Status event sequence around each utterance: transcribing → (on_update) → listening"
  - "Server and CLI use identical VadThread + WhisperTranscriber consumer thread pattern"

requirements-completed: [ARCH-04, PIPE-04]

duration: 18min
completed: "2026-03-27"
---

# Phase 4 Plan 2: Whisper Pipeline Wiring Summary

**server.py, telegram_sender.py, and realtime_demo.py all wired to WhisperTranscriber with per-utterance transcript shape, replacing the Parakeet streaming model end-to-end**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-03-27
- **Completed:** 2026-03-27
- **Tasks:** 3
- **Files modified:** 4 (src/server.py, src/telegram_sender.py, src/realtime_demo.py, tests/test_telegram_sender.py created)

## Accomplishments

- server.py now uses WhisperTranscriber with `_whisper_consumer` thread that emits `transcribing`/`listening` status events per D-02, and emits the per-utterance transcript shape (`text`, `finalized_text`, `sentences`, `no_speech_prob`, `duration_s`) replacing the old Parakeet shape
- telegram_sender.py simplified from ~160 lines to ~80: removed `_processed_chars`, `_draft_buf`, `_draft_id`, `_process_streaming`, `_send_draft`; now sends `update.text.strip()` once per utterance per D-03
- realtime_demo.py uses WhisperTranscriber + VadThread pipeline, removes all Parakeet engine selection (`--engine`, `--buffer`, `--feed-interval`, `--context-size`, `--depth`), simplifies ConsoleRenderer to single-line per utterance
- 7 TDD tests in `tests/test_telegram_sender.py` verify per-utterance model, empty/whitespace filtering, single-message guarantee, and queue type

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite server.py for WhisperTranscriber integration** - `e1a86ce` (feat)
2. **Task 2 (RED): Failing tests for per-utterance TelegramSender** - `0c33ea1` (test)
3. **Task 2 (GREEN): Rewrite TelegramSender for per-utterance model** - `966e939` (feat)
4. **Task 3: Update realtime_demo.py ConsoleRenderer for per-utterance model** - `efbad93` (feat)

## Files Created/Modified

- `src/server.py` — WhisperTranscriber integration, new transcript shape, `_whisper_consumer`, `_on_status` callback
- `src/telegram_sender.py` — Per-utterance sending, all streaming/draft code removed
- `src/realtime_demo.py` — WhisperTranscriber + VadThread pipeline, simplified ConsoleRenderer
- `tests/test_telegram_sender.py` — 7 TDD tests for per-utterance model (new file)

## Decisions Made

- `_whisper_consumer` replaces `_bridge_speech_q` — the consumer emits `transcribing`/`listening` status events flanking each `transcribe_utterance` call, giving the UI precise feedback on Whisper processing state (D-02)
- `TelegramSender.stream` parameter kept for API compatibility (server.py still passes it from telegram config) but is now a no-op — all sends are per-utterance
- `realtime_demo --record` now saves speech-only utterances from `speech_q`, not the full raw audio stream. This is a deliberate behavioral change: speech-only recordings are more useful and avoid needing a separate audio tap alongside VadThread
- `SAMPLE_RATE` imported from `config` (not `audio_capture`) — `audio_capture.py` no longer exports it after Phase 1 config consolidation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SAMPLE_RATE import from wrong module**
- **Found during:** Task 3 (realtime_demo.py rewrite)
- **Issue:** realtime_demo.py imported `SAMPLE_RATE` from `audio_capture`, but `audio_capture.py` no longer exports this constant after Phase 1 config consolidation — it now uses `config.SAMPLE_RATE` internally
- **Fix:** Changed `from .audio_capture import AudioCapture, SAMPLE_RATE, list_devices` to `from .audio_capture import AudioCapture, list_devices` and added `from . import config`, then changed `SAMPLE_RATE` reference to `config.SAMPLE_RATE`
- **Files modified:** `src/realtime_demo.py`
- **Verification:** `from src.realtime_demo import main` imports cleanly
- **Committed in:** `efbad93` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 bug)
**Impact on plan:** Necessary import fix — no scope creep.

## Issues Encountered

None beyond the auto-fixed SAMPLE_RATE import issue above.

## Known Stubs

None — all plan requirements implemented.

## Next Phase Readiness

- All three Python consumers wired to WhisperTranscriber with the per-utterance contract
- Ready for Plan 03: Swift client updates to consume new transcript event shape
- Full test suite (58 tests) passing

---
*Phase: 04-whisper-integration*
*Completed: 2026-03-27*
