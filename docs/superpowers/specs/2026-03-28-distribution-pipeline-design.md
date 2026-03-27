# Esper Distribution Pipeline Design

**Date**: 2026-03-28
**Status**: Approved
**Goal**: Ship Esper as a professional macOS app distributed via GitHub Releases as a self-contained DMG.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Distribution channel | GitHub Releases (direct download) | App spawns Python subprocess; App Store sandbox blocks this |
| Code signing | Unsigned | No Apple Developer account; users run `xattr -cr` to bypass Gatekeeper |
| Bundling | Everything inside .app | True "download and run" experience |
| VAD backend | ONNX runtime (replace PyTorch) | Saves ~2GB from distribution size |
| Versioning | Semver from v2.1.0 | Continues from existing v2.0 tag |
| License | MIT | Compatible with all deps (mlx-whisper, Silero, sounddevice) |
| CI | GitHub Actions — tests on push, DMG on tag | Standard professional setup |

---

## 1. ONNX VAD Migration

### What changes

Replace PyTorch-backed Silero VAD with the ONNX runtime version.

**Remove from requirements.txt:**
- `torch` (~2GB)
- `torchaudio` (depends on torch)
- `silero-vad` (PyTorch wrapper)

**Add to requirements.txt:**
- `onnxruntime` (~30MB)

**Bundle in repo:**
- `models/silero_vad.onnx` (~2MB) — downloaded once from Silero's GitHub releases

### Code changes in `src/vad.py`

Replace:
```python
import torch
from silero_vad import load_silero_vad

model = load_silero_vad()
model.reset_states()
speech_prob = model(tensor, config.SAMPLE_RATE).item()
```

With:
```python
import onnxruntime
import numpy as np

session = onnxruntime.InferenceSession("models/silero_vad.onnx")
# Silero ONNX model expects: input(float32[1,chunk]), sr(int64), h(float32[2,1,64]), c(float32[2,1,64])
# Returns: output(float32[1,1]), hn(float32[2,1,64]), cn(float32[2,1,64])
h = np.zeros((2, 1, 64), dtype=np.float32)
c = np.zeros((2, 1, 64), dtype=np.float32)

# Per frame:
ort_inputs = {"input": chunk, "sr": sr_array, "h": h, "c": c}
out, h, c = session.run(None, ort_inputs)
speech_prob = out[0][0]

# Reset states = zero h and c
```

The ONNX Silero model is a stateful LSTM identical to the PyTorch version. The interface is:
- Input: `(1, N)` float32 audio chunk, sample rate int64, hidden state h, cell state c
- Output: speech probability float32, updated h, updated c

### Impact on tests

`tests/test_vad.py` mocks the model — mock interface changes from `model(tensor, sr).item()` to the ONNX session pattern. Test logic (speech detection, buffering, sealing) is unchanged.

### Size impact

| Before | After | Savings |
|--------|-------|---------|
| torch 2GB + torchaudio 50MB + silero-vad 5MB | onnxruntime 30MB + silero_vad.onnx 2MB | **~2GB** |

---

## 2. Bundled App Structure

The .app is a self-contained macOS application bundle:

```
Esper.app/
  Contents/
    MacOS/
      EsperApp                    # Swift binary (compiled from Xcode)
    Resources/
      python/                     # Embedded Python 3.11 runtime (from venv)
        bin/python3               # Python interpreter
        lib/python3.11/           # Standard library
      site-packages/              # Pip packages (mlx-whisper, onnxruntime, numpy, etc.)
      models/
        whisper/                  # Whisper large-v3-turbo weights (~1.5GB)
          config.json
          weights.safetensors
        silero_vad.onnx           # Silero VAD ONNX model (~2MB)
      src/                        # Python source (server.py, vad.py, etc.)
        __init__.py
        config.py
        server.py
        vad.py
        transcriber.py
        whisper_worker.py
        audio_capture.py
        telegram_sender.py
    Info.plist
```

### ProcessBridge changes

`ProcessBridge.swift` currently receives `pythonPath` and `projectDir` from `AppSettings`. For the bundled app:

- `pythonPath` resolves to `Bundle.main.resourcePath + "/python/bin/python3"`
- `projectDir` resolves to `Bundle.main.resourcePath` (since `src/` is inside Resources)
- `PYTHONPATH` env var set to include `site-packages/` directory
- Model path (`config.WHISPER_MODEL_REPO`) resolved relative to bundle Resources

`AppSettings.resolvedPythonPath` and `resolvedProjectDir` updated to prefer bundle paths when running from .app, falling back to dev paths when running from Xcode.

### config.py changes

`_PROJECT_ROOT` detection updated:
```python
# When bundled: /path/to/Esper.app/Contents/Resources/src/config.py
# _PROJECT_ROOT should be /path/to/Esper.app/Contents/Resources/
# When dev: /path/to/Esper/src/config.py
# _PROJECT_ROOT should be /path/to/Esper/
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
```

This already works correctly for both cases — `parent.parent` of `Resources/src/config.py` is `Resources/`, and `parent.parent` of `Esper/src/config.py` is `Esper/`. No change needed.

### Estimated DMG size

| Component | Uncompressed | LZMA compressed (est.) |
|-----------|-------------|----------------------|
| Swift binary | 5MB | 2MB |
| Python runtime | 50MB | 20MB |
| site-packages (no torch) | 150MB | 60MB |
| Whisper model | 1.5GB | ~700MB |
| silero_vad.onnx | 2MB | 1MB |
| Python source | <1MB | <1MB |
| **Total** | **~1.7GB** | **~800MB** |

---

## 3. Build Script: `scripts/build-dmg.sh`

Single script that produces a distributable DMG.

### Steps

```
1. Parse version from argument or git tag
2. xcodebuild -project EsperApp/EsperApp.xcodeproj \
     -scheme EsperApp -configuration Release \
     MARKETING_VERSION=$VERSION \
     CURRENT_PROJECT_VERSION=$BUILD_NUMBER \
     build
3. Create staging directory: staging/Esper.app/
4. Copy built .app from DerivedData to staging/
5. Copy into Esper.app/Contents/Resources/:
   a. Python runtime (from .venv — interpreter + stdlib)
   b. site-packages (from .venv/lib/python3.11/site-packages/)
   c. models/whisper/ (from project models/)
   d. models/silero_vad.onnx
   e. src/ (Python source files only, no __pycache__)
6. Strip unnecessary files:
   - __pycache__/, *.pyc, *.pyo
   - pip metadata (*.dist-info/)
   - test directories in packages
   - torch (should not be present after migration)
7. Create DMG:
   hdiutil create -volname "Esper" \
     -srcfolder staging/ \
     -ov -format ULMO \
     dist/Esper-$VERSION-arm64.dmg
8. Print size and sha256
```

### Usage

```bash
# Build from git tag
./scripts/build-dmg.sh

# Build with explicit version
./scripts/build-dmg.sh --version 2.1.0
```

### Output

```
dist/Esper-2.1.0-arm64.dmg     (~800MB)
dist/Esper-2.1.0-arm64.dmg.sha256
```

---

## 4. Versioning

### Source of truth

Git tags following semver: `v2.1.0`, `v2.1.1`, `v2.2.0`, etc.

### Version propagation

1. Developer tags: `git tag v2.1.0`
2. Build script reads tag, passes to `xcodebuild` as `MARKETING_VERSION`
3. `CURRENT_PROJECT_VERSION` is the commit count or build number
4. GitHub Actions reads tag from `GITHUB_REF`

### Xcode project default

Set `MARKETING_VERSION = 2.1.0` in project.pbxproj as the default. Build script overrides when building for release.

---

## 5. GitHub Actions

### Workflow 1: `ci.yml`

**Triggers**: push to main, pull requests to main

```yaml
jobs:
  test:
    runs-on: macos-14  # Apple Silicon runner
    steps:
      - Checkout
      - Setup Python 3.11
      - pip install -r requirements.txt
      - pytest tests/ -v
      - xcodebuild build (compile check only, no packaging)
```

### Workflow 2: `release.yml`

**Triggers**: push of `v*` tag

```yaml
jobs:
  release:
    runs-on: macos-14
    steps:
      - Checkout
      - Setup Python 3.11
      - Create venv + install deps
      - Download Whisper model to models/whisper/
      - Download silero_vad.onnx to models/
      - Run pytest tests/
      - Run scripts/build-dmg.sh --version $TAG
      - Create GitHub Release:
          tag: $TAG
          name: "Esper $TAG"
          body: auto-generated changelog + install instructions
          assets: dist/Esper-$TAG-arm64.dmg
```

### Release body template

```markdown
## Install

1. Download `Esper-{version}-arm64.dmg`
2. Open the DMG, drag **Esper** to Applications
3. Open Terminal and run:
   ```
   xattr -cr /Applications/Esper.app
   ```
4. Open Esper from Applications

**Requirements:** macOS 14+ (Sonoma), Apple Silicon (M1/M2/M3/M4)

## What's New

{auto-generated from commits since last tag}
```

---

## 6. License

MIT license at `LICENSE` in repo root:

```
MIT License

Copyright (c) 2025 Yash Desai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software...
```

---

## 7. Xcode Project Updates

| Setting | Current | New |
|---------|---------|-----|
| `MARKETING_VERSION` | 1.0 | 2.1.0 |
| `ENABLE_HARDENED_RUNTIME` | NO | YES |
| `DEVELOPMENT_TEAM` | (none) | (unchanged — unsigned) |

Hardened Runtime enabled as good practice — it restricts dynamic code loading and is required if signing is added later. Since the app doesn't use JIT or dynamic libraries outside the bundle, this should work without issues.

---

## 8. Files Created/Modified

### New files
- `scripts/build-dmg.sh` — DMG build script
- `.github/workflows/ci.yml` — Test + compile on push
- `.github/workflows/release.yml` — Build DMG + create release on tag
- `LICENSE` — MIT license
- `models/silero_vad.onnx` — ONNX VAD model (downloaded)

### Modified files
- `src/vad.py` — ONNX runtime instead of PyTorch
- `requirements.txt` — Remove torch/torchaudio/silero-vad, add onnxruntime
- `EsperApp/EsperApp/ProcessBridge.swift` — Bundle-aware path resolution
- `EsperApp/EsperApp/Models/AppSettings.swift` — Bundle path defaults
- `EsperApp/EsperApp.xcodeproj/project.pbxproj` — Version, hardened runtime
- `README.md` — Update install instructions, add release download link
- `tests/test_vad.py` — Update mocks for ONNX interface

---

## Out of Scope

- Mac App Store distribution
- Code signing / notarization (can be added later with Apple Developer account)
- Auto-update mechanism (Sparkle — future milestone)
- Intel (x86_64) support (Apple Silicon only, matching MLX requirement)
- Windows/Linux builds
