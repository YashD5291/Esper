---
phase: 01-config-consolidation
plan: 02
subsystem: config
tags: [python, config, telegram, ipc]

# Dependency graph
requires:
  - phase: 01-config-consolidation plan 01
    provides: src/config.py with all tunable constants including TELEGRAM_*, SAMPLE_RATE, MODEL_LOAD_TIMEOUT_S, DEFAULT_ENGINE, ENERGY_EMIT_INTERVAL_S
provides:
  - telegram_sender.py reads retry/backoff/draft interval from config (no local constants)
  - server.py uses config for timeout (120s), engine default, energy interval, Telegram credential mutation
  - realtime_demo.py writes Telegram creds to config after load_dotenv(), uses config.SAMPLE_RATE
affects: [02-ipc-cleanup, 03-vad, 04-whisper]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Entry-point mutation pattern — server._do_start and realtime_demo.main mutate config.* before constructing dependent objects
    - from . import config — module-import enables runtime mutation visible to all callers

key-files:
  created: []
  modified:
    - src/telegram_sender.py
    - src/server.py
    - src/realtime_demo.py

key-decisions:
  - "TelegramSender.__init__ signature kept unchanged (bot_token, chat_id, stream=True) — cleanup deferred to Phase 5 per RESEARCH.md"
  - "Config mutation in server.py placed before TelegramSender construction so credentials are set before any downstream reads"

patterns-established:
  - "Entry-point mutation: set config.TELEGRAM_* before constructing TelegramSender"
  - "No module outside config.py defines tunables — all leaf modules read from config"

requirements-completed: [ARCH-01]

# Metrics
duration: 4min
completed: 2026-03-26
---

# Phase 01 Plan 02: Config Consolidation (Entry Points) Summary

**Telegram credentials, model timeout, engine default, and audio constants unified into config.py — all entry points mutate config at startup, no module defines its own tunables**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-26T23:16:30Z
- **Completed:** 2026-03-26T23:20:31Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Removed `_MAX_RETRIES`, `_BACKOFF_BASE`, `_DRAFT_INTERVAL` from telegram_sender.py — all read from config
- Removed `_MODEL_LOAD_TIMEOUT = 30` from server.py — replaced with `config.MODEL_LOAD_TIMEOUT_S` (120s)
- server.py now mutates `config.TELEGRAM_BOT_TOKEN`, `config.TELEGRAM_CHAT_ID`, `config.TELEGRAM_STREAM` before constructing TelegramSender
- realtime_demo.py writes Telegram credentials to config after `load_dotenv()`
- Both entry points import `SAMPLE_RATE` from config, not from audio_capture

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate telegram_sender.py to read constants from config** - `526a001` (feat)
2. **Task 2: Migrate server.py and realtime_demo.py to use config** - `e9a4333` (feat)

**Plan metadata:** _(final docs commit, see below)_

## Files Created/Modified
- `src/telegram_sender.py` - Removed 3 local constants; added `from . import config`; all usages point to config.*
- `src/server.py` - Added `from . import config`; removed `_engine_name="coreml"` and `_MODEL_LOAD_TIMEOUT=30`; uses config for engine default, timeout, energy interval; mutates config.TELEGRAM_* in _do_start
- `src/realtime_demo.py` - Added `from . import config`; removed SAMPLE_RATE from audio_capture import; writes Telegram creds to config after load_dotenv()

## Decisions Made
- TelegramSender.__init__ signature kept unchanged — taking explicit bot_token/chat_id args even though config now holds them. Cleanup deferred to Phase 5 per RESEARCH.md to keep this plan's scope tight.
- Config mutation placed immediately before TelegramSender construction so the values are committed to the module namespace before any downstream read.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Config consolidation complete — all src/ modules read tunables from config.py
- No module defines its own SAMPLE_RATE, CHANNELS, CHUNK_DURATION, QUEUE_MAXSIZE, _MAX_RETRIES, _BACKOFF_BASE, _DRAFT_INTERVAL, or _MODEL_LOAD_TIMEOUT
- Full import chain `python -c "import src.server"` passes cleanly
- Ready for Phase 02 IPC cleanup

---
*Phase: 01-config-consolidation*
*Completed: 2026-03-26*
