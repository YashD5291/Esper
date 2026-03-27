---
phase: 5
slug: telegram-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none — pytest auto-discovers `tests/` |
| **Quick run command** | `python3 -m pytest tests/test_telegram_sender.py -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_telegram_sender.py -x -q`
- **After every plan wave:** Run `python3 -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | INTG-01 | unit | `python3 -m pytest tests/test_telegram_sender.py::test_two_utterances_send_two_messages -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | INTG-01 | unit | `python3 -m pytest tests/test_telegram_sender.py::test_empty_utterance_not_sent -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | INTG-01 | unit | `python3 -m pytest tests/test_telegram_sender.py::test_dead_state_removed -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | INTG-02 | unit | `python3 -m pytest tests/test_telegram_sender.py::test_shutdown_drains_queue -x` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | INTG-02 | unit (AST) | `python3 -m pytest tests/test_server_ipc.py::test_telegram_wait_timeout -x` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 1 | D-06 | unit | `python3 -m pytest tests/test_telegram_sender.py::test_429_respects_retry_after -x` | ❌ W0 | ⬜ pending |
| 05-01-07 | 01 | 1 | D-07 | unit | `python3 -m pytest tests/test_telegram_sender.py::test_max_retries_drops_message -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_telegram_sender.py` — all 7 test cases above; covers INTG-01, INTG-02, D-06, D-07
- [ ] Update `tests/test_config.py` — remove `test_telegram_stream_default_true` and `test_telegram_draft_interval` tests

*Existing infrastructure covers framework — pytest 9.0.2 already present.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Telegram message delivery | INTG-01 | Requires real Telegram API credentials | Start pipeline, speak, verify message appears in Telegram chat |
| Real 429 rate-limit handling | D-06 | Cannot reliably trigger 429 in unit tests | Send many messages rapidly to Telegram API and verify retry behavior |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
