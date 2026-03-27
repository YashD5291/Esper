# Architecture Patterns: Esper v2.0 Pipeline Overhaul

**Domain:** Real-time transcription pipeline with VAD + Whisper on Apple Silicon
**Researched:** 2026-03-27
**Overall confidence:** HIGH (VAD pattern confirmed from The Professor; Whisper API verified via official source; MLX thread safety confirmed via official issue tracker)

---

## Recommended Architecture

### System Layers

```
SwiftUI App (macOS)
  │  JSON-line over stdout (no fd hack)
  │  stdin commands
  ▼
server.py — command dispatcher + event emitter
  │
  ├── AudioCapture thread (sounddevice callback → audio_q)
  │
  ├── VAD thread (reads audio_q → speech_q)
  │
  ├── Transcription thread (reads speech_q → calls whisper subprocess)
  │       │
  │       └── WhisperWorker subprocess (mlx-whisper in spawn context)
  │
  └── Telegram thread (reads transcript_q → HTTP send)
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `AudioCapture` | sounddevice callback → `audio_q` | VAD thread |
| `VAD` | 512-sample frames → speech boundary detection → `speech_q` | Transcription thread |
| `WhisperWorker` (subprocess) | mlx-whisper inference in isolated Metal context | Transcription thread via `multiprocessing.Pipe` |
| `Transcriber` | Owns subprocess lifecycle, feeds utterances, fires `on_update` callback | server.py fan-out |
| `TelegramSender` | Drains `transcript_q`, HTTP send with retry | None (terminal) |
| `server.py` | JSON-line protocol, command dispatch, lifecycle management | SwiftUI + all components |
| `config.py` | Single source of truth for all tunable values | All modules |

### Data Flow

```
Mic → [audio callback] → audio_q (queue.Queue, 100ms chunks)
                            │
                           VAD thread
                            │  consumes 512-sample frames
                            │  emits utterance: np.ndarray (full speech segment)
                            ▼
                         speech_q (queue.Queue)
                            │
                     Transcription thread
                            │  sends utterance over Pipe to WhisperWorker
                            │  receives {"text": "...", "segments": [...]}
                            │  fires on_update callback
                            ▼
                        on_update(TranscriptionUpdate)
                            │
                   ┌────────┴──────────┐
               _send("transcript")   TelegramSender.on_update()
               (→ SwiftUI via stdout)  (→ transcript_q → HTTP)
```

---

## IPC Cleanup: Replacing the Stdout fd Hack

### Current Problem

`server.py` does `os.dup(1)` / `os.dup2(2, 1)` at module load time to save real stdout before any import can call `print()`. This is fragile — it must run before imports, creates an ordering constraint, and is opaque to anyone reading the code later.

### Recommended Replacement: Explicit fd via CLI arg

Pass the protocol fd as a CLI argument. SwiftUI spawns:

```
python -m src.server --protocol-fd 3
```

Swift side: open an additional pipe, pass the write end as fd 3 to the subprocess.

Python side:

```python
import argparse, os

parser = argparse.ArgumentParser()
parser.add_argument("--protocol-fd", type=int, default=None)
args = parser.parse_args()

if args.protocol_fd is not None:
    _proto_out = os.fdopen(args.protocol_fd, "w", buffering=1)
else:
    _proto_out = sys.stdout  # CLI mode — write direct to stdout
```

**Result:** No fd redirect hack. No ordering constraint on imports. CLI mode works identically (stdout = protocol). SwiftUI mode uses the explicit fd. Logging stays on stderr unconditionally in all modes.

**Backward compatibility:** The current `os.dup` approach can stay as a fallback if `--protocol-fd` is absent, allowing a phased migration without breaking existing SwiftUI binary.

---

## Threading Model Changes

### Current (v1): 5 threads, no VAD

```
Thread 1: audio callback (sounddevice, not a thread — runs in PortAudio callback)
Thread 2: audio-pump (capture.get_chunk → transcriber.push_audio)
Thread 3: transcriber (CoreML or MLX, runs continuously on all audio)
Thread 4: energy-emitter (~10 Hz)
Thread 5: telegram-sender
```

Problems:
- No VAD — transcriber processes all audio including silence, wasting inference cycles
- `audio-pump` is a polling loop (0.2s timeout) that exists only to bridge two interfaces
- With VAD in place, `audio-pump` becomes redundant — VAD owns the audio loop

### Recommended (v2): 4 threads + 1 subprocess, VAD-gated

```
Thread 1: VAD (reads audio_q, owns speech detection, puts utterances on speech_q)
Thread 2: Transcription (reads speech_q, owns Whisper subprocess lifecycle)
Thread 3: Energy emitter (~10 Hz, reads energy from VAD or AudioCapture)
Thread 4: Telegram sender (reads transcript_q, HTTP, retry loop)
Subprocess: WhisperWorker (isolated Metal context, receives utterances via Pipe)
```

**Eliminates audio-pump thread.** VAD thread directly owns the sounddevice callback ring buffer (same pattern as The Professor's `VAD.run()`). The `AudioCapture` class either stays as a thin sounddevice wrapper that feeds `audio_q`, or gets absorbed into VAD — keeping it separate is cleaner for hot-swap support.

**Energy signal source changes.** VAD continuously processes frames, so `_speech_prob` from each frame can drive the energy event. Alternatively, keep reading `capture.energy` (RMS) from `AudioCapture` — both work. The 10 Hz energy emitter thread stays unchanged.

---

## Silero VAD Integration

### Frame Size and API

Silero VAD requires exactly **512 samples at 16 kHz** (32 ms per frame). This is a hard constraint — not configurable.

`AudioCapture` currently uses `blocksize=CHUNK_SAMPLES` (1600 samples = 100ms). Change to `blocksize=512` to match VAD's requirement, or accumulate in VAD thread and slice into 512-sample frames (The Professor slices from a ring buffer).

Recommended: keep `AudioCapture.blocksize=512` and let it queue 512-sample frames directly. Simpler, less buffering overhead.

### Integration Pattern (from The Professor — HIGH confidence)

```python
# Load once at startup
model, utils = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)

# Per-frame in VAD thread
frame = audio_queue.get()                          # 512 float32 samples
tensor = torch.from_numpy(frame)
speech_prob = model(tensor, SAMPLE_RATE).item()    # ~0.3ms on M1

if speech_prob >= 0.5:
    # accumulate into speech_buffer
else:
    silence_frames += 1
    if silence_frames >= SILENCE_THRESHOLD_FRAMES:
        if len(speech_buffer) >= MIN_SPEECH_FRAMES:
            speech_q.put(np.concatenate(speech_buffer))
        reset_state()
```

### Config Parameters

```python
# config.py additions
VAD_SPEECH_THRESHOLD = 0.5          # probability above which frame is speech
VAD_SILENCE_THRESHOLD_MS = 500      # ms of silence to end utterance
VAD_MIN_SPEECH_DURATION_MS = 500    # discard utterances shorter than this
VAD_MIN_ENERGY = 0.01               # RMS floor, discard very quiet utterances
```

---

## Whisper Subprocess: Yes, Isolate It

### Decision: Run Whisper in a spawn subprocess

**Verdict: YES, subprocess isolation is required.**

**Rationale:**

1. **MLX is not thread-safe.** The MLX C++ core has confirmed, unfixed thread safety issues: concurrent `eval()` calls corrupt the lazy evaluation graph and cause segfaults. The maintainers have stated this will not be fixed at the C++ level. (Source: ml-explore/mlx issue #2133)

2. **Metal context must be clean.** Using `multiprocessing.get_context("spawn")` gives the child process a fresh Metal context, avoiding semaphore leaks that occur when MLX arrays are present at fork time. This is exactly why The Professor uses subprocess isolation for MLX TTS.

3. **Memory growth is manageable in-process.** The mlx-whisper memory growth issue (variable QK cache shapes) is solved by calling `mx.metal.clear_cache()` between utterances or `mx.metal.set_cache_limit()`. No need to restart the subprocess for this. The subprocess should still restart after N utterances (e.g., 50) as a conservative memory guard — same pattern as The Professor's `TTS_MAX_GENERATIONS_BEFORE_RESTART`.

4. **Whisper is batch-only, not streaming.** `mlx_whisper.transcribe()` accepts a `np.ndarray` and returns when done. This maps naturally to the utterance-gated model: VAD emits a complete utterance → Transcription thread sends it over Pipe → subprocess transcribes → returns result. No streaming complexity needed.

5. **Latency is acceptable.** Whisper large-v3-turbo on M1 Max is fast (~200-400ms for a typical 2-3s utterance). The batch model fits the VAD-gated pattern better than continuous streaming would.

### Subprocess IPC Protocol

Uses `multiprocessing.Pipe` (same as The Professor), dict-based messages:

```python
# Transcription thread → WhisperWorker
{"type": "transcribe", "audio": audio_ndarray}   # np.ndarray, 16kHz float32

# WhisperWorker → Transcription thread
{"type": "result", "text": "...", "segments": [...]}
{"type": "error", "message": "..."}
{"type": "ready"}   # sent once on startup after model load
```

The `audio` field can pass `np.ndarray` directly through Pipe — no serialization needed for same-machine IPC.

### WhisperWorker Pattern

```python
# components/_whisper_worker.py

def worker_main(conn, model_repo):
    import mlx.core as mx
    import mlx_whisper

    model = None  # load on first transcribe or pre-load on ready

    # Warmup
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    mlx_whisper.transcribe(silence, path_or_hf_repo=model_repo)
    mx.metal.clear_cache()
    conn.send({"type": "ready"})

    generation_count = 0
    while True:
        msg = conn.recv()
        if msg["type"] == "shutdown":
            break
        if msg["type"] == "transcribe":
            try:
                result = mlx_whisper.transcribe(
                    msg["audio"],
                    path_or_hf_repo=model_repo,
                    language="en",
                    condition_on_previous_text=False,
                )
                mx.metal.clear_cache()
                generation_count += 1
                if generation_count >= MAX_GENERATIONS_BEFORE_RESTART:
                    conn.send({"type": "restart_needed"})
                    break
                conn.send({"type": "result", "text": result["text"], "segments": result.get("segments", [])})
            except Exception as exc:
                conn.send({"type": "error", "message": str(exc)})
```

### Subprocess Lifecycle (in Transcriber class)

Mirrors The Professor's `Synthesizer`:
- Spawn on `start()`, wait for `ready` message with timeout
- 3-strike failure counter — after 3 consecutive errors, fallback mode (log warning, skip utterance)
- Restart after `MAX_GENERATIONS_BEFORE_RESTART` utterances
- Watchdog timeout per transcription (e.g., 15s) using `conn.poll(timeout=15.0)` before `recv()`
- `shutdown()` sends `{"type": "shutdown"}`, joins process with timeout, kills if still alive

---

## Config Consolidation

### Problem: Config is split across 3 sources

| Source | Contains | Access Pattern |
|--------|----------|----------------|
| `.env` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `python-dotenv` + `os.environ` |
| `@AppStorage` (Swift) | UI preferences (device, engine, Telegram toggle) | Passed as JSON in `start` command |
| CLI args | `--device`, `--engine`, `--buffer`, `--telegram` | `argparse` in `realtime_demo.py` |

### Recommended: Single `config.py` with layered override

```python
# config.py

# Audio
SAMPLE_RATE = 16000
VAD_FRAME_SIZE = 512
VAD_SILENCE_THRESHOLD_MS = 500
VAD_MIN_SPEECH_DURATION_MS = 500
VAD_SPEECH_THRESHOLD = 0.5
VAD_MIN_ENERGY = 0.01

# Whisper
WHISPER_MODEL_REPO = "mlx-community/whisper-large-v3-turbo"
WHISPER_LANGUAGE = "en"
WHISPER_MAX_GENERATIONS_BEFORE_RESTART = 50
WHISPER_SUBPROCESS_TIMEOUT_S = 15.0
WHISPER_MAX_SYNTHESIS_TIME_S = 8.0

# Telegram (populated at runtime, not in file)
TELEGRAM_BOT_TOKEN: str = ""
TELEGRAM_CHAT_ID: str = ""
TELEGRAM_STREAM: bool = True

# Runtime (mutable — set during startup)
INPUT_DEVICE: int | None = None
PROTOCOL_FD: int | None = None

# IPC
ENERGY_EMIT_INTERVAL_S = 0.1
```

**How CLI and SwiftUI modes use config:**

- **CLI mode (`realtime_demo.py`):** Parse `argparse`, mutate `config.INPUT_DEVICE` etc. Load Telegram creds from `.env` into `config.TELEGRAM_BOT_TOKEN`. All modules import `config` directly.
- **SwiftUI mode (`server.py`):** On `start` command, extract fields from JSON data dict and mutate `config.*` before component initialization. Telegram creds come from the `telegram` subdict in the command (already working).

This eliminates `python-dotenv` as a dependency for `server.py` (SwiftUI sends creds over IPC). `realtime_demo.py` can keep `python-dotenv` for CLI convenience.

**No env vars, no YAML, no external files for server mode** — clean.

---

## New vs. Modified Components

### New Files

| File | Type | Description |
|------|------|-------------|
| `src/components/vad.py` | New | Silero VAD — 512-sample frames → utterance boundaries |
| `src/components/_whisper_worker.py` | New | Subprocess worker — mlx_whisper.transcribe loop |
| `src/components/transcriber_v2.py` | New | Replaces both CoreML and MLX transcribers; owns subprocess |
| `config.py` | New | Single source of truth; replaces scattered constants |

### Modified Files

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/server.py` | Modified | IPC fd hack removed; imports config; wires new VAD + Transcriber |
| `src/audio_capture.py` | Minor | `blocksize` becomes configurable (default 512 for VAD); remove hardcoded constant |
| `src/telegram_sender.py` | Minor | Import from `config` instead of receiving creds at construction |
| `src/realtime_demo.py` | Significant | Argparse maps to config mutations; new VAD-gated pipeline |

### Deleted Files (after v2.0)

| File | Reason |
|------|--------|
| `src/coreml_transcriber.py` | Replaced by Whisper |
| `src/transcriber.py` | Replaced by transcriber_v2.py (parakeet-mlx gone) |

---

## Build Order (Phase Dependencies)

The new features have a strict dependency chain:

```
Phase 1: config.py consolidation
   ↓ (all other phases import config)
Phase 2: AudioCapture blocksize fix + VAD thread
   ↓ (VAD feeds speech_q)
Phase 3: WhisperWorker subprocess + Transcriber v2
   ↓ (replaces CoreML/MLX transcribers)
Phase 4: IPC fd hack cleanup in server.py
   ↓ (requires all imports to be import-order-safe)
Phase 5: Telegram lifecycle hardening
   ↓ (builds on clean server.py)
Phase 6: Error handling + watchdog timeouts
   (wraps all components)
```

**Rationale for this order:**
- Config must come first — every other component imports it, and refactoring config mid-stream causes churn.
- VAD before Whisper — Whisper needs an utterance-gated input source; can't test Transcriber v2 without speech_q being populated.
- IPC cleanup deferred until after new components are wired — the fd hack still works during transition and removing it requires all modules to be print()-safe first (easy once config.py is the only place constants live).
- Telegram last — it's a pure consumer; can be hardened any time.

---

## Scalability Considerations

This is a single-user, local-only app. Scalability means "stays working over a long session."

| Concern | Mitigation |
|---------|------------|
| MLX Metal cache growth | `mx.metal.clear_cache()` after each utterance in worker |
| Subprocess memory leak | Restart after N utterances (conservative, proven pattern) |
| speech_q backup | VAD should discard utterances if speech_q is full (maxsize=5), not block |
| Transcriber subprocess hangs | `conn.poll(timeout=15.0)` before recv; kill + restart |
| Telegram network failure | Existing retry with backoff; add queue maxsize cap to prevent accumulation |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Running MLX Whisper in a background thread
**What:** `threading.Thread(target=mlx_whisper.transcribe, ...)` from the main process.
**Why bad:** MLX is not thread-safe — concurrent eval graph corruption, segfaults. The issue is confirmed will not be fixed upstream.
**Instead:** Always isolate in a `spawn`-context subprocess.

### Anti-Pattern 2: Passing all audio continuously to Whisper (no VAD gate)
**What:** Sending every 100ms chunk to Whisper, as CoreML transcriber currently does.
**Why bad:** Whisper processes the full 30s Mel window on every call; inference on silence wastes ~200ms per chunk. VAD reduces calls by 80%+ in a typical session with pauses.
**Instead:** VAD gates utterances; Whisper only sees complete speech segments.

### Anti-Pattern 3: Keeping the stdout fd redirect hack
**What:** `os.dup(1)` at import time, ordering constraints on imports.
**Why bad:** Fragile, opaque, breaks any library that calls `print()` before the redirect (import side effects). The explicit `--protocol-fd` arg is equally simple on both sides.
**Instead:** `--protocol-fd` CLI arg; CLI mode writes to stdout directly.

### Anti-Pattern 4: Config scattered across argparse + .env + command data dicts
**What:** Different config sources for CLI vs SwiftUI vs subprocess.
**Why bad:** Same knob in multiple places; drift between modes; hard to reason about effective configuration at runtime.
**Instead:** `config.py` constants with runtime mutation at startup; single import everywhere.

### Anti-Pattern 5: word_timestamps=True on mlx-whisper for long sessions
**What:** Enabling word-level timing in the Whisper call.
**Why bad:** Variable-shaped QK scores in attention; known memory growth issue (GitHub issue #1254). Growth rate is significant enough to OOM in hours-long sessions.
**Instead:** Use `word_timestamps=False` (default). Segment-level timestamps from `"segments"` key are sufficient for Telegram draft positioning.

---

## Sources

- The Professor `components/vad.py` — VAD frame size, ring buffer pattern, silence threshold logic (HIGH confidence — verified from existing working code)
- [ml-explore/mlx issue #2133](https://github.com/ml-explore/mlx/issues/2133) — MLX thread safety confirmed unfixed (HIGH confidence — official repo)
- [ml-explore/mlx-examples/whisper/transcribe.py](https://github.com/ml-explore/mlx-examples/blob/main/whisper/mlx_whisper/transcribe.py) — `transcribe(audio: Union[str, np.ndarray, mx.array])` signature (HIGH confidence — official source)
- [mlx-whisper memory issue #1254](https://github.com/ml-explore/mlx-examples/issues/1254) — `mx.metal.clear_cache()` resolves growth; `set_cache_limit()` alternative (HIGH confidence — maintainer confirmed)
- [mlx-openai-server](https://pypi.org/project/mlx-openai-server/) — spawn subprocess pattern for clean Metal context (MEDIUM confidence — third-party but matches The Professor's proven approach)
- [silero-vad GitHub](https://github.com/snakers4/silero-vad) — 512-sample frame requirement at 16kHz confirmed (HIGH confidence — official repo)
- [mlx-whisper PyPI](https://pypi.org/project/mlx-whisper/) — `transcribe()` is batch-only, no streaming (HIGH confidence — official package docs)
