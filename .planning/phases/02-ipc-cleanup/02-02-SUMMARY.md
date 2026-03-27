---
phase: 02-ipc-cleanup
plan: 02
subsystem: ipc
tags: [swift, processbridge, pipe, protocol-fd, posix, fd-inheritance]
checkpoint_pending: false

requires:
  - phase: 02-ipc-cleanup
    plan: 01
    provides: "--protocol-fd server.py that writes JSON events to a dedicated fd"

provides:
  - "ProcessBridge creates a dedicated protocol Pipe and passes --protocol-fd N to the Python server"
  - "JSON events flow over the protocol pipe read end, not stdout"
  - "stdout captures stray output only (logged as [Python stdout])"

affects: [future phases modifying ProcessBridge, Telegram integration, error handling]

tech-stack:
  added: []
  patterns:
    - "Protocol pipe IPC: Swift creates Pipe(), passes write-end fd as --protocol-fd arg, reads from read end"
    - "CLOEXEC cleared on extra pipe write end before proc.run() for fd inheritance through exec"
    - "Parent closes write end after proc.run() so read end gets EOF on child exit"

key-files:
  created:
    - EsperApp/EsperApp/Models/Protocol.swift
    - EsperApp/EsperApp/Models/AppSettings.swift
  modified:
    - EsperApp/EsperApp/ProcessBridge.swift

key-decisions:
  - "CLOEXEC explicitly cleared via Darwin.fcntl before proc.run() -- defensive even if Foundation doesn't set it, because macOS version behavior is undocumented"
  - "Write end closed in parent immediately after proc.run() -- required for EOF propagation to reader thread when Python exits"
  - "stdout demoted to stray-output capture with readabilityHandler logging -- no longer protocol channel"

patterns-established:
  - "Protocol pipe pattern: Pipe() + CLOEXEC clear + --protocol-fd arg + parent close write end after run"

requirements-completed: [INTG-03]

duration: 15min
completed: 2026-03-27
---

# Phase 02 Plan 02: IPC Cleanup - ProcessBridge Protocol Pipe Summary

**ProcessBridge now reads JSON events from a dedicated POSIX pipe (--protocol-fd) instead of stdout, eliminating any risk of stray print() output corrupting the IPC protocol**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-27T05:55:00Z
- **Completed:** 2026-03-27T06:10:00Z
- **Tasks:** 2/2 complete
- **Files modified:** 3

## Accomplishments
- ProcessBridge creates a dedicated `protocolPipe` alongside the existing stdin/stdout/stderr pipes
- Write-end fd number passed to Python as `--protocol-fd <N>`, CLOEXEC cleared for fd inheritance through exec
- Parent closes write end after `proc.run()` so the reader thread gets EOF when Python exits
- `startReading()` renamed to `startReading(protocolPipe:)` and reads from protocol pipe read end
- stdout demoted to stray-output capture with `readabilityHandler` logging `[Python stdout]` prefix
- `terminate()` updated: clears stdout readabilityHandler and nils protocolPipe

## Task Commits

1. **Task 1: Update ProcessBridge.swift for protocol pipe IPC** - `11b07ab` (feat)
2. **Task 2: Verify end-to-end IPC works in SwiftUI app** - checkpoint approved (Xcode BUILD SUCCEEDED, idle event received on protocol fd, stdout clean)

## Files Created/Modified
- `EsperApp/EsperApp/ProcessBridge.swift` - Protocol pipe IPC: protocolPipe, --protocol-fd arg, CLOEXEC clear, write-end close, renamed startReading
- `EsperApp/EsperApp/Models/Protocol.swift` - Added ServerEvent enum with parse() (was missing from git, causing pre-existing build failure)
- `EsperApp/EsperApp/Models/AppSettings.swift` - Added engine, pythonPath, projectDir, resolvedPythonPath, resolvedProjectDir properties (were missing from git)

## Decisions Made
- CLOEXEC cleared defensively via `Darwin.fcntl` even though Foundation may not set it -- the smoke test (Task 2 human verify) will catch any fd inheritance failure
- Write end closed in parent immediately after `proc.run()` -- this is critical; if parent holds it open, reader thread hangs indefinitely at Python exit
- No changes to `send()`, `events` AsyncStream, stderr handler, terminationHandler, or `init()` -- exactly as specified in plan

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added missing ServerEvent enum definition**
- **Found during:** Task 1 (xcodebuild verification step)
- **Issue:** `Protocol.swift` and `AppSettings.swift` existed on disk but were never committed to git. Build was already failing before this plan with "cannot find type 'ServerEvent' in scope". The Models directory was gitignored because `.gitignore` contains `models/` which macOS HFS+ matched case-insensitively against `Models/`.
- **Fix:** Wrote `ServerEvent` enum with all cases (devices, status, transcript, energy, telegramSent, telegramTest, crashed, error, unknown) and `static func parse(json:) -> ServerEvent?`. Added all missing `AppSettings` properties (`engine`, `pythonPath`, `projectDir`, `resolvedPythonPath`, `resolvedProjectDir`). Force-added files with `git add --force` to bypass gitignore.
- **Files modified:** EsperApp/EsperApp/Models/Protocol.swift, EsperApp/EsperApp/Models/AppSettings.swift
- **Verification:** xcodebuild returned BUILD SUCCEEDED
- **Committed in:** 11b07ab (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - pre-existing build failure)
**Impact on plan:** Essential fix -- the task's acceptance criteria require BUILD SUCCEEDED, which was impossible without ServerEvent being defined.

## Issues Encountered
- `EsperApp/EsperApp/Models/` was silently ignored by git due to case-insensitive match of `models/` in `.gitignore` on macOS. Fixed via `git add --force`.

## Known Stubs
None -- all wired types and behavior are real.

## Checkpoint Verification

**Task 2 (human-verify)** approved 2026-03-27:
- Xcode build: BUILD SUCCEEDED
- Automated IPC smoke test: idle event received on protocol fd
- stdout clean: no protocol leakage observed

## Next Phase Readiness
- Phase 02 complete -- clean IPC protocol with no stdout fd hack
- Phase 03 (VAD Integration) can proceed

---
*Phase: 02-ipc-cleanup*
*Completed: 2026-03-27*
