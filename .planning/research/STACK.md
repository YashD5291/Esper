# Technology Stack — Esper v2.0 Pipeline Overhaul

**Project:** Esper v2.0
**Researched:** 2026-03-27
**Scope:** NEW dependencies only. Validated stack (sounddevice, httpx, python-dotenv, soundfile, numpy) is not re-examined.

---

## What Changes

| Action | Package | Why |
|--------|---------|-----|
| REMOVE | `parakeet-mlx` | Entire transcription engine replaced |
| REMOVE | `coremltools` | Only used by `coreml_transcriber.py` which is being replaced |
| REMOVE | `scipy` | In requirements.txt but not imported anywhere in the codebase — dead dependency |
| ADD | `mlx-whisper>=0.4.3` | New transcription engine |
| ADD | `silero-vad>=6.2.1` | Speech boundary detection |
| ADD | `torch>=2.1.0` | Required by silero-vad; already transitively present via mlx-whisper |
| ADD | `torchaudio>=2.1.0` | Required by silero-vad for audio I/O utilities |

---

## New Dependencies

### Primary: mlx-whisper

| Attribute | Value |
|-----------|-------|
| Package | `mlx-whisper` |
| Version | `0.4.3` (latest as of 2026-03-27; verified via PyPI) |
| Model | `mlx-community/whisper-large-v3-turbo` (1.61 GB quantized, auto-downloaded from HuggingFace) |
| Why mlx-whisper | MLX-native, runs on Apple Neural Engine + GPU unified memory. Batch transcription API: `mlx_whisper.transcribe(audio_array, path_or_hf_repo="mlx-community/whisper-large-v3-turbo")` |
| Why large-v3-turbo | Best speed/accuracy tradeoff for Indian accent recognition on Apple Silicon — confirmed decision per PROJECT.md |
| Streaming mode | `mlx_whisper` does NOT have a streaming token-by-token API. The pattern for real-time use is: accumulate audio chunks via VAD until speech ends, then call `transcribe()` on the segment. This is a known constraint. |

**Integration note:** mlx-whisper's `transcribe()` accepts a numpy float32 array at 16kHz directly — no intermediate file needed. Return value is a dict with `"text"` and `"segments"` keys.

```python
import mlx_whisper
import numpy as np

# audio: np.ndarray, float32, 16kHz
result = mlx_whisper.transcribe(
    audio,
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
)
text = result["text"]
```

**Transitive dependencies pulled in by mlx-whisper:** `mlx>=0.11`, `torch`, `scipy`, `tiktoken`, `huggingface_hub`, `numba`, `tqdm`, `more-itertools`. These are managed transitively — do not pin them separately.

---

### Primary: silero-vad

| Attribute | Value |
|-----------|-------|
| Package | `silero-vad` |
| Version | `6.2.1` (latest as of 2026-03-27; released 2026-02-24, verified via PyPI) |
| Why | Lightweight, fast (<1ms per 32ms chunk on CPU), proven stable in The Professor (50+ generations zero hangs) |
| Torch requirement | `torch>=1.12.0` — satisfied by torch installed for mlx-whisper |

**Streaming API pattern** (VADIterator, verified via whisper_streaming reference implementation):

The VADIterator processes fixed 512-sample chunks at 16kHz (= 32ms per chunk). It returns a dict when a speech boundary is detected:
- `{"start": N}` — speech began at sample N
- `{"end": N}` — speech ended at sample N (after min_silence_duration_ms of quiet)

After each complete utterance, call `vad_iterator.reset_states()`.

```python
from silero_vad import load_silero_vad, VADIterator

model = load_silero_vad()
vad_iterator = VADIterator(
    model,
    sampling_rate=16000,
    threshold=0.5,
    min_silence_duration_ms=500,
    speech_pad_ms=100,
)

CHUNK = 512  # samples at 16kHz = 32ms
buffer = []

for chunk in mic_stream:  # chunk must be exactly 512 samples
    event = vad_iterator(chunk, return_seconds=False)
    if event:
        if "start" in event:
            buffer = []  # begin collecting
        if "end" in event:
            # utterance complete — transcribe buffer
            audio = np.concatenate(buffer)
            result = mlx_whisper.transcribe(audio, ...)
            vad_iterator.reset_states()
    if buffer is not None:
        buffer.append(chunk)
```

**Chunk size mismatch:** sounddevice captures 1600-sample chunks (100ms at 16kHz). The VADIterator requires exactly 512 samples. The VAD consumer must re-chunk the 1600-sample blocks into 512-sample windows before passing to VADIterator. This is a required integration step — not an optional detail.

---

### Supporting: torch + torchaudio

| Attribute | Value |
|-----------|-------|
| Package | `torch` |
| Version | `>=2.1.0` (silero-vad requires `>=1.12.0`; `2.6.0` is currently installed in The Professor's venv) |
| Package | `torchaudio` |
| Version | `>=2.1.0` (must match torch major.minor) |
| Why | silero-vad's `load_silero_vad()` and `VADIterator` depend on torch for model inference. torchaudio listed as silero-vad dependency for audio I/O helpers. |
| Apple Silicon | torch 2.1+ supports MPS (Metal Performance Shaders). Silero VAD runs on CPU (recommended — it's fast enough and avoids MPS overhead for tiny model). Set `torch.set_num_threads(1)` as recommended by silero-vad docs. |

---

## Updated requirements.txt

```
# Audio capture
sounddevice

# Audio utilities
numpy
soundfile

# VAD
silero-vad>=6.2.1
torch>=2.1.0
torchaudio>=2.1.0

# Transcription
mlx-whisper>=0.4.3

# Telegram
httpx

# Config
python-dotenv
```

**Removed from original requirements.txt:**
- `parakeet-mlx` — transcription engine replaced entirely
- `coremltools` — only used in `coreml_transcriber.py` (Parakeet); not needed for Whisper or VAD
- `scipy` — present in requirements.txt but not imported anywhere in the codebase (dead dep)

**Note:** `scipy` will still be installed transitively by mlx-whisper, so removing it from requirements.txt has no runtime effect — it just removes an explicit pin of an unused dep.

---

## What Does NOT Change

These were pre-validated and are NOT re-researched:

| Package | Role | Status |
|---------|------|--------|
| `sounddevice` | 16kHz mono mic capture | Keep as-is |
| `httpx` | Telegram Bot API | Keep as-is |
| `python-dotenv` | .env loading | Keep as-is (until config.py consolidation — internal refactor, no dep change) |
| `soundfile` | WAV recording | Keep as-is |
| `numpy` | Audio array ops | Keep as-is |

**Config consolidation** (`config.py` pattern): Zero new dependencies. This is a code reorganization — move constants from `.env` + `@AppStorage` into a `config.py` module. python-dotenv can be removed after migration, but that's a cleanup decision for the implementation phase.

**IPC cleanup**: Zero new dependencies. The existing JSON-line over stdio protocol stays; the "fd redirect hack" removal is a code change in `server.py` and the Swift `ProcessBridge` side.

---

## Files That Must Be Deleted or Gutted

| File | Action | Reason |
|------|--------|--------|
| `src/coreml_transcriber.py` | Delete | Entire CoreML/Parakeet engine; replaced by mlx-whisper |
| `src/transcriber.py` | Gut/replace | parakeet-mlx streaming transcriber; replace with mlx-whisper segment transcriber |
| `models/coreml/` | Remove from build artifacts | CoreML model bundles no longer needed (230MB+ saved) |

---

## VAD ↔ Whisper Integration Architecture

The key architectural decision: mlx-whisper does NOT stream. It is a batch transcription API. Therefore:

```
mic chunks (1600 samples / 100ms)
  → re-chunk to 512 samples
  → VADIterator (real-time, per-32ms-chunk)
  → on speech end: concatenate utterance audio buffer
  → mlx_whisper.transcribe(utterance_buffer)  ← single blocking call
  → emit text
```

Latency budget:
- VAD detection: <1ms per 32ms chunk (CPU, silero docs)
- Whisper large-v3-turbo on M1 Max: ~0.5–2s for a typical 3–10s utterance (MEDIUM confidence — no direct benchmark found; based on model size 1.61GB and Apple Silicon MLX throughput reports)
- End-to-end: speech ends → text arrives in ~1–2s, comfortably under the 500ms-from-speech constraint only if that constraint applies to the streaming draft text. For final text, expect 1–2s after utterance end.

**Implication for roadmap:** The <500ms latency requirement from PROJECT.md applies to "speech to text." With this architecture, text only appears after speech ends. Either (a) the requirement means "latency from speech END, not speech start" — which is met — or (b) streaming word-by-word output was expected, which mlx-whisper cannot provide. This should be clarified before implementation.

---

## Confidence Assessment

| Claim | Confidence | Source |
|-------|------------|--------|
| mlx-whisper 0.4.3 is latest | HIGH | PyPI JSON API, verified directly |
| silero-vad 6.2.1 is latest | HIGH | PyPI JSON API, verified directly |
| `mlx-community/whisper-large-v3-turbo` exists and is 1.61GB | HIGH | HuggingFace model page, verified |
| mlx-whisper accepts numpy array directly (no file needed) | MEDIUM | PyPI docs + community examples; official docs don't explicitly state this |
| Silero VAD VADIterator uses 512-sample chunks at 16kHz | HIGH | Official wiki + whisper_streaming reference implementation |
| torch.set_num_threads(1) recommended for Silero VAD | HIGH | Official Silero VAD PyTorch Hub page |
| scipy is unused in Esper src/ | HIGH | Grep of entire src/ directory confirms zero imports |
| Whisper large-v3-turbo latency 1–2s on M1 Max | LOW | No direct benchmark found; estimate from model size and MLX throughput reports |

---

## Sources

- PyPI mlx-whisper: https://pypi.org/project/mlx-whisper/ (0.4.3, released 2025-08-29)
- PyPI silero-vad: https://pypi.org/project/silero-vad/ (6.2.1, released 2026-02-24)
- HuggingFace mlx-community/whisper-large-v3-turbo: https://huggingface.co/mlx-community/whisper-large-v3-turbo
- Silero VAD Wiki (VADIterator examples): https://github.com/snakers4/silero-vad/wiki/Examples-and-Dependencies
- whisper_streaming silero_vad_iterator.py (FixedVADIterator reference): https://github.com/ufal/whisper_streaming/blob/main/silero_vad_iterator.py
- PyTorch Hub Silero VAD (torch.set_num_threads recommendation): https://pytorch.org/hub/snakers4_silero-vad_vad/
