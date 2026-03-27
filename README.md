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
  <img src="https://img.shields.io/badge/tests-71%20passing-brightgreen?style=flat-square" alt="Tests">
</p>

<p align="center">
  Captures microphone audio, detects speech with Silero VAD, transcribes with Whisper large-v3-turbo via MLX, and optionally streams text to Telegram. Runs entirely on-device. No cloud. No internet.
</p>

---

## Quick Start

### CLI

```bash
# 1. Set up environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Run
python -m src.realtime_demo
```

Select your mic from the device picker, speak, see transcriptions.

### SwiftUI App

```bash
# Build and install
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Release build
cp -R build/Release/EsperApp.app /Applications/
```

Or open `EsperApp/EsperApp.xcodeproj` in Xcode and hit Cmd+R.

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

Create `.env` in the project root:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

Run with `--telegram`, or configure in the SwiftUI app settings.

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

**IPC:** SwiftUI spawns `python -m src.server` as a subprocess. Commands go over stdin, events come back over stdout -- both as newline-delimited JSON.

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
    EsperApp.swift               App entry (MenuBarExtra + WindowGroup)
    ProcessBridge.swift          Python subprocess management
    TranscriptionEngine.swift    @Observable state + event consumption
    Models/
      Protocol.swift             Event types + JSON parsing
      AppSettings.swift          @AppStorage preferences
    Views/
      MainWindowView.swift       Primary window
      MenuBarView.swift          Menu bar controls
      TranscriptView.swift       Scrolling transcript
      AudioLevelMeter.swift      Real-time audio meter
      StatusBadge.swift          Status indicator
      SettingsView.swift         App settings

models/
  whisper/                  Whisper large-v3-turbo (local, gitignored)

tests/                      71 tests (config, IPC, VAD, transcriber, cleanup)
```

---

## License

Private project.
