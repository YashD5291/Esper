# PyInstaller Build Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual Python embedding (otool/install_name_tool/codesign loops) with a PyInstaller-frozen `esper-server` binary that the Swift app launches directly.

**Architecture:** PyInstaller freezes `src/server.py` + all dependencies + models into a self-contained `esper-server` directory. The Swift app checks for this in Resources, falls back to dev venv if absent. The build script shrinks from 160 lines of dylib gymnastics to a clean freeze→build→copy→sign→package flow.

**Tech Stack:** PyInstaller 6.x, Python 3.11, Xcode/xcodebuild, codesign, hdiutil

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `esper-server.spec` | PyInstaller spec — entry point, data files, excludes |
| Modify | `src/config.py:10` | Detect `sys._MEIPASS` for frozen model paths |
| Modify | `src/whisper_worker.py:20-22` | Detect frozen mode for sys.path in subprocess |
| Create | `tests/test_frozen_paths.py` | Verify config path resolution in both modes |
| Modify | `EsperApp/EsperApp/ProcessBridge.swift` | Simplify launch — frozen binary or dev fallback |
| Modify | `EsperApp/EsperApp/Models/AppSettings.swift` | Replace path resolution with frozen binary detection |
| Modify | `EsperApp/EsperApp/TranscriptionEngine.swift` | Update launch call signature |
| Rewrite | `scripts/build-dmg.sh` | Replace dylib embedding with PyInstaller + copy |
| Modify | `.github/workflows/release.yml` | Add PyInstaller step |
| Modify | `requirements.txt` | Add PyInstaller as build dep (or separate file) |

---

### Task 1: Add PyInstaller and Create Spec File

**Files:**
- Create: `requirements-build.txt`
- Create: `esper-server.spec`

- [ ] **Step 1: Create build requirements file**

Create `requirements-build.txt`:

```
pyinstaller==6.13.0
```

Keep it separate from `requirements.txt` — PyInstaller is a build tool, not a runtime dependency.

- [ ] **Step 2: Install PyInstaller in venv**

Run:
```bash
.venv/bin/pip install -r requirements-build.txt
```

Expected: PyInstaller installs successfully.

- [ ] **Step 3: Create PyInstaller spec file**

Create `esper-server.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Esper headless server.

Freezes src/server.py + all dependencies + models into a self-contained
directory at dist/esper-server/.
"""

import os
import sys

block_cipher = None

# Paths
PROJECT_ROOT = os.path.abspath('.')
MODELS_DIR = os.path.join(PROJECT_ROOT, 'models')

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'src', 'server.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(MODELS_DIR, 'silero_vad.onnx'), 'models'),
        (os.path.join(MODELS_DIR, 'whisper'), 'models/whisper'),
    ],
    hiddenimports=[
        'src',
        'src.config',
        'src.audio_capture',
        'src.vad',
        'src.vad_model',
        'src.transcriber',
        'src.whisper_worker',
        'src.telegram_sender',
        # onnxruntime internals PyInstaller misses
        'onnxruntime',
        'onnxruntime.capi',
        'onnxruntime.capi._pybind_state',
        # sounddevice needs _sounddevice_data for portaudio
        '_sounddevice_data',
        # mlx-whisper and its deps
        'mlx_whisper',
        'mlx',
        'mlx.core',
        'huggingface_hub',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'torchaudio',
        'torchvision',
        'torchgen',
        'functorch',
        'tensorflow',
        'tensorboard',
        'pytest',
        'IPython',
        'jupyter',
        'matplotlib',
        'PIL',
        'tkinter',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='esper-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch='arm64',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='esper-server',
)
```

- [ ] **Step 4: Test freeze locally**

Run:
```bash
.venv/bin/pyinstaller esper-server.spec --noconfirm --distpath build/frozen
```

Expected: `build/frozen/esper-server/esper-server` exists and is executable.

- [ ] **Step 5: Smoke test the frozen binary**

Run:
```bash
echo '{"cmd":"list_devices"}' | (cat; sleep 2) | build/frozen/esper-server/esper-server 2>/tmp/esper-frozen-test.log
```

Expected: JSON output with `{"event": "status", "data": "idle"}` and `{"event": "devices", ...}` on stdout. Check stderr log:
```bash
cat /tmp/esper-frozen-test.log
```

Expected: `Esper server started`, `Listed N input devices`, no import errors.

- [ ] **Step 6: Commit**

```bash
git add esper-server.spec requirements-build.txt
git commit -m "feat: add PyInstaller spec for frozen esper-server build"
```

---

### Task 2: Update Python Config for Frozen Mode

**Files:**
- Modify: `src/config.py:10`
- Modify: `src/whisper_worker.py:20-22`
- Create: `tests/test_frozen_paths.py`

- [ ] **Step 1: Write failing test for frozen path detection**

Create `tests/test_frozen_paths.py`:

```python
"""Tests for frozen (PyInstaller) vs dev mode path resolution."""

import pathlib
import sys
from unittest import mock


def test_config_uses_meipass_when_frozen():
    """When sys._MEIPASS is set, _PROJECT_ROOT should point to it."""
    fake_meipass = "/tmp/fake_meipass"
    with mock.patch.dict(sys.__dict__, {"_MEIPASS": fake_meipass}):
        # Re-import to pick up the patched value
        import importlib
        from src import config
        importlib.reload(config)

        assert config._PROJECT_ROOT == pathlib.Path(fake_meipass)
        assert config.VAD_MODEL_PATH == str(pathlib.Path(fake_meipass) / "models" / "silero_vad.onnx")
        assert config.WHISPER_MODEL_REPO == str(pathlib.Path(fake_meipass) / "models" / "whisper")

    # Restore normal state
    importlib.reload(config)


def test_config_uses_file_path_when_not_frozen():
    """In dev mode, _PROJECT_ROOT should be based on __file__."""
    from src import config
    # _PROJECT_ROOT should be the repo root (parent of src/)
    expected = pathlib.Path(__file__).resolve().parent.parent
    assert config._PROJECT_ROOT == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_frozen_paths.py -v`

Expected: `test_config_uses_meipass_when_frozen` FAILS because config.py doesn't check `sys._MEIPASS`.

- [ ] **Step 3: Update config.py for frozen mode**

In `src/config.py`, replace line 10:

```python
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
```

With:

```python
import sys

_FROZEN = getattr(sys, '_MEIPASS', None)
_PROJECT_ROOT = pathlib.Path(_FROZEN) if _FROZEN else pathlib.Path(__file__).resolve().parent.parent
```

- [ ] **Step 4: Update whisper_worker.py sys.path for frozen mode**

In `src/whisper_worker.py`, replace lines 20-22:

```python
_PROJECT_ROOT = str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
```

With:

```python
_FROZEN = getattr(sys, '_MEIPASS', None)
_PROJECT_ROOT = _FROZEN if _FROZEN else str(pathlib.Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_frozen_paths.py -v`

Expected: Both tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`

Expected: All existing tests still pass (no regressions).

- [ ] **Step 7: Test frozen binary again with updated paths**

Run:
```bash
.venv/bin/pyinstaller esper-server.spec --noconfirm --distpath build/frozen
(echo '{"cmd":"list_devices"}'; sleep 2) | build/frozen/esper-server/esper-server 2>/tmp/esper-frozen-test.log
cat /tmp/esper-frozen-test.log
```

Expected: Server starts, lists devices, no `FileNotFoundError` for models.

- [ ] **Step 8: Commit**

```bash
git add src/config.py src/whisper_worker.py tests/test_frozen_paths.py
git commit -m "feat: detect PyInstaller frozen mode for model path resolution"
```

---

### Task 3: Simplify ProcessBridge.swift

**Files:**
- Modify: `EsperApp/EsperApp/ProcessBridge.swift`
- Modify: `EsperApp/EsperApp/Models/AppSettings.swift`
- Modify: `EsperApp/EsperApp/TranscriptionEngine.swift`

- [ ] **Step 1: Rewrite AppSettings.swift**

Replace the entire content of `EsperApp/EsperApp/Models/AppSettings.swift` with:

```swift
import SwiftUI

@Observable
final class AppSettings {
    // Telegram
    @ObservationIgnored
    @AppStorage("telegramEnabled") var telegramEnabled: Bool = false

    @ObservationIgnored
    @AppStorage("telegramBotToken") var telegramBotToken: String = ""

    @ObservationIgnored
    @AppStorage("telegramChatId") var telegramChatId: String = ""

    // MARK: - Server executable path

    /// Path to the frozen esper-server binary (bundled mode), or nil for dev mode.
    var frozenServerPath: String? {
        guard let resources = Bundle.main.resourcePath else { return nil }
        let path = (resources as NSString).appendingPathComponent("esper-server/esper-server")
        return FileManager.default.fileExists(atPath: path) ? path : nil
    }

    /// Dev-mode Python path (venv in project directory).
    var devPythonPath: String {
        (devProjectDir as NSString).appendingPathComponent(".venv/bin/python3")
    }

    /// Dev-mode project directory.
    var devProjectDir: String {
        (NSHomeDirectory() as NSString).appendingPathComponent("Codebase/Fun/Esper")
    }
}
```

- [ ] **Step 2: Simplify ProcessBridge.swift launch method**

Replace the `launch(pythonPath:projectDir:)` method in `EsperApp/EsperApp/ProcessBridge.swift` with:

```swift
    func launch(settings: AppSettings) {
        guard !isRunning else { return }

        let proc = Process()

        if let frozenPath = settings.frozenServerPath {
            // Bundled mode: launch the frozen esper-server binary directly
            proc.executableURL = URL(fileURLWithPath: frozenPath)
            proc.currentDirectoryURL = URL(fileURLWithPath: frozenPath).deletingLastPathComponent()
            proc.arguments = []
            dlog("[Bridge] Launching frozen: \(frozenPath)")
        } else {
            // Dev mode: launch python -m src.server
            let pythonPath = settings.devPythonPath
            let projectDir = settings.devProjectDir
            proc.executableURL = URL(fileURLWithPath: pythonPath)
            proc.currentDirectoryURL = URL(fileURLWithPath: projectDir)
            proc.arguments = ["-m", "src.server"]
            dlog("[Bridge] Launching dev: \(pythonPath) -m src.server, cwd=\(projectDir)")
        }

        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        proc.environment = env
```

Remove from the old `launch` method:
- The venv `PATH` prepending block
- The `PYTHONHOME` / `PYTHONPATH` / `sitePackages` detection block
- The hardcoded `proc.arguments = ["-m", "src.server"]` at line 85

Keep everything after `proc.environment = env` the same (stdin/stdout/stderr pipe setup, termination handler, startReading).

- [ ] **Step 3: Update TranscriptionEngine.swift to pass settings**

In `EsperApp/EsperApp/TranscriptionEngine.swift`, update the `launch()` method. Replace:

```swift
    func launch() {
        NSLog("[Engine] launch() called")
        bridge.launch(
            pythonPath: settings.resolvedPythonPath,
            projectDir: settings.resolvedProjectDir
        )
```

With:

```swift
    func launch() {
        NSLog("[Engine] launch() called")
        bridge.launch(settings: settings)
```

- [ ] **Step 4: Build from Xcode to verify compilation**

Run:
```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj \
    -scheme EsperApp -configuration Debug \
    build 2>&1 | tail -5
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/ProcessBridge.swift \
       EsperApp/EsperApp/Models/AppSettings.swift \
       EsperApp/EsperApp/TranscriptionEngine.swift
git commit -m "refactor: simplify ProcessBridge — frozen binary or dev fallback"
```

---

### Task 4: Rewrite build-dmg.sh

**Files:**
- Rewrite: `scripts/build-dmg.sh`

- [ ] **Step 1: Rewrite the build script**

Replace `scripts/build-dmg.sh` entirely with:

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
ENTITLEMENTS="$PROJECT_DIR/EsperApp/EsperApp/EsperApp.entitlements"

# ── Clean ────────────────────────────────────────────────────────────────────
rm -rf "$BUILD_DIR" "$DIST"
mkdir -p "$DIST"

# ── 1. Freeze Python server with PyInstaller ────────────────────────────────
echo "==> Freezing Python server..."
if [[ ! -d "$PROJECT_DIR/.venv" ]]; then
    echo "ERROR: .venv not found. Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

"$PROJECT_DIR/.venv/bin/pyinstaller" "$PROJECT_DIR/esper-server.spec" \
    --noconfirm \
    --distpath "$BUILD_DIR/frozen" \
    --workpath "$BUILD_DIR/pyinstaller-work"

FROZEN_DIR="$BUILD_DIR/frozen/esper-server"
if [[ ! -f "$FROZEN_DIR/esper-server" ]]; then
    echo "ERROR: Frozen binary not found at $FROZEN_DIR/esper-server"
    exit 1
fi

echo "    Frozen server: $(du -sh "$FROZEN_DIR" | cut -f1)"

# ── 2. Build the Swift app ───────────────────────────────────────────────────
echo "==> Building Swift app..."
xcodebuild -project "$PROJECT_DIR/EsperApp/EsperApp.xcodeproj" \
    -scheme EsperApp \
    -configuration Release \
    -derivedDataPath "$BUILD_DIR/derived" \
    MARKETING_VERSION="$VERSION" \
    CURRENT_PROJECT_VERSION="$(git rev-list --count HEAD)" \
    clean build

BUILT_APP=$(find "$BUILD_DIR/derived" -name "EsperApp.app" -type d | head -1)
if [[ -z "$BUILT_APP" ]]; then
    echo "ERROR: Built .app not found"
    exit 1
fi

# ── 3. Stage the app bundle ─────────────────────────────────────────────────
echo "==> Staging app bundle..."
mkdir -p "$STAGING"
cp -R "$BUILT_APP" "$APP"

# ── 4. Embed frozen server ──────────────────────────────────────────────────
echo "==> Embedding frozen server..."
cp -R "$FROZEN_DIR" "$RESOURCES/esper-server"

# ── 5. Sign the app bundle ──────────────────────────────────────────────────
echo "==> Signing app bundle..."

# Sign all Mach-O files inside the frozen server directory
find "$RESOURCES/esper-server" -type f | while read -r f; do
    file "$f" | grep -q "Mach-O" && codesign --force --sign - "$f"
done

# Sign the app bundle with entitlements (must be last)
codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP"

# ── 6. Verify bundle ────────────────────────────────────────────────────────
echo "==> Verifying bundle..."
# Check frozen binary exists and is signed
codesign --verify "$RESOURCES/esper-server/esper-server" || { echo "ERROR: Frozen binary signature invalid"; exit 1; }
codesign --verify "$APP" || { echo "ERROR: App signature invalid"; exit 1; }
# Check entitlements
codesign -d --entitlements - "$APP" 2>&1 | grep -q "audio-input" || { echo "ERROR: Audio entitlement missing"; exit 1; }
# Check no torch snuck in
if find "$RESOURCES" -name "torch" -type d 2>/dev/null | grep -q .; then
    echo "WARNING: torch found in bundle — check PyInstaller excludes"
fi
echo "    All checks passed."

# ── 7. Create DMG ───────────────────────────────────────────────────────────
DMG_NAME="Esper-${VERSION}-arm64.dmg"
echo "==> Creating $DMG_NAME..."
hdiutil create \
    -volname "Esper" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DIST/$DMG_NAME"

# ── 8. Checksum ─────────────────────────────────────────────────────────────
shasum -a 256 "$DIST/$DMG_NAME" > "$DIST/$DMG_NAME.sha256"

# ── Done ─────────────────────────────────────────────────────────────────────
SIZE=$(du -sh "$DIST/$DMG_NAME" | cut -f1)
echo ""
echo "==> Done!"
echo "    DMG:  $DIST/$DMG_NAME ($SIZE)"
echo "    SHA:  $(cat "$DIST/$DMG_NAME.sha256")"
```

- [ ] **Step 2: Verify the script is executable**

Run:
```bash
chmod +x scripts/build-dmg.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build-dmg.sh
git commit -m "rewrite: build-dmg.sh — PyInstaller replaces manual dylib embedding"
```

---

### Task 5: Update CI Release Workflow

**Files:**
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Update release.yml**

Replace `.github/workflows/release.yml` with:

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

      - name: Select Xcode
        run: |
          sudo xcode-select -s /Applications/Xcode_16.2.app || sudo xcode-select -s /Applications/Xcode_16.1.app || sudo xcode-select -s /Applications/Xcode_16.0.app || sudo xcode-select -s /Applications/Xcode.app
          xcodebuild -version

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Create venv and install dependencies
        run: |
          python -m venv .venv
          .venv/bin/pip install -r requirements.txt -r requirements-build.txt pytest huggingface_hub

      - name: Run tests
        run: .venv/bin/python -m pytest tests/ -v

      - name: Download Whisper model
        run: |
          .venv/bin/python -c "
          from huggingface_hub import snapshot_download
          snapshot_download('mlx-community/whisper-large-v3-turbo', local_dir='models/whisper')
          "

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
          {
            echo "changes<<EOF"
            echo "$CHANGES"
            echo "EOF"
          } >> "$GITHUB_OUTPUT"

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
git add .github/workflows/release.yml requirements-build.txt
git commit -m "ci: update release workflow to use PyInstaller frozen build"
```

---

### Task 6: Local End-to-End Test

**Files:** None (validation only)

- [ ] **Step 1: Full local build**

Run:
```bash
./scripts/build-dmg.sh --version 2.2.0-test
```

Expected: Script completes with `==> Done!`, all verification checks pass, DMG created in `dist/`.

- [ ] **Step 2: Install and test**

```bash
# Kill existing Esper
pkill -f EsperApp 2>/dev/null || true
sleep 1

# Mount DMG and install
hdiutil attach dist/Esper-2.2.0-test-arm64.dmg
cp -R /Volumes/Esper/Esper.app /Applications/Esper.app
hdiutil detach /Volumes/Esper

# Remove quarantine
xattr -cr /Applications/Esper.app

# Reset TCC so permission dialog appears
tccutil reset Microphone com.esper.app

# Launch
open /Applications/Esper.app
```

- [ ] **Step 3: Verify functionality**

Wait for app to launch, then check:

```bash
sleep 5
cat /tmp/esper-bridge.log | head -20
```

Expected:
- Log shows `Launching frozen:` (not dev mode)
- Server starts successfully
- Devices are listed
- No `Library not loaded` errors
- No `ImportError` in Python logs

- [ ] **Step 4: Test audio capture**

Click "Start Listening" in the app. Check:

```bash
sleep 10
grep '"energy"' /tmp/esper-bridge.log | tail -5
```

Expected: Energy values > 0.0 (e.g., `{"level": 0.03...}`).

- [ ] **Step 5: Verify no torch in bundle**

```bash
find /Applications/Esper.app -name "torch" -type d
```

Expected: No output (torch excluded by PyInstaller spec).

- [ ] **Step 6: Check bundle size**

```bash
du -sh /Applications/Esper.app
du -sh dist/Esper-2.2.0-test-arm64.dmg
```

Expected: App < 2GB, DMG < 1.5GB (most of the size is the Whisper model).

- [ ] **Step 7: Clean up test build**

```bash
rm -rf build/frozen build/derived build/staging dist/Esper-2.2.0-test-*
```

- [ ] **Step 8: Commit all changes and push**

```bash
git add -A
git status  # verify no secrets or large files
git commit -m "feat: PyInstaller build pipeline — replaces manual Python embedding"
git push origin main
```

---

### Task 7: Tag Release

**Files:** None

- [ ] **Step 1: Tag and push**

```bash
git tag v2.2.0
git push origin v2.2.0
```

Expected: GitHub Actions release workflow triggers, builds DMG with PyInstaller, creates GitHub Release.

- [ ] **Step 2: Monitor CI**

Check `https://github.com/YashD5291/Esper/actions` — workflow should complete successfully.

- [ ] **Step 3: Download and verify release DMG**

Download the DMG from the GitHub Release page and repeat the install/test from Task 6 Steps 2-5.
