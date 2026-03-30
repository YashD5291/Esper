# Esper Production Hardening Design

**Date:** 2026-03-30
**Goal:** Fix 32 identified issues across Python, Swift, IPC, audio, Telegram, security, tests, and build — without breaking any existing functionality.
**Constraint:** Zero regressions. Not a single percent effect on current working functionality.

---

## Ground Rules & Safety Protocol

### The Iron Rule

No production code changes without a test that proves current behavior first.

**Sequence for every fix:**

1. Branch off latest `main`
2. Write test(s) that exercise current behavior around the fix area
3. Run full suite — all tests MUST be green (existing 73 + new ones)
4. Make the production code change
5. Run full suite again — all tests MUST still be green
6. If any test turns red — revert the production change, investigate, try again clean
7. PR to main — merge ONLY with explicit user approval and full green suite

**Revert policy:** If step 6 fails, `git checkout` the production file back to pre-change state. No debug-and-patch on top.

**Smoke test checkpoint:** After every 5 merged PRs, manual end-to-end verification (mic -> transcript -> Telegram).

**Merge policy:** Nothing touches `main` without explicit user approval. All work stays on feature branches until verified.

### Execution Strategy

**Atomic Branch-Per-Fix.** Each issue gets its own branch off `main`. Maximum isolation — if fix #7 breaks something, it doesn't contaminate fix #8. Any single fix can be reverted without losing others.

---

## Phase 0: Security Quick Wins (Zero Code Changes)

No production logic touched. Housekeeping only.

### Fix #2 — Exposed Telegram Credentials

- User rotates bot token via BotFather (manual step)
- Remove `.env` from git history with `git filter-repo`
- Create `.env.example` with placeholder values
- Verify `.gitignore` already covers `.env`

### Fix #16 — gitignore Contradiction

- `/models/` ignores entire directory, then `!/models/silero_vad.onnx` negation doesn't work
- Fix: change to ignore `models/*/` (subdirs only) or `git add -f models/silero_vad.onnx`

### Fix #25 — Debug Logs to World-Readable /tmp

- Move `esper-bridge.log` path from `/tmp/` to `~/Library/Logs/Esper/`
- One line change in `ProcessBridge.swift` — zero functional impact

---

## Phase 1: Test Infrastructure (No Production Code Changes)

Only adds tests. Zero production files modified.

### Python — Fill the 50% Coverage Gap

| New test file | Module covered | What it locks down |
|---|---|---|
| `test_audio_capture.py` | `audio_capture.py` | Device selection, energy calc, queue behavior, callback handling |
| `test_whisper_worker.py` | `whisper_worker.py` | `_send_msg`/`_recv_msg` roundtrip, ready sentinel, model load error path |
| `test_vad_model.py` | `vad_model.py` | ONNX session init, `__call__` output shape, `reset_states` |
| `test_server_commands.py` | `server.py` | All 5 commands (list_devices, start, stop, set_device, test_telegram), error handling |
| `test_integration.py` | Full pipeline | Mock audio -> VAD -> Whisper -> Telegram end-to-end |

All tests use mocks (no real devices, no real Telegram, no real models). They lock down current behavior as-is, including current bugs.

### Swift — XCTest Target from Scratch

| Test file | What it locks down |
|---|---|
| `ProcessBridgeTests.swift` | Launch, send command, receive event, terminate lifecycle |
| `TranscriptionEngineTests.swift` | State transitions, crash recovery, restart logic |
| `ProtocolTests.swift` | JSON parsing for all event types, malformed input handling |
| `AppSettingsTests.swift` | Default values, dev path computation |

Requires adding an `EsperAppTests` target to the Xcode project. Tests use mock processes (not real Python) to verify Swift behavior in isolation.

**Exit criteria:** All new tests pass. Existing 73 tests still pass. Zero production files touched.

---

## Phase 2: Python Backend Hardening

Each fix is its own branch. Tests written first, then the fix. Ordered by dependency.

### Fix #1 — Missing `_pipe_proc` init (FIRST)
- **File:** `transcriber.py:86`
- **Change:** Add `self._pipe_proc = None`, `self._reader_thread = None`, `self._stderr_thread = None` to `__init__`
- **Risk:** Near-zero — adding initializers for attributes already expected to exist

### Fix #9 — Unclosed subprocess pipes
- **File:** `transcriber.py:311`
- **Change:** Close stdout and stderr in `_kill_worker()`, not just stdin
- **Risk:** Low — only affects cleanup path

### Fix #11 — Unhandled BrokenPipeError
- **File:** `transcriber.py:186`
- **Change:** Wrap `_send_msg()` in try/except, call `_on_failure()` on error
- **Risk:** Low — adds error handling around existing call

### Fix #10 — Silent VAD thread death
- **File:** `vad.py:134` + `server.py` (consumer loop)
- **Change:** When VAD thread catches an unexpected exception, log error and put an error sentinel into `speech_q`. The Whisper consumer loop in `server.py` detects the sentinel, emits an `error` event to Swift, and restarts the VAD thread (stop + create new + start).
- **Risk:** Medium — new behavior, but only triggers on currently-unhandled crash

### Fix #8 — Silent pipe overflow
- **File:** `server.py:80`
- **Change:** Replace `pass` with `log.warning()` in the BrokenPipeError catch
- **Risk:** Near-zero — only adds logging

### Fix #27 — Swallowed exceptions in readers
- **File:** `transcriber.py:289-308`
- **Change:** Replace `pass` with `log.error(..., exc_info=True)` in `_pipe_reader` and `_stderr_reader`
- **Risk:** Near-zero — only adds logging

### Fix #21 — Hardcoded sample rate
- **File:** `vad.py:169`
- **Change:** Change `16000` to `config.SAMPLE_RATE`
- **Risk:** Near-zero — value is currently 16000 anyway

### Fix #30 — Unbounded session memory
- **File:** `transcriber.py:95`
- **Change:** Cap `_sentences` to last 500 entries
- **Risk:** Low — only affects sessions longer than 500 utterances

### Fix #31 — No config validation
- **File:** `config.py`
- **Change:** Add assertions at module level (0 <= threshold <= 1, queue_size > 0, etc.)
- **Risk:** Low — validates what's already true, fails fast on misconfiguration

### Fix #33 — SIGTERM skips cleanup
- **File:** `server.py:329`
- **Change:** Replace `sys.exit(0)` with raising `SystemExit` so finally blocks execute
- **Risk:** Low — same exit behavior but cleaner path

### Fix #32 — No Telegram credential validation
- **File:** `server.py:176`
- **Change:** Validate token format (regex) and chat_id (numeric) before creating sender
- **Risk:** Low — rejects what would fail later anyway

---

## Phase 3: Swift/IPC Hardening

Most delicate phase. XCTests from Phase 1 are the safety net. Ordered by dependency.

### Fix #3 — ProcessBridge data races (FIRST)
- **File:** `ProcessBridge.swift`
- **Change:** Add `NSLock` to guard all mutable state (`isRunning`, `userInitiatedStop`, `eventContinuation`, pipe references). Every read/write goes through the lock.
- **Risk:** Medium — threading change, but mechanical (lock/unlock around existing accesses)

### Fix #5 — Reader thread can't be cancelled
- **File:** `ProcessBridge.swift:184`
- **Change:** Replace `while true` + `availableData` with a loop that checks a `shouldStop` flag. Close the pipe's file descriptor on terminate to force EOF.
- **Risk:** Medium — changes blocking behavior, XCTests verify lifecycle

### Fix #6 — Zombie Python processes
- **File:** `ProcessBridge.swift:160`
- **Change:** After `process?.terminate()`, add `DispatchQueue.global().async { process.waitUntilExit() }` with 5s timeout, then SIGKILL if still alive
- **Risk:** Medium — new cleanup logic, only on termination path

### Fix #4 — IPC deadlock potential
- **Files:** `ProcessBridge.swift` + `server.py`
- **Change:** Make Python's stdout writes non-blocking (catch `BlockingIOError`, drop event with warning). On Swift side, add bounded buffer to AsyncStream (`.bufferingPolicy(.bufferingNewest(100))`)
- **Risk:** Medium-High — changes both sides of the protocol. Tests must verify event flow still works.

### Fix #7 — No command-response timeout
- **File:** `TranscriptionEngine.swift`
- **Change:** Add 30s watchdog after sending a command. If no relevant event arrives within 30s, yield `.error("Python unresponsive")` and trigger restart.
- **Risk:** Medium — new behavior, only activates when things are already broken

### Fix #20 — No protocol versioning
- **Files:** `Protocol.swift` + `server.py`
- **Change:** Add `"v": 1` field to all events. Swift logs warning on unknown version but still processes. Forward-compatible, no breaking change.
- **Risk:** Low — additive only

### Fix #12 — Credentials in plaintext UserDefaults
- **Files:** `AppSettings.swift` + new `KeychainHelper.swift`
- **Change:** Move `telegramBotToken` and `telegramChatId` from `@AppStorage` to Keychain via a small helper. Migration: on first launch with new code, read old UserDefaults values, write to Keychain, delete from UserDefaults.
- **Risk:** Medium — changes credential storage location, migration must be seamless

---

## Phase 4: Audio + Telegram Robustness

Real-world resilience: device unplugged, network drops, API quirks.

### Fix #18 — Queue overflow silently drops audio
- **File:** `audio_capture.py:115`
- **Change:** Add `log.warning("Audio queue full — dropping frame")` with periodic counter (not per-frame spam)
- **Risk:** Near-zero — only adds logging

### Fix #13 — Audio device disconnect not detected
- **File:** `audio_capture.py:106`
- **Change:** When `status` flag indicates device error, log at ERROR level and put sentinel error marker into queue. VAD propagates upstream. Server emits `error` event to Swift.
- **Risk:** Medium — new error propagation path, only triggers on hardware failure

### Fix #22 — No Telegram response body verification
- **File:** `telegram_sender.py:65`
- **Change:** After `status_code == 200`, also check `resp.json().get("ok")`. If `False`, log error and treat as failure.
- **Risk:** Low — tightens success criteria

### Fix #23 — Non-retryable errors retried
- **File:** `telegram_sender.py:81`
- **Change:** Early return for 400/401/403 (don't retry, log as permanent failure). Only retry on 429, 5xx, and transport errors.
- **Risk:** Low — reduces wasted retries, doesn't change success path

### Fix #24 — No message length limit
- **File:** `telegram_sender.py:62`
- **Change:** If `len(text) > 4096`, truncate to 4093 + `"..."`. Log warning.
- **Risk:** Near-zero — Whisper utterances almost never exceed 4K chars

### Fix #26 — Pickle deserialization in IPC
- **Files:** `whisper_worker.py` + `transcriber.py`
- **Change:** Replace pickle with length-prefixed JSON for control messages. Keep raw numpy bytes for audio (length-prefixed `ndarray.tobytes()` + shape header). No pickle.
- **Risk:** Medium — serialization format change, both sides change together. Tests verify roundtrip.

---

## Phase 5: Build & Packaging

Making the app installable by someone who isn't you.

### Fix #17 — No microphone permission request
- **Change:** Add `NSMicrophoneUsageDescription` to Info.plist. Add pre-flight check in `TranscriptionEngine` via `AVCaptureDevice.authorizationStatus(for: .audio)`. If denied, show clear error in UI.
- **Risk:** Low — additive, doesn't change audio capture logic

### Fix #28 — Hardcoded dev path in AppSettings
- **Change:** Replace hardcoded `Codebase/Fun/Esper` with dynamic resolution: `Bundle.main.bundlePath` parent for frozen mode, environment variable `ESPER_PROJECT_DIR` for dev mode.
- **Risk:** Low — only affects dev mode fallback path

### Fix #14 — No Gatekeeper/notarization
- **Change:** Update `build-dmg.sh` with `--options runtime` flag (hardened runtime). Document notarization step (requires Apple Developer account). If no account, document `xattr -cr` workaround in README and first-run dialog.
- **Risk:** Low — build script changes, no runtime code changes

### Fix #29 — No update mechanism
- **Decision:** Out of scope. Sparkle integration is a feature addition, not a bug fix. Documented as future enhancement.

---

## Issue Tracker

Total: 32 fixes across 5 phases (issue #29 cut as out-of-scope, #19 merged into #4).

| Phase | Fixes | Risk Profile |
|---|---|---|
| Phase 0: Security | #2, #16, #25 | Near-zero (no logic changes) |
| Phase 1: Tests | New test files only | Zero (no production changes) |
| Phase 2: Python | #1, #8, #9, #10, #11, #21, #27, #30, #31, #32, #33 | Low to Medium |
| Phase 3: Swift/IPC | #3, #4, #5, #6, #7, #12, #20 | Medium to Medium-High |
| Phase 4: Audio/Telegram | #13, #18, #22, #23, #24, #26 | Low to Medium |
| Phase 5: Build | #14, #17, #28 | Low |
