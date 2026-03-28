# PyInstaller Build Pipeline Design

**Date:** 2026-03-28
**Status:** Approved
**Goal:** Replace fragile manual Python embedding with PyInstaller-frozen executable

## Problem

The current build pipeline manually embeds Python into the macOS .app bundle: copying binaries, rewriting dylib paths with `install_name_tool`, re-signing Mach-O files, cleaning broken symlinks, and removing transitive dependencies. This has caused 8 build-fix commits in the last 15 — every macOS update, CI runner change, or Python version shift breaks the build.

Specific recurring failures:
- Framework-style dylib names (`Python` vs `*.dylib`) missed by globs
- `install_name_tool` invalidating code signatures in wrong order
- Broken symlinks from Python stdlib copy
- Transitive torch dependency sneaking into bundle
- CI runner Python layout diverging from local dev machine

## Solution

Freeze the Python server into a standalone executable using PyInstaller. The Swift app launches this single binary instead of spawning `python3 -m src.server` with environment variable gymnastics.

### Architecture

```
Current:
  Swift App → Process(python3) + PYTHONHOME + PYTHONPATH + venv PATH
    └── 50+ lines of dylib rebinding, signing, symlink cleanup

New:
  Swift App → Process(esper-server)
    └── Self-contained frozen binary. One codesign call.
```

## Components

### 1. PyInstaller Spec (`esper-server.spec`)

- **Entry point:** `src/server.py`
- **Mode:** `--onedir` (faster startup, easier debugging than `--onefile`)
- **Bundled data:**
  - `models/silero_vad.onnx` → `models/`
  - `models/whisper/` → `models/whisper/`
- **Hidden imports:** All `src.*` modules (audio_capture, vad, vad_model, transcriber, whisper_worker, telegram_sender, config)
- **Excludes:** torch, torchaudio, tensorflow, pytest (prevent transitive bloat)
- **Output:** `dist/esper-server/` directory

### 2. Server-Side Model Path Detection (`src/server.py`, `src/config.py`)

Detect frozen mode and resolve model paths accordingly:

```python
# In config.py
import sys
if getattr(sys, '_MEIPASS', None):
    _PROJECT_ROOT = Path(sys._MEIPASS)
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
```

This makes `VAD_MODEL_PATH` and any Whisper model path resolve correctly in both frozen and dev modes.

### 3. ProcessBridge.swift Changes

Simplify `launch()`:

```
1. Check Bundle.main.resourcePath + "/esper-server/esper-server"
2. If exists → launch it directly (bundled mode)
3. If not → fall back to .venv/bin/python3 -m src.server (dev mode)
```

Remove:
- PYTHONHOME / PYTHONPATH environment setup
- venv bin PATH prepending
- Bundle site-packages detection

The frozen binary needs no environment variables — PyInstaller handles all path resolution internally.

### 4. AppSettings.swift Changes

Remove `resolvedPythonPath` and `resolvedProjectDir` computed properties. Replace with a single `serverExecutablePath` that returns the frozen binary path or nil (triggering dev fallback).

### 5. Build Script (`scripts/build-dmg.sh`)

New flow:

```bash
# 1. Freeze Python server
pyinstaller esper-server.spec --distpath build/frozen --noconfirm

# 2. Build Swift app
xcodebuild -project EsperApp/EsperApp.xcodeproj \
    -scheme EsperApp -configuration Release ...

# 3. Stage app bundle
cp -R "$BUILT_APP" "$STAGING/Esper.app"

# 4. Embed frozen server + models
cp -R build/frozen/esper-server "$RESOURCES/esper-server"

# 5. Sign everything once
codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP"

# 6. Create DMG
hdiutil create -volname "Esper" -srcfolder "$STAGING" ...
```

**Eliminated:** otool, install_name_tool, dylib loops, symlink cleanup, stdlib copy, site-packages copy, torch removal, multi-pass signing.

### 6. CI Changes (`release.yml`)

```yaml
- name: Install build tools
  run: .venv/bin/pip install pyinstaller

- name: Freeze Python server
  run: .venv/bin/pyinstaller esper-server.spec --noconfirm
```

No changes to `ci.yml` — tests run against source, not the frozen build.

## Dev Mode

No disruption to development workflow:
- Developers run from Xcode as before
- Swift app detects no `esper-server` in Resources → uses `.venv/bin/python3 -m src.server`
- All existing dev tooling (pytest, direct Python execution) unchanged

## What This Eliminates

| Removed | Why It Existed |
|---------|---------------|
| `otool -L` dylib discovery | PyInstaller does this internally |
| `install_name_tool` path rewriting | PyInstaller handles loader paths |
| Per-file `codesign` loops | Single app-level sign suffices |
| PYTHONHOME / PYTHONPATH env vars | Frozen binary has no external deps |
| Python stdlib copy | Bundled inside frozen executable |
| site-packages copy + torch removal | PyInstaller includes only what's imported |
| Broken symlink cleanup | No symlinks to break |
| `*.dylib` glob matching | No globs needed |
| `nullglob` workarounds | No globs needed |

## Success Criteria

1. `build-dmg.sh` has zero `otool`, `install_name_tool`, or dylib-related code
2. DMG installs and runs on a clean macOS 14+ machine (after `xattr -cr`)
3. Audio capture works (energy > 0.0) when launched from Launchpad
4. Transcription produces output when speaking
5. Build succeeds on GitHub Actions without signing workarounds
6. No torch/torchaudio in final bundle
