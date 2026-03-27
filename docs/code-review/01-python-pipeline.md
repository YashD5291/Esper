# Agent 1: Python Pipeline Architecture Review

**Scope**: All files in `src/` and `tests/` — architecture, error handling, code quality, threading, correctness.

**Date**: 2026-03-28

---

## 1. Architecture & Design

**Rating: Excellent**

- Module separation is clean: `audio_capture.py`, `vad.py`, `transcriber.py`, `telegram_sender.py`, `server.py` all have well-defined single responsibilities
- Config pattern (`src/config.py`) is properly enforced as SSOT — zero internal imports (verified by test at `test_config.py:133-156`)
- No circular dependencies detected
- Subprocess isolation strategy is sound: `WhisperTranscriber` uses spawn-context multiprocessing (`transcriber.py:230-239`) to isolate Whisper from main process

---

## 2. Error Handling

**Rating: Good with gaps**

### Strengths
- Explicit error handling throughout critical paths
- Clean error event propagation: `WhisperTranscriber` emits `on_status("error")` before retry logic (`transcriber.py:181, 187`)
- Resource cleanup is thorough:
  - VadThread: proper `thread.join()` with timeout (`vad.py:56`)
  - WhisperTranscriber: `_kill_worker()` with join timeout (`transcriber.py:243-245`)
  - AudioCapture: closes stream properly (`audio_capture.py:84-87`)
  - TelegramSender: `httpx.Client` context manager (`telegram_sender.py:50`)
  - server.py: graceful shutdown with `_do_stop()` on SIGTERM (`server.py:318-321`)

### Issues Found

1. **`telegram_sender.py:49-58` — No exception logging in `_loop()`**
   - If `_queue.get()` or `_send_message()` raises an unexpected exception, the loop exits silently
   - Should add `except Exception: log.error(..., exc_info=True)`

2. **`vad.py:139-140` — Thread exits without notifying downstream**
   - On exception, VadThread logs and exits but never sends `None` sentinel to `speech_q`
   - Downstream `_whisper_consumer` will block forever on `speech_q.get()`

3. **`server.py:356-358` — Broad exception catch in command dispatch**
   - Catches all exceptions, logs them, and continues
   - If a handler has a critical failure (OOM), server stays running in potentially corrupted state

---

## 3. Code Quality

**Rating: Very Good**

### Strengths
- No commented-out code in production files
- No debug `print()` left in (logging used consistently)
- All imports are used
- Every module/class has clear docstrings
- Magic numbers centralized in `config.py`

### Issues Found

1. **`telegram_sender.py:20-21` — Hardcoded config values**
   ```python
   _MAX_RETRIES = 3
   _BACKOFF_BASE = 1.0
   ```
   Should import from `config.TELEGRAM_MAX_RETRIES` and `config.TELEGRAM_BACKOFF_BASE`. Currently silently ignores config changes.

2. **`realtime_demo.py:127` and `server.py:208` — Magic queue size**
   ```python
   speech_q = _queue.Queue(maxsize=10)
   ```
   Should be in config as `SPEECH_QUEUE_MAXSIZE`.

---

## 4. Thread Safety & Concurrency

**Rating: Good**

### Strengths
- All inter-thread communication uses `queue.Queue` (thread-safe)
- `AudioCapture` uses proper locking for energy property (`audio_capture.py:101-102`)
- `ConsoleRenderer` locks output (`realtime_demo.py:43, 47-48`)

### Issues Found

1. **`server.py:82-88` — Global mutable state without locks**
   ```python
   _capture: AudioCapture | None = None
   _transcriber = None
   _telegram_sender = None
   _vad_thread: VadThread | None = None
   ```
   Accessed from `_do_start()`, `_do_stop()`, `_do_set_device()`, and consumer threads. If `stop` arrives while `start` is setting up globals, partial initialization could crash.

   The code relies on JSON command stream being single-threaded, but this isn't explicitly enforced.

---

## 5. Correctness Issues

### Critical: Test/Config Value Mismatch

Tests were written for old config values. Config was tuned to be more aggressive, tests weren't updated.

| Parameter | config.py | Tests expect |
|-----------|-----------|-------------|
| `VAD_SPEECH_THRESHOLD` | 0.3 (line 21) | 0.5 (`test_config.py:57`) |
| `VAD_SILENCE_THRESHOLD_MS` | 300 (line 22) | 500 (`test_config.py:62`) |
| `VAD_MIN_SPEECH_DURATION_MS` | 100 (line 23) | 500 (`test_config.py:67`) |
| `VAD_MIN_ENERGY` | 0.003 (line 24) | 0.01 (`test_config.py:72`) |
| `WHISPER_NO_SPEECH_THRESHOLD` | 0.8 (line 31) | 0.6 (`test_whisper_transcriber.py:97`) |
| `WHISPER_COMPRESSION_RATIO_THRESHOLD` | 3.0 (line 32) | 2.4 (`test_whisper_transcriber.py:98`) |

### Other Issues

2. **`vad.py:25` — Hardcoded frame duration**
   ```python
   _FRAME_MS: int = 32
   ```
   Should verify against `config.CHUNK_DURATION` or derive from it.

3. **`vad.py:174-175` — Silent data loss on queue full**
   ```python
   except queue.Full:
       log.warning("speech_q full -- utterance discarded")
   ```
   Utterance is silently dropped. No way for caller to know.

---

## 6. Shutdown & Cleanup

**Rating: Very Good**

- SIGTERM handler correct (`server.py:318-321`)
- All threads have `join(timeout=...)` — no indefinite hangs
- Sentinel pattern used (`None` to queues)
- `AudioCapture` sends sentinel (`audio_capture.py:89`)
- `TelegramSender` drains queue on stop (`telegram_sender.py:95-97`)

### Minor Issues
- `server.py:254` — 2.0s timeout on energy_thread join is aggressive, should be 5.0s
- No verification via `is_alive()` after join timeout

---

## 7. Subprocess Management

**Rating: Excellent**

- Spawn context prevents fork issues (`transcriber.py:230`)
- Worker process uses `daemon=True` (`transcriber.py:236`)
- No zombie process risk — `join()` always called
- Parent sends audio via `SimpleQueue` (fast, no pickling overhead)
- Watchdog timeout on `result_q.get()` kills hung workers
- Generation-based restart prevents memory creep (`transcriber.py:205-216`)

---

## Summary

| Category | Rating | Critical Issues |
|----------|--------|-----------------|
| Architecture | 9/10 | None |
| Error Handling | 7/10 | Silent loop exit, no downstream sentinel |
| Code Quality | 8.5/10 | Hardcoded config in telegram_sender |
| Thread Safety | 7.5/10 | Unprotected global state in server.py |
| Correctness | 6/10 | 6 test/config mismatches |
| Shutdown | 8.5/10 | Minor timeout issues |
| Subprocess | 9.5/10 | Near-perfect isolation |
