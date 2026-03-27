---
phase: 05-telegram-hardening
plan: 01
subsystem: telegram
tags: [telegram, hardening, 429, rate-limit, cleanup]
dependency_graph:
  requires: [04-02]
  provides: [INTG-01, INTG-02]
  affects: [src/telegram_sender.py, src/server.py, src/config.py]
tech_stack:
  added: []
  patterns: [429-retry-after-parsing, shutdown-drain-with-timeout]
key_files:
  created: []
  modified:
    - tests/test_telegram_sender.py
    - src/telegram_sender.py
    - src/config.py
    - tests/test_config.py
    - src/server.py
decisions:
  - "429 retry_after parsed from JSON body.parameters.retry_after; falls back to exponential backoff when absent (D-06)"
  - "wait() default timeout set to 10.0s enabling 10s shutdown drain window (D-05, INTG-02)"
  - "stream parameter removed from TelegramSender.__init__ — D-02 cleanup deferred from Phase 4"
  - "TELEGRAM_STREAM and TELEGRAM_DRAFT_INTERVAL removed from config.py — dead constants"
metrics:
  duration: "5min"
  completed_date: "2026-03-27"
  tasks_completed: 2
  files_modified: 5
---

# Phase 5 Plan 1: Telegram Hardening — 429 handling, stream cleanup, 10s timeout

TelegramSender hardened with 429 rate-limit retry_after parsing, stream parameter removal, and 10s shutdown drain; dead config constants TELEGRAM_STREAM and TELEGRAM_DRAFT_INTERVAL removed from config.py and server.py.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 RED | Add 6 hardening tests for 429/shutdown/timeout | ff81a6f | tests/test_telegram_sender.py |
| 1 GREEN | Add 429 handling, remove stream param, 10s timeout | 1b4ff2e | src/telegram_sender.py |
| 2 | Remove dead config, update server.py constructor | d2164f9 | src/config.py, tests/test_config.py, src/server.py |

## What Was Built

### TelegramSender (src/telegram_sender.py)

- `__init__` no longer accepts `stream` parameter — per-utterance model is the only mode
- `_send_message` intercepts 429 responses: parses `parameters.retry_after` from JSON body and sleeps that duration; falls back to `_BACKOFF_BASE * (2**attempt)` when absent
- `wait()` default timeout changed from 5.0 to 10.0 seconds

### Config cleanup (src/config.py)

- `TELEGRAM_STREAM: bool = True` removed
- `TELEGRAM_DRAFT_INTERVAL: float = 0.5` removed
- `TELEGRAM_MAX_RETRIES` and `TELEGRAM_BACKOFF_BASE` retained

### Server (src/server.py)

- `_do_start`: constructs `TelegramSender(bot_token, chat_id)` — no `stream=` kwarg
- `_do_start`: no longer sets `config.TELEGRAM_STREAM`
- `_do_stop`: uses `_telegram_sender.wait(timeout=10.0)` instead of 5.0

### Tests (tests/test_telegram_sender.py, tests/test_config.py)

- 6 new hardening tests added to `TestHardening` class
- `test_telegram_stream_default_true` and `test_telegram_draft_interval` removed from test_config.py

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

All created files verified on disk. All task commits verified in git history.

## Verification Results

```
python3 -m pytest tests/test_telegram_sender.py -x -q  → 13 passed
python3 -m pytest tests/test_config.py -x -q           → 15 passed
python3 -m pytest tests/ -x -q                         → 62 passed
grep TELEGRAM_STREAM src/config.py                     → 0 matches
grep "wait(timeout=10.0)" src/server.py                → 1 match in _do_stop
grep "resp.status_code == 429" src/telegram_sender.py  → 1 match
```
