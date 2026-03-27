---
phase: 01-config-consolidation
plan: 01
subsystem: config
tags: [python, config, constants, audio, telegram, ipc]

# Dependency graph
requires: []
provides:
  - src/config.py as single source of truth for all Esper tunables
  - Audio, VAD, Whisper, Telegram, and IPC constant namespaces with documented defaults
  - Zero print() calls in audio_capture.py (IPC corruption risk eliminated)
affects:
  - 01-02 (next plan in phase 1 — server.py and realtime_demo.py migration)
  - Phase 2 IPC cleanup
  - Phase 3 VAD (reads VAD_FRAME_SIZE, VAD_SPEECH_THRESHOLD from config)
  - Phase 4 Whisper (reads WHISPER_MODEL_REPO, WHISPER_SUBPROCESS_TIMEOUT_S from config)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level constants in src/config.py with runtime mutation at startup (server._do_start or realtime_demo.main)"
    - "from . import config pattern — all leaf modules import the module, not individual names"
    - "log.info() for all audio device info — never print() in modules used by server.py"

key-files:
  created:
    - src/config.py
    - tests/test_config.py
  modified:
    - src/audio_capture.py
    - src/transcriber.py
    - src/coreml_transcriber.py

key-decisions:
  - "MODEL_LOAD_TIMEOUT_S set to 120.0 (not 30) per CLEAN-03 — covers Whisper cold Metal shader compile time (45-90s)"
  - "from . import config pattern used instead of from .config import X — allows future mutation of config.X at startup"
  - "list_devices() print() calls converted to log.info() — consistent no-print rule in non-CLI modules"

patterns-established:
  - "Pattern 1: All tunables in src/config.py — no module defines its own copy of a constant"
  - "Pattern 2: Mutation only at startup — components read config values when constructing, never cache them at import"
  - "Pattern 3: Zero print() in modules called by server.py — use logging only to prevent IPC corruption"

requirements-completed: [ARCH-01]

# Metrics
duration: 6min
completed: 2026-03-26
---

# Phase 01 Plan 01: Config Consolidation Summary

**src/config.py with 5 namespaced sections (Audio, VAD, Whisper, Telegram, IPC) replacing scattered module constants; audio_capture.py IPC print() landmine eliminated**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-26T23:10:10Z
- **Completed:** 2026-03-26T23:11:18Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created `src/config.py` as single source of truth with all 5 namespaced constant sections
- Stubbed Phase 3 (VAD) and Phase 4 (Whisper) namespaces with documented defaults
- Migrated audio_capture.py, transcriber.py, and coreml_transcriber.py to `from . import config`
- Removed the IPC corruption landmine: all 3 `print()` calls in audio_capture.py replaced with `log.info()`
- Added 25-test suite in tests/test_config.py covering all constants and structural invariants

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: test_config.py (failing tests)** - `42658a9` (test)
2. **Task 1 GREEN: src/config.py implementation** - `0a286c7` (feat)
3. **Task 2: Migrate three modules to import from config** - `a0e2d4b` (feat)

_Note: TDD Task 1 has two commits (test RED then feat GREEN)_

## Files Created/Modified
- `src/config.py` - New: single source of truth, 5 namespaced sections, zero internal imports
- `tests/test_config.py` - New: 25 tests covering all constants and structural invariants
- `src/audio_capture.py` - Removed 5 module-level constants; `from . import config`; 3 print() → log.info()
- `src/transcriber.py` - Replaced `from .audio_capture import SAMPLE_RATE` with `from . import config`
- `src/coreml_transcriber.py` - Replaced `from .audio_capture import SAMPLE_RATE` with `from . import config`; 5 SAMPLE_RATE usages updated

## Decisions Made
- MODEL_LOAD_TIMEOUT_S = 120.0 (not 30) — Whisper cold Metal shader compile takes 45-90s per PITFALLS.md Pitfall 10
- Used `from . import config` (import the module) rather than `from .config import X` (import individual names) — the module-import pattern is required for runtime mutation to be visible to all callers
- Converted `list_devices()` print() calls to log.info() — consistent no-print rule in non-CLI modules, even for CLI utility functions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Running tests directly (`python tests/test_config.py`) failed with "No module named 'src'" because the tests directory was on sys.path but not the project root. Added `sys.path.insert(0, project_root)` to test file. The plan's verify command (`python -c "from src import config"`) works correctly when run from project root.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- src/config.py is ready for Phase 1 Plan 2 (server.py and realtime_demo.py migration)
- Phase 2 IPC cleanup can now import config.MODEL_LOAD_TIMEOUT_S and config.DEFAULT_ENGINE
- Phase 3 VAD stub constants (VAD_FRAME_SIZE=512, etc.) are in place
- Phase 4 Whisper stub constants (WHISPER_MODEL_REPO, etc.) are in place

## Known Stubs

- `config.TELEGRAM_BOT_TOKEN = ""` and `config.TELEGRAM_CHAT_ID = ""` — empty by design, set at runtime. telegram_sender.py still receives these as constructor args (migration deferred to Phase 1 Plan 2).
- `config.VAD_*` constants — Phase 3 stubs, not yet wired to any VAD implementation
- `config.WHISPER_*` constants — Phase 4 stubs, not yet wired to any Whisper implementation

---
*Phase: 01-config-consolidation*
*Completed: 2026-03-26*
