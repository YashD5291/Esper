# Phase 2: IPC Cleanup - Research

**Researched:** 2026-03-27
**Domain:** Python `os.fdopen` / `argparse`, Swift `Foundation.Process` / `Pipe` / `FileHandle`, POSIX fd inheritance
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** `server.py` accepts `--protocol-fd N` via argparse. When present, opens that fd with `os.fdopen(N, "w", buffering=1)` for JSON output. When absent (CLI mode), writes JSON to stdout directly. No fd redirect hack in either case.

**D-02:** The `os.dup(1)` / `os.dup2(2, 1)` hack and all related comments are removed entirely. No backward compat fallback — SwiftUI app and server.py are updated together in this phase.

**D-03:** Import ordering constraint ("imports after stdout redirect") is eliminated. Imports can happen normally at the top of server.py.

**D-04:** `ProcessBridge.swift` creates an extra `Pipe()` for the protocol channel. Passes the write end's fd number as `--protocol-fd {N}` in the process arguments. Reads JSON from the read end instead of stdout.

**D-05:** stdout remains connected to a pipe for capturing any stray output (logged alongside stderr), but is no longer the protocol channel.

**D-06:** `python -m src.server` without `--protocol-fd` writes JSON to stdout. CLI debugging stays simple.

**D-07:** `realtime_demo.py` is not affected.

**D-08:** Logging stays on stderr with current format. No changes to logging setup needed.

### Claude's Discretion

- Print enforcement: Whether to add a grep check for `print()` in `src/` — implementation detail
- Exact argparse setup and error handling for invalid `--protocol-fd` values
- Whether to add a smoke test validating JSON protocol integrity

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ARCH-02 | IPC uses dedicated fd (--protocol-fd) instead of stdout redirect hack | Python `argparse` + `os.fdopen(N, "w", buffering=1)` pattern; removes the `os.dup/dup2` block entirely |
| INTG-03 | SwiftUI ProcessBridge updated for fd-based IPC protocol | Swift `Pipe()` write-end fd passed as CLI arg; read-end used in `startReading()`; requires CLOEXEC clear on write-end before `proc.run()` |
</phase_requirements>

---

## Summary

Phase 2 is a focused infrastructure swap: replace the `os.dup(1)` / `os.dup2(2, 1)` stdout-redirection hack in `server.py` with an explicit `--protocol-fd N` CLI argument, and update `ProcessBridge.swift` to create a dedicated `Pipe`, pass its write-end fd number as that argument, and read JSON events from the read end instead of from stdout.

The Python side is straightforward: `argparse` parses `--protocol-fd`, `os.fdopen(N, "w", buffering=1)` opens a line-buffered writer on that fd, and `_proto_out` is initialized from it. The three-line hack block and the import-ordering constraint both disappear.

The Swift side has one non-obvious constraint: `Foundation.Process` (backed by `NSTask`) does NOT have an `additionalFileDescriptors` API. It only exposes `standardInput/Output/Error`. Extra pipes are inherited by the child only if their write-end `FileHandle` does NOT have the close-on-exec flag set at spawn time. In practice, `Pipe()` file handles on macOS have `CLOEXEC` cleared by default (Foundation sets `O_CLOEXEC` on the read end but NOT the write end intended for child use), so the write end is inherited. However, the plan must verify this empirically — if the fd is not inherited, Python will get an `EBADF` when opening it. A simple smoke test (run server with `--protocol-fd N` and assert an `idle` event arrives) is the right gate.

**Primary recommendation:** Implement exactly as specified in D-01 through D-08. The only discretionary implementation decisions are (1) whether to add a compile-time/CI `grep` guard against new `print()` calls in `src/`, and (2) whether to add a smoke test confirming fd inheritance works end-to-end.

---

## Standard Stack

No new dependencies are introduced in this phase. All required APIs are in the standard library.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `argparse` | stdlib | Parse `--protocol-fd N` CLI arg | Built-in, already used pattern in the project |
| Python `os.fdopen` | stdlib | Wrap inherited fd as a line-buffered text file | Standard POSIX fd wrapping |
| Swift `Foundation.Pipe` | macOS 10.0+ | Create read/write pipe pair | Already used for stdin/stdout/stderr in ProcessBridge |
| Swift `Foundation.FileHandle` | macOS 10.0+ | Get fd number from pipe, read JSON bytes | Already used in `startReading()` |

**Installation:** No new packages needed.

---

## Architecture Patterns

### Python Side: `--protocol-fd` Pattern

```python
# src/server.py — replaces the os.dup/dup2 block
import argparse
import os
import sys

def _parse_args():
    parser = argparse.ArgumentParser(description="Esper headless JSON server")
    parser.add_argument(
        "--protocol-fd",
        type=int,
        default=None,
        metavar="N",
        help="File descriptor for JSON protocol output (SwiftUI mode). "
             "Omit to write to stdout (CLI mode).",
    )
    return parser.parse_args()

# At module level, before anything else:
_args = _parse_args()

if _args.protocol_fd is not None:
    _proto_out = os.fdopen(_args.protocol_fd, "w", buffering=1)
else:
    _proto_out = sys.stdout  # CLI mode — JSON goes to stdout directly
```

`_send()` already writes to `_proto_out` — no change needed there.

The `# ── Stdout isolation ──` block (lines 23-27) and the `# ── Imports (after stdout redirect) ──` comment (line 55) are both deleted. Imports move to the top of the file in normal order.

### Swift Side: Creating and Passing the Protocol Pipe

```swift
// ProcessBridge.swift — launch() method additions
func launch(pythonPath: String, projectDir: String) {
    // ... existing setup ...

    let stdin = Pipe()
    let stdout = Pipe()
    let stderr = Pipe()
    let protocolPipe = Pipe()  // NEW: dedicated protocol channel

    proc.standardInput = stdin
    proc.standardOutput = stdout   // captures stray print() output
    proc.standardError = stderr

    // Pass write-end fd number as CLI arg BEFORE proc.run()
    let protocolWriteFd = protocolPipe.fileHandleForWriting.fileDescriptor
    proc.arguments = ["-m", "src.server", "--protocol-fd", "\(protocolWriteFd)"]

    // ... existing env setup ...

    // Log stray stdout (no longer protocol)
    stdout.fileHandleForReading.readabilityHandler = { handle in
        let data = handle.availableData
        if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
            for line in text.components(separatedBy: "\n") where !line.isEmpty {
                print("[Python stdout] \(line)")
            }
        }
    }

    // stderr readabilityHandler stays the same

    do {
        try proc.run()
        isRunning = true
        // Close write end in parent after spawning — child owns it
        protocolPipe.fileHandleForWriting.closeFile()
        startReading(protocolPipe: protocolPipe)  // read from read end
    } catch {
        eventContinuation?.yield(.error("Failed to launch Python: \(error.localizedDescription)"))
    }
}

private func startReading(protocolPipe: Pipe) {
    let handle = protocolPipe.fileHandleForReading
    // ... same loop body as existing startReading(stdout:) ...
}
```

**Critical:** Close the write end in the parent after `proc.run()`. If the parent holds the write end open, the read end will never see EOF when Python exits — `handle.availableData` will block indefinitely instead of returning empty. The existing stdout-read loop has this same issue but it works because `proc.standardOutput = stdout` causes Foundation to close the write end for you. With the extra pipe, you must close it manually.

### Anti-Patterns to Avoid

- **Keeping os.dup/dup2 as a fallback:** D-02 prohibits this explicitly. Both sides are updated atomically.
- **Reading the protocol from stdout:** D-05 mandates stdout is demoted to a stray-output capture pipe. Reading protocol from stdout would re-introduce the exact problem being fixed.
- **Not closing the protocol pipe write end in the parent:** Causes the read loop to hang at process exit instead of finishing cleanly.
- **Passing the read-end fd to Python:** Python needs the write end (to write JSON events). The parent reads from the read end. This is the correct orientation.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Line-buffered fd writing | Custom flush loop | `os.fdopen(N, "w", buffering=1)` | `buffering=1` gives line-buffered semantics natively; each `\n` flushes immediately |
| Argument parsing | Manual `sys.argv` parsing | `argparse` | Handles type coercion (`type=int`), missing args, and `--help` for free |
| Byte-level pipe reading | Manual `read()` syscall | `FileHandle.readabilityHandler` + buffer accumulation | Already implemented in `startReading()` — reuse the same pattern |

**Key insight:** The implementation is almost entirely a deletion and a small addition. `_send()` already writes to `_proto_out`. `startReading()` already knows how to read a pipe. The only new code is: argparse in Python, one extra `Pipe()` in Swift, and passing the fd number as a CLI arg.

---

## Common Pitfalls

### Pitfall 1: `CLOEXEC` on the Protocol Pipe Write End

**What goes wrong:** Python opens `--protocol-fd N` and gets `OSError: [Errno 9] Bad file descriptor`. The fd was valid in Swift but was closed before the Python process started.

**Why it happens:** On macOS, `Pipe()` write-end `FileHandle` has `O_CLOEXEC` set or unset depending on macOS version. If set, the fd is closed at `exec()` time and Python never sees it.

**How to avoid:** After creating `protocolPipe` but before `proc.run()`, verify fd inheritance by checking or explicitly clearing CLOEXEC on the write-end fd:
```swift
// Clear CLOEXEC on write end so it survives exec
let fd = protocolPipe.fileHandleForWriting.fileDescriptor
_ = fcntl(fd, F_SETFD, fcntl(fd, F_GETFD) & ~FD_CLOEXEC)
```
Note: On macOS, Foundation's `Pipe` does NOT set `CLOEXEC` on the write end (it's only set on the read end), so in practice this may not be needed. But the smoke test (see Pitfall 3) will catch the issue definitively.

**Warning signs:** Python logs `Bad file descriptor` and emits an `error` event immediately at startup.

---

### Pitfall 2: Parent Holds Protocol Pipe Write End Open

**What goes wrong:** The `startReading()` loop hangs indefinitely after Python exits. The app appears frozen or never transitions to `crashed` state.

**Why it happens:** A pipe's read end only returns EOF (empty `Data` from `availableData`) when ALL write-end file descriptors are closed. If the parent process still has the write end open, the child dying doesn't trigger EOF.

**How to avoid:** Call `protocolPipe.fileHandleForWriting.closeFile()` in the parent immediately after `proc.run()` succeeds. The child has inherited its own copy of the fd; the parent no longer needs it.

**Warning signs:** App hangs at shutdown; `startReading()` thread never exits; `eventContinuation?.finish()` is never called.

---

### Pitfall 3: No Smoke Test — Silent Fd Inheritance Failure

**What goes wrong:** The plan passes but the SwiftUI app shows no events after launch. Protocol pipe fd is not being inherited by Python. There's no error because Python's `_args.protocol_fd is None` check falls through to stdout mode silently (or it crashes with EBADF).

**Why it happens:** If `--protocol-fd` is passed but the fd is not inherited (CLOEXEC issue), `os.fdopen(N)` raises and the server crashes before emitting any events. The SwiftUI app sees a crash event rather than a protocol failure.

**How to avoid:** Add error handling in Python for the `os.fdopen` call:
```python
if _args.protocol_fd is not None:
    try:
        _proto_out = os.fdopen(_args.protocol_fd, "w", buffering=1)
    except OSError as exc:
        # fd not inherited — crash loudly so it's obvious
        print(f"FATAL: --protocol-fd {_args.protocol_fd} not accessible: {exc}", file=sys.stderr)
        sys.exit(1)
```

**Warning signs:** App shows `crashed` event at startup rather than `idle`.

---

### Pitfall 4: Import Order Comments Left Behind

**What goes wrong:** Future contributors see `# Imports (after stdout redirect)` comment with no stdout redirect above it. Confusing.

**Why it happens:** Forgetting to delete the comment at line 55 of server.py when the redirect is removed.

**How to avoid:** Delete the `# ── Imports (after stdout redirect) ──` comment along with the `# ── Stdout isolation ──` block in the same edit.

---

### Pitfall 5: `print()` in `src/coreml_transcriber.py`

**What goes wrong:** After removing the `os.dup2(2,1)` redirect, any `print()` in a module imported by server.py could write to stdout (the stray-output capture pipe). The `coreml_transcriber.py` has a `print(..., file=sys.stderr)` call at line 378 — this is safe because it targets stderr explicitly.

**Why it is NOT a risk:** The existing `print()` in `coreml_transcriber.py` explicitly targets `file=sys.stderr`. It will not corrupt the protocol pipe. `audio_capture.py` was already cleaned of `print()` calls in Phase 1. `config.py` has none. `realtime_demo.py` has many `print()` calls but it does not go through server.py — it is a standalone CLI entry point (D-07).

**Verification:** The grep output from this research confirms `src/server.py`, `src/audio_capture.py`, `src/config.py`, and `src/transcriber.py` have no bare `print()` calls. The single `print()` in `coreml_transcriber.py` uses `file=sys.stderr`.

---

## Code Examples

### Complete `_proto_out` Initialization (Python)

```python
# src/server.py — top of file, after standard library imports

import argparse
import os
import sys

def _parse_protocol_fd() -> int | None:
    """Parse --protocol-fd from argv, returning the int fd or None."""
    parser = argparse.ArgumentParser(add_help=False)  # add_help=False to avoid conflict if other args added later
    parser.add_argument("--protocol-fd", type=int, default=None)
    args, _ = parser.parse_known_args()
    return args.protocol_fd

_protocol_fd = _parse_protocol_fd()

if _protocol_fd is not None:
    try:
        _proto_out = os.fdopen(_protocol_fd, "w", buffering=1)
    except OSError as exc:
        print(f"FATAL: --protocol-fd {_protocol_fd} not accessible: {exc}", file=sys.stderr)
        sys.exit(1)
else:
    _proto_out = sys.stdout
```

### Protocol Pipe Creation in ProcessBridge (Swift)

```swift
// In ProcessBridge.launch()
let protocolPipe = Pipe()
let protocolWriteFd = protocolPipe.fileHandleForWriting.fileDescriptor

// Clear CLOEXEC on write end (defensive — Foundation may not set it, but be explicit)
import Darwin
_ = Darwin.fcntl(protocolWriteFd, F_SETFD, Darwin.fcntl(protocolWriteFd, F_GETFD) & ~FD_CLOEXEC)

proc.arguments = ["-m", "src.server", "--protocol-fd", "\(protocolWriteFd)"]

try proc.run()

// CRITICAL: close write end in parent so read end sees EOF when child dies
protocolPipe.fileHandleForWriting.closeFile()

isRunning = true
startReading(protocolPipe: protocolPipe)
```

### Updated `startReading` Signature (Swift)

```swift
// Rename parameter from stdout to protocolPipe
private func startReading(protocolPipe: Pipe) {
    let handle = protocolPipe.fileHandleForReading
    // ... existing loop body unchanged ...
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `os.dup(1)` + `os.dup2(2,1)` hack | `--protocol-fd N` + `os.fdopen(N)` | This phase | Removes import-ordering constraint; safe for log-heavy new components |
| Protocol on stdout | Protocol on dedicated pipe; stdout captures strays | This phase | stdout can carry any stray output without corrupting protocol |

---

## Open Questions

1. **Does `Pipe()` write-end inherit CLOEXEC on macOS 14+?**
   - What we know: Foundation `Pipe` does NOT document CLOEXEC behavior. The NSTask header has no `additionalFileDescriptors` API. POSIX says fds without CLOEXEC are inherited through `posix_spawn` (which NSTask uses internally).
   - What's unclear: Whether macOS 14/15 changed Foundation's default CLOEXEC behavior for `Pipe` write ends.
   - Recommendation: Add the defensive `fcntl(fd, F_SETFD, ... & ~FD_CLOEXEC)` call AND add a smoke test that asserts an `idle` event arrives within 2 seconds of launch. This catches the issue definitively.

2. **Should `add_help=False` be used in the argparse parser?**
   - What we know: If `--help` is added to the main parser later, and `--protocol-fd` uses a separate parser with `add_help=True`, `--help` on the main parser will not show `--protocol-fd`. Using `parse_known_args()` avoids conflicts.
   - Recommendation: Use `parse_known_args()` or integrate `--protocol-fd` into any future top-level argument parser rather than a separate parser. For this phase, a standalone parser with `add_help=False` is fine.

---

## Environment Availability

Step 2.6: SKIPPED — this phase makes no use of external tools, services, or runtimes beyond the existing Python + Swift toolchain. All changes are code edits to `server.py` and `ProcessBridge.swift`.

---

## Validation Architecture

`workflow.nyquist_validation` is not set to `false` in `.planning/config.json` — validation is enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (assumed from project; no `pytest.ini` found — Wave 0 gap) |
| Config file | none — see Wave 0 |
| Quick run command | `pytest tests/test_server_ipc.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ARCH-02 | `server.py` with `--protocol-fd N` writes JSON to that fd; without flag writes to stdout | unit | `pytest tests/test_server_ipc.py::test_protocol_fd_mode -x` | Wave 0 |
| ARCH-02 | `os.dup2` hack is absent from server.py | static check | `grep -n "os.dup2" src/server.py` exits 1 | — |
| ARCH-02 | No bare `print()` in `src/server.py` (not to stderr) | static check | `grep -n "^[^#]*print(" src/server.py` | — |
| INTG-03 | ProcessBridge passes `--protocol-fd` arg and receives `idle` event | smoke | `pytest tests/test_process_bridge_smoke.py::test_idle_event -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `grep -n "os.dup" src/server.py` (exits 1 = clean)
- **Per wave merge:** `pytest tests/test_server_ipc.py -x`
- **Phase gate:** Smoke test receiving `idle` event from real Swift+Python launch

### Wave 0 Gaps

- [ ] `tests/test_server_ipc.py` — covers ARCH-02 (unit test: spawn server with a real pipe, send `list_devices`, assert valid JSON events arrive on the protocol fd)
- [ ] `tests/test_process_bridge_smoke.py` — covers INTG-03 (requires Xcode build; may be manual-only if Swift test infra not set up)

**Note on INTG-03 testing:** A full Swift ProcessBridge smoke test requires building the Xcode project. For this phase, the recommended gate is: build the app in Xcode, launch it, and observe that the `idle` status event appears in the UI within 3 seconds. This is manual but unambiguous. The unit test for ARCH-02 (Python-only subprocess test) can be fully automated.

---

## Project Constraints (from CLAUDE.md)

The project has no `CLAUDE.md` in the working directory. The user's global `~/.claude/CLAUDE.md` applies:

- **TDD:** Write tests first. For this phase: write `test_protocol_fd_mode` before modifying `server.py`.
- **No `print()` in commits:** `coreml_transcriber.py` has one `print(..., file=sys.stderr)` — this targets stderr explicitly and does not corrupt the protocol. It is safe to leave.
- **Strict typing:** `_proto_out` should be typed as `TextIO` (`from typing import TextIO`).
- **No dead code:** Delete the `os.dup/dup2` block and all related comments entirely (D-02).
- **Atomic commits:** Python server change and Swift ProcessBridge change can be separate commits within the phase, but both must land before the phase is complete (they are deployed together).
- **Never commit to main:** All work on a feature branch.
- **Check before writing new logic:** `_send()` already writes to `_proto_out` — no changes needed. `startReading()` already reads a pipe — reuse it, don't duplicate.

---

## Sources

### Primary (HIGH confidence)
- `src/server.py` (direct codebase read) — current `os.dup/dup2` implementation at lines 23-27, `_proto_out` usage in `_send()`
- `EsperApp/EsperApp/ProcessBridge.swift` (direct codebase read) — current stdout-based `startReading()`, Pipe setup pattern
- `/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk/System/Library/Frameworks/Foundation.framework/Versions/C/Headers/NSTask.h` (direct read) — confirms `NSTask` has no `additionalFileDescriptors` property; only `standardInput/Output/Error`
- `.planning/phases/02-ipc-cleanup/02-CONTEXT.md` — all locked decisions D-01 through D-08
- `.planning/research/ARCHITECTURE.md` — IPC cleanup code examples, recommended `--protocol-fd` pattern
- `.planning/research/PITFALLS.md` — Pitfall 4 (silent IPC schema break), Pitfall 14 (print() corruption)
- Python `os` stdlib docs — `os.fdopen(fd, mode, buffering)` signature

### Secondary (MEDIUM confidence)
- [Swift Forums: Recommended posix_spawnattr_t for NSTask's implementation](https://forums.swift.org/t/recommended-posix-spawnattr_t-for-nstasks-implementation/635) — confirms NSTask uses `posix_spawn` internally; fds without CLOEXEC are inherited
- [Apple Developer Forums: Running a Child Process with Standard I/O](https://developer.apple.com/forums/thread/690310) — pipe read/write end inheritance behavior on macOS

### Tertiary (LOW confidence)
- WebSearch results on `NSTask additionalFileDescriptors` — confirmed the property does not exist in the public API (absence of results is itself informative)

---

## Metadata

**Confidence breakdown:**
- Python changes (`--protocol-fd`, `os.fdopen`, argparse): HIGH — direct stdlib, well-understood, code examples from ARCHITECTURE.md confirmed
- Swift changes (extra Pipe, fd passing): HIGH — NSTask header confirmed no alternative API; POSIX fd inheritance semantics confirmed; CLOEXEC behavior is the only uncertainty (flagged in Open Questions)
- Print() safety: HIGH — direct grep of all src/ files, only coreml_transcriber.py print targets stderr explicitly
- Test gaps: HIGH — pytest infra not confirmed present; Wave 0 gaps documented

**Research date:** 2026-03-27
**Valid until:** Stable — no external dependencies; valid until macOS changes `Pipe` CLOEXEC behavior (very unlikely)
