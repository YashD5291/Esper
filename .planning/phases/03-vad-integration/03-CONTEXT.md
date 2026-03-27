# Phase 3: VAD Integration - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Silero VAD owns the audio loop. AudioCapture feeds 512-sample frames to a VAD thread that scores each frame, accumulates speech into utterance buffers with pre/post padding, and emits complete utterances to `speech_q`. The existing `_pump_audio()` polling thread is replaced. Whisper (Phase 4) will consume from `speech_q` — this phase only produces to it.

</domain>

<decisions>
## Implementation Decisions

### Audio block size
- **D-01:** AudioCapture blocksize changes from 1600 (100ms) to 512 (32ms) — hard Silero requirement. `config.CHUNK_DURATION` updates accordingly (0.032s). `config.CHUNK_SAMPLES` derives from it (512).
- **D-02:** `config.QUEUE_MAXSIZE` stays at 300 (~9.6s of buffered audio at 512 samples/frame) — sufficient for VAD processing lag.

### VAD thread architecture
- **D-03:** New `src/vad.py` module with a `VadThread` class. Runs as a daemon thread consuming from `audio_q` (AudioCapture's queue). Scores each 512-sample frame with Silero VAD. Accumulates speech frames into an utterance buffer.
- **D-04:** VAD runs on CPU, not MPS — `torch.set_num_threads(1)` to avoid contention with MLX (Phase 4). Model loaded via `torch.jit.load()` from `silero_vad` package.
- **D-05:** The `_pump_audio()` thread in server.py is replaced by VadThread. VadThread reads from `audio_q` directly (same queue AudioCapture writes to).

### Utterance detection
- **D-06:** Speech starts when VAD probability exceeds `config.VAD_SPEECH_THRESHOLD` (0.5) for a frame.
- **D-07:** Utterance ends after `config.VAD_SILENCE_THRESHOLD_MS` (500ms) of consecutive non-speech frames.
- **D-08:** Utterances shorter than `config.VAD_MIN_SPEECH_DURATION_MS` (500ms) are discarded — prevents button clicks, coughs, etc.
- **D-09:** Low-energy frames (RMS below `config.VAD_MIN_ENERGY` = 0.01) are rejected before VAD scoring — saves compute on silence.

### Pre-buffer / post-buffer
- **D-10:** A rolling pre-buffer of 300ms (configurable) of audio is maintained. When speech starts, the pre-buffer is prepended to the utterance so the first phoneme isn't clipped.
- **D-11:** Post-buffer of 200ms after silence detection — captures trailing consonants.

### speech_q output
- **D-12:** Complete utterances are placed on a `queue.Queue` called `speech_q`. Each entry is a numpy array (int16 or float32, full utterance audio). Phase 4's Whisper subprocess will consume from this queue.
- **D-13:** For Phase 3 only (before Whisper is integrated), the existing transcriber's `push_audio()` receives the full utterance buffer instead of continuous chunks. This keeps the current pipeline functional during Phase 3.

### Server wiring
- **D-14:** server.py creates VadThread, passes it `audio_q` and `speech_q`. VadThread replaces `_pump_audio()`.
- **D-15:** Energy emission stays on its own thread reading from `AudioCapture.energy` — no change.
- **D-16:** The `on_update` callback chain (server → SwiftUI + Telegram) is unchanged.

### Dependencies
- **D-17:** New pip dependency: `silero-vad` (or `torch` + download from snakers4/silero-vad). Prefer the `silero-vad` package if it exists as a clean pip install; otherwise `torch` + `torchaudio.pipelines.SILERO_VAD`.

### Claude's Discretion
- Exact rolling buffer implementation (circular buffer vs deque)
- Whether to emit energy events from VadThread or keep separate energy thread
- Test structure and fixtures for VAD unit tests
- Whether `speech_q` uses a bounded or unbounded queue

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `.planning/research/ARCHITECTURE.md` — VAD integration pattern (lines 138-177), audio pipeline diagram, The Professor's proven approach
- `.planning/research/FEATURES.md` — VAD-gated Whisper rationale, silence padding, no_speech_prob gate
- `.planning/research/PITFALLS.md` — Pitfall 6 (Silero MPS crash), Pitfall 10 (model load timeout)

### Current implementation
- `src/audio_capture.py` — AudioCapture class, blocksize change needed, energy tracking
- `src/config.py` — VAD constants already defined (lines 15-20)
- `src/server.py` — Current `_pump_audio()` thread to replace, wiring pattern
- `src/transcriber.py` — `push_audio()` / `on_update` interface (Phase 3 bridge)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AudioCapture`: Queue-based audio producer — VadThread becomes the consumer (replaces _pump_audio)
- `config.py` VAD section: All 5 constants already defined with documented defaults
- `TranscriptionUpdate` dataclass: Unchanged — VAD doesn't touch the output contract

### Established Patterns
- Daemon threads with stop events (AudioCapture, _pump_audio, _emit_energy)
- Queue-based producer/consumer (audio_q pattern)
- Config module-level mutation at startup

### Integration Points
- `server.py _do_start()` — Create VadThread here, wire audio_q → speech_q
- `server.py _do_stop()` — Stop VadThread with timeout
- `audio_capture.py` — Blocksize change from 1600 → 512

</code_context>

<specifics>
## Specific Ideas

- Port directly from The Professor's proven VAD pattern — not a reimplementation
- Silero VAD must run on CPU (torch.set_num_threads(1)) to avoid MPS contention with MLX Whisper in Phase 4

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-vad-integration*
*Context gathered: 2026-03-27*
