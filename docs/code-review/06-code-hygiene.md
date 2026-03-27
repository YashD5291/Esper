# Agent 6: Code Hygiene & Standards Review

**Scope**: All source files — dead code, debug artifacts, naming, Python/Swift standards, configuration, documentation.

**Date**: 2026-03-28

---

## 1. Security Issue

### Real Telegram Credentials in `.env`
**Severity: CRITICAL**

`.env` contains real bot token and chat ID:
```
TELEGRAM_BOT_TOKEN=8469557645:AAE6mP76K2cSYjO0p5Xh-1Ec_hvAQ7JXHZ8
TELEGRAM_CHAT_ID=-1003838519860
```

- File exists in repo (even though `.env` is in `.gitignore`)
- May already be in git history
- **Action**: Revoke token immediately, scrub git history, create `.env.example`

---

## 2. Test/Config Value Mismatch
**Severity: HIGH**

6 config values updated in production but tests still assert old values. See Agent 5 report for full table. All affected tests will fail.

---

## 3. Debug Logging in Production Swift Code
**Severity: MEDIUM**

15+ verbose NSLog calls across:
- `EsperApp.swift` — lines 34, 36, 38
- `TranscriptionEngine.swift` — lines 44, 49, 56, 151, 154
- `ProcessBridge.swift` — lines 69, 135, 142, 145, 153, 156, 162

Examples:
```swift
NSLog("[Bridge] Reader: got %d bytes", data.count)
NSLog("[Bridge] Reader thread started on fd=%d", handle.fileDescriptor)
```

These include low-level details (file descriptors, byte counts). Should be wrapped in `#if DEBUG`.

---

## 4. Hardcoded Values Not in Config
**Severity: MEDIUM**

### VAD buffer durations
`vad.py:67-68`:
```python
pre_frames = math.ceil(300 / _FRAME_MS)   # 300ms
post_frames = math.ceil(200 / _FRAME_MS)  # 200ms
```
Should be `config.VAD_PRE_BUFFER_MS` and `config.VAD_POST_BUFFER_MS`.

### Speech queue maxsize
`server.py:208` and `realtime_demo.py:127`:
```python
speech_q = _queue.Queue(maxsize=10)
```
Should be `config.SPEECH_QUEUE_MAXSIZE`.

---

## 5. Dependencies Not Pinned
**Severity: MEDIUM**

`requirements.txt`:
```
sounddevice
numpy
soundfile
httpx
python-dotenv
silero-vad
torch
torchaudio
mlx-whisper==0.4.3
```

Only `mlx-whisper` is pinned. All other deps float. Breaks reproducibility across machines and over time.

**Fix**: Run `pip freeze` and pin all versions.

---

## 6. .gitignore Incomplete
**Severity: MEDIUM**

Missing entries:
- `.pytest_cache/`
- `.claude/`
- `*.log`
- `*.swp`, `*.swo`
- `.vscode/`
- `.idea/`

---

## 7. Unused Import
**Severity: Very Low**

`vad.py:13`:
```python
from typing import Optional
```
`Optional` is imported but Python 3.10+ union syntax is available. Minor style issue.

---

## 8. Missing Documentation

### @unchecked Sendable Rationale
`ProcessBridge.swift:5` — `@unchecked Sendable` without explaining why thread safety is guaranteed (it isn't fully — see Agent 2 report).

### Swift Module Docstrings
Missing top-level doc comments:
- `TranscriptionEngine.swift`
- `MainWindowView.swift`
- `TranscriptView.swift`
- `AudioLevelMeter.swift`

### AudioLevelMeter Magic Number
`AudioLevelMeter.swift:7`:
```swift
min(level * 3.0, 1.0)  // 3.0x scaling factor
```
UI tuning parameter not documented or configurable.

---

## 9. Naming & Consistency

### CLI vs Server Logging
- `realtime_demo.py` uses `print()` for output (11+ calls)
- `server.py` uses `logging.*` exclusively

Acceptable for interactive CLI vs headless server, but inconsistent pattern.

### Python Standards
- Type hints: present on all config values, most function signatures
- Docstrings: all modules and classes have clear docstrings
- PEP 8: compliant throughout
- Module constants: uppercase (correct)

### Swift Standards
- Access control: mostly correct, some properties could be private
- Value vs reference types: correct (class for ProcessBridge/Engine, struct for views)
- Memory management: weak/unowned used correctly

---

## Issue Summary Table

| # | Category | Severity | Issue | Location | Fix Effort |
|---|----------|----------|-------|----------|-----------|
| 1 | Security | **CRITICAL** | Real Telegram credentials | `.env` | 30 min |
| 2 | Correctness | **HIGH** | 6 test/config mismatches | `test_config.py`, `test_whisper_transcriber.py` | 10 min |
| 3 | Debug Code | MEDIUM | Verbose NSLog in production | 3 Swift files | 20 min |
| 4 | Config | MEDIUM | VAD buffer/queue magic numbers | `vad.py`, `server.py` | 15 min |
| 5 | Build | MEDIUM | requirements.txt not pinned | `requirements.txt` | 10 min |
| 6 | VCS | MEDIUM | .gitignore incomplete | `.gitignore` | 5 min |
| 7 | Dead Code | Very Low | Unused Optional import | `vad.py:13` | 1 min |
| 8 | Documentation | Low | Missing docstrings/rationale | Swift files | 20 min |
| 9 | Consistency | Low | print() vs logging | `realtime_demo.py` | 20 min |
