---
phase: 02-ipc-cleanup
verified: 2026-03-27T07:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 2: IPC Cleanup Verification Report

**Phase Goal:** The Python backend communicates with SwiftUI exclusively over a dedicated file descriptor, making it safe to add log-heavy VAD and Whisper components without corrupting the protocol stream
**Verified:** 2026-03-27T07:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | server.py with `--protocol-fd N` writes JSON events to fd N, not stdout | VERIFIED | `os.fdopen(_protocol_fd, "w", buffering=1)` at line 48; `test_protocol_fd_writes_json_to_fd` passes |
| 2 | server.py without `--protocol-fd` writes JSON events to stdout | VERIFIED | `_proto_out = sys.stdout` fallback at line 53; `test_no_protocol_fd_writes_to_stdout` passes |
| 3 | The `os.dup(1)` / `os.dup2(2,1)` hack is completely absent from server.py | VERIFIED | `grep -n "os.dup" src/server.py` returns no matches; `test_dup2_hack_absent` passes |
| 4 | No bare `print()` calls exist in `src/server.py` | VERIFIED | AST walk confirms zero print() Call nodes; `test_no_bare_print` passes |
| 5 | Imports are at the top of server.py with no ordering constraint | VERIFIED | All imports at lines 13-31; no `# -- Imports (after stdout redirect) --` comment present |
| 6 | ProcessBridge creates a dedicated protocol Pipe and passes `--protocol-fd N` to the Python process | VERIFIED | `let protoPipe = Pipe()` + `proc.arguments = ["-m", "src.server", "--protocol-fd", "\(protoWriteFd)"]` at lines 49, 65 |
| 7 | ProcessBridge reads JSON events from the protocol pipe read end, not stdout | VERIFIED | `startReading(protocolPipe: protoPipe)` reads from `protocolPipe.fileHandleForReading`; old `startReading(stdout:)` signature is absent |
| 8 | stdout is captured as stray output and logged, not used as the protocol channel | VERIFIED | `stdout.fileHandleForReading.readabilityHandler` logs `[Python stdout]` prefix at line 68-75 |
| 9 | The protocol pipe write end is closed in the parent after `proc.run()` so EOF propagates on child exit | VERIFIED | `protoPipe.fileHandleForWriting.closeFile()` at line 104, immediately after `proc.run()` |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_server_ipc.py` | Automated tests for `--protocol-fd` IPC | VERIFIED | 4 tests present and all passing: `test_protocol_fd_writes_json_to_fd`, `test_no_protocol_fd_writes_to_stdout`, `test_dup2_hack_absent`, `test_no_bare_print` |
| `src/server.py` | Server with argparse-based `--protocol-fd` support | VERIFIED | `_parse_protocol_fd()` + `os.fdopen(_protocol_fd, "w", buffering=1)` + `TextIO` annotation present; no `os.dup2` |
| `EsperApp/EsperApp/ProcessBridge.swift` | Protocol pipe-based IPC with `--protocol-fd` argument | VERIFIED | `import Darwin`, `private var protocolPipe: Pipe?`, CLOEXEC clear, write-end close, `startReading(protocolPipe:)` |
| `EsperApp/EsperApp/Models/Protocol.swift` | `ServerEvent` enum with `parse(json:)` | VERIFIED | Full enum with all 9 cases + substantive `parse()` implementation; force-added to git to bypass gitignore issue |
| `EsperApp/EsperApp/Models/AppSettings.swift` | App settings properties | VERIFIED | Present and committed |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/server.py` | `_proto_out` | `os.fdopen(_protocol_fd, "w", buffering=1)` | WIRED | Line 48: exact pattern present; `_send()` writes to `_proto_out` at line 70 |
| `EsperApp/EsperApp/ProcessBridge.swift` | `src/server.py` | `--protocol-fd N` CLI argument | WIRED | `proc.arguments = ["-m", "src.server", "--protocol-fd", "\(protoWriteFd)"]` at line 65 |
| `EsperApp/EsperApp/ProcessBridge.swift` | `protocolPipe.fileHandleForReading` | `startReading(protocolPipe:)` reads from read end | WIRED | `private func startReading(protocolPipe: Pipe)` uses `protocolPipe.fileHandleForReading` at lines 145-146 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `ProcessBridge.swift` | `ServerEvent` stream | `protocolPipe.fileHandleForReading.availableData` | Yes — read loop parses newline-delimited JSON from the live pipe | FLOWING |
| `src/server.py` | `_proto_out` | `os.fdopen(_protocol_fd)` or `sys.stdout` | Yes — `_send()` writes real JSON; startup sends `status: idle`; `list_devices` queries `sounddevice` | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 4 IPC tests pass | `.venv/bin/python tests/test_server_ipc.py` | `4 passed, 0 failed` | PASS |
| Xcode build succeeds | `xcodebuild ... build` | `BUILD SUCCEEDED` | PASS |
| `os.dup` absent from server.py | `grep -n "os.dup" src/server.py` | No output (exit 1) | PASS |
| No bare print() in server.py | grep for `print(` in src/server.py | No matches | PASS |
| IPC-path modules clean (audio_capture, transcriber, telegram_sender) | grep for `print(` in each | No matches in any | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ARCH-02 | 02-01-PLAN.md | IPC uses dedicated fd (`--protocol-fd`) instead of stdout redirect hack | SATISFIED | `--protocol-fd` argparse in server.py; `os.dup2` absent; all 4 tests pass |
| INTG-03 | 02-02-PLAN.md | SwiftUI ProcessBridge updated for fd-based IPC protocol | SATISFIED | ProcessBridge creates `protocolPipe`, clears CLOEXEC, passes `--protocol-fd`, reads from pipe read end; BUILD SUCCEEDED |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `EsperApp/EsperApp/ProcessBridge.swift` | 72 | `print("[Python stdout] \(line)")` | Info | Intentional — this is the stray-output capture log, not a protocol write. Logs unintended stdout output from Python for debugging. No impact on correctness. |
| `src/realtime_demo.py` | multiple | `print(...)` calls | Info | `realtime_demo.py` is a standalone CLI entrypoint, never imported by `server.py` or `ProcessBridge`. These print() calls cannot corrupt the IPC stream. |
| `src/coreml_transcriber.py` | 378 | `print(..., file=sys.stderr)` | Info | Explicitly directed to stderr. Cannot corrupt the protocol fd. |

No blocker or warning anti-patterns. All noted items are intentional or inert with respect to the protocol channel.

### Human Verification Required

### 1. End-to-End SwiftUI App Launch

**Test:** Build and run EsperApp in Xcode. Within 3 seconds of launch the status badge should show "Ready" (proving the `idle` event arrived over the protocol pipe). Click "Start Listening" — status should transition to "Loading Model" then "Listening". Click "Stop" — status should return to "Ready". Check the Xcode console: no JSON events should appear in the `[Python stdout]` log lines.

**Expected:** App shows "Ready" within 3 seconds; start/stop cycle completes without protocol corruption; no JSON in stray stdout log.

**Why human:** Live process spawn, pipe fd inheritance through exec, and observable UI state cannot be verified programmatically without running the app. The xcodebuild check confirms compilation. The 02-02-SUMMARY.md documents that this human checkpoint was approved on 2026-03-27 (checkpoint_pending: false).

Note: Per 02-02-SUMMARY.md, Task 2 (human checkpoint) was approved on 2026-03-27 with "idle event received on protocol fd, stdout clean." This item is documented as satisfied by prior human approval.

### Gaps Summary

None. All 9 observable truths are verified. Both requirements (ARCH-02, INTG-03) are satisfied. The test suite passes with 4/4 tests. The Xcode build succeeds. No orphaned requirements were found for Phase 2 in REQUIREMENTS.md.

The phase goal is fully achieved: the Python backend communicates with SwiftUI exclusively over a dedicated file descriptor (`--protocol-fd`), and the `os.dup2` stdout redirect hack has been completely eliminated. Adding log-heavy VAD and Whisper components in subsequent phases cannot corrupt the protocol stream.

---

_Verified: 2026-03-27T07:00:00Z_
_Verifier: Claude (gsd-verifier)_
