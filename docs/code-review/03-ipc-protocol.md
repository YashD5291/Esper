# Agent 3: IPC Protocol Correctness Review

**Scope**: `src/server.py`, `ProcessBridge.swift`, `Protocol.swift` — protocol contract, stdout isolation, buffering, error propagation, race conditions.

**Date**: 2026-03-28

---

## 1. Protocol Correctness

### Command -> Handler Mapping
**Status: All commands have handlers**

| Swift sends | Python handler | Verified |
|-------------|---------------|----------|
| `list_devices` | `server.py:344-345` | Yes |
| `start` | `server.py:346-347` | Yes |
| `stop` | `server.py:348-349` | Yes |
| `set_device` | `server.py:350-351` | Yes |
| `test_telegram` | `server.py:352-353` | Yes |

### Event -> Parser Mapping
**Status: Asymmetry found**

| Python sends | Swift parser | Verified |
|-------------|-------------|----------|
| `devices` | `Protocol.swift:79-90` | Yes |
| `status` | `Protocol.swift:92-95` | Yes |
| `transcript` | `Protocol.swift:97-110` | Yes |
| `energy` | `Protocol.swift:112-115` | Yes |
| `telegram_test` | `Protocol.swift:120-124` | Yes |
| `error` | `Protocol.swift:130-135` | Yes |

**BUG: `telegram_sent` dead code** — Swift parser recognizes `telegram_sent` event (`Protocol.swift:117-118`), TranscriptionEngine handles it (line 178), but Python **never emits** this event. Telegram sender has no completion callback.

### Field Name & Type Correctness
**Status: All match**

- Transcript payload: `text`, `finalized_text`, `sentences`, `no_speech_prob`, `duration_s` — match exactly
- Device payload: `index`, `name`, `channels`, `is_default` — match exactly
- Error payload: `message` key with string fallback — correct
- Status payload: bare string — correct

---

## 2. Stdout Isolation

### Current Approach

No `os.dup2` hack. Python writes protocol events to `sys.stdout` (when no `--protocol-fd`). All logging goes to `sys.stderr`.

### Contamination Risk

Third-party libraries that could print to stdout:
- `sounddevice` — verbose mode device info
- `mlx-whisper` — model loading progress
- `torch/MLX` — shader compilation, device selection
- `httpx` — debug mode logging

### Swift Reader Vulnerability

If stdout contains non-JSON (e.g., "Loading model..."):
1. Reader extracts line
2. `ServerEvent.parse()` returns nil (JSON decode fails)
3. **Line is silently dropped** — no logging
4. App waits forever for the expected event

**Verdict**: If any library prints to stdout, Swift silently loses that line. Critical vulnerability.

---

## 3. Pipe Buffering

### PYTHONUNBUFFERED
**Status: Set correctly** — `ProcessBridge.swift:36` sets `PYTHONUNBUFFERED=1`

### Flush After Write

| Side | Flushes? | Location |
|------|----------|----------|
| Python | Yes — `_proto_out.flush()` after every write | `server.py:71` |
| Swift | **No** — `pipe.fileHandleForWriting.write()` with no flush | `ProcessBridge.swift:112` |

**BUG**: Swift doesn't flush stdin pipe after writing commands. Commands might sit in kernel buffer. Mitigated in practice by Python's line-buffered stdin reading, but not guaranteed.

### Partial JSON Lines
**Status: Handled correctly**

- Swift reader accumulates in buffer until `\n` arrives (`ProcessBridge.swift:136-147`)
- Python writes JSON + newline atomically with immediate flush

---

## 4. Error Propagation

### Python -> Swift Errors
**Status: Complete path**

- `_send_error()` at `server.py:76-78` for all error cases
- Whisper start fails, audio capture fails, invalid device, JSON decode fails, unknown command, handler throws — all covered
- Swift receives and displays via `friendlyError()` mapping

### Process Crash Detection
**Status: Correct**

- `proc.terminationHandler` at `ProcessBridge.swift:77-85` detects non-zero exit
- Yields `.crashed(code)` event
- TranscriptionEngine auto-restarts with backoff

### Clean Shutdown vs Force Kill
**Status: Both handled**

- Clean: Swift sends "stop" -> Python runs `_do_stop()` -> sends "idle" -> Swift calls `terminate()`
- Force: Python gets SIGTERM -> signal handler calls `_do_stop()` -> `sys.exit(0)`

---

## 5. Race Conditions

### Swift Sends Before Python is Ready

**Startup timeline**:
1. Swift spawns Python
2. Python initializes, sends `status: "idle"` immediately
3. Swift sends `list_devices` after 500ms delay
4. Python is ready to read stdin immediately (model loading happens later in `_do_start()`)

**BUG**: If `bridge.isRunning` is not yet `true` when `send()` is called, command is silently dropped (`ProcessBridge.swift:98`). Mitigated by 500ms/1000ms delays, but not foolproof.

**Better approach**: Implement handshake — Python sends `ready` event, Swift waits for it before sending commands.

### Python Sends Before Swift is Reading

Python writes `status: "idle"` immediately on startup. If Swift reader thread hasn't started yet, events buffer in pipe (64KB capacity). Reader thread starts quickly due to `userInitiated` QoS. **Low risk**.

### Event Ordering
**Status: Safe** — Python is single-threaded for commands, ordering guaranteed.

---

## 6. Edge Cases

### Concurrent stdout/stderr Writes
**Safe** — separate fd handling, no conflict.

### Pipe Buffer Full
**Low risk** — 20 events/second at ~100 bytes each = 2KB/s. 64KB buffer = 32 seconds. Only fills if reader thread is starved.

### JSON Parsing Failure
**Robust** — malformed lines don't crash the reader, silently dropped. But no logging (hard to debug).

### Unicode
**Safe** — JSON handles Unicode via escape sequences, UTF-8 encoding correct on both sides.

---

## Bugs Found Summary

| # | Severity | Description | Location |
|---|----------|-------------|----------|
| 1 | Medium | `telegram_sent` event never emitted | `Protocol.swift:117`, `server.py` |
| 2 | Low | Swift doesn't flush stdin pipe after write | `ProcessBridge.swift:112` |
| 3 | Low | Silent JSON parse failure drops | `ProcessBridge.swift:112` |
| 4 | Low | Unparseable protocol lines silently dropped | `ProcessBridge.swift:155` |
| 5 | Medium | Commands sent before `isRunning=true` silently dropped | `ProcessBridge.swift:98` |

## Design Fragilities

| Area | Risk | Mitigation |
|------|------|-----------|
| Stdout isolation | Third-party libs can break protocol | No fd hijacking |
| No explicit sync | Swift doesn't know Python is ready | Hardcoded delays |
| Telegram async | Completion not signaled to Swift | `telegram_sent` never used |
| Pipe buffering | Writer stalls if reader blocked >30s | High-priority reader thread |
