# Esper

Voice-to-Telegram relay for macOS. Captures microphone audio, transcribes it in real time using Parakeet TDT v3, and optionally sends the text to Telegram. Ships as both a CLI tool and a native SwiftUI menu bar app.

## Architecture

```
┌──────────────────────────────────┐
│     SwiftUI App (EsperApp/)      │
│                                  │
│  MenuBarExtra ◄── quick controls │
│  WindowGroup  ◄── full UI       │
│       │                          │
│  TranscriptionEngine             │
│       │                          │
│  ProcessBridge                   │
│    stdin ──JSON──► Python        │
│    stdout ◄─JSON── Python        │
└──────────────────────────────────┘
            ▲            │
            │            ▼
┌──────────────────────────────────┐
│   python -m src.server           │
│   (or python -m src.realtime_demo│
│    for standalone CLI)           │
│                                  │
│   AudioCapture → Transcriber     │
│        → TelegramSender          │
└──────────────────────────────────┘
            ▲
            │ 16kHz mono float32
            │
        Microphone
```

### Transcription Pipeline

```
  Microphone
      │
      │ 16kHz mono float32, 100ms chunks
      v
 +-----------+     sounddevice.InputStream callback
 |  Audio    |     Drops old chunks if queue full (~30s buffer)
 |  Capture  |     Auto-selects real mic (skips Loopback)
 +-----------+
      │
      │ np.ndarray chunks via thread-safe queue
      v
 +-----------+
 |Transcriber|─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
 | (daemon   |                                       |
 |  thread)  |    CoreML engine       MLX engine     |
 +-----------+    (default)           (--engine mlx) |
      |               |                    |         |
      |          ┌────┴────┐        ┌──────┴──────┐  |
      |          | Buffer  |        |  parakeet   |  |
      |          | ~5s of  |        |   -mlx      |  |
      |          | audio   |        | streaming   |  |
      |          └────┬────┘        |  context    |  |
      |               |             └──────┬──────┘  |
      |               v                    |         |
      |     ┌─────────────────┐            |         |
      |     |   MelEncoder    |  ← ANE    |         |
      |     | (fused mel +    |            |         |
      |     |  FastConformer) |            |         |
      |     └────────┬────────┘            |         |
      |              |                     |         |
      |              v                     |         |
      |     ┌─────────────────┐            |         |
      |     |   TDT Greedy    |            |         |
      |     |   Decode Loop   |            |         |
      |     |  Decoder (LSTM) |            |         |
      |     |  Joint Decision |            |         |
      |     └────────┬────────┘            |         |
      |              |                     |         |
      |              v                     |         |
      |     ┌─────────────────┐            |         |
      |     | Vocab Lookup    |            |         |
      |     | (8192 tokens,   |            |         |
      |     |  SentencePiece) |            |         |
      |     └────────┬────────┘            |         |
      |              |                     |         |
      └──────────────┴─────────────────────┘         |
      |                                    ─ ─ ─ ─ ─┘
      │ TranscriptionUpdate
      │ (finalized_text, draft_text, sentences)
      v
 ┌──────────┐     ┌──────────┐
 │ Console  │     │ Telegram │
 │ Renderer │     │ Sender   │ ← optional, background thread
 └──────────┘     └──────────┘
```

## Quick Start

### Prerequisites

- macOS 14+ (Sonoma or later)
- Python 3.11 (via pyenv recommended — avoid 3.11.14 which is missing `_lzma`)
- `ffmpeg` (install via `brew install ffmpeg`)
- Xcode 15+ (only needed to build the SwiftUI app)

### CLI Setup

```bash
# Create venv and install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Download CoreML models (~200MB)
python -c "from huggingface_hub import snapshot_download; snapshot_download('FluidInference/parakeet-tdt-0.6b-v3-coreml', local_dir='models/coreml')"
```

### CLI Usage

```bash
python -m src.realtime_demo                    # CoreML on ANE (default)
python -m src.realtime_demo --engine mlx       # MLX on GPU
python -m src.realtime_demo --list-devices     # Show audio devices
python -m src.realtime_demo --device 0         # Pick specific mic
python -m src.realtime_demo --telegram         # Send transcriptions to Telegram
python -m src.realtime_demo --record           # Save session audio to WAV
python -m src.realtime_demo --buffer 3.0       # CoreML: shorter buffer (faster, less context)
```

### Telegram Setup

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_CHAT_ID=your-chat-id-here
```

Then run with `--telegram` flag.

### SwiftUI App

```bash
# Build from command line
cd EsperApp
xcodebuild -project EsperApp.xcodeproj -scheme EsperApp -configuration Debug build

# Or open in Xcode and hit Cmd+R
open EsperApp/EsperApp.xcodeproj
```

The app runs as a **menu bar icon** (waveform circle). Click it for:
- Start/Stop listening
- Input device picker
- Open the main window (transcript view, audio level meter, settings)

The app automatically finds the Python venv at `.venv/bin/python` and launches `python -m src.server` as a subprocess. Settings (engine, buffer size, Telegram config, paths) are configurable from the main window.

## Performance

| Metric | CoreML (ANE) | MLX (GPU) |
|--------|-------------|-----------|
| Model load | 0.24s | ~4s |
| 5s audio inference | ~82-98ms | ~400ms |
| Realtime factor | ~57x | ~12x |

## Engines

**CoreML** (default) — Runs on Apple Neural Engine. Three compiled models (`MelEncoder`, `Decoder`, `JointDecision`) process audio in fixed-size chunks with 1s overlap and word-level deduplication at boundaries. Fastest inference.

**MLX** — Runs on GPU via Metal. Uses `parakeet-mlx`'s native streaming API with true incremental transcription. The model handles segmentation and finalization internally. Slower but produces more natural sentence boundaries.

## Project Structure

```
src/
  audio_capture.py         Mic input via sounddevice (16kHz mono)
  transcriber.py           MLX streaming transcriber + TranscriptionUpdate dataclass
  coreml_transcriber.py    CoreML transcriber with TDT greedy decoding
  telegram_sender.py       Background Telegram sender with retry logic
  realtime_demo.py         CLI entry point (--engine, --telegram, --record)
  server.py                Headless JSON server for SwiftUI app

EsperApp/
  EsperApp.xcodeproj/      Xcode project (macOS 14+, no sandbox)
  EsperApp/
    EsperApp.swift          App entry — MenuBarExtra + WindowGroup
    ProcessBridge.swift     Spawns Python subprocess, JSON-line protocol
    TranscriptionEngine.swift  @Observable state management
    Models/
      Protocol.swift        Codable command/event types
      AppSettings.swift     @AppStorage-backed preferences
    Views/
      MenuBarView.swift     Menu bar dropdown controls
      MainWindowView.swift  Primary window layout
      TranscriptView.swift  Scrolling transcript display
      AudioLevelMeter.swift RMS audio level bar
      SettingsSection.swift Collapsible settings form
      StatusBadge.swift     Colored status dot

models/
  coreml/                  CoreML model files (.mlmodelc)

scripts/
  inspect_coreml.py        One-time model tensor inspection

recordings/                Session audio recordings (--record flag)
```

## JSON Protocol (Swift <-> Python)

The SwiftUI app communicates with `src/server.py` via newline-delimited JSON over stdin/stdout.

### Commands (Swift -> Python)

| Command | Data | Effect |
|---------|------|--------|
| `list_devices` | — | Returns available audio input devices |
| `start` | `{engine, device?, buffer?, telegram?}` | Load model, start capture + transcription |
| `stop` | — | Shut down capture + transcriber |
| `set_device` | `{device: int}` | Hot-swap audio input device |

### Events (Python -> Swift)

| Event | Data | When |
|-------|------|------|
| `devices` | `[{index, name, channels, is_default}]` | After `list_devices` |
| `status` | `"idle" / "loading_model" / "listening"` | State changes |
| `transcript` | `{finalized_text, draft_text, finalized_sentences}` | Each transcription update |
| `energy` | `{level: 0.0-1.0}` | ~10 Hz while listening |
| `error` | `{message}` | On any error |
