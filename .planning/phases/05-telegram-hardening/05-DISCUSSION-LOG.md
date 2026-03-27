# Phase 5: Telegram Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 05-telegram-hardening
**Areas discussed:** Shutdown flush, Rate-limit recovery, Draft streaming fate

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Shutdown flush | Queue drain behavior on stop, 10s timeout | |
| Rate-limit recovery | 429 handling, Retry-After parsing, queue management | |
| Draft streaming fate | sendMessageDraft removal vs keeping optional | |

**User's choice:** "Nothing extra, just vad detects the utterances -> transcribe -> send to telegram, simple"
**Notes:** User deferred all three areas to Claude's discretion. Emphasized simplicity — the pipeline is VAD → transcribe → send, no extra features needed.

---

## Claude's Discretion

- Shutdown flush implementation (10s drain window)
- Rate-limit 429 handling specifics
- Draft streaming removal approach
- All implementation details

## Deferred Ideas

None
