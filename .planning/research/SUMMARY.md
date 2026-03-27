# Project Research Summary

**Project:** Esper v2.0
**Domain:** Real-time VAD-gated Whisper transcription pipeline with Telegram relay (macOS, Apple Silicon)
**Researched:** 2026-03-27
**Confidence:** HIGH

## Executive Summary

Esper v2.0 replaces a continuously-running CoreML Parakeet transcriber with a VAD-gated MLX Whisper pipeline. The correct approach — validated by The Professor codebase — is to gate Whisper invocations strictly on VAD-detected utterance boundaries, run Whisper in a `spawn`-context subprocess for Metal isolation, and consolidate all configuration into a single `config.py` before touching any other component. The entire pattern is well-understood and has a proven implementation already running on the same hardware.

The recommended stack swap is narrow: remove `parakeet-mlx` and `coremltools`, add `mlx-whisper>=0.4.3` and `silero-vad>=6.2.1` (with `torch`/`torchaudio` already transitively present). No other dependencies change. The architecture evolves from 5 threads with no VAD to 4 threads plus a WhisperWorker subprocess, eliminating the audio-pump polling thread and replacing it with a VAD thread that owns speech boundary detection. The IPC fd redirect hack (`os.dup2(2, 1)`) should be replaced with an explicit `--protocol-fd` CLI argument, decoupling the protocol channel from stdout.

The critical risks are three: (1) the `TranscriptionUpdate` contract between the new Whisper transcriber and `TelegramSender` must be defined before any transcriber code is written — Parakeet emits cumulative text, Whisper-VAD will emit per-utterance text, and misalignment silently breaks Telegram with no error; (2) MLX Whisper must be isolated in a subprocess (MLX is not thread-safe, confirmed unfixed upstream); (3) `word_timestamps=True` and `clip_timestamps` must both be omitted from every `mlx_whisper.transcribe()` call or the pipeline becomes unusably slow or OOMs within 30 minutes.

---

## Key Findings

### Recommended Stack

The stack change is surgical. Only the transcription engine changes; all audio I/O, HTTP, and config tooling stays. `mlx-whisper 0.4.3` with the `mlx-community/whisper-large-v3-turbo` model (1.61 GB quantized) is the correct primary transcription engine — MLX-native, runs on Apple Neural Engine + GPU unified memory, accepts a numpy float32 array at 16 kHz directly. `silero-vad 6.2.1` is the correct VAD — under 1ms per 32ms chunk on CPU, proven stable in The Professor at 50+ generations zero hangs.

**Core technologies:**
- `mlx-whisper>=0.4.3`: batch transcription — accepts `np.ndarray` at 16kHz, returns `{"text": ..., "segments": [...]}` — why: MLX-native, best speed/accuracy for Indian accent recognition on Apple Silicon
- `silero-vad>=6.2.1`: speech boundary detection via `VADIterator` on 512-sample frames — why: <1ms per frame on CPU, zero threading concerns, direct port from The Professor
- `torch>=2.1.0` / `torchaudio>=2.1.0`: required by silero-vad; already transitively present — run silero on CPU explicitly, never on MPS
- **Remove** `parakeet-mlx`, `coremltools`, `scipy` (dead dep): saves ~230MB of CoreML model artifacts

**Critical version constraint:** silero-vad VADIterator requires exactly 512-sample frames at 16kHz — not configurable. AudioCapture's `blocksize` must change from 1600 to 512.

### Expected Features

**Must have (table stakes):**
- Silero VAD speech boundary detection — without it, Whisper runs on every 100ms chunk (30-50x excess inference calls) and hallucinates on silence
- VAD-gated Whisper invocation — Whisper only called after utterance end, never speculatively
- 300–500ms pre-buffer prepended to each utterance — prevents leading phoneme clipping at sentence onset
- `no_speech_prob > 0.6` post-transcription gate — suppresses Whisper hallucinations that pass VAD
- Single `config.py` consolidating all tunable constants — eliminates `.env` / `@AppStorage` / argparse divergence
- Clean JSON-line IPC via `--protocol-fd` CLI arg — removes the `os.dup2(2, 1)` fd redirect hack
- Watchdog timeout on Whisper subprocess (15s `conn.poll`) — guards against MLX inference hangs
- Telegram session flush on stop — ensures trailing draft buffer commits before process exits
- `condition_on_prev_text=False` in every `mlx_whisper.transcribe()` call — prevents repetition loops

**Should have (differentiators, but defer to v3):**
- Adaptive silence threshold calibration on startup — useful, but static defaults from The Professor are good enough for v2
- Graceful Whisper subprocess restart on N consecutive failures — watchdog timeout covers most cases
- VAD state events emitted to SwiftUI (`speaking: true/false`) — high UI value, trivial to add after VAD is stable

**Defer (v3+):**
- Dual-buffer speculative transcription — halves perceived latency but adds substantial complexity; overkill for single-user tool
- Cloud Whisper fallback — violates local-only constraint
- Word-level timestamps — requires second alignment pass; causes Metal OOM; not needed for Telegram use case
- On-the-fly language detection — hard-code `language="en"`

### Architecture Approach

The pipeline becomes: mic (512-sample chunks) → `audio_q` → VAD thread (accumulate frames, detect utterance boundaries, emit to `speech_q`) → Transcription thread (sends utterance over `multiprocessing.Pipe` to WhisperWorker subprocess) → `on_update(TranscriptionUpdate)` → fan-out to SwiftUI JSON-line stdout and `TelegramSender`. The audio-pump polling thread is eliminated; VAD owns the audio loop directly. All components import from `config.py` as the single source of truth.

**Major components:**
1. `config.py` (new) — single module-level constants file; runtime mutation at startup for device/Telegram creds; imported by all modules
2. `components/vad.py` (new) — Silero VAD `VADIterator`, 512-sample frames, utterance boundary detection, pre-buffer management
3. `components/_whisper_worker.py` (new) — `spawn`-context subprocess; `mlx_whisper.transcribe()` loop with `mx.metal.clear_cache()` after each call; restarts after 50 utterances
4. `components/transcriber_v2.py` (new) — subprocess lifecycle owner; fires `on_update` callback with `TranscriptionUpdate`
5. `server.py` (modified) — `--protocol-fd` arg replaces fd redirect; wires new VAD + Transcriber; `multiprocessing.set_start_method("spawn")` at top before all imports
6. `audio_capture.py` (minor) — `blocksize` becomes configurable, defaulting to 512

**Delete after v2.0:** `src/coreml_transcriber.py`, `src/transcriber.py`, `models/coreml/`

### Critical Pitfalls

1. **TranscriptionUpdate contract undefined before transcriber rewrite** — Parakeet emits cumulative `finalized_text`; Whisper-VAD will emit per-utterance strings. If `TelegramSender._processed_chars` is not reset between utterances, `new_text = full[self._processed_chars:]` returns `""` and Telegram goes silent with no error. Define the dataclass contract and write a unit test feeding two sequential `TranscriptionUpdate` objects before writing any transcriber code.

2. **MLX Whisper run in a thread instead of subprocess** — MLX's C++ core has confirmed, unfixed thread safety issues: concurrent `eval()` calls corrupt the lazy evaluation graph and cause segfaults. Always isolate in a `multiprocessing.get_context("spawn")` subprocess. Set `multiprocessing.set_start_method("spawn")` at the very top of `server.py` before any imports.

3. **`word_timestamps=True` or `clip_timestamps` passed to `mlx_whisper.transcribe()`** — `word_timestamps` leaks ~10MB Metal cache per call, causing OOM in 20-30 minutes. `clip_timestamps` causes 7-10x processing slowdown (27s for a 40s segment). Both must be omitted unconditionally.

4. **Model load timeout too short for first MLX shader compilation** — `_MODEL_LOAD_TIMEOUT = 30s` was calibrated for CoreML (pre-compiled). First MLX Whisper load triggers shader compilation: 45-90 seconds on cold cache. Raise to 120s and emit a `"compiling"` status event.

5. **Silero VAD and MLX Whisper sharing Metal in the same process** — Metal does not pre-empt between frameworks; concurrent shader compilation causes hangs. Force Silero to CPU (`torch.device("cpu")`) and run Whisper in a subprocess. Test first inference timing: VAD > 5s or Whisper > 30s on first call means Metal contention.

---

## Implications for Roadmap

Based on the combined research, the build order has a strict dependency chain. Every subsequent phase assumes the previous is complete.

### Phase 1: Config Consolidation
**Rationale:** Every other component imports `config.py`. Refactoring config mid-stream causes churn across all files. This is the lowest-risk, highest-leverage change — no new dependencies, no behavior change.
**Delivers:** Single `config.py` with all VAD, Whisper, Telegram, and IPC constants; `server.py` reads Telegram creds from `start` command data dict rather than `.env`; runtime device/fd mutation pattern established.
**Addresses:** Config fragmentation across `.env`, `@AppStorage`, argparse. Pitfall 13 (AppStorage key mismatch). Pitfall 14 (live `print()` in `audio_capture.py`).
**Avoids:** Config divergence between CLI and SwiftUI modes silently using different values.

### Phase 2: IPC Cleanup
**Rationale:** Adding VAD and Whisper introduces heavy logging. Any new `print()` or log misconfiguration after the current `os.dup2` redirect corrupts the JSON protocol stream. The fd hack must be removed before new log-heavy components are added, not after.
**Delivers:** `--protocol-fd` CLI argument; `os.dup2` hack removed; all `print()` calls in `src/` replaced with `log.*`; JSON output validated in CI.
**Addresses:** Pitfall 4 (IPC schema changes break Swift silently). Pitfall 14 (print corruption).
**Avoids:** Needing to coordinate Swift + Python changes mid-VAD work.

### Phase 3: VAD Integration + AudioCapture Blocksize Fix
**Rationale:** VAD provides the utterance boundaries that gate Whisper. Whisper cannot be integrated without a speech boundary source. The Professor's `VAD` pattern is a direct port — this phase has the least unknowns.
**Delivers:** `components/vad.py` with `VADIterator`; `AudioCapture.blocksize=512`; utterance buffers (with 300-500ms pre-buffer) emitted to `speech_q`; VAD state events to SwiftUI.
**Addresses:** Pitfall 5 (leading phoneme clipping — pre-buffer). Pitfall 7 (VAD threshold tuning). Pitfall 8 (Silero forced to CPU).
**Avoids:** Sending silence or sub-500ms fragments to Whisper.

### Phase 4: Whisper Integration + Transcriber v2
**Rationale:** VAD must be producing utterances before Whisper can be tested end-to-end. The subprocess pattern is mandatory (MLX thread safety). This is the heaviest phase — new subprocess lifecycle, IPC protocol, warmup, generation count restart.
**Delivers:** `components/_whisper_worker.py`; `components/transcriber_v2.py`; `multiprocessing.set_start_method("spawn")` at server top; `mx.metal.set_cache_limit(100MB)` + `clear_cache()` after each call; watchdog timeout (15s `conn.poll`); model load timeout raised to 120s; `language="en"`, `condition_on_prev_text=False`, `word_timestamps=False` enforced.
**Addresses:** Pitfall 1 (Metal memory leak). Pitfall 2 (hallucination — `no_speech_prob` gate). Pitfall 6 (clip_timestamps). Pitfall 10 (load timeout). Pitfall 12 (fork vs spawn).
**Avoids:** MLX thread safety crashes; OOM from cache growth; 10x slowdowns.

### Phase 5: TranscriptionUpdate Contract + Telegram Lifecycle Hardening
**Rationale:** The `TranscriptionUpdate` dataclass contract must be locked and tested before Telegram integration is turned on. Once defined, Telegram hardening is isolated and low-risk.
**Delivers:** Explicit `TranscriptionUpdate` dataclass with documented semantics (per-utterance vs cumulative); `TelegramSender` adapted to per-utterance model with `_processed_chars` reset logic; unit test for two sequential updates; session flush on stop with 10s drain timeout; `429` rate limit handling.
**Addresses:** Pitfall 3 (TranscriptionUpdate mismatch → silent Telegram failure). Pitfall 9 (`_processed_chars` desync). Pitfall 11 (Telegram rate limiting).
**Avoids:** Telegram going silent mid-session with no error.

### Phase 6: Cleanup and Deletion
**Rationale:** Dead code left in place increases maintenance surface and confuses future work.
**Delivers:** `src/coreml_transcriber.py` deleted; `src/transcriber.py` deleted; `models/coreml/` removed from build artifacts; `parakeet-mlx` and `coremltools` removed from `requirements.txt`; `scipy` explicit pin removed.

### Phase Ordering Rationale

- Config first because it's a true leaf — nothing depends on it yet but everything will.
- IPC second because the current fd hack creates import ordering constraints that block adding new log-heavy code.
- VAD third because it's a known-good port from The Professor with no architectural unknowns.
- Whisper fourth because it requires VAD to provide utterance boundaries and is the highest-risk phase (subprocess lifecycle, Metal isolation, timeout tuning).
- Telegram fifth because it is a pure downstream consumer — it can be hardened any time, but its contract with the transcriber must be explicit before live testing.
- Cleanup last because there's no reason to delete until the replacement is proven.

### Research Flags

Phases with standard patterns (skip `/gsd:research-phase`):
- **Phase 1 (Config):** Direct port of The Professor's `config.py` pattern. No unknowns.
- **Phase 2 (IPC):** Pattern is fully specified in ARCHITECTURE.md — `--protocol-fd` arg, `os.fdopen`. No unknowns.
- **Phase 3 (VAD):** Direct port from The Professor's `components/vad.py`. Chunk size, threshold values, and pre-buffer pattern are all documented.
- **Phase 6 (Cleanup):** Pure deletion — no research needed.

Phases likely needing `/gsd:research-phase` during planning:
- **Phase 4 (Whisper subprocess):** The subprocess lifecycle (startup warmup, `ready` handshake, generation count restart, 3-strike fallback) involves several moving parts. Worth a focused plan before execution to confirm the exact `multiprocessing.Pipe` IPC message schema and timeout sequencing.
- **Phase 5 (TranscriptionUpdate contract):** The contract definition requires reading both `TelegramSender._process_streaming` and the existing `TranscriptionUpdate` dataclass carefully before deciding cumulative vs per-utterance semantics. A short targeted research session would reduce risk.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Package versions verified via PyPI JSON API; HuggingFace model page confirmed; scipy dead dep confirmed via grep |
| Features | HIGH | Feature set derived from working codebase analysis + confirmed Telegram Bot API 9.5 docs; no speculation |
| Architecture | HIGH | VAD frame size and integration pattern from The Professor (production-validated); MLX thread safety from official GitHub issue; `transcribe()` signature from official source |
| Pitfalls | HIGH | All critical pitfalls backed by maintainer-confirmed GitHub issues or direct codebase analysis; Metal OOM and clip_timestamps issues confirmed by MLX maintainers |

**Overall confidence:** HIGH

### Gaps to Address

- **Whisper large-v3-turbo latency on M1 Max:** No direct benchmark found. Estimate is 0.5-2s for a 3-10s utterance. Establish a timing baseline (audio duration vs call duration) immediately after first end-to-end integration before committing to any latency SLO.
- **`mlx_whisper.transcribe()` numpy array acceptance:** MEDIUM confidence — PyPI docs and community examples confirm it, but the official docs don't state it explicitly. Verify with a unit test before committing the subprocess IPC design.
- **`<500ms latency` requirement in PROJECT.md:** Research flagged this as ambiguous. The current architecture delivers text ~1-2s after utterance END, not utterance start. Clarify whether the requirement means "500ms from speech end" (met) or "streaming word-by-word output" (not achievable with mlx-whisper batch API without major additional complexity).
- **IPC schema documentation:** No `PROTOCOL.md` exists. Creating one as part of Phase 2 is recommended to prevent silent Swift decoder failures when fields change.

---

## Sources

### Primary (HIGH confidence)
- PyPI mlx-whisper 0.4.3 — version, API, batch-only constraint
- PyPI silero-vad 6.2.1 — version, VADIterator API, 512-sample frame requirement
- HuggingFace mlx-community/whisper-large-v3-turbo — model size (1.61GB), availability
- ml-explore/mlx issue #2133 — MLX thread safety confirmed unfixed
- ml-explore/mlx-examples issue #1254 — word_timestamps Metal memory leak, maintainer-confirmed workaround
- ml-explore/mlx-examples discussion #1275 — clip_timestamps 7-10x slowdown
- ml-explore/mlx issue #2457 — multiprocessing spawn vs fork with MLX
- Silero VAD GitHub (snakers4/silero-vad) — 512-sample frame requirement, VADIterator API
- Telegram Bot API changelog 9.5 — sendMessageDraft availability
- The Professor `components/vad.py` — VAD pattern, ring buffer, silence threshold (production-validated)
- Direct codebase analysis: `server.py`, `telegram_sender.py`, `transcriber.py`, `audio_capture.py`

### Secondary (MEDIUM confidence)
- LiveKit Silero VAD plugin — prefix_padding_duration default (0.5s)
- UFAL whisper_streaming silero_vad_iterator.py — FixedVADIterator reference implementation
- mlx-openai-server — spawn subprocess pattern for clean Metal context
- WhisperLive issue #185 — hallucination on near-threshold noise

### Tertiary (LOW confidence)
- Whisper large-v3-turbo latency estimate (0.5-2s on M1 Max) — no direct benchmark; inferred from model size and MLX throughput reports; validate at integration time

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
