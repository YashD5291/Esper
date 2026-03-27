# Phase 4: Whisper Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 04-whisper-integration
**Areas discussed:** Transcription contract, Latency target, Error & timeout UX, Cold start experience

---

## Transcription Contract

### Q1: TranscriptionUpdate shape

| Option | Description | Selected |
|--------|-------------|----------|
| Simplify to per-utterance | Each update = one complete utterance. Drop draft_text/draft_sentences. | ✓ |
| Keep draft/finalized facade | Emit 'processing' draft update, then finalized. Visual continuity. | |
| You decide | Claude picks | |

**User's choice:** Simplify to per-utterance
**Notes:** None

### Q2: Processing indicator

| Option | Description | Selected |
|--------|-------------|----------|
| Processing indicator | Emit 'transcribing' status event. UI can show spinner. | ✓ |
| Silent wait | No intermediate feedback. | |
| You decide | Claude picks | |

**User's choice:** Processing indicator
**Notes:** None

### Q3: Telegram sending model

| Option | Description | Selected |
|--------|-------------|----------|
| One message per utterance | Each VAD utterance = one Telegram message. Simple, natural pacing. | ✓ |
| Batch with timeout | Accumulate utterances for N seconds, send as one message. | |
| You decide | Claude picks | |

**User's choice:** One message per utterance
**Notes:** None

---

## Latency Target

### Q1: Latency expectation

| Option | Description | Selected |
|--------|-------------|----------|
| <3s from utterance end | Realistic for batch Whisper on M1 Max. Matches roadmap. | ✓ |
| <1s from utterance end | Aggressive. Likely not achievable for longer sentences. | |
| <500ms (original) | Only possible with streaming inference. Out of scope. | |

**User's choice:** <3s from utterance end
**Notes:** User also confirmed VAD eliminates need for 5s fixed chunking window.

---

## Error & Timeout UX

### Q1: Whisper timeout behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Log + skip utterance | Kill, log, skip, auto-restart for next utterance. | ✓ |
| Log + retry once | Kill, restart, retry same utterance once. | |
| You decide | Claude picks | |

**User's choice:** Log + skip utterance
**Notes:** None

### Q2: Hallucination filter visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Silent discard | Log at DEBUG, no event. User never sees hallucinated text. | ✓ |
| Debug-visible discard | Log at INFO + emit 'filtered' event. | |
| You decide | Claude picks | |

**User's choice:** Silent discard
**Notes:** None

### Q3: Subprocess crash restart

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate restart, 3 strikes | Auto-restart up to 3 times. Stop pipeline after 4th crash. | ✓ |
| Backoff restart | Restart with exponential backoff (1s, 2s, 4s). | |
| You decide | Claude picks | |

**User's choice:** Immediate restart, 3 strikes
**Notes:** Counter resets on successful transcription.

---

## Cold Start Experience

### Q1: Loading status granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Status events with stage info | downloading_model, compiling_shaders, loading_model events. | ✓ |
| Single loading_model status | Keep current behavior. | |
| You decide | Claude picks | |

**User's choice:** Status events with stage info
**Notes:** None

### Q2: Download timing

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy on first start | Download on first 'start' command. No surprise background downloads. | ✓ |
| Eager on app launch | Pre-download in background when app opens. | |
| You decide | Claude picks | |

**User's choice:** Lazy on first start
**Notes:** None

---

## Claude's Discretion

- Subprocess IPC mechanism
- Hallucination thresholds (no_speech_prob, compression_ratio)
- Model warmth between utterances
- Internal watchdog architecture
- Process restart implementation details

## Deferred Ideas

None — discussion stayed within phase scope
