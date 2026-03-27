# Phase 5: Telegram Hardening - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Telegram sender adapts to the per-utterance `TranscriptionUpdate` contract from Phase 4. The old streaming/draft model is removed entirely. Each VAD-gated utterance produces one Whisper transcription which becomes one Telegram message. Shutdown flushes reliably within 10 seconds. 429 rate-limit responses are handled without crashing.

</domain>

<decisions>
## Implementation Decisions

### Message model
- **D-01:** One Telegram message per utterance. No drafts, no accumulation, no `_processed_chars`. Each `TranscriptionUpdate` from Whisper maps to exactly one `sendMessage` call.
- **D-02:** Remove `sendMessageDraft` entirely — no draft streaming, no `_draft_buf`, no `_draft_id`, no `_last_draft_t`. The `stream` parameter and `stream=True/False` mode are eliminated.
- **D-03:** Remove the legacy `stream=False` sentence-counting mode (`_prev_sentence_count`). Only one mode: per-utterance send.

### Shutdown flush
- **D-04:** On stop, drain all queued messages within a 10-second window (up from current 5s). Messages still in queue after 10s are logged and dropped.
- **D-05:** The `wait()` timeout updates to 10.0s to match INTG-02 requirement.

### Rate-limit handling
- **D-06:** 429 responses are handled explicitly — parse `Retry-After` header if present, otherwise use existing exponential backoff. Pipeline does not crash on rate limits.
- **D-07:** Messages that fail after max retries are logged at ERROR level and dropped — pipeline continues processing subsequent utterances.

### Claude's Discretion
- Exact implementation of 429 detection and Retry-After parsing
- Whether to distinguish 429 from other HTTP errors in retry logic
- Queue drain implementation details during shutdown
- Whether `TelegramSender.__init__` signature simplifies (removing `stream` param)
- Test structure and fixtures

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — INTG-01 (per-utterance contract), INTG-02 (10s shutdown flush)

### Current implementation (to be rewritten)
- `src/telegram_sender.py` — Current TelegramSender with streaming/draft model to simplify
- `src/config.py` lines 29-34 — Telegram config constants (some may be removed with draft streaming)

### Phase 4 contract (upstream dependency)
- `.planning/phases/04-whisper-integration/04-CONTEXT.md` — D-01 (new TranscriptionUpdate shape), D-03 (per-utterance Telegram model)

### Integration points
- `src/server.py` — `_on_update()` (line 107) fans out to Telegram; `_do_stop()` (line 256) handles shutdown
- `src/transcriber.py` — Current `TranscriptionUpdate` dataclass (line 19) — replaced in Phase 4

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TelegramSender._send_message()`: Retry loop with exponential backoff — adapt for 429 handling
- `TelegramSender._loop()`: Queue-based background thread pattern — keep, simplify
- `config.TELEGRAM_MAX_RETRIES`, `config.TELEGRAM_BACKOFF_BASE`: Retry config already in place

### Established Patterns
- Queue-based background sender thread with sentinel `None` for shutdown
- httpx.Client for Telegram API calls with timeout
- Logging to stderr via `logging.getLogger(__name__)`

### Integration Points
- `server.py _on_update()` — calls `_telegram_sender.on_update(update)` with new TranscriptionUpdate
- `server.py _do_stop()` — calls `stop()` then `wait(timeout=5.0)` — timeout increases to 10s
- `config.py` — `TELEGRAM_DRAFT_INTERVAL` and `TELEGRAM_STREAM` become dead config after draft removal

</code_context>

<specifics>
## Specific Ideas

- User emphasized simplicity: VAD → transcribe → send to Telegram. No extra features.
- All implementation details deferred to Claude — user trusts the builder to make the right calls.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-telegram-hardening*
*Context gathered: 2026-03-27*
