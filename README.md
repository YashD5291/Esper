<p align="center">
  <img src="docs/assets/app-icon.png" width="128" height="128" alt="Esper icon">
</p>

<h1 align="center">Esper</h1>

<p align="center">
  <strong>Real-time voice transcription for macOS</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS%2014%2B-blue?style=flat-square" alt="macOS 14+">
  <img src="https://img.shields.io/badge/chip-Apple%20Silicon-black?style=flat-square&logo=apple" alt="Apple Silicon">
  <img src="https://img.shields.io/badge/model-Whisper%20large--v3--turbo-green?style=flat-square" alt="Whisper">
  <img src="https://img.shields.io/badge/inference-MLX%20Metal-orange?style=flat-square" alt="MLX">
  <img src="https://img.shields.io/badge/tests-158%20passing-brightgreen?style=flat-square" alt="Tests">
</p>

<p align="center">
  Captures microphone audio, detects speech with Silero VAD, transcribes with Whisper large-v3-turbo via MLX, and optionally streams text to Telegram. Runs entirely on-device. No cloud. No internet.
</p>

---

## Install

1. Download [**Esper.dmg**](https://github.com/YashD5291/Esper/releases/latest) from the latest release
2. Open the DMG and drag **Esper** to **Applications**
3. Open Esper from Applications or Launchpad

**Requirements:** macOS 14+ (Sonoma), Apple Silicon (M1/M2/M3/M4)

---

## Developer Setup

### CLI

```bash
# 1. Set up environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Run
python -m src.realtime_demo
```

Select your mic from the device picker, speak, see transcriptions.

### SwiftUI App (from source)

Open `EsperApp/EsperApp.xcodeproj` in Xcode and hit Cmd+R.

---

## Global Hotkey

Press **Option+Space** from any app to toggle transcription on/off. No need to switch to the Esper window.

Customize the shortcut in **Settings > Shortcuts**.

---

## How It Works

```
  Microphone
      |  16kHz mono, 512-sample frames
      v
  AudioCapture ──> audio_q ──> VadThread (Silero VAD)
                                    |
                                    | speech detected, silence sealed
                                    v
                                speech_q ──> WhisperTranscriber
                                                 |
                                                 | spawn-context subprocess
                                                 | (MLX Metal isolation)
                                                 v
                                            mlx-whisper
                                            large-v3-turbo
                                                 |
                                                 v
                                        TranscriptionUpdate
                                            |           |
                                            v           v
                                        Console    Telegram
                                        (CLI)      (optional)
```

### Pipeline

| Stage | What it does |
|-------|-------------|
| **AudioCapture** | Continuous mic input via sounddevice (16kHz mono, 32ms frames) |
| **VadThread** | Silero VAD scores each frame. 300ms pre-buffer on speech onset. 300ms silence seals utterance. |
| **WhisperTranscriber** | Whisper large-v3-turbo in isolated subprocess (MLX Metal safety). 15s watchdog. Auto-restart on crash. |
| **Hallucination filter** | Discards high `no_speech_prob` or extreme `compression_ratio` outputs |
| **Output** | Per-utterance text to console, SwiftUI transcript view, and/or Telegram |

---

## Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | macOS 14+ (Sonoma or later) |
| **Chip** | Apple Silicon (M1/M2/M3/M4) |
| **Python** | 3.11+ via [pyenv](https://github.com/pyenv/pyenv) |
| **Xcode** | 15+ (SwiftUI app only) |

---

## CLI Usage

```bash
python -m src.realtime_demo                    # Interactive device picker
python -m src.realtime_demo --device 0         # Specific mic
python -m src.realtime_demo --list-devices     # Show audio devices
python -m src.realtime_demo --telegram         # Send to Telegram
python -m src.realtime_demo --record           # Save speech audio to WAV
```

### Telegram Setup

Copy the example config and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your bot token and chat ID from [@BotFather](https://t.me/BotFather):

```env
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

Run with `--telegram`, or configure in the SwiftUI app settings.

**Reliability:** Messages retry up to 3x with exponential backoff. Rate limits (429) are respected automatically. Non-retryable errors (401/403) fail immediately. Messages over 4096 chars are truncated.

---

## SwiftUI App

Menu bar app with waveform icon. Click to start/stop listening.

| Feature | Description |
|---------|-------------|
| **Device picker** | Dropdown with refresh button for Bluetooth hot-connect |
| **Audio level meter** | Real-time RMS visualization |
| **Transcript view** | Scrolling per-utterance transcript |
| **Telegram** | Configure bot token + chat ID in settings |
| **Auto-restart** | Python process auto-restarts on crash (up to 3x) |
| **Mic permission** | Prompts for microphone access with clear error if denied |
| **Command timeout** | 30s watchdog — auto-restarts if Python becomes unresponsive |
| **Floating overlay** | Always-on-top transcription text over any window (configurable) |
| **Auto-updates** | Sparkle 2 — checks every 24h, EdDSA-verified, installs and relaunches automatically |

### Auto-Updates

| Feature | Details |
|---------|---------|
| **Framework** | Sparkle 2 |
| **Check interval** | Every 24 hours (configurable in Settings) |
| **Manual check** | Menu bar > "Check for Updates..." or Settings > Updates |
| **Verification** | EdDSA signature verification |
| **Install** | Downloads, verifies, replaces, relaunches automatically |

### Floating Overlay

A transparent floating panel that shows live transcription text on top of all windows — no need to switch to the app to verify what was said.

**Enable:** Settings → Overlay → toggle ON, or click "Show Overlay" in the menu bar.

| Setting | Options |
|---------|---------|
| **Placement** | Draggable (drag anywhere) or Fixed (6 preset positions) |
| **Text Size** | Small / Medium / Large |
| **Text Color** | 5 presets + custom color picker |
| **Lines** | 1–9 visible lines |
| **Opacity** | 30–100% |

The overlay is click-through in fixed mode — clicks pass to windows below. In draggable mode, grab and reposition it anywhere on screen. Position is remembered between sessions.

**IPC:** SwiftUI spawns `python -m src.server` as a subprocess. Commands go over stdin, events come back over stdout -- both as newline-delimited JSON (protocol v1). Thread-safe with NSLock, bounded event buffer (200), zombie process cleanup with SIGKILL fallback.

---

## Model

| | |
|---|---|
| **Model** | Whisper large-v3-turbo |
| **Source** | `mlx-community/whisper-large-v3-turbo` |
| **Params** | 809M |
| **Format** | MLX (Metal-optimized) |
| **Size** | ~1.5GB |
| **Location** | `models/whisper/` (local, gitignored) |
| **Inference** | ~1-2s per utterance (M1 Max) |
| **Model load** | ~2-3s (warm) |
| **Compute** | Apple Silicon GPU via Metal |

No internet required at runtime. Model ships with the project.

---

## Configuration

All tunables live in `src/config.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `VAD_SPEECH_THRESHOLD` | 0.3 | Silero speech probability threshold |
| `VAD_SILENCE_THRESHOLD_MS` | 300 | Silence duration to seal utterance |
| `VAD_MIN_SPEECH_DURATION_MS` | 100 | Minimum utterance length |
| `VAD_MIN_ENERGY` | 0.003 | RMS floor for quiet speech |
| `WHISPER_LANGUAGE` | en | Transcription language |
| `WHISPER_SUBPROCESS_TIMEOUT_S` | 15.0 | Inference watchdog timeout |
| `WHISPER_NO_SPEECH_THRESHOLD` | 0.8 | Hallucination filter sensitivity |

---

## Project Structure

```
src/
  config.py                All tunables (single source of truth)
  audio_capture.py         Mic input via sounddevice
  vad.py                   Silero VAD thread (speech gating)
  transcriber.py           WhisperTranscriber + subprocess management
  whisper_worker.py        Whisper inference subprocess (MLX)
  telegram_sender.py       Per-utterance Telegram sender with 429 retry
  server.py                JSON-line server for SwiftUI app
  realtime_demo.py         CLI entry point

EsperApp/
  EsperApp/
    EsperApp.swift               App entry (MenuBarExtra + WindowGroup + OverlayController)
    ProcessBridge.swift          Python subprocess management (NSLock, bounded stream)
    TranscriptionEngine.swift    @Observable state + event consumption + watchdog
    TranscriptPanel.swift        Floating NSPanel (vibrancy, click-through, draggable)
    GlobalHotkey.swift           KeyboardShortcuts name definition (Option+Space default)
    Helpers/
      KeychainHelper.swift       Keychain read/write (for future use with Developer ID)
    Models/
      Protocol.swift             Event types + JSON parsing (protocol v1)
      AppSettings.swift          @AppStorage preferences (Telegram + Overlay + dev paths)
      OverlayPosition.swift      6-position enum with screen coordinate math
    Views/
      MainWindowView.swift       Primary window
      MenuBarView.swift          Menu bar controls (incl. overlay toggle)
      TranscriptView.swift       Scrolling transcript
      TranscriptOverlayView.swift  Floating overlay SwiftUI content + OverlayViewModel
      AudioLevelMeter.swift      Real-time audio meter
      StatusBadge.swift          Status indicator
      SettingsView.swift         App settings (6 tabs, sidebar navigation)
      ShortcutsTab.swift         Global hotkey configuration (KeyboardShortcuts.Recorder)
      OverlaySettingsTab.swift   Overlay config (position, appearance, preview)
  EsperAppTests/
    ProtocolTests.swift          25 XCTests for JSON event parsing
    OverlayPositionTests.swift   8 XCTests for position coordinate math
    AppSettingsOverlayTests.swift  6 XCTests for overlay settings defaults

models/
  silero_vad.onnx           Silero VAD model (2.2MB, tracked in git)
  whisper/                  Whisper large-v3-turbo (1.5GB, gitignored)

tests/                      119 Python tests
  test_config.py            Configuration constants + validation
  test_server_ipc.py        IPC protocol (--protocol-fd)
  test_server_commands.py   Server command handlers
  test_vad.py               VAD state machine
  test_vad_model.py         Silero ONNX wrapper
  test_audio_capture.py     Microphone capture + queue
  test_whisper_transcriber.py  Whisper subprocess lifecycle
  test_whisper_worker.py    Pipe protocol (JSON + numpy framing)
  test_telegram_sender.py   Telegram retry/truncation/validation
  test_integration.py       Full pipeline (VAD -> Whisper -> Telegram)
  test_cleanup.py           Dead code assertions
  test_frozen_paths.py      PyInstaller path resolution
```

---

## License

[MIT License](LICENSE) -- Copyright (c) 2025 Yash Desai
