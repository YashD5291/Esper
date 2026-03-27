# Phase 4: Whisper Integration - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Whisper large-v3-turbo transcribes every VAD-gated utterance from `speech_q`, running in an isolated spawn-context subprocess with Metal safety, watchdog timeouts, and hallucination filtering. The transcription contract is simplified from streaming draft/finalized to per-utterance batch output. A new `TranscriptionUpdate` dataclass replaces the Parakeet-era one.

</domain>

<decisions>
## Implementation Decisions

### Transcription contract
- **D-01:** Simplified per-utterance `TranscriptionUpdate` replaces the streaming draft/finalized model. Fields: `text` (this utterance), `finalized_text` (session accumulator), `sentences` (all finalized), `no_speech_prob`, `duration_s`. No more `draft_text` or `draft_sentences`.
- **D-02:** A `"transcribing"` status event is emitted when an utterance enters Whisper, followed by `"listening"` when done. This gives the UI a processing indicator without fake draft text.
- **D-03:** Telegram sends one message per utterance. The `_processed_chars` tracking is replaced by a simpler per-utterance model — each `TranscriptionUpdate` is one complete message.

### Latency target
- **D-04:** Target is <3 seconds from utterance end to transcription, not <500ms. The 500ms figure in PROJECT.md was from streaming Parakeet — not applicable to batch Whisper. Realistic timeline: ~500ms VAD silence detection + 1-2s Whisper inference on M1 Max.
- **D-05:** No need for fixed 5s chunking window — VAD provides natural utterance boundaries. Whisper receives complete utterances of variable length.

### Error & timeout UX
- **D-06:** Whisper timeout (15s): kill subprocess, log error, emit `"error"` event, skip the utterance, auto-spawn new subprocess for next utterance. Pipeline continues.
- **D-07:** Hallucination filtering: silent discard at DEBUG log level. No event emitted. User never sees hallucinated text.
- **D-08:** Subprocess crash: immediate auto-restart up to 3 consecutive times. After 3 strikes, emit `"crashed"` event and stop pipeline. Crash counter resets on any successful transcription.

### Cold start experience
- **D-09:** Granular status events during model loading: `"downloading_model"` (first run, ~60-90s), `"compiling_shaders"` (first run, ~10-30s), `"loading_model"` (subsequent runs, ~5-10s). Replaces the single `"loading_model"` status.
- **D-10:** Model download is lazy — happens on first `start` command, not on app launch. Matches existing `_load_model_with_timeout` pattern.

### Claude's Discretion
- Subprocess IPC mechanism (pipes, shared memory, multiprocessing.Queue — whatever fits best for audio + result passing)
- Exact hallucination thresholds for `no_speech_prob` and `compression_ratio`
- Whether the subprocess keeps the model warm between utterances or reinitializes per batch
- Internal watchdog architecture (threading, asyncio, signal-based)
- Exact process restart implementation details

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — PIPE-04, PIPE-05, PIPE-06, ARCH-03, ARCH-04, CLEAN-03 all map to this phase

### Current implementation (will be replaced)
- `src/transcriber.py` — Current `TranscriptionUpdate` dataclass (line 19) and `StreamingTranscriber` class. The dataclass is redefined in this phase; the transcriber class is replaced.
- `src/server.py` — `_load_model_with_timeout()` (line 147), `_on_update()` (line 107), `_pump_audio()` (line 121). All three change to work with subprocess-based Whisper.
- `src/coreml_transcriber.py` — Imports `TranscriptionUpdate` from transcriber.py. Will be removed in Phase 6 but must not break during Phase 4.

### Consumers of TranscriptionUpdate
- `src/telegram_sender.py` — Uses `TranscriptionUpdate.finalized_sentences` and `_processed_chars`. Must be updated for per-utterance model.
- `src/realtime_demo.py` — CLI display uses `finalized_text` + `draft_text`. Must be updated.
- `EsperApp/EsperApp/TranscriptionEngine.swift` — Consumes `transcript` events. Field names change.

### Config
- `src/config.py` — Whisper constants already defined (lines 22-26): `WHISPER_MODEL_REPO`, `WHISPER_LANGUAGE`, `WHISPER_MAX_GENERATIONS_BEFORE_RESTART`, `WHISPER_SUBPROCESS_TIMEOUT_S`

### Prior phase context
- `.planning/phases/02-ipc-cleanup/02-CONTEXT.md` — IPC decisions (--protocol-fd pattern, stderr logging)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config.py` Whisper namespace: Model repo, language, generation limit, timeout already defined
- `server.py _send()`: Protocol event emitter — reuse for new status events (`transcribing`, `downloading_model`, etc.)
- `server.py _load_model_with_timeout()`: Pattern for threaded loading with timeout — adapt for subprocess spawning
- `AudioCapture`: Unchanged — still produces audio chunks for the pipeline

### Established Patterns
- JSON-line protocol over `--protocol-fd` — new status events follow same format
- `config.py` module-import pattern — new Whisper tunables go here
- Logging to stderr — subprocess logging must also go to stderr (or parent captures it)
- Entry-point mutation pattern — `_do_start()` mutates config before constructing objects

### Integration Points
- `speech_q` (from Phase 3 VAD) → Whisper subprocess: main data flow
- `_on_update()` in server.py → emits `transcript` events: must handle new `TranscriptionUpdate` shape
- `TelegramSender.on_update()` → receives per-utterance updates: simplified from `_processed_chars` tracking
- `realtime_demo.py` CLI display → must render per-utterance text instead of draft/finalized

</code_context>

<specifics>
## Specific Ideas

- User confirmed VAD eliminates the need for 5s fixed chunking — variable-length utterances from `speech_q` are the input
- Processing indicator preferred over silent waits — `"transcribing"` status event gives UI feedback without fake draft text

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-whisper-integration*
*Context gathered: 2026-03-27*
