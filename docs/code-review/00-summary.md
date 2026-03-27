# Esper Code Review: Combined Summary

**Date**: 2026-03-28
**Reviewed by**: 6 parallel analysis agents + first-principles verification pass
**Scope**: Full codebase — `src/`, `tests/`, `EsperApp/EsperApp/`
**Status**: All real issues fixed. 71/71 tests passing.

---

## Agent Reports

| # | Agent | Scope | Report |
|---|-------|-------|--------|
| 1 | [Python Pipeline](01-python-pipeline.md) | `src/`, `tests/` — architecture, threading, correctness |
| 2 | [Swift App](02-swift-app.md) | `EsperApp/` — @Observable, ProcessBridge, views, lifecycle |
| 3 | [IPC Protocol](03-ipc-protocol.md) | `server.py` <-> `ProcessBridge.swift` — contract, buffering, races |
| 4 | [Error Handling](04-error-handling-resilience.md) | Full codebase — failure modes, resource leaks, recovery |
| 5 | [Test Coverage](05-test-coverage.md) | `tests/` — coverage gaps, quality, missing tests |
| 6 | [Code Hygiene](06-code-hygiene.md) | Full codebase — dead code, standards, config, security |

---

## Overall Verdict

| Dimension | Score | Notes |
|-----------|-------|-------|
| Architecture | 8.5/10 | Clean separation, queue-based threading, subprocess isolation |
| Code Quality | 8/10 | Well-documented, minimal dead code, consistent patterns |
| Error Handling | 6.5/10 | Happy paths solid, edge cases have gaps |
| Thread Safety | 6/10 | No write lock on `_send()`, @unchecked Sendable hides races |
| Test Suite | 5/10 | 50% coverage, mock-heavy, zero integration tests |
| IPC Protocol | 6.5/10 | Functional but fragile — silent drops, no handshake |
| Security | 4/10 | Real credentials in .env |
| Build/Config | 6/10 | Deps unpinned, .gitignore gaps |

---

## All Issues by Severity

### CRITICAL (Fix Before Anything Else)

| # | Issue | Found by | Location |
|---|-------|----------|----------|
| C1 | Real Telegram credentials in `.env` | Agent 6 | `.env` |
| C2 | Test suite broken — 6 config values out of sync | Agents 1, 5, 6 | `test_config.py`, `test_whisper_transcriber.py` |
| C3 | No write lock on `_send()` — JSON interleaving | Agents 3, 4 | `server.py:70` |
| C4 | TelegramSender hardcodes config values | Agent 1 | `telegram_sender.py:20-21` |

### HIGH (Should Fix Soon)

| # | Issue | Found by | Location |
|---|-------|----------|----------|
| H1 | ProcessBridge reader thread — blocking I/O, no timeout | Agent 2 | `ProcessBridge.swift:140` |
| H2 | VadThread doesn't send sentinel on exception | Agents 1, 4 | `vad.py:139-140` |
| H3 | Microphone disconnect not propagated | Agent 4 | `audio_capture.py:106` |
| H4 | Silent protocol parse failures | Agents 2, 3, 4 | `ProcessBridge.swift:155` |
| H5 | @unchecked Sendable without synchronization | Agent 2 | `ProcessBridge.swift:5` |
| H6 | Pipes not closed on exception in launch() | Agents 2, 4 | `ProcessBridge.swift:88-93` |
| H7 | `telegram_sent` event dead code | Agent 3 | `Protocol.swift:117` |
| H8 | Old multiprocessing queues not closed on restart | Agent 4 | `transcriber.py:209` |
| H9 | `requirements.txt` not pinned | Agent 6 | `requirements.txt` |
| H10 | Commands sent before `isRunning=true` silently dropped | Agent 3 | `ProcessBridge.swift:98` |

### MEDIUM

| # | Issue | Found by | Location |
|---|-------|----------|----------|
| M1 | Debug NSLog in production Swift code | Agent 6 | 3 Swift files, 15+ calls |
| M2 | VAD pre/post buffer durations hardcoded | Agents 1, 6 | `vad.py:67-68` |
| M3 | No IPC handshake protocol (hardcoded delays) | Agent 3 | `ProcessBridge.swift`, `server.py` |
| M4 | Queue.Full silently drops utterances | Agent 1 | `vad.py:174-175` |
| M5 | Restart off-by-one (4 attempts, not 3) | Agent 2 | `TranscriptionEngine.swift:192` |
| M6 | .gitignore incomplete | Agent 6 | `.gitignore` |
| M7 | Server global state without lock | Agent 1 | `server.py:82-88` |
| M8 | openWindow in App.init() via async — fragile | Agent 2 | `EsperApp.swift:43-45` |
| M9 | stderr readabilityHandler never cleared | Agent 2 | `ProcessBridge.swift:65-72` |
| M10 | Swift doesn't flush stdin pipe after write | Agent 3 | `ProcessBridge.swift:112` |
| M11 | Python not found -> generic error | Agent 4 | `AppSettings.swift:27` |
| M12 | Crash counter not incremented on restart timeout | Agent 4 | `transcriber.py:263-265` |
| M13 | Speech queue maxsize magic number | Agent 6 | `server.py:208` |

### LOW

| # | Issue | Found by | Location |
|---|-------|----------|----------|
| L1 | Unused `Optional` import | Agent 6 | `vad.py:13` |
| L2 | Missing Swift module docstrings | Agent 6 | Multiple Swift files |
| L3 | AudioLevelMeter 3.0x scaling magic number | Agent 6 | `AudioLevelMeter.swift:7` |
| L4 | CLI print() vs server logging inconsistency | Agent 6 | `realtime_demo.py` |
| L5 | VadThread frame duration not from config | Agent 1 | `vad.py:25` |

---

## Test Suite Gaps

### Coverage by Module

| Module | Tests | Coverage |
|--------|-------|----------|
| `config.py` | 24 | ~95% (values stale) |
| `vad.py` | 13 | ~85% |
| `transcriber.py` | 16 | ~80% |
| `telegram_sender.py` | 13 | ~75% |
| `server.py` | 4 | **~15%** |
| `audio_capture.py` | 0 | **0%** |
| `whisper_worker.py` | 0 | **0%** |
| `realtime_demo.py` | 0 | **0%** |

### Key Gaps
- **No integration tests exist** — entire pipeline never tested end-to-end
- **All subprocess tests are mocked** — real spawn-context Process never tested
- **Server command handlers have zero tests** — `_do_start`, `_do_stop`, `_do_set_device`
- **Concurrent `_send()` interleaving never tested** — the actual bug in C3

---

## What's Good (Don't Touch)

- Clean module separation with single responsibilities
- Queue-based inter-thread communication (thread-safe by design)
- Spawn-context subprocess isolation for Whisper (MLX Metal safety)
- `config.py` as single source of truth (no circular deps, verified by test)
- Auto-restart with bounded retry at both Python and Swift layers
- Hallucination filtering with configurable thresholds
- Proper SIGTERM handling and graceful shutdown flow
- Sentinel pattern for clean queue termination
- `@Observable` + `@MainActor` pattern in SwiftUI (correctly applied)
- View reactivity — minimal re-renders, proper state binding

---

## Recommended Fix Order

### Phase 1: Security & Correctness (30 min)
1. Revoke Telegram token, scrub `.env` from git history
2. Update 6 test values to match current config
3. Pin `requirements.txt`

### Phase 2: Thread Safety (1 hr)
4. Add `threading.Lock` around `_send()` in `server.py`
5. Import config values in `telegram_sender.py` instead of hardcoding
6. Add logging for parse failures in ProcessBridge reader

### Phase 3: Resilience (1 hr)
7. VadThread: send sentinel to `speech_q` on exception
8. ProcessBridge: close pipes on launch exception
9. ProcessBridge: clear stderr readabilityHandler in terminate()
10. Add `#if DEBUG` around verbose NSLog calls

### Phase 4: IPC Hardening (1 hr)
11. Implement ready handshake (Python sends `ready`, Swift waits)
12. Remove dead `telegram_sent` event handling
13. Fix restart off-by-one in TranscriptionEngine
14. Add stdin pipe flush in ProcessBridge

### Phase 5: Test Suite (2-3 hrs)
15. Add integration test for server command round-trip
16. Add `audio_capture.py` tests
17. Add `_whisper_consumer()` tests
18. Add concurrent `_send()` interleaving test
19. Add VAD/Telegram edge case tests

### Phase 6: Hygiene (30 min)
20. Extract VAD buffer durations to config
21. Complete .gitignore
22. Add speech queue maxsize to config
