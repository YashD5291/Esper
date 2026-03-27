# Phase 4: Whisper Integration - Research

**Researched:** 2026-03-27
**Domain:** mlx-whisper subprocess isolation, watchdog timeouts, hallucination filtering, TranscriptionUpdate contract
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Simplified per-utterance `TranscriptionUpdate` replaces the streaming draft/finalized model. Fields: `text` (this utterance), `finalized_text` (session accumulator), `sentences` (all finalized), `no_speech_prob`, `duration_s`. No more `draft_text` or `draft_sentences`.
- **D-02:** A `"transcribing"` status event is emitted when an utterance enters Whisper, followed by `"listening"` when done. This gives the UI a processing indicator without fake draft text.
- **D-03:** Telegram sends one message per utterance. The `_processed_chars` tracking is replaced by a simpler per-utterance model — each `TranscriptionUpdate` is one complete message.
- **D-04:** Target is <3 seconds from utterance end to transcription, not <500ms. Realistic timeline: ~500ms VAD silence detection + 1-2s Whisper inference on M1 Max.
- **D-05:** No need for fixed 5s chunking window — VAD provides natural utterance boundaries. Whisper receives complete utterances of variable length.
- **D-06:** Whisper timeout (15s): kill subprocess, log error, emit `"error"` event, skip the utterance, auto-spawn new subprocess for next utterance. Pipeline continues.
- **D-07:** Hallucination filtering: silent discard at DEBUG log level. No event emitted. User never sees hallucinated text.
- **D-08:** Subprocess crash: immediate auto-restart up to 3 consecutive times. After 3 strikes, emit `"crashed"` event and stop pipeline. Crash counter resets on any successful transcription.
- **D-09:** Granular status events during model loading: `"downloading_model"` (first run), `"compiling_shaders"` (first run), `"loading_model"` (subsequent runs). Replaces single `"loading_model"` status.
- **D-10:** Model download is lazy — happens on first `start` command, not on app launch.

### Claude's Discretion

- Subprocess IPC mechanism (pipes, shared memory, multiprocessing.Queue — whatever fits best for audio + result passing)
- Exact hallucination thresholds for `no_speech_prob` and `compression_ratio`
- Whether the subprocess keeps the model warm between utterances or reinitializes per batch
- Internal watchdog architecture (threading, asyncio, signal-based)
- Exact process restart implementation details

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PIPE-04 | Whisper large-v3-turbo transcribes VAD-gated utterances via mlx-whisper | mlx-whisper 0.4.3 API confirmed; numpy array input verified; model repo confirmed |
| PIPE-05 | Whisper runs in isolated spawn-context subprocess for MLX thread safety | MLX thread-safety issue #2133 confirmed unfixed; spawn context is the correct workaround |
| PIPE-06 | Hallucination guard filters outputs using no_speech_prob and compression_ratio thresholds | Thresholds documented from official transcribe() signature; recommended values researched |
| ARCH-03 | Cascading watchdog timeouts at per-utterance and process level | Threading-based watchdog pattern documented; 15s per-utterance + restart-count at process level |
| ARCH-04 | TranscriptionUpdate dataclass defines clear contract between Whisper and all consumers | All consumers (server.py, telegram_sender.py, realtime_demo.py, TranscriptionEngine.swift) audited |
| CLEAN-03 | Model load timeout updated from 30s to 120s for Whisper cold Metal compilation | Already done in Phase 1 — `config.MODEL_LOAD_TIMEOUT_S = 120.0` confirmed in config.py |
</phase_requirements>

---

## Summary

Phase 4 replaces the Parakeet/CoreML streaming transcriber with `mlx-whisper` running in an isolated `spawn`-context subprocess. The architectural reason for subprocess isolation is confirmed: MLX has an open, unfixed thread-safety issue (issue #2133) causing segfaults and Metal assertion failures ("A command encoder is already encoding to this command buffer") under concurrent use. The `spawn` start method gives Whisper its own clean Metal context.

The `mlx_whisper.transcribe()` function (version 0.4.3) accepts numpy arrays directly — this is confirmed from source. The return dict contains `segments` each with `no_speech_prob` and `compression_ratio`, which drives the hallucination guard. The subprocess receives complete utterances from `speech_q` (Phase 3 output), calls `transcribe()` once per utterance, and returns a result dict via IPC. The parent process applies hallucination filtering, builds a `TranscriptionUpdate`, and fans out to all consumers.

Consumer migration is the most touch-intensive part: `TranscriptionUpdate` loses `draft_text`/`draft_sentences`, gains `text`/`no_speech_prob`/`duration_s`. Three Python files plus one Swift file must update. `telegram_sender.py` gets significantly simpler — no more `_processed_chars` cursor, just send `update.text` directly. `Protocol.swift` must add new status string cases and update `TranscriptionPayload`.

**Primary recommendation:** Use `multiprocessing.get_context("spawn")` with a `multiprocessing.SimpleQueue` (not Queue) for IPC. Keep the model warm in the subprocess between utterances — reinitializing per batch adds 5-10s latency. Implement the watchdog as a daemon thread in the parent that kills the subprocess if the result hasn't arrived within 15s.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mlx-whisper | 0.4.3 | Whisper inference on Apple Silicon via MLX | Official MLX-native Whisper package; numpy input; returns no_speech_prob |
| mlx | 0.31.1 | GPU/ANE tensor operations (dep of mlx-whisper) | Already in venv at 0.30.6; 0.31.1 available |
| multiprocessing (stdlib) | Python 3.11 | spawn-context subprocess isolation | Solves MLX thread safety; no extra dep |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| threading (stdlib) | Python 3.11 | Watchdog timer in parent process | Per-utterance 15s kill timer |
| queue (stdlib) | Python 3.11 | speech_q producer/consumer | Already in use; VAD → Whisper path |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| multiprocessing.SimpleQueue | multiprocessing.Queue | Queue spawns extra threads, can deadlock; SimpleQueue is thread-safe and simpler for this pattern |
| multiprocessing.SimpleQueue | Pipe | Pipe is lower-level, bidirectional — useful but SimpleQueue is more natural for one-way result passing |
| subprocess keep-warm (model stays loaded) | reinitialize per utterance | Reinitialize adds 5-10s per utterance — unacceptable. Keep model loaded in worker loop |

**Installation:**
```bash
pip install mlx-whisper==0.4.3
```

mlx (dep) will be upgraded from 0.30.6 to a compatible version automatically.

**Version verification (confirmed 2026-03-27):**
- `pip index versions mlx-whisper` → latest is **0.4.3** (released Aug 29, 2025)
- `pip index versions mlx` → latest is **0.31.1**
- mlx-whisper is NOT yet installed in the project venv — must be added to requirements.txt

---

## Architecture Patterns

### Recommended Project Structure

The new code adds one file and modifies several:

```
src/
├── whisper_worker.py     # NEW: subprocess worker (loads model, inference loop)
├── transcriber.py        # REPLACE: new TranscriptionUpdate dataclass + WhisperTranscriber
├── server.py             # MODIFY: _do_start, _on_update, _load_model_with_timeout
├── telegram_sender.py    # MODIFY: on_update for per-utterance model
├── realtime_demo.py      # MODIFY: ConsoleRenderer for per-utterance model
└── config.py             # UNCHANGED (Whisper constants already present)

EsperApp/EsperApp/
├── Models/Protocol.swift        # MODIFY: EngineStatus new cases, TranscriptionPayload
└── TranscriptionEngine.swift    # MODIFY: handle new transcript fields
```

### Pattern 1: Spawn-Context Subprocess Worker Loop

**What:** A long-running child process loads the Whisper model once, then loops reading utterances from an IPC queue, running inference, and posting results back.

**When to use:** Any time MLX runs in a process that also has other threads (AudioCapture, VAD, Telegram). Spawn gives a clean Metal context.

**Example:**
```python
# Source: multiprocessing stdlib + mlx-whisper API (verified)
import multiprocessing as mp
import mlx_whisper
import numpy as np
from . import config

def _whisper_worker(
    audio_q: mp.SimpleQueue,   # parent → worker: numpy arrays + sentinels
    result_q: mp.SimpleQueue,  # worker → parent: result dicts + error dicts
) -> None:
    """Runs in spawn context. Loads model once, loops until sentinel."""
    import logging, sys
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG,
                        format="%(asctime)s %(levelname)s worker: %(message)s")
    log = logging.getLogger("esper.worker")

    log.info("Loading model: %s", config.WHISPER_MODEL_REPO)
    # model is lazy-loaded by mlx_whisper.transcribe on first call

    while True:
        audio = audio_q.get()
        if audio is None:          # sentinel — clean shutdown
            break
        try:
            raw = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=config.WHISPER_MODEL_REPO,
                language=config.WHISPER_LANGUAGE,
                word_timestamps=False,   # MUST omit — crashes on some inputs
                # clip_timestamps OMITTED — crashes on some inputs
                condition_on_previous_text=False,  # no context bleed between utterances
                temperature=0.0,
                no_speech_threshold=None,  # filtering done in parent, not here
                compression_ratio_threshold=None,
            )
            result_q.put({"ok": True, "result": raw})
        except Exception as exc:
            log.error("Inference error: %s", exc, exc_info=True)
            result_q.put({"ok": False, "error": str(exc)})
```

### Pattern 2: Watchdog Timer Thread

**What:** A daemon thread in the parent watches each in-flight utterance. If `result_q.get()` doesn't return within `WHISPER_SUBPROCESS_TIMEOUT_S` (15s), the subprocess is terminated.

**When to use:** Every utterance dispatch. The worker may hang on a corrupted audio input or a Metal crash that doesn't propagate as an exception.

**Example:**
```python
# Source: threading stdlib pattern (verified)
import threading

class WhisperTranscriber:
    def transcribe_utterance(self, audio: np.ndarray) -> dict | None:
        """Send audio to worker, wait up to timeout, return result or None."""
        self._audio_q.put(audio)
        try:
            result = self._result_q.get(timeout=config.WHISPER_SUBPROCESS_TIMEOUT_S)
            return result
        except queue.Empty:
            # Watchdog fires — kill and schedule restart
            self._kill_worker()
            return None  # caller emits error event, increments crash counter
```

### Pattern 3: Crash Counter with Auto-Restart

**What:** A counter in the parent tracks consecutive failures. Reset on any successful transcription. Emit `"crashed"` after 3 consecutive failures and stop accepting utterances.

**When to use:** After any timeout kill or worker process exit with non-zero code.

```python
# Pattern for the crash counter state machine
def _on_worker_failure(self):
    self._crash_count += 1
    if self._crash_count >= 3:
        self._send_event("crashed")
        self._stopped = True
        return
    self._spawn_worker()  # fresh subprocess

def _on_transcription_success(self):
    self._crash_count = 0  # D-08: reset on any success
```

### Pattern 4: Hallucination Filter

**What:** After each successful `transcribe()` call, inspect the first segment's `no_speech_prob` and `compression_ratio`. If either exceeds threshold, discard silently at DEBUG level.

**When to use:** Before building `TranscriptionUpdate` or calling any consumer callback.

```python
# Source: mlx_whisper.transcribe return schema (verified from source code)
def _is_hallucination(result: dict) -> bool:
    segs = result.get("segments", [])
    if not segs:
        return True  # empty result — treat as hallucination
    # Check aggregate across all segments
    avg_no_speech = sum(s["no_speech_prob"] for s in segs) / len(segs)
    avg_compression = sum(s["compression_ratio"] for s in segs) / len(segs)
    text = result.get("text", "").strip()
    if not text:
        return True
    if avg_no_speech > config.WHISPER_NO_SPEECH_THRESHOLD:
        return True
    if avg_compression > config.WHISPER_COMPRESSION_RATIO_THRESHOLD:
        return True
    return False
```

### Pattern 5: New TranscriptionUpdate Dataclass

**What:** Replaces the Parakeet-era dataclass. Consumed by `_on_update()`, `TelegramSender`, `realtime_demo.py`, and Swift `Protocol.swift`.

```python
# Source: D-01 from CONTEXT.md (locked decision)
from dataclasses import dataclass, field

@dataclass
class TranscriptionUpdate:
    """Per-utterance transcription result from Whisper."""
    text: str = ""                   # this utterance's text
    finalized_text: str = ""         # session accumulator (all utterances joined)
    sentences: list[str] = field(default_factory=list)  # all utterances so far
    no_speech_prob: float = 0.0      # from Whisper segment
    duration_s: float = 0.0          # length of the audio utterance
```

### Anti-Patterns to Avoid

- **`word_timestamps=True` in subprocess:** Confirmed by prior STATE.md decision and source review — omit entirely. Causes crashes on some inputs.
- **`clip_timestamps` in subprocess:** Same — omit. Prior decision confirmed.
- **`condition_on_previous_text=True` for utterance-based model:** Creates context bleed between unrelated utterances. Set to `False`.
- **Using `multiprocessing.Queue` instead of `SimpleQueue`:** Queue spawns threads internally, can deadlock at shutdown. Use SimpleQueue.
- **`fork` start method on macOS:** MLX + Metal state does not fork safely. Always use `mp.get_context("spawn")`.
- **Checking `no_speech_prob` only on the first segment:** Short utterances may have a single segment, but longer ones may have many. Average across all segments or use max.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Whisper inference on Apple Silicon | Custom ONNX / ctranslate2 pipeline | `mlx-whisper` | Native Metal via MLX, correct numpy input API, no_speech_prob in return |
| Subprocess IPC for large numpy arrays | Custom socket / shared memory | `multiprocessing.SimpleQueue` (pickle) | Audio utterances are at most a few MB; pickle overhead is ~1ms; far simpler |
| Model warm-up detection | Custom file cache / first-run flag | Check if model dir exists in HuggingFace cache | `~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo` |
| Temperature fallback logic | Custom retry loop | mlx-whisper built-in `temperature=(0.0, 0.2, ...)` | transcribe() already retries with higher temperature when compression_ratio_threshold exceeded |

**Key insight:** mlx-whisper wraps all the complexity of Whisper inference including temperature fallback, segment-level quality metrics, and hallucination scoring parameters. Don't re-implement what it already provides.

---

## Common Pitfalls

### Pitfall 1: word_timestamps / clip_timestamps Causes Crashes
**What goes wrong:** Passing `word_timestamps=True` or non-default `clip_timestamps` to `mlx_whisper.transcribe()` causes crashes or silent hangs on certain audio inputs.
**Why it happens:** These features interact with the MLX graph in ways that aren't robustly handled for all input lengths.
**How to avoid:** Always call with `word_timestamps=False`. Omit `clip_timestamps` entirely.
**Warning signs:** Worker subprocess exits with non-zero code on certain utterances, never on silence.

### Pitfall 2: Subprocess Uses Fork Instead of Spawn
**What goes wrong:** On macOS, forked processes inherit the parent's Metal GPU state. The child process either crashes on first MLX call or leaks Metal semaphores at shutdown.
**Why it happens:** macOS default multiprocessing start method is `spawn` in Python 3.8+, but if someone calls `mp.set_start_method("fork")` or uses `Process()` without explicit context, it may be overridden.
**How to avoid:** Always use `ctx = mp.get_context("spawn")` and call `ctx.Process(...)`. Never use `mp.Process(...)` directly.
**Warning signs:** "Semaphore leaked" warning at process exit, or Metal assertion failure on first transcription.

### Pitfall 3: Result Queue Deadlock on Large Audio
**What goes wrong:** `multiprocessing.Queue` (not SimpleQueue) spawns background feeder threads. If the worker process crashes while data is in the queue, the feeder thread in the parent can deadlock waiting for the worker's pipe.
**Why it happens:** Queue uses a background thread to flush buffered data. A dead worker means the pipe is broken, but the thread blocks indefinitely.
**How to avoid:** Use `multiprocessing.SimpleQueue`. It has no background threads and does a direct pipe read/write.
**Warning signs:** Parent process hangs after worker crash, never emitting `"error"` event.

### Pitfall 4: MLX Metal Cold Shader Compilation Triggers 120s Timeout
**What goes wrong:** First-ever run compiles Metal shaders (~10-30s). If `MODEL_LOAD_TIMEOUT_S` were still 30s, the subprocess would be killed before it could even start transcribing.
**Why it happens:** MLX compiles GPU shaders lazily on first inference, not on model load.
**How to avoid:** CLEAN-03 is already done — `config.MODEL_LOAD_TIMEOUT_S = 120.0`. The subprocess model-loading path must also respect this. Use the same timeout for the first transcription in the subprocess if a "first warmup" pattern is used.
**Warning signs:** Subprocess times out only on first run after a clean install or after clearing MLX cache.

### Pitfall 5: Crash Counter Not Reset on Success
**What goes wrong:** A temporary blip (corrupted audio frame → timeout → restart) increments the crash counter. If it's not reset on the next success, three timeout events over a long session permanently stop the pipeline.
**Why it happens:** Forgetting D-08: "Crash counter resets on any successful transcription."
**How to avoid:** `self._crash_count = 0` in the success path of the transcribe loop, not just on start.
**Warning signs:** Pipeline stops after 3 timeouts spread over many successful transcriptions.

### Pitfall 6: TranscriptionUpdate Consumer Breakage
**What goes wrong:** `telegram_sender.py` references `update.finalized_sentences` (list of sentence objects with `.text`), `update.finalized_text`, and `update.draft_text`. `realtime_demo.py` renders `draft_sentences`. Both break silently (AttributeError) when the dataclass loses those fields.
**Why it happens:** Multiple consumers of the same dataclass; changing the schema requires updating all of them in the same changeset.
**How to avoid:** Plan all consumer updates (telegram_sender.py, realtime_demo.py, Protocol.swift, TranscriptionEngine.swift) in the same wave as the dataclass change. Test each consumer with the new shape.
**Warning signs:** `AttributeError: 'TranscriptionUpdate' object has no attribute 'draft_text'`

### Pitfall 7: Subprocess Cannot Import src Package
**What goes wrong:** The spawned subprocess has a clean Python environment. If `src/` is not on `sys.path`, `from . import config` fails with ImportError.
**Why it happens:** Spawn does not inherit the parent's `sys.path` modifications made at runtime. The worker module must add the project root to `sys.path` before any relative imports, or be launched as a fully-qualified module.
**How to avoid:** In `whisper_worker.py`, add the project root to `sys.path` at the top using `pathlib.Path(__file__).parent.parent`. Alternatively, pass config values as constructor args instead of importing config in the worker.
**Warning signs:** Worker crashes immediately with ImportError on first spawn.

---

## Code Examples

### mlx_whisper.transcribe() — Full Verified Signature

```python
# Source: https://raw.githubusercontent.com/ml-explore/mlx-examples/main/whisper/mlx_whisper/transcribe.py
# Verified: 2026-03-27

import mlx_whisper
import numpy as np

audio: np.ndarray  # float32, shape (N,), 16kHz mono

result = mlx_whisper.transcribe(
    audio,                                    # numpy array accepted directly
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    language="en",
    verbose=False,
    temperature=0.0,
    compression_ratio_threshold=2.4,          # default; set None to disable
    logprob_threshold=-1.0,
    no_speech_threshold=0.6,                  # default; set None to disable
    condition_on_previous_text=False,         # no context bleed between utterances
    word_timestamps=False,                    # MUST be False — crashes on some inputs
    # clip_timestamps OMITTED                 # MUST be omitted — crashes on some inputs
)

# Return structure:
# result["text"]       → str  (full transcript)
# result["language"]   → str  (detected or specified)
# result["segments"]   → list of dicts, each with:
#   segment["no_speech_prob"]   → float  (0.0–1.0; higher = more likely silence)
#   segment["compression_ratio"] → float (higher = more repetitive/hallucinated)
#   segment["avg_logprob"]       → float (more negative = lower confidence)
#   segment["text"]              → str
#   segment["start"], ["end"]    → float (seconds)
```

### Spawn-Context Process Bootstrap

```python
# Source: Python multiprocessing stdlib (verified)
import multiprocessing as mp

ctx = mp.get_context("spawn")  # explicit — never rely on default on macOS

audio_q: mp.SimpleQueue = ctx.SimpleQueue()
result_q: mp.SimpleQueue = ctx.SimpleQueue()

proc = ctx.Process(
    target=_whisper_worker,
    args=(audio_q, result_q),
    daemon=True,
    name="whisper-worker",
)
proc.start()
```

### Recommended Hallucination Thresholds

```python
# Source: mlx_whisper defaults + community research (MEDIUM confidence)
# In config.py — add to Whisper section:
WHISPER_NO_SPEECH_THRESHOLD: float = 0.6      # default from mlx-whisper source
WHISPER_COMPRESSION_RATIO_THRESHOLD: float = 2.4  # default from mlx-whisper source
WHISPER_LOGPROB_THRESHOLD: float = -1.0       # default from mlx-whisper source

# D-07: Filtering is done in the PARENT, not the subprocess.
# Pass threshold=None to transcribe() to get raw segments, then filter here.
# This avoids the mlx-whisper temperature-fallback retry behavior, which
# is undesirable in the real-time VAD-gated context.
```

### Protocol.swift — EngineStatus Updates Needed

```swift
// Current Protocol.swift only has: idle, loadingModel, listening
// New status strings from D-09:
enum EngineStatus: String {
    case idle
    case loadingModel = "loading_model"
    case downloadingModel = "downloading_model"  // NEW
    case compilingShaders = "compiling_shaders"  // NEW
    case transcribing                            // NEW — per-utterance indicator
    case listening
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Parakeet CoreML streaming draft/finalized | Whisper batch per-utterance after VAD | Phase 4 | Simpler consumer contract; eliminates 5s fixed chunking |
| Single `loading_model` status | Three granular status events | Phase 4 | Better UX on cold start (120s possible) |
| `StreamingTranscriber` in-process | `WhisperTranscriber` subprocess-isolated | Phase 4 | MLX thread safety; model survives 50-utterance restart |
| `_processed_chars` cursor in Telegram | Per-utterance direct send | Phase 4 | Eliminates sentence boundary detection complexity |

**Deprecated/outdated:**
- `TranscriptionUpdate.draft_text`, `.draft_sentences`, `.finalized_sentences` (Parakeet-era fields): removed in this phase
- `StreamingTranscriber` class: removed and replaced by `WhisperTranscriber`
- `coreml_transcriber.py` import of `TranscriptionUpdate`: still imports during Phase 4 (remove in Phase 6); the dataclass rename must not break this import until then

---

## Open Questions

1. **Subprocess warmup on cold Metal shader compilation — who owns the 120s timeout?**
   - What we know: `config.MODEL_LOAD_TIMEOUT_S = 120.0` is set. The parent's `_load_model_with_timeout()` pattern uses this for the model-load thread.
   - What's unclear: In the subprocess architecture, model loading happens inside the worker process. The parent spawns the worker and then waits for a "ready" signal. Does the parent's 120s timeout cover the worker's first MLX shader compile, or does it need a separate mechanism?
   - Recommendation: Worker should emit a "ready" sentinel on `result_q` after model load. Parent waits up to 120s for that sentinel. If it times out, treat as crash.

2. **mlx-whisper version constraint vs. current mlx version**
   - What we know: mlx-whisper 0.4.3 is latest. mlx in venv is 0.30.6. mlx 0.31.1 is available.
   - What's unclear: Does mlx-whisper 0.4.3 require mlx >= 0.31? pip will resolve this automatically, but it may upgrade mlx.
   - Recommendation: Let pip resolve; test after install. The VAD's Silero/PyTorch is unaffected by mlx version.

3. **coreml_transcriber.py imports TranscriptionUpdate from transcriber.py**
   - What we know: `from .transcriber import TranscriptionUpdate` is at the top of `coreml_transcriber.py`. Phase 6 removes this file, but Phase 4 must not break it.
   - What's unclear: If `TranscriptionUpdate` fields change (remove `draft_text`, etc.), does anything in `coreml_transcriber.py` use those fields?
   - Recommendation: Audit `coreml_transcriber.py` before modifying the dataclass. If it uses old fields, add them as deprecated no-ops (empty string defaults) so the import doesn't break.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.11.5 | venv runtime | in venv | 3.11.5 | — |
| mlx | mlx-whisper dep | in venv | 0.30.6 (0.31.1 available) | — |
| mlx-whisper | PIPE-04 | NOT installed | 0.4.3 available | — |
| ffmpeg | mlx-whisper audio decode | in PATH | 8.0.1 | — |
| multiprocessing | PIPE-05 | stdlib | 3.11 | — |
| pytest | Testing | in venv | 9.0.2 | — |

**Missing dependencies with no fallback:**
- `mlx-whisper==0.4.3` — must be added to `requirements.txt` and installed before any implementation

**Missing dependencies with fallback:**
- None

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (direct invocation pattern used) |
| Quick run command | `python -m pytest tests/test_whisper_transcriber.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-04 | `transcribe()` accepts numpy array; returns text + segments | unit (mock subprocess) | `pytest tests/test_whisper_transcriber.py::test_transcribe_numpy_array -x` | Wave 0 |
| PIPE-05 | Worker uses spawn context, not fork | unit | `pytest tests/test_whisper_transcriber.py::test_spawn_context -x` | Wave 0 |
| PIPE-06 | no_speech_prob above threshold → silently discarded, no event | unit | `pytest tests/test_whisper_transcriber.py::test_hallucination_filter_no_speech -x` | Wave 0 |
| PIPE-06 | compression_ratio above threshold → silently discarded | unit | `pytest tests/test_whisper_transcriber.py::test_hallucination_filter_compression -x` | Wave 0 |
| ARCH-03 | Timeout after 15s kills subprocess, pipeline continues | unit | `pytest tests/test_whisper_transcriber.py::test_watchdog_timeout -x` | Wave 0 |
| ARCH-03 | Subprocess crash triggers auto-restart, max 3 times | unit | `pytest tests/test_whisper_transcriber.py::test_crash_restart -x` | Wave 0 |
| ARCH-03 | Crash counter resets on successful transcription | unit | `pytest tests/test_whisper_transcriber.py::test_crash_counter_reset -x` | Wave 0 |
| ARCH-04 | TranscriptionUpdate has new fields: text, finalized_text, sentences, no_speech_prob, duration_s | unit | `pytest tests/test_whisper_transcriber.py::test_transcription_update_fields -x` | Wave 0 |
| ARCH-04 | telegram_sender.on_update handles new shape without _processed_chars | unit | `pytest tests/test_telegram_sender.py::test_per_utterance_send -x` | Wave 0 |
| CLEAN-03 | config.MODEL_LOAD_TIMEOUT_S == 120.0 | unit | `pytest tests/test_config.py -x` (already exists) | exists |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_whisper_transcriber.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_whisper_transcriber.py` — covers PIPE-04, PIPE-05, PIPE-06, ARCH-03, ARCH-04. All tests should mock the subprocess worker so no GPU access is required in CI.
- [ ] `tests/test_telegram_sender.py` — covers ARCH-04 Telegram consumer update (existing file may not test new per-utterance shape)

*(Existing `tests/test_config.py`, `tests/test_vad.py`, `tests/test_server_ipc.py` already exist and should continue to pass unchanged.)*

---

## Sources

### Primary (HIGH confidence)
- `https://raw.githubusercontent.com/ml-explore/mlx-examples/main/whisper/mlx_whisper/transcribe.py` — Full function signature, parameter list, return schema, numpy array input confirmation, no_speech_prob and compression_ratio in segment dict
- `https://github.com/ml-explore/mlx/issues/2133` — MLX thread safety issue confirmed open and unfixed; segfaults and Metal assertion failures under concurrent use documented
- Python stdlib multiprocessing docs — SimpleQueue vs Queue, spawn context, process lifecycle
- Existing project source: `src/config.py`, `src/transcriber.py`, `src/vad.py`, `src/server.py`, `src/telegram_sender.py`, `EsperApp/EsperApp/Models/Protocol.swift`

### Secondary (MEDIUM confidence)
- `https://huggingface.co/mlx-community/whisper-large-v3-turbo` — Model repo confirmed, 1.61GB, pip install command
- mlx-whisper hallucination default thresholds: `no_speech_threshold=0.6`, `compression_ratio_threshold=2.4` — confirmed from source code
- `https://pypi.org/project/mlx-whisper/` — Version 0.4.3 confirmed current (Aug 29, 2025)
- Community discussions on hallucination filter values: `no_speech_prob > 0.6` and `compression_ratio > 2.4` are the mlx-whisper defaults; match what the parent codebase already sets as `no_speech_threshold` parameter

### Tertiary (LOW confidence)
- Inference speed estimates (1-2s per utterance on M1 Max): derived from "12 minutes in 14 seconds on M2 Ultra" community report; M1 Max will be slower; actual benchmark needed at first integration per STATE.md blocker note

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — mlx-whisper 0.4.3 version confirmed via pip; API confirmed from source
- Architecture: HIGH — multiprocessing spawn pattern confirmed against stdlib docs; MLX thread safety issue confirmed from GitHub
- Hallucination thresholds: MEDIUM — defaults from source code; community values consistent; exact optimal values for accented English speech need empirical tuning
- Pitfalls: HIGH — word_timestamps/clip_timestamps ban confirmed from STATE.md prior decisions; subprocess/fork pitfall confirmed from MLX issue tracker

**Research date:** 2026-03-27
**Valid until:** 2026-06-27 (mlx-whisper is actively developed; check for breaking API changes if > 30 days)
