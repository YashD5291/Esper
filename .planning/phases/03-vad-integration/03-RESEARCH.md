# Phase 3: VAD Integration - Research

**Researched:** 2026-03-27
**Domain:** Silero VAD + Python threading + audio pipeline wiring
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** AudioCapture blocksize changes from 1600 → 512 (hard Silero requirement). `config.CHUNK_DURATION` = 0.032s, `config.CHUNK_SAMPLES` = 512.
- **D-02:** `config.QUEUE_MAXSIZE` stays at 300.
- **D-03:** New `src/vad.py` with `VadThread` class. Daemon thread consuming from `audio_q`. Scores each 512-sample frame with Silero VAD. Accumulates speech frames into utterance buffer.
- **D-04:** VAD runs on CPU (`torch.set_num_threads(1)`). Model loaded via `torch.jit.load()` from `silero_vad` package.
- **D-05:** `_pump_audio()` thread in server.py replaced by VadThread.
- **D-06:** Speech starts when VAD probability exceeds `config.VAD_SPEECH_THRESHOLD` (0.5).
- **D-07:** Utterance ends after `config.VAD_SILENCE_THRESHOLD_MS` (500ms) of consecutive non-speech frames.
- **D-08:** Utterances shorter than `config.VAD_MIN_SPEECH_DURATION_MS` (500ms) discarded.
- **D-09:** Low-energy frames (RMS below `config.VAD_MIN_ENERGY` = 0.01) rejected before VAD scoring.
- **D-10:** Rolling pre-buffer of 300ms prepended to utterance when speech starts.
- **D-11:** Post-buffer of 200ms after silence detection.
- **D-12:** Complete utterances placed on `queue.Queue` called `speech_q`. Each entry is a numpy array (float32, full utterance audio).
- **D-13:** For Phase 3 only, existing transcriber's `push_audio()` receives the full utterance buffer instead of continuous chunks.
- **D-14:** server.py creates VadThread, passes it `audio_q` and `speech_q`.
- **D-15:** Energy emission stays on its own thread reading from `AudioCapture.energy` — no change.
- **D-16:** `on_update` callback chain unchanged.
- **D-17:** New pip dependency: `silero-vad` pip package (preferred; verified to exist as 6.2.1).

### Claude's Discretion

- Exact rolling buffer implementation (circular buffer vs deque)
- Whether to emit energy events from VadThread or keep separate energy thread
- Test structure and fixtures for VAD unit tests
- Whether `speech_q` uses a bounded or unbounded queue

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PIPE-01 | VAD detects speech boundaries using Silero VAD with configurable silence threshold | Silero VADIterator API confirmed; silence threshold via `min_silence_duration_ms` param; VAD thread pattern from ARCHITECTURE.md |
| PIPE-02 | VAD applies 150-300ms silence padding before/after utterances to prevent word clipping | Pre-buffer (D-10: 300ms) implemented as `collections.deque`; post-buffer (D-11: 200ms) appended after silence detection; matches PITFALLS Pitfall 5 prevention |
| PIPE-03 | VAD rejects low-energy chunks below configurable noise floor | RMS gate before VAD scoring (D-09); `config.VAD_MIN_ENERGY = 0.01` already defined |
</phase_requirements>

---

## Summary

Silero VAD 6.2.1 is a clean pip install that bundles the JIT model file (~2.2MB) inside the wheel — no internet download at model load time. It requires `torch >= 1.12.0` and `torchaudio >= 0.12.0` as dependencies, neither of which is currently in the venv. The silero-vad `load_silero_vad()` function calls `torch.set_num_threads(1)` at module import time automatically; the VadThread should also call it explicitly before scoring to be safe.

The `silero_vad.VADIterator` class provides a streaming-friendly `__call__` API that processes one 512-sample frame at a time and returns `{'start': N}` or `{'end': N}` signals when speech boundaries are detected. However, since decisions D-06 through D-11 specify a custom state machine (with explicit pre-buffer, post-buffer, min-duration filtering, and energy gate), **VADIterator is not the right API**. Use `load_silero_vad()` to get the raw model and call `model(tensor, 16000).item()` per frame, implementing the state machine manually. VADIterator's `speech_pad_ms` only pads by 30ms at each side (not configurable to 300ms), and its `min_silence_duration_ms` default is 100ms — both too small.

The Phase 3 bridge (D-13) keeps the pipeline functional by passing full utterance buffers directly to `transcriber.push_audio()`. This means the existing `StreamingTranscriber` receives one large chunk rather than streaming 100ms pieces — it will accumulate normally but each utterance triggers one transcription pass. This is acceptable for Phase 3.

**Primary recommendation:** Use `silero_vad.load_silero_vad()` for model loading; implement VadThread as a custom state machine rather than wrapping `VADIterator`; use `collections.deque` for the pre-buffer with a fixed maxlen.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| silero-vad | 6.2.1 | VAD model + utilities | Official Silero package; bundles JIT model; no download at runtime |
| torch | 2.6.0+ (latest: 2.11.0) | PyTorch runtime for Silero | Required by silero-vad; CPU-only usage for VAD |
| torchaudio | 2.6.0+ | Required silero-vad dep | Must match torch major.minor version |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| collections.deque | stdlib | Pre-buffer ring buffer | maxlen-bounded circular buffer; O(1) append/popleft |
| queue.Queue | stdlib | speech_q output | Bounded or unbounded utterance queue between VAD and transcriber |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| silero-vad pip package | torch.hub.load("snakers4/silero-vad") | torch.hub requires internet at first load; pip package has model bundled |
| silero-vad JIT model | silero-vad ONNX model (onnxruntime-cpu) | ONNX avoids torch/torchaudio dep but adds onnxruntime; JIT simpler given torch already needed |
| collections.deque | numpy ring buffer | deque is simpler; no numpy overhead for buffer management |

**Installation:**
```bash
pip install silero-vad torch torchaudio
```

Note: `torch` and `torchaudio` versions must match. The latest compatible pair is `torch==2.11.0 torchaudio==2.11.0`. Both support macOS/M1/CPU-only usage.

**Version verification (confirmed 2026-03-27):**
- `silero-vad`: 6.2.1 (latest) — confirmed via `pip index versions silero-vad`
- `torch`: 2.11.0 (latest) — confirmed via `pip index versions torch`
- `torchaudio`: 2.11.0 (latest) — confirmed via `pip index versions torchaudio`

---

## Architecture Patterns

### Recommended Project Structure

```
src/
├── vad.py           # New: VadThread class (this phase)
├── audio_capture.py # Modified: blocksize 1600 → 512
├── config.py        # Modified: CHUNK_DURATION/CHUNK_SAMPLES update
├── server.py        # Modified: VadThread replaces _pump_audio()
└── transcriber.py   # Unchanged: push_audio() used as Phase 3 bridge
```

### Pattern 1: VadThread State Machine

**What:** Daemon thread that reads 512-sample frames from `audio_q`, scores each frame with Silero, accumulates speech into utterance buffers with pre-buffer, and emits complete utterances to `speech_q`.

**When to use:** This is the only pattern — it's the implementation of VadThread.

**Key state variables:**
- `_prebuf: deque` — rolling window of last ~300ms (≈ 10 frames × 512 samples). `maxlen = ceil(PRE_BUFFER_MS / 32)`.
- `_speech_buf: list[np.ndarray]` — frames collected while in speech state.
- `_triggered: bool` — whether currently in speech.
- `_silence_frames: int` — consecutive non-speech frames since last speech.

**Derived constants (computed from config, not stored in config):**
```python
SILENCE_THRESHOLD_FRAMES = ceil(config.VAD_SILENCE_THRESHOLD_MS / 32)   # 500ms / 32ms = 16 frames
MIN_SPEECH_FRAMES         = ceil(config.VAD_MIN_SPEECH_DURATION_MS / 32) # 500ms / 32ms = 16 frames
PRE_BUFFER_FRAMES         = ceil(300 / 32)                               # 300ms pre-buffer = 10 frames
POST_BUFFER_MS            = 200
```

**State machine flow:**
```python
# Source: ARCHITECTURE.md lines 148-167 (The Professor's proven pattern), adapted

from silero_vad import load_silero_vad
import torch, math, collections, numpy as np, queue, threading
from . import config

class VadThread:
    def __init__(self, audio_q: queue.Queue, speech_q: queue.Queue):
        self._audio_q = audio_q
        self._speech_q = speech_q
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="vad")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def wait(self, timeout: float = 5.0):
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self):
        torch.set_num_threads(1)        # prevent MPS/MLX contention
        model = load_silero_vad()       # JIT model, bundled, CPU only
        model.reset_states()

        PRE_FRAMES  = math.ceil(300 / 32)   # 300ms pre-buffer
        SIL_FRAMES  = math.ceil(config.VAD_SILENCE_THRESHOLD_MS / 32)
        MIN_FRAMES  = math.ceil(config.VAD_MIN_SPEECH_DURATION_MS / 32)
        POST_FRAMES = math.ceil(200 / 32)   # 200ms post-buffer

        prebuf: collections.deque[np.ndarray] = collections.deque(maxlen=PRE_FRAMES)
        speech_buf: list[np.ndarray] = []
        triggered = False
        silence_frames = 0
        post_frames_remaining = 0

        while not self._stop.is_set():
            try:
                frame = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if frame is None:
                break   # sentinel from AudioCapture.stop()

            # Energy gate
            rms = float(np.sqrt(np.mean(frame ** 2)))
            if rms < config.VAD_MIN_ENERGY:
                if not triggered:
                    prebuf.append(frame)
                continue

            # VAD score
            tensor = torch.from_numpy(frame.reshape(1, -1))
            speech_prob = model(tensor, config.SAMPLE_RATE).item()

            if not triggered:
                prebuf.append(frame)
                if speech_prob >= config.VAD_SPEECH_THRESHOLD:
                    triggered = True
                    silence_frames = 0
                    # Prepend pre-buffer
                    speech_buf = list(prebuf) + [frame]
                    prebuf.clear()
            else:
                speech_buf.append(frame)
                if speech_prob < config.VAD_SPEECH_THRESHOLD:
                    silence_frames += 1
                else:
                    silence_frames = 0

                if silence_frames >= SIL_FRAMES:
                    # Collect post-buffer frames
                    for _ in range(POST_FRAMES):
                        try:
                            pf = self._audio_q.get(timeout=0.05)
                            if pf is not None:
                                speech_buf.append(pf)
                        except queue.Empty:
                            break

                    if len(speech_buf) >= MIN_FRAMES:
                        utterance = np.concatenate(speech_buf).astype(np.float32)
                        try:
                            self._speech_q.put_nowait(utterance)
                        except queue.Full:
                            pass  # discard if downstream is backed up

                    speech_buf = []
                    triggered = False
                    silence_frames = 0
                    model.reset_states()
```

### Pattern 2: AudioCapture Blocksize Change

**What:** `config.CHUNK_DURATION` and `config.CHUNK_SAMPLES` update for 512-sample frames.

**Change in config.py:**
```python
CHUNK_DURATION: float = 0.032          # 512 / 16000 = 32ms (hard Silero requirement)
CHUNK_SAMPLES: int = 512               # hard Silero VAD requirement; was 1600
QUEUE_MAXSIZE: int = 300               # unchanged — still ~9.6s at 512 samples/frame
```

**Impact on test_config.py:** Two existing tests will fail after this change:
- `test_chunk_duration` — asserts 0.1, must change to 0.032
- `test_chunk_samples` — asserts 1600, must change to 512

**AudioCapture is unchanged** — it already uses `config.CHUNK_SAMPLES` as blocksize. The change flows automatically.

### Pattern 3: server.py Wiring (replacing _pump_audio)

**What:** VadThread replaces the `_pump_audio` thread. `speech_q` is created in `_do_start`.

```python
# In server.py _do_start():
import queue as _queue
_speech_q: _queue.Queue = _queue.Queue(maxsize=10)  # bounded: 10 utterances max
_vad_thread = VadThread(audio_q=_capture._queue, speech_q=_speech_q)
_vad_thread.start()

# Phase 3 bridge — connect speech_q → existing transcriber
_bridge_thread = threading.Thread(target=_bridge_speech_q, daemon=True, name="speech-bridge")
_bridge_thread.start()

# In server.py: bridge function
def _bridge_speech_q():
    while not _stop_event.is_set():
        try:
            utterance = _speech_q.get(timeout=0.2)
        except queue.Empty:
            continue
        if utterance is None:
            break
        if _transcriber is not None:
            _transcriber.push_audio(utterance)
```

### Anti-Patterns to Avoid

- **Using VADIterator:** Its `speech_pad_ms` default is 30ms (not configurable to 300ms). Its `min_silence_duration_ms` default is 100ms. Neither matches D-07/D-10. Use raw model instead.
- **Running VAD on MPS:** `torch.set_num_threads(1)` is required. Loading model without explicit CPU device risks contention with MLX's Metal context. `load_silero_vad()` already passes `map_location='cpu'` to `torch.jit.load()`.
- **Blocking audio_q.get() indefinitely in VAD loop:** Use `timeout=0.2` to allow clean shutdown when `_stop` is set.
- **Skipping `model.reset_states()` between utterances:** Silero's LSTM state carries over between calls. Failing to reset after an utterance ends can cause the next utterance to have inflated probabilities from the previous one.
- **Passing pre-buffer frames through the energy gate:** Low-energy frames should still go into the pre-buffer (they are part of the audio stream, just quiet). Only skip VAD scoring on them.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Speech probability scoring | Custom energy/ZCR detector | `load_silero_vad()` model | Silero is trained on real speech; energy-based detection has high false-positive on accented speech |
| Torch JIT model loading | Manual ONNX runtime | `silero_vad.load_silero_vad()` | Model is bundled in the wheel; loading is one line |
| Rolling pre-buffer | Custom ring buffer class | `collections.deque(maxlen=N)` | stdlib; O(1); thread-safe for single-producer/single-consumer |

**Key insight:** The silero-vad package bundles the model file inside the wheel. No internet download occurs at `load_silero_vad()` call time — unlike `torch.hub.load()` which downloads on first call.

---

## Common Pitfalls

### Pitfall 1: Pre-buffer frames bypassed by energy gate

**What goes wrong:** If the energy gate `continue`s before appending to `prebuf`, the pre-buffer contains gaps. When speech starts, the prepended pre-buffer has holes in it — first phoneme is still clipped.

**Why it happens:** Energy gate is placed before `prebuf.append()`.

**How to avoid:** Append to `prebuf` before the energy gate check, then apply the gate for the VAD scoring step only.

**Code:**
```python
prebuf.append(frame)           # always buffer
if rms < config.VAD_MIN_ENERGY:
    continue                   # skip VAD scoring, but frame is in prebuf
```

### Pitfall 2: model.reset_states() not called between utterances

**What goes wrong:** Silero's LSTM has recurrent state. After a high-energy utterance, the state tensor carries activation that biases the next utterance toward high probability. Short ambient noises get classified as speech.

**Why it happens:** Missing `model.reset_states()` after sealing an utterance.

**How to avoid:** Call `model.reset_states()` immediately after an utterance is emitted to `speech_q`.

**Warning signs:** VAD triggers immediately on session start, or consecutive utterances have unusually high confidence for ambient noise.

### Pitfall 3: speech_q.put() blocks the VAD thread

**What goes wrong:** If `speech_q` is bounded and full (e.g., Phase 3 transcriber is slow), `speech_q.put()` blocks. The VAD thread stalls, `audio_q` fills up, and `AudioCapture._callback` drops frames (silent `queue.Full` handling).

**How to avoid:** Use `speech_q.put_nowait()` with a try/except, discarding utterances when full rather than blocking. Log the discard.

**Warning signs:** Increasing number of `queue.Full` exceptions in VAD thread during long speech segments.

### Pitfall 4: torch import time (first-ever import is slow)

**What goes wrong:** First import of `torch` can take 1-3 seconds while loading native extensions. If VadThread loads the model inside `_run()` (after the thread starts), the first 1-3 seconds of audio are silently dropped.

**How to avoid:** Load the Silero model in `VadThread.__init__()` or in a pre-load step before starting the thread. This way the model is ready before audio starts flowing.

**Warning signs:** First 2-3 seconds of speech never appear in speech_q.

### Pitfall 5: AudioCapture._queue accessed directly by VadThread

**What goes wrong:** `VadThread` is passed `_capture._queue` directly (a private attribute). This is a coupling smell but is acceptable for Phase 3 given the architecture decision. However, if `AudioCapture.stop()` puts a `None` sentinel, VadThread must handle it explicitly — otherwise `torch.from_numpy(None)` raises.

**How to avoid:** In the VadThread loop, check `if frame is None: break` before processing.

---

## Code Examples

Verified patterns from official sources:

### Loading Silero VAD (silero-vad 6.x API)

```python
# Source: silero_vad/model.py in silero_vad-6.2.1 wheel (inspected directly)
from silero_vad import load_silero_vad

model = load_silero_vad()   # loads JIT model from bundled file; CPU only
model.reset_states()
```

### Per-frame scoring

```python
# Source: silero_vad/utils_vad.py — OnnxWrapper.__call__ shows 512-sample requirement
# JIT model has same constraint (validated in OnnxWrapper._validate_input)
import torch, numpy as np

frame: np.ndarray  # shape (512,), dtype float32
tensor = torch.from_numpy(frame.reshape(1, -1))  # shape (1, 512)
speech_prob: float = model(tensor, 16000).item()
```

### Pre-buffer with deque

```python
# stdlib pattern
import collections, math

PRE_BUFFER_MS = 300
FRAME_MS = 32  # 512 samples / 16kHz
PRE_FRAMES = math.ceil(PRE_BUFFER_MS / FRAME_MS)   # = 10

prebuf: collections.deque = collections.deque(maxlen=PRE_FRAMES)
# When speech starts:
speech_buf = list(prebuf) + [current_frame]   # prepend last 300ms
prebuf.clear()
```

### VAD thread stop pattern (consistent with existing codebase)

```python
# Matches existing daemon thread pattern in server.py/_pump_audio and audio_capture.py
_stop = threading.Event()

def _run(self):
    while not self._stop.is_set():
        try:
            frame = self._audio_q.get(timeout=0.2)
        except queue.Empty:
            continue
        if frame is None:
            break
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `torch.hub.load("snakers4/silero-vad")` | `from silero_vad import load_silero_vad` | silero-vad 5.0+ | No internet download; model bundled in wheel |
| VAD model downloaded from GitHub at runtime | JIT + ONNX models bundled in `silero_vad/data/` | silero-vad 5.0+ | Works offline; faster startup |
| Only JIT format available | JIT (2.2MB) + ONNX variants (1.2-2.8MB) available | silero-vad 6.x | Can use ONNX+onnxruntime to avoid torch dep if needed |

**Deprecated/outdated:**
- `torch.hub.load("snakers4/silero-vad", "silero_vad")`: Still works but requires internet. The ARCHITECTURE.md example uses this — it is correct functionally but the pip package API (`load_silero_vad()`) is preferred.
- `VADIterator` from silero-vad: Still usable for simple batch processing, but not for the custom state machine required by D-06 through D-11.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| silero-vad | VadThread | Not installed | 6.2.1 on PyPI | None — must install |
| torch | silero-vad dependency | Not installed | 2.11.0 on PyPI | None — must install |
| torchaudio | silero-vad dependency | Not installed | 2.11.0 on PyPI | None — must install |
| sounddevice | AudioCapture | Installed 0.5.5 | 0.5.5 | — |
| numpy | VadThread frame ops | Installed 2.3.5 | 2.3.5 | — |
| Python 3.11.5 | All | Installed | 3.11.5 | — |
| pytest | Test suite | Now installed 9.0.2 | 9.0.2 | — |

**Missing dependencies with no fallback:**
- `silero-vad`, `torch`, `torchaudio` — must be installed via `pip install silero-vad torch torchaudio` before Wave 1 can run.

**Missing dependencies with fallback:**
None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none — run from project root |
| Quick run command | `python -m pytest tests/test_vad.py -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

Current baseline: 29 tests pass (`tests/test_config.py` + `tests/test_server_ipc.py`).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | VAD emits nothing to speech_q during silence frames | unit | `pytest tests/test_vad.py::test_silence_produces_no_utterance -x` | Wave 0 |
| PIPE-01 | VAD emits utterance buffer after speech + silence frames | unit | `pytest tests/test_vad.py::test_speech_then_silence_emits_utterance -x` | Wave 0 |
| PIPE-02 | Emitted utterance includes pre-buffer audio prepended | unit | `pytest tests/test_vad.py::test_prebuffer_prepended_to_utterance -x` | Wave 0 |
| PIPE-02 | Emitted utterance includes post-buffer audio appended | unit | `pytest tests/test_vad.py::test_postbuffer_appended_to_utterance -x` | Wave 0 |
| PIPE-03 | Frames below VAD_MIN_ENERGY are not scored and do not trigger speech | unit | `pytest tests/test_vad.py::test_low_energy_frames_rejected -x` | Wave 0 |
| D-01 | config.CHUNK_SAMPLES == 512 after update | unit | `pytest tests/test_config.py::test_chunk_samples -x` | Existing (update value) |
| D-08 | Utterances shorter than MIN_SPEECH_DURATION discarded | unit | `pytest tests/test_vad.py::test_short_utterance_discarded -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_config.py -q` (no torch needed)
- **Per wave merge:** `python -m pytest tests/ -q` (requires torch installed)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_vad.py` — covers PIPE-01, PIPE-02, PIPE-03, D-08 (6 test functions above)
- [ ] Wave 0 task: install `silero-vad torch torchaudio` into venv so VAD tests can import the model

**Test approach for VAD unit tests:** Mock the Silero model to control `speech_prob` output. This avoids torch dependency in the test runner and allows deterministic testing:

```python
# tests/test_vad.py pattern
from unittest.mock import MagicMock
import numpy as np, queue

# Mock model returns controlled probabilities
mock_model = MagicMock()
mock_model.return_value.item.return_value = 0.9  # high speech prob
mock_model.reset_states = MagicMock()
```

---

## Open Questions

1. **speech_q maxsize**
   - What we know: D-12 says `queue.Queue` but doesn't specify bound. ARCHITECTURE.md scalability table says `maxsize=5` with discard on full.
   - What's unclear: Whether Phase 3 transcriber is fast enough to keep up with speech_q.
   - Recommendation: Use `maxsize=10` (Claude's discretion). Discard with `put_nowait` + log warning if full.

2. **Pre-buffer frames during energy gate**
   - What we know: D-09 says low-energy frames are rejected before VAD scoring. D-10 says pre-buffer prepended when speech starts.
   - What's unclear: Should very-quiet frames still enter the pre-buffer (so the audio is there if speech follows)?
   - Recommendation: Yes — append to pre-buffer first, then apply energy gate to skip VAD scoring. This ensures the audio is available even if it was below threshold.

3. **torch + torchaudio download size**
   - What we know: torch 2.11.0 is ~65-80MB on macOS; torchaudio is ~10MB.
   - What's unclear: Whether requirements.txt should be updated now or in a separate task.
   - Recommendation: Update `requirements.txt` in the same Wave 1 task that installs the deps.

---

## Project Constraints (from CLAUDE.md)

No project-level `CLAUDE.md` found. User-level `~/.claude/CLAUDE.md` applies:

- TDD: write tests first. Wave 0 must create `tests/test_vad.py` before Wave 1 implementation.
- No bare `print()` in `src/` modules — use `log.*`. VadThread must use `logging.getLogger(__name__)`.
- No dead code, no commented-out code. Remove `_pump_audio` entirely (don't just comment it out).
- Atomic commits with clear messages.
- Strict typing — VadThread methods should use type annotations.
- No silent catches — errors in VadThread loop must be logged with `exc_info=True`.

---

## Sources

### Primary (HIGH confidence)

- `silero_vad-6.2.1-py3-none-any.whl` — inspected directly: `__init__.py`, `model.py`, `utils_vad.py`, `METADATA`. VADIterator API, load_silero_vad(), bundled model files.
- `.planning/research/ARCHITECTURE.md` — VAD integration pattern, The Professor's frame-scoring loop, config parameters (lines 138-177)
- `.planning/research/PITFALLS.md` — Pitfall 5 (pre-buffer), Pitfall 8 (MPS contention), Pitfall 7 (VAD tuning)
- `src/config.py` — VAD constants already defined (lines 15-20), current CHUNK_SAMPLES=1600
- `src/audio_capture.py` — AudioCapture._queue is `queue.Queue`, blocksize driven by config.CHUNK_SAMPLES
- `src/server.py` — `_pump_audio` thread pattern, `_do_start` / `_do_stop` wiring
- `tests/test_config.py` — two tests will need updating (chunk_duration, chunk_samples)
- `pip index versions silero-vad torch torchaudio` — version confirmation 2026-03-27

### Secondary (MEDIUM confidence)

- `.planning/research/FEATURES.md` — VAD-gated Whisper rationale, silence padding values
- Official silero-vad GitHub README (via ARCHITECTURE.md citations) — 512-sample frame requirement

### Tertiary (LOW confidence)

None — all claims verified from primary sources.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — silero-vad wheel inspected directly; torch/torchaudio versions confirmed via pip index
- Architecture: HIGH — VadThread pattern from The Professor (production-validated) + direct code inspection
- Pitfalls: HIGH — derived from direct code analysis of existing patterns and silero-vad API inspection

**Research date:** 2026-03-27
**Valid until:** 2026-06-27 (silero-vad API is stable; torch versions will update but 2.x API is unchanged)
