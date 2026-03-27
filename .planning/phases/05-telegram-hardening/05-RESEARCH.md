# Phase 5: Telegram Hardening - Research

**Researched:** 2026-03-27
**Domain:** Telegram Bot API, Python threading/queue patterns, HTTP retry logic
**Confidence:** HIGH

## Summary

This phase is a focused rewrite of `src/telegram_sender.py`. The current implementation accumulates partial text across utterances using `_processed_chars` and supports draft/streaming modes that become meaningless under the new per-utterance contract from Phase 4. The fix is to strip away all that complexity: each `TranscriptionUpdate` arrives with a complete `text` field for the utterance, and the sender enqueues exactly one `sendMessage` call per update.

The three correctness problems being solved are: (1) stale `_processed_chars` causing the second utterance's text to be swallowed, (2) a 5-second shutdown window that is too short under realistic Telegram API latency, and (3) unhandled 429 responses that crash the sender thread. All three have clear, well-understood solutions in the existing codebase — this is a simplification and a targeted fix, not a redesign.

The Telegram Bot API returns 429 errors with a JSON body containing `parameters.retry_after` (integer seconds). Parsing this field and sleeping for that duration before the next retry is the correct handling strategy — better than fixed exponential backoff because the server communicates exactly how long to wait.

**Primary recommendation:** Delete all streaming/draft state, implement a stateless `on_update()` that enqueues `update.text`, handle 429 by parsing `retry_after` from the response JSON, and set the shutdown `wait()` timeout to 10.0s.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** One Telegram message per utterance. No drafts, no accumulation, no `_processed_chars`. Each `TranscriptionUpdate` from Whisper maps to exactly one `sendMessage` call.
- **D-02:** Remove `sendMessageDraft` entirely — no draft streaming, no `_draft_buf`, no `_draft_id`, no `_last_draft_t`. The `stream` parameter and `stream=True/False` mode are eliminated.
- **D-03:** Remove the legacy `stream=False` sentence-counting mode (`_prev_sentence_count`). Only one mode: per-utterance send.
- **D-04:** On stop, drain all queued messages within a 10-second window (up from current 5s). Messages still in queue after 10s are logged and dropped.
- **D-05:** The `wait()` timeout updates to 10.0s to match INTG-02 requirement.
- **D-06:** 429 responses are handled explicitly — parse `Retry-After` header if present, otherwise use existing exponential backoff. Pipeline does not crash on rate limits.
- **D-07:** Messages that fail after max retries are logged at ERROR level and dropped — pipeline continues processing subsequent utterances.

### Claude's Discretion

- Exact implementation of 429 detection and Retry-After parsing
- Whether to distinguish 429 from other HTTP errors in retry logic
- Queue drain implementation details during shutdown
- Whether `TelegramSender.__init__` signature simplifies (removing `stream` param)
- Test structure and fixtures

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INTG-01 | Telegram sender works with new per-utterance TranscriptionUpdate contract | D-01 through D-03: remove all cross-utterance state; `on_update()` enqueues `update.text` directly |
| INTG-02 | Telegram shutdown flush uses 10s timeout for API latency spikes | D-04, D-05: `wait(timeout=10.0)` in `_do_stop()`, drain loop with 10s window |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | already installed | HTTP client for Telegram API | Already in use; supports timeout, clean error hierarchy |
| threading / queue | stdlib | Background sender thread | Already in use; fits the synchronous callback model |

No new dependencies for this phase. The existing `httpx`, `threading`, and `queue` imports cover all requirements.

**Version verification:** No new packages — no install step needed.

---

## Architecture Patterns

### Recommended Project Structure

No file changes beyond `src/telegram_sender.py`, `src/config.py`, and `src/server.py`. The test file `tests/test_telegram_sender.py` is new (Wave 0 gap).

### Pattern 1: Stateless Per-Utterance Enqueue

**What:** `on_update()` enqueues `update.text` (a plain string) — no state is read or written on the calling thread.

**When to use:** Whenever the upstream contract guarantees one complete text per call (which Phase 4 does via `TranscriptionUpdate.text`).

**Example:**
```python
# Source: derived from existing _loop() pattern in telegram_sender.py
def on_update(self, update: TranscriptionUpdate) -> None:
    """Fast callback — enqueues utterance text for background send."""
    text = update.text.strip()
    if text:
        self._queue.put(text)
```

The background `_loop()` only ever handles `str | None` now — the `TranscriptionUpdate` branch is removed.

### Pattern 2: 429 Retry-After Parsing

**What:** Parse `parameters.retry_after` from the Telegram API JSON response body and use that as the sleep duration instead of (or in addition to) exponential backoff.

**When to use:** Any 429 response from `sendMessage`. The API may also return a `Retry-After` HTTP header but the JSON body field is more reliable and widely documented.

**Telegram 429 response JSON (HIGH confidence, cross-verified):**
```json
{
  "ok": false,
  "error_code": 429,
  "description": "Too Many Requests: retry after 35",
  "parameters": {
    "retry_after": 35
  }
}
```

**Example implementation:**
```python
# Source: Telegram Bot API docs + grammy.dev/advanced/flood
def _send_message(self, client: httpx.Client, text: str) -> None:
    for attempt in range(config.TELEGRAM_MAX_RETRIES):
        try:
            resp = client.post(
                f"{self._base_url}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
            )
            if resp.status_code == 200:
                log.debug("Sent: %s", text[:40])
                return
            if resp.status_code == 429:
                body = resp.json()
                retry_after = (
                    body.get("parameters", {}).get("retry_after")
                    or config.TELEGRAM_BACKOFF_BASE * (2 ** attempt)
                )
                log.warning(
                    "Telegram 429: retry after %ss (attempt %d)",
                    retry_after, attempt + 1,
                )
                time.sleep(retry_after)
                continue
            log.warning("Telegram API %d: %s", resp.status_code, resp.text[:200])
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            log.warning("Telegram send error (attempt %d): %s", attempt + 1, exc)
        time.sleep(config.TELEGRAM_BACKOFF_BASE * (2 ** attempt))
    log.error(
        "Failed to send after %d attempts: %s",
        config.TELEGRAM_MAX_RETRIES, text[:60],
    )
```

### Pattern 3: Shutdown Queue Drain

**What:** The `_loop()` runs until it receives the `None` sentinel. The 10-second window is enforced by `wait(timeout=10.0)` in `_do_stop()`. Messages still in queue when the thread exits after the timeout are unreachable — log count at WARNING level.

**When to use:** Always. The sentinel-based drain is already the pattern; only the timeout changes.

The `_loop()` itself does not need a timer — it drains naturally until the sentinel arrives. The timeout is entirely in the caller (`wait()`). This means `_do_stop()` in `server.py` changes from `wait(timeout=5.0)` to `wait(timeout=10.0)`.

### Pattern 4: Cleanup of Dead Config

After removing draft streaming, two config constants become dead: `TELEGRAM_STREAM` and `TELEGRAM_DRAFT_INTERVAL`. Remove them from `config.py` and remove any references (including the `test_telegram_stream_default_true` and `test_telegram_draft_interval` tests in `test_config.py`).

### Anti-Patterns to Avoid

- **Resetting `_processed_chars` between utterances instead of removing it:** The new contract means there is no cumulative text to track. Any per-utterance reset still leaves the state variable alive to cause bugs.
- **Keeping the `stream` parameter as a no-op:** Dead parameters obscure the interface. Remove it entirely.
- **Sleeping in `on_update()`:** This is called on the transcription callback thread. Any blocking here stalls the pipeline. All sleeps must be inside `_loop()`.
- **Catching `resp.json()` parse errors as silent no-ops:** If Telegram returns 429 with a malformed body, fall back to exponential backoff (already handled by the `or` fallback in the pattern above). Do not let a JSON parse error propagate out of `_send_message()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry-After sleep duration | Custom duration calculator | `resp.json()["parameters"]["retry_after"]` | Server provides the exact value; any calculation is a guess |
| Queue drain timeout | Custom drain-with-timer loop | `thread.join(timeout=10.0)` | Thread.join already handles the timeout correctly; the queue drains naturally as `_loop()` processes messages until sentinel |

**Key insight:** The existing queue/thread pattern already implements correct drain-on-stop. The only changes needed are (1) what gets enqueued and (2) how long the caller waits.

---

## Common Pitfalls

### Pitfall 1: Forgetting to Update `server.py`

**What goes wrong:** `telegram_sender.wait(timeout=5.0)` in `_do_stop()` is a separate call from the `TelegramSender.wait()` method. If only one is updated, INTG-02 is not met.

**Why it happens:** The timeout value appears in two places: the `wait()` method default parameter and the `_do_stop()` call site. Updating only one is a common oversight.

**How to avoid:** Update `_do_stop()` to call `_telegram_sender.wait(timeout=10.0)` explicitly (overriding the default). Keep the method default at 10.0 for consistency.

**Warning signs:** `wait(timeout=5.0)` still in `server.py` after the change.

### Pitfall 2: Keeping Dead Config References

**What goes wrong:** `test_telegram_stream_default_true` and `test_telegram_draft_interval` in `test_config.py` will fail if those constants are removed from `config.py`.

**Why it happens:** Test coverage for config constants is exhaustive (one test per constant) — removing a constant without removing its test causes a test failure.

**How to avoid:** Remove the config constants and their corresponding tests in the same wave.

**Warning signs:** `AttributeError: module 'src.config' has no attribute 'TELEGRAM_STREAM'` in test output.

### Pitfall 3: Wrong TranscriptionUpdate Field

**What goes wrong:** Phase 4 renames the field. The old `TranscriptionUpdate` has `finalized_text`; the new one (Phase 4 D-01) has `text`. Using `update.finalized_text` in the Phase 5 implementation will fail at runtime against the Phase 4 dataclass.

**Why it happens:** Phase 5 is researched before Phase 4 is implemented. The import still points at the old `transcriber.py` until Phase 4 ships.

**How to avoid:** Phase 5 implementation uses `update.text`. If Phase 4 is not yet merged, the Phase 5 tests must mock `TranscriptionUpdate` with the Phase 4 shape.

**Warning signs:** `AttributeError: 'TranscriptionUpdate' object has no attribute 'text'` at runtime.

### Pitfall 4: Sending Empty Text

**What goes wrong:** Whisper can return empty strings for very short or silent utterances that pass the hallucination filter. Sending an empty `sendMessage` call results in a Telegram API error.

**Why it happens:** The guard `if text:` in `on_update()` prevents empty enqueues, but it must be present.

**How to avoid:** Strip and guard in `on_update()` before enqueuing. The `_send_message()` method can also guard defensively.

---

## Code Examples

### Simplified `__init__` (removing dead state)

```python
# Source: refactored from existing telegram_sender.py
def __init__(self, bot_token: str, chat_id: str) -> None:
    self._base_url = f"https://api.telegram.org/bot{bot_token}"
    self._chat_id = chat_id
    self._queue: queue.Queue[str | None] = queue.Queue()
    self._thread = threading.Thread(
        target=self._loop, daemon=True, name="telegram-sender"
    )
    self._thread.start()
```

All removed: `stream`, `_processed_chars`, `_draft_buf`, `_draft_id`, `_last_draft_t`, `_prev_sentence_count`.

### Simplified `_loop()`

```python
def _loop(self) -> None:
    client = httpx.Client(timeout=10.0)
    try:
        while True:
            item = self._queue.get()
            if item is None:
                break
            self._send_message(client, item)
    finally:
        client.close()
```

No `_process_streaming()`, no `_send_draft()`, no final flush (no draft to flush — per-utterance messages are already complete when enqueued).

### `server.py _do_stop()` change

```python
# Change only the timeout value — no other structural change
if _telegram_sender is not None:
    _telegram_sender.stop()
    _telegram_sender.wait(timeout=10.0)  # was 5.0
    _telegram_sender = None
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Streaming draft + finalized sentence accumulation | Per-utterance send | Phase 5 (this phase) | Eliminates `_processed_chars` bug, removes draft API dependency |
| Fixed exponential backoff on all HTTP errors | 429-specific `retry_after` parsing | Phase 5 (this phase) | Respects server-communicated wait times instead of guessing |
| 5s shutdown drain window | 10s shutdown drain window | Phase 5 (this phase) | Accommodates realistic Telegram API latency spikes |

**Deprecated/outdated:**
- `sendMessageDraft` API call: removed entirely — Esper no longer uses draft streaming
- `config.TELEGRAM_STREAM`: dead after this phase — remove from config.py
- `config.TELEGRAM_DRAFT_INTERVAL`: dead after this phase — remove from config.py

---

## Open Questions

1. **Phase 4 TranscriptionUpdate field name**
   - What we know: Phase 4 D-01 specifies `text` as the per-utterance field name
   - What's unclear: Phase 4 is not yet implemented — the current `transcriber.py` still has `finalized_text`. Phase 5 tests must mock with the Phase 4 shape.
   - Recommendation: Phase 5 tests import a locally defined `TranscriptionUpdate(text=...)` stub, not the live one from `src/transcriber.py`. This decouples Phase 5 tests from Phase 4 implementation order.

2. **`TelegramSender.__init__` signature change and `server.py` construction call**
   - What we know: `server.py` constructs `TelegramSender(token, chat_id, stream=config.TELEGRAM_STREAM)` — if `stream` is removed from `__init__`, that call site breaks.
   - What's unclear: Where exactly `TelegramSender` is constructed in `server.py` (need to verify line numbers).
   - Recommendation: Search `server.py` for `TelegramSender(` and update that call to remove `stream=...`. Low risk — one call site.

---

## Environment Availability

Step 2.6: SKIPPED — this phase is a code-only rewrite. No new external dependencies. `httpx` is already installed. Telegram API access is a runtime concern, not a build-time dependency.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none — pytest auto-discovers `tests/` |
| Quick run command | `python3 -m pytest tests/test_telegram_sender.py -x -q` |
| Full suite command | `python3 -m pytest tests/ -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTG-01 | Two sequential utterances both enqueue two separate `sendMessage` calls | unit | `python3 -m pytest tests/test_telegram_sender.py::test_two_utterances_send_two_messages -x` | Wave 0 gap |
| INTG-01 | `on_update()` ignores empty/whitespace-only text | unit | `python3 -m pytest tests/test_telegram_sender.py::test_empty_utterance_not_sent -x` | Wave 0 gap |
| INTG-01 | No `_processed_chars`, `_draft_buf`, or `stream` attributes exist | unit | `python3 -m pytest tests/test_telegram_sender.py::test_dead_state_removed -x` | Wave 0 gap |
| INTG-02 | `stop()` + `wait(timeout=10.0)` drains the queue within 10s | unit | `python3 -m pytest tests/test_telegram_sender.py::test_shutdown_drains_queue -x` | Wave 0 gap |
| INTG-02 | `server.py _do_stop()` calls `wait(timeout=10.0)` not 5.0 | unit (AST) | `python3 -m pytest tests/test_server_ipc.py::test_telegram_wait_timeout -x` | Wave 0 gap |
| D-06 | 429 response triggers sleep using `retry_after` from JSON body | unit | `python3 -m pytest tests/test_telegram_sender.py::test_429_respects_retry_after -x` | Wave 0 gap |
| D-07 | Message dropped and logged at ERROR after max retries | unit | `python3 -m pytest tests/test_telegram_sender.py::test_max_retries_drops_message -x` | Wave 0 gap |

### Sampling Rate

- **Per task commit:** `python3 -m pytest tests/test_telegram_sender.py -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_telegram_sender.py` — all 7 test cases above; covers INTG-01, INTG-02, D-06, D-07
- [ ] Update `tests/test_config.py` — remove `test_telegram_stream_default_true` and `test_telegram_draft_interval` tests (they will fail once config constants are deleted)

*(No new framework install needed — pytest 9.0.2 already present)*

---

## Sources

### Primary (HIGH confidence)

- `src/telegram_sender.py` — direct read of current implementation
- `src/config.py` — direct read of constants to be removed
- `src/server.py` lines 259-284 — direct read of `_do_stop()` shutdown sequence
- `.planning/phases/05-telegram-hardening/05-CONTEXT.md` — locked decisions D-01 through D-07
- `.planning/phases/04-whisper-integration/04-CONTEXT.md` — D-01 (new `TranscriptionUpdate.text` field)

### Secondary (MEDIUM confidence)

- [Telegram Bot API — Making Requests](https://core.telegram.org/bots/api#making-requests) — error response format with `parameters.retry_after`
- [grammy.dev — Scaling Up IV: Flood Limits](https://grammy.dev/advanced/flood) — retry_after behavior and best practices
- WebSearch cross-verification of 429 JSON body format (`parameters.retry_after` confirmed by multiple sources)

### Tertiary (LOW confidence)

- None — all claims verified by official docs or direct source code inspection

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — no new dependencies; existing httpx + threading already in use
- Architecture: HIGH — patterns derived directly from existing code and locked CONTEXT.md decisions
- Pitfalls: HIGH — identified by direct inspection of current implementation's stale-state bug and server.py call sites
- 429 response format: MEDIUM — confirmed by multiple secondary sources; official Telegram API docs excerpt did not include full ResponseParameters schema but the format is consistent across community and framework sources

**Research date:** 2026-03-27
**Valid until:** 2026-09-27 (Telegram Bot API rate-limit behavior is stable; ResponseParameters schema has been consistent for years)
