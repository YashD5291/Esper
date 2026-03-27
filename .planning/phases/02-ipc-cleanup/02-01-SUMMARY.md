---
phase: 02-ipc-cleanup
plan: 01
subsystem: ipc
tags: [ipc, server, argparse, protocol-fd, tdd]
dependency_graph:
  requires: []
  provides: [protocol-fd-ipc, clean-server-imports]
  affects: [src/server.py, EsperApp/ProcessBridge.swift]
tech_stack:
  added: [argparse, TextIO]
  patterns: [argparse-protocol-fd, os.fdopen-line-buffered]
key_files:
  created: [tests/test_server_ipc.py]
  modified: [src/server.py]
decisions:
  - "Used sys.stderr.write() instead of print(..., file=sys.stderr) to satisfy test_no_bare_print AST check"
  - "parse_known_args() used in argparse to avoid conflicts with future top-level argument additions"
metrics:
  duration: "~3 minutes"
  completed: "2026-03-27"
  tasks_completed: 1
  files_changed: 2
---

# Phase 02 Plan 01: IPC Protocol-FD Cleanup Summary

**One-liner:** Replaced os.dup(1)/os.dup2(2,1) stdout redirect hack with argparse-based --protocol-fd N; JSON events now go to the dedicated fd or stdout in CLI mode.

## What Was Done

Removed the fragile three-line stdout redirect hack from `src/server.py` (lines 23-27) and replaced it with a clean `--protocol-fd N` argparse argument. When the argument is present, the server opens that fd via `os.fdopen(N, "w", buffering=1)` as the `_proto_out` writer. When absent (CLI mode), `_proto_out` falls back to `sys.stdout` — preserving the CLI debugging workflow. The import ordering constraint ("imports after stdout redirect") is gone; all imports now live at the top of the file. `_proto_out` is annotated as `TextIO`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Write failing tests for --protocol-fd IPC | 4d03f9a | tests/test_server_ipc.py |
| 1 (GREEN) | Replace stdout redirect hack with --protocol-fd | 13a3566 | src/server.py |

## Test Results

All 4 tests in `tests/test_server_ipc.py` pass:
- `test_protocol_fd_writes_json_to_fd` — subprocess with --protocol-fd receives JSON on that fd
- `test_no_protocol_fd_writes_to_stdout` — subprocess without flag receives JSON on stdout
- `test_dup2_hack_absent` — asserts os.dup2/os.dup( absent from server.py
- `test_no_bare_print` — AST walk confirms zero bare print() calls in server.py

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] sys.stderr.write() instead of print() for FATAL message**
- **Found during:** GREEN implementation
- **Issue:** Plan specified `print(f"FATAL...", file=sys.stderr)` in the error-exit path, but the AST-based `test_no_bare_print` test catches ANY `print()` call regardless of the `file=` argument. Using `print()` would fail the test.
- **Fix:** Used `sys.stderr.write()` directly, which avoids a `print()` AST node entirely while still writing to stderr.
- **Files modified:** src/server.py (line 50)
- **Commit:** 13a3566

## Acceptance Criteria Check

- [x] tests/test_server_ipc.py contains `def test_protocol_fd_writes_json_to_fd`
- [x] tests/test_server_ipc.py contains `def test_no_protocol_fd_writes_to_stdout`
- [x] tests/test_server_ipc.py contains `def test_dup2_hack_absent`
- [x] tests/test_server_ipc.py contains `def test_no_bare_print`
- [x] src/server.py contains `--protocol-fd`
- [x] src/server.py contains `os.fdopen(_protocol_fd, "w", buffering=1)`
- [x] src/server.py contains `from typing import TextIO`
- [x] src/server.py contains `_proto_out: TextIO`
- [x] src/server.py does NOT contain `os.dup2`
- [x] src/server.py does NOT contain `os.dup(`
- [x] src/server.py does NOT contain `# -- Imports (after stdout redirect)`
- [x] src/server.py does NOT contain `# -- Stdout isolation`
- [x] `python tests/test_server_ipc.py` exits 0 with all tests passing
- [x] `grep -c "os.dup2" src/server.py` returns 0

## Known Stubs

None — plan goal fully achieved. The `--protocol-fd` mechanism is live and tested. ProcessBridge.swift changes are tracked in plan 02-02.

## Self-Check: PASSED
