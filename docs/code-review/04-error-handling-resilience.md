# Agent 4: Error Handling & Resilience Review

**Scope**: All source files — failure modes, resource leaks, thread safety, graceful degradation, recovery, logging.

**Date**: 2026-03-28

---

## 1. Failure Modes

### 1.1 Microphone Disconnection Mid-Stream
**Status: Handled Partially**

- `audio_capture.py:106-116` — callback logs status warning but doesn't propagate error
- No signal sent to stop VAD or Whisper processing
- Chunks may contain invalid/zero data
- VAD keeps processing garbage audio

**Scenario**: User unplugs USB mic while listening
- Expected: graceful stop, clear error message
- Actual: VAD processes silence/garbage, Whisper times out, UI frozen on "transcribing"

### 1.2 Whisper Subprocess Crash
**Status: Partially Handled**

- Auto-restart works (`transcriber.py:247-265`): 3 attempts then stops
- **Gap**: On restart, new queues are created but old ones not drained (`transcriber.py:209`). Stale results from old queue could theoretically be read.
- **Gap**: If restarted worker also fails startup, `_crash_count` is not incremented at lines 263-265. Counter stays at 1, next utterance retries with stale count.

### 1.3 Telegram API Unreachable
**Status: Well Handled**

- Exponential backoff: `_BACKOFF_BASE * (2 ** attempt)`
- Max 3 retries
- 429 rate limit handling with `retry_after` from response
- On final failure, message dropped cleanly with log

### 1.4 Model Files Corrupted/Missing
**Status: Partially Handled**

- Worker detects `ImportError` on startup (`whisper_worker.py:44-49`)
- Model corruption detected only at first `transcribe()` call — after ready sentinel already sent
- Parent thinks worker is ready, first transcribe times out (15s)
- Auto-restarts 3 times, each time waiting up to 120s for model load
- **User sees**: "Model loading..." hangs, then "crashed" — doesn't know model is corrupted

### 1.5 Python Not Found
**Status: Poor**

- `AppSettings.swift:27` defaults to `.venv/bin/python3`
- No validation that path exists before `ProcessBridge.launch()`
- Error message: generic "Failed to launch Python: No such file or directory"
- User doesn't know to run setup.sh

---

## 2. Resource Leaks

### 2.1 Python Threads

**`_bridge_thread` may not exit** (`server.py:212`):
- If transcriber fails to start, `_whisper_consumer()` loops on `_speech_q.get(timeout=0.2)` indefinitely
- 2s join timeout may not be enough — thread orphaned

**`_energy_thread` safe** — checks `_stop_event.is_set()` and `_capture is not None`

**All threads are daemon=True** — on Python exit, daemon threads terminated forcefully. No cleanup code runs.

### 2.2 Swift Reader Thread

**`ProcessBridge.terminate()` at lines 116-127** — no explicit join on reader thread:
- Thread blocks on `handle.availableData` (line 140)
- If Python doesn't close stdout, thread hangs permanently
- Thread holds reference to handle, can't be cleaned up

### 2.3 File Descriptors

**Pipes not closed on exception** (`ProcessBridge.swift:88-93`):
- If `proc.run()` throws, catch block yields error but never closes 3 pipes created at lines 46-48
- FD leak on launch failure

**Old multiprocessing queues not closed on restart** (`transcriber.py:231-232`):
- On worker restart, new queues created. Old `_audio_q` and `_result_q` are orphaned
- Multiprocessing queues hold FDs internally
- After 3 restarts = 3 orphaned queue pairs

### 2.4 Audio Streams
**Status: Safe** — `stop()` calls `stream.stop()`, `stream.close()`, sends sentinel

---

## 3. Thread Safety

### 3.1 Python Queues
**Safe** — `queue.Queue` and `multiprocessing.Queue` are thread/process-safe

### 3.2 `_stop_event`
**Safe** — `threading.Event` is thread-safe

### 3.3 Cross-Process Pipe Safety
**ISSUE: No write lock on `_send()`**

Multiple threads call `_send()` (`server.py:70`):
- `_bridge_thread` (whisper consumer)
- `_energy_thread`
- Main thread (command responses)

`_proto_out.write()` is NOT atomic for multi-line writes. Two concurrent writes can produce:
```
{"event":"tra{"event":"energy",...}\n
nsript",...}\n
```

**Result**: ProcessBridge reader gets malformed JSON, `ServerEvent.parse()` returns nil, events silently dropped.

---

## 4. Graceful Degradation

### Model Not Found
- `TranscriptionEngine.swift:209` — detects "model not found" and "no such file" patterns
- Shows user-friendly message
- **Gap**: Worker's `ImportError` message doesn't contain "model" — generic message shown

### No Audio Devices
- Detects "no audio device", "no input device", "invalid device"
- Shows "No microphone detected. Check System Settings > Sound."

### Python Not Found
- Generic error message, no guidance to run setup.sh

---

## 5. Recovery

### Auto-Restart Logic
**Correct, no infinite loop**

Python (transcriber.py): 3 crash limit, then stops
Swift (TranscriptionEngine.swift): 3 restart limit, 2s backoff, counter resets on success

**Minor**: Restart counter not incremented on startup timeout in Python (`transcriber.py:263-265`). Could lead to extra restart attempts.

---

## 6. Logging Quality

### Sufficient for diagnosis
- Model loading, worker startup, ready sentinel, timeouts, crashes, VAD utterances, Telegram sends/errors — all logged

### Missing log statements
1. Audio device switch doesn't show device name (`server.py:282`)
2. Swift protocol parse failures silent (`ProcessBridge.swift:155`)
3. Process exit codes not logged with meaning (`ProcessBridge.swift:80`)

### Log levels
**Appropriate** — debug for verbose, info for events, warning for degraded, error for failures

---

## Concrete Failure Scenarios

### Scenario A: Whisper Model Corrupted
1. Worker imports mlx_whisper OK, sends ready sentinel
2. First `transcribe()` call crashes on corrupted weights
3. Parent times out (15s), kills worker, restarts
4. Repeats 2 more times (45s total)
5. User sees: "Python crashed repeatedly. Restart manually."
6. **Expected**: "Model files corrupted. Delete models/whisper/ and re-run setup."

### Scenario B: JSON Interleave
1. Energy thread and whisper consumer both call `_send()` simultaneously
2. Writes interleave, producing malformed JSON on pipe
3. ProcessBridge reader gets corrupted line
4. `ServerEvent.parse()` returns nil, event silently dropped
5. **Expected**: Lock prevents interleaving

### Scenario C: USB Microphone Unplug
1. User unplugs USB mic during recording
2. sounddevice callback fires with status != 0
3. `audio_capture.py:108` logs warning, continues
4. VAD processes garbage, Whisper waits for speech
5. App shows "Listening" with no transcription
6. **Expected**: "Audio device disconnected" message, capture stops

---

## Issue Summary Table

| Category | Issue | Location | Severity |
|----------|-------|----------|----------|
| Failure Modes | Mic disconnect not propagated | `audio_capture.py:106` | HIGH |
| Failure Modes | Model corruption -> 120s timeout | `whisper_worker.py:64` | MEDIUM |
| Failure Modes | Python not found -> generic error | `AppSettings.swift:27` | MEDIUM |
| Resource Leaks | Reader thread not joined | `ProcessBridge.swift:134` | MEDIUM |
| Resource Leaks | Pipes not closed on exception | `ProcessBridge.swift:88` | LOW |
| Resource Leaks | Old queues not closed on restart | `transcriber.py:209` | LOW |
| Thread Safety | No write lock on `_send()` | `server.py:70` | **HIGH** |
| Logging | Silent parse failures | `ProcessBridge.swift:155` | MEDIUM |
