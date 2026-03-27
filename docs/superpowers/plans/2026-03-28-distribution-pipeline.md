# Distribution Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Esper as a professional macOS app distributed via GitHub Releases as a self-contained DMG with automated CI/CD.

**Architecture:** Replace PyTorch VAD with ONNX runtime (~2GB savings), bundle Python + deps + models inside .app, automate builds with GitHub Actions triggered by git tags.

**Tech Stack:** onnxruntime (VAD), hdiutil (DMG), GitHub Actions (CI/CD), xcodebuild (Swift)

**Spec:** `docs/superpowers/specs/2026-03-28-distribution-pipeline-design.md`

---

### Task 1: ONNX VAD Migration — Model & Class

**Files:**
- Create: `src/vad_model.py`
- Modify: `src/config.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Download the Silero ONNX model**

```bash
curl -L -o models/silero_vad.onnx \
  "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
```

Verify: file should be ~2MB.

- [ ] **Step 2: Update requirements.txt**

Remove `torch`, `torchaudio`, `silero-vad`. Add `onnxruntime`.

```
sounddevice==0.5.5
numpy==2.3.5
soundfile==0.13.1
httpx==0.28.1
python-dotenv==1.2.1
onnxruntime==1.22.0
mlx-whisper==0.4.3
```

Run: `pip install onnxruntime && pip uninstall -y torch torchaudio silero-vad`

- [ ] **Step 3: Add VAD_MODEL_PATH to config.py**

Add after the `VAD_POST_BUFFER_MS` line:

```python
VAD_MODEL_PATH: str = str(_PROJECT_ROOT / "models" / "silero_vad.onnx")
```

- [ ] **Step 4: Create src/vad_model.py**

```python
"""Silero VAD v5 via ONNX runtime -- no PyTorch dependency.

Drop-in replacement for the torch-based Silero model. Implements the same
__call__ and reset_states interface used by VadThread.
"""

from __future__ import annotations

import numpy as np
import onnxruntime


class SileroVadOnnx:
    """Silero VAD running on ONNX runtime (CPU only, ~2MB model)."""

    def __init__(self, model_path: str) -> None:
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)

    def reset_states(self) -> None:
        """Zero RNN state and context buffer between utterances."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)

    def __call__(self, audio: np.ndarray, sr: int) -> float:
        """Score a 512-sample audio chunk. Returns speech probability [0, 1].

        Args:
            audio: float32 array, shape (1, 512) or (512,).
            sr: sample rate, must be 16000.
        """
        if audio.ndim == 1:
            audio = audio[np.newaxis, :]

        # Prepend 64-sample context for temporal continuity
        x = np.concatenate([self._context, audio], axis=1)  # (1, 576)

        ort_inputs = {
            "input": x,
            "state": self._state,
            "sr": np.array(sr, dtype=np.int64),
        }
        out, self._state = self._session.run(None, ort_inputs)

        # Save last 64 samples as context for next call
        self._context = x[:, -64:]

        return float(out[0, 0])
```

- [ ] **Step 5: Commit**

```bash
git add models/silero_vad.onnx src/vad_model.py src/config.py requirements.txt
git commit -m "feat: add Silero VAD ONNX model and wrapper class"
```

---

### Task 2: ONNX VAD Migration — Wire Into VadThread

**Files:**
- Modify: `src/vad.py`

- [ ] **Step 1: Replace torch imports with vad_model import**

Replace the imports at the top of `src/vad.py`:

```python
import numpy as np
import torch
from silero_vad import load_silero_vad
```

With:

```python
import numpy as np

from .vad_model import SileroVadOnnx
```

- [ ] **Step 2: Replace model initialization in _run()**

Replace:

```python
        torch.set_num_threads(1)  # prevent MPS/MLX contention
        model = load_silero_vad()
        model.reset_states()
```

With:

```python
        model = SileroVadOnnx(config.VAD_MODEL_PATH)
```

- [ ] **Step 3: Replace torch tensor creation in _run()**

Replace:

```python
                tensor = torch.from_numpy(frame.reshape(1, -1))
                speech_prob = model(tensor, config.SAMPLE_RATE).item()
```

With:

```python
                speech_prob = model(frame, config.SAMPLE_RATE)
```

The ONNX wrapper accepts raw numpy arrays and returns a float directly — no tensor conversion or `.item()` needed.

- [ ] **Step 4: Remove `from typing import Optional`**

This import is no longer needed since we can use Python 3.11+ `X | None` syntax. Replace line 13:

```python
from typing import Optional
```

With nothing (delete the line). And update line 42:

```python
        self._thread: Optional[threading.Thread] = None
```

To:

```python
        self._thread: threading.Thread | None = None
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_vad.py -v
```

Expected: All 6 VAD tests pass. The tests mock `load_silero_vad` — we need to update them to mock `SileroVadOnnx` instead. See Task 3.

- [ ] **Step 6: Commit**

```bash
git add src/vad.py
git commit -m "feat: switch VadThread from PyTorch to ONNX runtime"
```

---

### Task 3: ONNX VAD Migration — Update Tests

**Files:**
- Modify: `tests/test_vad.py`

- [ ] **Step 1: Update the mock target**

In `run_vad()`, change the patch target from `src.vad.load_silero_vad` to `src.vad.SileroVadOnnx`.

Replace:

```python
    with patch("src.vad.load_silero_vad", return_value=mock_model):
        vad = VadThread(audio_q=audio_q, speech_q=speech_q)
        vad.start()
        vad.wait(timeout=timeout)
```

With:

```python
    with patch("src.vad.SileroVadOnnx", return_value=mock_model):
        vad = VadThread(audio_q=audio_q, speech_q=speech_q)
        vad.start()
        vad.wait(timeout=timeout)
```

- [ ] **Step 2: Update mock model interface**

The mock model's `__call__` currently returns an object with `.item()`. The ONNX wrapper returns a float directly. Update `make_mock_model`:

Replace:

```python
def make_mock_model(speech_prob: float = 0.9) -> MagicMock:
    """Return a mock Silero model that returns a fixed speech probability."""
    model = MagicMock()
    model.return_value.item.return_value = speech_prob
    model.reset_states = MagicMock()
    return model
```

With:

```python
def make_mock_model(speech_prob: float = 0.9) -> MagicMock:
    """Return a mock ONNX VAD model that returns a fixed speech probability."""
    model = MagicMock()
    model.return_value = speech_prob
    model.reset_states = MagicMock()
    return model
```

- [ ] **Step 3: Update side_effect functions**

In every test that uses a `side_effect` function, the mock returns an object with `.item()`. Update to return a float directly.

In `test_speech_then_silence_emits_utterance`, `test_prebuffer_prepended_to_utterance`, `test_postbuffer_appended_to_utterance`, and `test_short_utterance_discarded`, change all occurrences of:

```python
        result = MagicMock()
        ...
        result.item.return_value = 0.9
        ...
        result.item.return_value = 0.1
        ...
        return result
```

To simply return the float:

```python
        if <condition>:
            return 0.9
        else:
            return 0.1
```

For `test_speech_then_silence_emits_utterance` (line 92-98):
```python
    def side_effect(audio, sample_rate):
        if call_count[0] < 20:
            prob = 0.9
        else:
            prob = 0.1
        call_count[0] += 1
        return prob
```

For `test_prebuffer_prepended_to_utterance` (line 129-138):
```python
    def side_effect(audio, sample_rate):
        if 15 <= call_count[0] < 35:
            prob = 0.9
        else:
            prob = 0.1
        call_count[0] += 1
        return prob
```

For `test_postbuffer_appended_to_utterance` (line 171-178):
```python
    def side_effect(audio, sample_rate):
        if call_count[0] < 20:
            prob = 0.9
        else:
            prob = 0.1
        call_count[0] += 1
        return prob
```

For `test_short_utterance_discarded` (line 222-228):
```python
    def side_effect(audio, sample_rate):
        if call_count[0] < 2:
            prob = 0.9
        else:
            prob = 0.1
        call_count[0] += 1
        return prob
```

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All 71 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_vad.py
git commit -m "test: update VAD tests for ONNX model interface"
```

---

### Task 4: Bundle-Aware Path Resolution

**Files:**
- Modify: `EsperApp/EsperApp/Models/AppSettings.swift`
- Modify: `EsperApp/EsperApp/ProcessBridge.swift`

- [ ] **Step 1: Update AppSettings to detect bundle paths**

Replace `resolvedPythonPath` and `resolvedProjectDir` in `AppSettings.swift`:

```swift
    var resolvedPythonPath: String {
        if !pythonPath.isEmpty { return pythonPath }
        // Bundled app: python inside Resources
        if let bundled = Bundle.main.resourcePath {
            let bundledPython = (bundled as NSString).appendingPathComponent("python/bin/python3")
            if FileManager.default.fileExists(atPath: bundledPython) {
                return bundledPython
            }
        }
        // Dev fallback: venv in project directory
        return (resolvedProjectDir as NSString).appendingPathComponent(".venv/bin/python3")
    }

    var resolvedProjectDir: String {
        if !projectDir.isEmpty { return projectDir }
        // Bundled app: src/ and models/ inside Resources
        if let bundled = Bundle.main.resourcePath {
            let bundledSrc = (bundled as NSString).appendingPathComponent("src")
            if FileManager.default.fileExists(atPath: bundledSrc) {
                return bundled
            }
        }
        // Dev fallback
        return (NSHomeDirectory() as NSString).appendingPathComponent("Codebase/Fun/Esper")
    }
```

- [ ] **Step 2: Add PYTHONPATH and PYTHONHOME to ProcessBridge env**

In `ProcessBridge.swift` `launch()` method, after the existing `env["PYTHONUNBUFFERED"] = "1"` block and before `proc.environment = env`, add:

```swift
        // When running from app bundle, set Python paths for embedded runtime
        if let resourcePath = Bundle.main.resourcePath {
            let sitePackages = (resourcePath as NSString).appendingPathComponent("site-packages")
            if FileManager.default.fileExists(atPath: sitePackages) {
                // Bundled mode: tell Python where to find packages and source
                let pythonHome = (resourcePath as NSString).appendingPathComponent("python")
                env["PYTHONHOME"] = pythonHome
                env["PYTHONPATH"] = "\(sitePackages):\(resourcePath)"
            }
        }
```

- [ ] **Step 3: Build and verify in Xcode**

Open `EsperApp.xcodeproj` in Xcode, build (Cmd+B). Verify no compile errors. Run from Xcode (Cmd+R) — should still work in dev mode since the bundle detection falls back to dev paths.

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/Models/AppSettings.swift EsperApp/EsperApp/ProcessBridge.swift
git commit -m "feat: bundle-aware path resolution for embedded Python runtime"
```

---

### Task 5: Build DMG Script

**Files:**
- Create: `scripts/build-dmg.sh`

- [ ] **Step 1: Create the build script**

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── Parse arguments ──────────────────────────────────────────────────────────
VERSION=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --version) VERSION="$2"; shift 2 ;;
        *) echo "Usage: $0 [--version X.Y.Z]"; exit 1 ;;
    esac
done

# Auto-detect version from git tag if not provided
if [[ -z "$VERSION" ]]; then
    VERSION=$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')
    if [[ -z "$VERSION" ]]; then
        echo "ERROR: No --version provided and no git tag found"
        exit 1
    fi
fi

echo "==> Building Esper v${VERSION}"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/build"
STAGING="$BUILD_DIR/staging"
APP="$STAGING/Esper.app"
RESOURCES="$APP/Contents/Resources"
DIST="$PROJECT_DIR/dist"

# ── Clean ────────────────────────────────────────────────────────────────────
rm -rf "$BUILD_DIR" "$DIST"
mkdir -p "$DIST"

# ── 1. Build the Swift app ───────────────────────────────────────────────────
echo "==> Building Swift app..."
xcodebuild -project "$PROJECT_DIR/EsperApp/EsperApp.xcodeproj" \
    -scheme EsperApp \
    -configuration Release \
    -derivedDataPath "$BUILD_DIR/derived" \
    MARKETING_VERSION="$VERSION" \
    CURRENT_PROJECT_VERSION="$(git rev-list --count HEAD)" \
    clean build 2>&1 | tail -5

# Find the built .app
BUILT_APP=$(find "$BUILD_DIR/derived" -name "EsperApp.app" -type d | head -1)
if [[ -z "$BUILT_APP" ]]; then
    echo "ERROR: Built .app not found"
    exit 1
fi

# ── 2. Stage the app ────────────────────────────────────────────────────────
echo "==> Staging app bundle..."
mkdir -p "$STAGING"
cp -R "$BUILT_APP" "$APP"

# ── 3. Embed Python runtime ─────────────────────────────────────────────────
echo "==> Embedding Python runtime..."
VENV="$PROJECT_DIR/.venv"
PYTHON_VERSION="3.11"

if [[ ! -d "$VENV" ]]; then
    echo "ERROR: .venv not found. Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

# Copy Python interpreter and stdlib
PYTHON_PREFIX=$("$VENV/bin/python3" -c "import sys; print(sys.base_prefix)")
mkdir -p "$RESOURCES/python/bin" "$RESOURCES/python/lib"
cp "$VENV/bin/python3" "$RESOURCES/python/bin/python3"
cp -R "$PYTHON_PREFIX/lib/python${PYTHON_VERSION}" "$RESOURCES/python/lib/"

# Copy site-packages (installed deps)
cp -R "$VENV/lib/python${PYTHON_VERSION}/site-packages" "$RESOURCES/site-packages"

# ── 4. Embed source and models ──────────────────────────────────────────────
echo "==> Embedding source and models..."
cp -R "$PROJECT_DIR/src" "$RESOURCES/src"
mkdir -p "$RESOURCES/models"
cp -R "$PROJECT_DIR/models/whisper" "$RESOURCES/models/whisper"
cp "$PROJECT_DIR/models/silero_vad.onnx" "$RESOURCES/models/silero_vad.onnx"

# ── 5. Strip unnecessary files ──────────────────────────────────────────────
echo "==> Stripping unnecessary files..."
find "$RESOURCES" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RESOURCES" -name "*.pyc" -delete 2>/dev/null || true
find "$RESOURCES" -name "*.pyo" -delete 2>/dev/null || true
find "$RESOURCES/site-packages" -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RESOURCES/site-packages" -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
find "$RESOURCES/site-packages" -name "test" -type d -exec rm -rf {} + 2>/dev/null || true
# Remove torch if it snuck in as a transitive dep
rm -rf "$RESOURCES/site-packages/torch" \
       "$RESOURCES/site-packages/torchaudio" \
       "$RESOURCES/site-packages/silero_vad" 2>/dev/null || true
# Remove pip/setuptools/wheel
rm -rf "$RESOURCES/site-packages/pip" \
       "$RESOURCES/site-packages/setuptools" \
       "$RESOURCES/site-packages/wheel" \
       "$RESOURCES/site-packages/_distutils_hack" 2>/dev/null || true

# ── 6. Create DMG ───────────────────────────────────────────────────────────
DMG_NAME="Esper-${VERSION}-arm64.dmg"
echo "==> Creating $DMG_NAME..."
hdiutil create \
    -volname "Esper" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DIST/$DMG_NAME"

# ── 7. Checksum ─────────────────────────────────────────────────────────────
shasum -a 256 "$DIST/$DMG_NAME" > "$DIST/$DMG_NAME.sha256"

# ── Done ─────────────────────────────────────────────────────────────────────
SIZE=$(du -sh "$DIST/$DMG_NAME" | cut -f1)
echo ""
echo "==> Done!"
echo "    DMG:  $DIST/$DMG_NAME ($SIZE)"
echo "    SHA:  $(cat "$DIST/$DMG_NAME.sha256")"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/build-dmg.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build-dmg.sh
git commit -m "feat: add DMG build script for distribution"
```

---

### Task 6: GitHub Actions — CI Workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m venv .venv
          source .venv/bin/activate
          pip install -r requirements.txt

      - name: Run tests
        run: |
          source .venv/bin/activate
          pytest tests/ -v

      - name: Build Swift app (compile check)
        run: |
          xcodebuild -project EsperApp/EsperApp.xcodeproj \
            -scheme EsperApp \
            -configuration Release \
            build 2>&1 | tail -20
```

- [ ] **Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/ci.yml
git commit -m "ci: add test and compile check on push/PR"
```

---

### Task 7: GitHub Actions — Release Workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create release workflow**

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    runs-on: macos-14
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m venv .venv
          source .venv/bin/activate
          pip install -r requirements.txt

      - name: Run tests
        run: |
          source .venv/bin/activate
          pytest tests/ -v

      - name: Download Whisper model
        run: |
          source .venv/bin/activate
          python -c "
          import mlx_whisper
          mlx_whisper.transcribe(
              'tests/fixtures/silence.wav' if False else '',
              path_or_hf_repo='mlx-community/whisper-large-v3-turbo',
          )
          " || true
          # Copy from HuggingFace cache to local models/
          mkdir -p models/whisper
          HF_MODEL=\$(find ~/.cache/huggingface/hub -name "whisper-large-v3-turbo" -type d | head -1)
          if [[ -n "\$HF_MODEL" ]]; then
            cp -R "\$HF_MODEL/snapshots/"*/* models/whisper/
          fi

      - name: Extract version from tag
        id: version
        run: echo "version=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"

      - name: Build DMG
        run: ./scripts/build-dmg.sh --version ${{ steps.version.outputs.version }}

      - name: Generate changelog
        id: changelog
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo "")
          if [[ -n "$PREV_TAG" ]]; then
            CHANGES=$(git log --oneline "$PREV_TAG"..HEAD --no-merges)
          else
            CHANGES=$(git log --oneline -20 --no-merges)
          fi
          echo "changes<<EOF" >> "$GITHUB_OUTPUT"
          echo "$CHANGES" >> "$GITHUB_OUTPUT"
          echo "EOF" >> "$GITHUB_OUTPUT"

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          name: "Esper v${{ steps.version.outputs.version }}"
          body: |
            ## Install

            1. Download `Esper-${{ steps.version.outputs.version }}-arm64.dmg` below
            2. Open the DMG, drag **Esper** to Applications
            3. Open Terminal and run:
               ```
               xattr -cr /Applications/Esper.app
               ```
            4. Open Esper from Applications

            **Requirements:** macOS 14+ (Sonoma), Apple Silicon (M1/M2/M3/M4)

            ## Changes

            ${{ steps.changelog.outputs.changes }}
          files: |
            dist/Esper-${{ steps.version.outputs.version }}-arm64.dmg
            dist/Esper-${{ steps.version.outputs.version }}-arm64.dmg.sha256
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add release workflow — build DMG on tag push"
```

---

### Task 8: License, Xcode Project, README

**Files:**
- Create: `LICENSE`
- Modify: `EsperApp/EsperApp.xcodeproj/project.pbxproj`
- Modify: `README.md`

- [ ] **Step 1: Create LICENSE file**

```
MIT License

Copyright (c) 2025 Yash Desai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Update Xcode project version**

In `EsperApp/EsperApp.xcodeproj/project.pbxproj`, update both Debug and Release build settings:

Change `MARKETING_VERSION = 1.0;` to `MARKETING_VERSION = 2.1.0;` (appears twice — Debug and Release sections).

Change `ENABLE_HARDENED_RUNTIME = NO;` to `ENABLE_HARDENED_RUNTIME = YES;` (appears twice).

- [ ] **Step 3: Update README.md**

Replace the "License" section at the bottom:

```markdown
## License

[MIT License](LICENSE) -- Copyright (c) 2025 Yash Desai
```

Add a "Download" section after the badges:

```markdown
## Download

Grab the latest release: [**Esper.dmg**](https://github.com/YashD5291/Esper/releases/latest)

After installing, open Terminal and run:
```
xattr -cr /Applications/Esper.app
```

Then open Esper from Applications.
```

- [ ] **Step 4: Commit**

```bash
git add LICENSE EsperApp/EsperApp.xcodeproj/project.pbxproj README.md
git commit -m "feat: add MIT license, update version to 2.1.0, update README"
```

---

### Task 9: End-to-End Verification

- [ ] **Step 1: Run full test suite**

```bash
source .venv/bin/activate
pytest tests/ -v
```

Expected: All tests pass (71 tests, updated for ONNX).

- [ ] **Step 2: Test CLI pipeline**

```bash
source .venv/bin/activate
python -m src.realtime_demo
```

Verify: device picker shows, speech is transcribed. This confirms the ONNX VAD migration works end-to-end.

- [ ] **Step 3: Build DMG locally**

```bash
./scripts/build-dmg.sh --version 2.1.0
```

Expected: `dist/Esper-2.1.0-arm64.dmg` created with SHA256 checksum.

- [ ] **Step 4: Test the DMG**

```bash
# Mount and install
open dist/Esper-2.1.0-arm64.dmg
# Drag to Applications
xattr -cr /Applications/Esper.app
open /Applications/Esper.app
```

Verify: app launches, menu bar icon appears, device list populates, transcription works.

- [ ] **Step 5: Tag and push**

```bash
git tag v2.1.0
git push origin main --tags
```

This triggers the release workflow on GitHub Actions.

- [ ] **Step 6: Verify GitHub Release**

Go to `https://github.com/YashD5291/Esper/releases` and confirm:
- Release `Esper v2.1.0` was created
- DMG and SHA256 are attached
- Install instructions are in the body
