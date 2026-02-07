# Esper — Real-Time Voice-to-Telegram Relay

## Project Overview

**Esper** is a desktop application (Python) that captures microphone input in real-time, transcribes it using NVIDIA Parakeet TDT v3, and sends the transcribed text to a Telegram chat. The app is used as a communication relay — the user (Y) speaks, and a proxy person (B) receives the transcribed messages on Telegram in near real-time to relay to person (A) during an online meeting.

The name "Esper" reflects the app's purpose — like telepathy, your words reach the other person instantly, without you being in the room.

## Target Machine

- **Hardware**: Mac Pro, M1 Max, 64GB RAM, 4TB SSD, 24 CPU cores, 10 GPU cores
- **OS**: macOS
- **Python**: 3.10+ (use conda or pyenv)
- **Note**: No CUDA GPU — use Apple Silicon optimizations (MLX, CoreML, or CPU with ONNX)

## Tech Stack

- **STT Engine**: NVIDIA Parakeet TDT 0.6B v3 (via NeMo or ONNX runtime)
- **Audio Capture**: `sounddevice` or `pyaudio` (16kHz mono)
- **Messaging**: Telegram Bot API (`python-telegram-bot` or raw HTTP)
- **GUI**: Tkinter (lightweight, built-in) — upgrade to PyQt6 later if needed
- **Packaging**: PyInstaller (for distributable .app later)

---

## Phase 1: Accent Validation & STT Proof of Concept

**Goal**: Confirm Parakeet v3 transcribes Indian English accent accurately on this Mac before building the full app.

### Tasks

1. **Set up Python environment**
   ```bash
   conda create -n esper python=3.10
   conda activate esper
   ```

2. **Install Parakeet v3 via NVIDIA NeMo**
   ```bash
   pip install nemo_toolkit[asr]
   ```
   If NeMo has issues on Apple Silicon, fall back to:
   - `parakeet-mlx` (MLX-optimized for Apple Silicon) — check https://github.com/search for parakeet-mlx
   - ONNX Runtime with the ONNX-converted Parakeet model

3. **Write a simple test script** (`test_stt.py`):
   - Record 10 seconds of audio from the microphone using `sounddevice`
   - Save as a 16kHz mono WAV file
   - Load Parakeet v3 model and transcribe the WAV file
   - Print the transcription to console
   - Test with various Indian English phrases, technical terms, and fast speech

4. **Benchmark accuracy**:
   - Transcribe 10 different sentences spoken in Indian English accent
   - Compare output to what was actually said
   - Log Word Error Rate informally (manual check is fine)
   - Test with: normal pace, fast pace, technical jargon, numbers, and names

### Success Criteria
- Parakeet v3 model loads and runs on M1 Max
- Transcription accuracy is subjectively good (>90% of words correct)
- Transcription latency per 5-second chunk is under 1 second

### Deliverables
- `test_stt.py` — records and transcribes a single audio clip
- Console output showing transcription results
- A short accuracy report (just print to console)

---

## Phase 2: Real-Time Streaming Transcription

**Goal**: Capture audio continuously from the mic and transcribe in near real-time using a chunked/streaming approach.

### Tasks

1. **Implement continuous audio capture** (`audio_capture.py`):
   - Use `sounddevice.InputStream` to capture mic audio in a callback
   - Buffer audio in a thread-safe queue
   - Audio format: 16kHz, mono, float32 or int16

2. **Implement Voice Activity Detection (VAD)**:
   - Use `webrtcvad` or simple energy-based detection
   - Detect when the user starts speaking and stops speaking
   - Configurable silence threshold (e.g., 1.0 - 3.0 seconds)

3. **Implement chunked transcription** (`transcriber.py`):
   - Run transcription in a separate thread/process
   - When VAD detects end-of-speech (silence), send the audio chunk to Parakeet
   - Return transcribed text via a callback or queue
   - Support configurable chunking modes:
     - **Silence-based**: Send after N seconds of silence (default: 1.5s)
     - **Time-based**: Send every N seconds regardless (e.g., every 3s)
     - **Word-count**: Send after N words detected (requires interim results)

4. **Console demo** (`realtime_demo.py`):
   - Continuously listen to mic
   - Print transcribed chunks to console as they're detected
   - Show "[Listening...]", "[Processing...]", "[Sent]: <text>" status indicators

### Success Criteria
- Audio is captured without dropouts or lag
- Transcription happens within 1-2 seconds of finishing a phrase
- Silence detection correctly segments speech into logical chunks
- No memory leaks during extended (10+ minute) sessions

### Deliverables
- `audio_capture.py` — continuous mic capture with VAD
- `transcriber.py` — chunked transcription engine
- `realtime_demo.py` — console app showing real-time transcription

---

## Phase 3: Telegram Integration

**Goal**: Send transcribed messages to a Telegram chat in real-time.

### Tasks

1. **Create Telegram Bot**:
   - User creates a bot via @BotFather on Telegram
   - Save the bot token in a `.env` file or config
   - Get the target chat ID (the chat with proxy person B)

2. **Implement Telegram sender** (`telegram_sender.py`):
   - Use `python-telegram-bot` library or raw `httpx`/`requests` for simplicity
   - Async message sending (don't block the transcription pipeline)
   - Queue-based: messages go into a send queue, a separate thread sends them
   - Handle rate limits (Telegram allows ~30 msgs/sec to same chat)
   - Optional: edit last message instead of sending new one (for partial results)

3. **Wire everything together** (`main.py`):
   - Audio capture → VAD → Transcription → Telegram send
   - Pipeline architecture with queues between each stage
   - Clean shutdown on Ctrl+C

4. **Configuration** (`config.yaml` or `config.json`):
   ```yaml
   telegram:
     bot_token: "YOUR_BOT_TOKEN"
     chat_id: "YOUR_CHAT_ID"
   
   chunking:
     mode: "silence"  # silence | time | word_count
     silence_timeout: 1.5  # seconds
     time_interval: 3.0  # seconds (if mode=time)
     min_words: 3  # minimum words before sending
   
   audio:
     sample_rate: 16000
     device: null  # null = default mic
   ```

### Success Criteria
- Messages appear on Telegram within 2-3 seconds of speaking
- No messages are dropped
- Bot handles network interruptions gracefully
- Config file controls all behavior without code changes

### Deliverables
- `telegram_sender.py` — async Telegram message sender
- `main.py` — complete pipeline (mic → STT → Telegram)
- `config.yaml` — user-configurable settings
- `setup_telegram.md` — instructions for creating the bot and getting chat_id

---

## Phase 4: GUI Application

**Goal**: Add a desktop GUI so the user can control the app without the terminal.

### Tasks

1. **Build Tkinter GUI** (`app.py`):
   - **Start/Stop button** — toggle listening on/off
   - **Status indicator** — shows "Idle", "Listening", "Processing", "Sent"
   - **Live transcript view** — scrolling text area showing what was transcribed
   - **Message log** — shows what was sent to Telegram with timestamps
   - **Settings panel**:
     - Chunking mode selector (silence / time / word_count)
     - Silence timeout slider (0.5s - 5.0s)
     - Minimum words before sending (1 - 20)
     - Telegram bot token and chat ID fields
     - Mic device selector (dropdown of available mics)
   - **Manual send button** — type and send a message manually as fallback
   - **Hotkey support** — global hotkey to toggle listening (e.g., Cmd+Shift+L)

2. **System tray / menu bar** (optional but nice):
   - App runs in macOS menu bar
   - Quick toggle on/off
   - Shows last sent message as tooltip

3. **Audio level meter**:
   - Visual indicator showing mic input level
   - Helps user confirm mic is working and picking up voice

### Success Criteria
- App launches with a clean, functional GUI
- All settings are configurable from the GUI
- Settings persist between app launches (save to config file)
- App doesn't freeze during transcription (proper threading)

### Deliverables
- `app.py` — main GUI application
- All settings saveable/loadable from `config.yaml`
- App icon and window title set properly

---

## Phase 5: Polish & Optimization

**Goal**: Make the app production-ready, fast, and reliable.

### Tasks

1. **Performance optimization**:
   - Profile transcription latency — identify bottlenecks
   - Test ONNX Runtime vs NeMo for inference speed on M1 Max
   - Consider model quantization (INT8) for faster inference
   - Implement model warm-up on app start (first transcription is always slower)

2. **Smart message batching**:
   - If user speaks in rapid bursts, batch nearby chunks into one message
   - Add punctuation/capitalization cleanup (Parakeet v3 does this natively)
   - Optional: use an LLM (local or API) to clean up/rephrase before sending

3. **Error handling & resilience**:
   - Graceful handling of: mic disconnection, network loss, Telegram API errors
   - Auto-reconnect for Telegram
   - Save unsent messages and retry
   - Log errors to a file for debugging

4. **Testing**:
   - Test with 30+ minute continuous sessions
   - Test with background noise (fan, AC, keyboard typing)
   - Test with varying speech speeds
   - Test rapid start/stop toggling

5. **Packaging**:
   - Package as a standalone macOS .app using PyInstaller or py2app
   - Include the Parakeet model in the bundle or download on first launch
   - Create a DMG installer (optional)

### Success Criteria
- End-to-end latency (speech → Telegram message) under 2 seconds
- App runs stable for 1+ hour sessions
- Clean error messages, no crashes
- Packaged as a distributable app

### Deliverables
- Optimized pipeline
- Error handling throughout
- Packaged .app file (or clear instructions to build it)

---

## Phase 6 (Future/Optional): Advanced Features

These are stretch goals — implement only if the core app works well.

1. **WhatsApp support**: Add WhatsApp as an alternative to Telegram (via whatsapp-web.js or official API)
2. **Multiple recipients**: Send to multiple chats/groups simultaneously
3. **Two-way relay**: Receive messages from B and have them read aloud via TTS
4. **Noise suppression**: Integrate `noisereduce` or `RNNoise` for cleaner audio before STT
5. **Custom vocabulary**: Add a list of frequently used names/terms to boost accuracy
6. **Keyboard shortcut integration**: Global hotkey to toggle, with macOS Accessibility permissions
7. **Meeting integration**: Capture system audio (not just mic) to transcribe what others say in the meeting
8. **AI enhancement**: Use a local LLM to clean up, summarize, or rephrase before sending
9. **Speech commands**: Say "new paragraph", "send now", "delete last" to control the app by voice

---

## Project Structure

```
esper/
├── README.md
├── requirements.txt
├── config.yaml
├── setup_telegram.md
├── src/
│   ├── __init__.py
│   ├── audio_capture.py      # Mic input & VAD
│   ├── transcriber.py         # Parakeet STT engine
│   ├── telegram_sender.py     # Telegram bot integration
│   ├── pipeline.py            # Wires audio → STT → send
│   ├── config_manager.py      # Load/save config
│   └── app.py                 # Tkinter GUI
├── tests/
│   ├── test_stt.py            # Phase 1 accent test
│   ├── test_realtime.py       # Phase 2 streaming test
│   └── test_telegram.py       # Phase 3 send test
└── assets/
    └── icon.png               # Esper app icon
```

## Key Dependencies

```txt
# requirements.txt
nemo_toolkit[asr]       # or alternative for Apple Silicon
sounddevice
numpy
webrtcvad
python-telegram-bot
pyyaml
python-dotenv
```

## Important Notes for Claude Code

- **Apple Silicon compatibility**: NeMo/PyTorch may need special builds for M1 Max. If NeMo doesn't install cleanly, try `pip install torch torchvision torchaudio` first with the Apple Silicon build, then NeMo. Alternatively, explore `parakeet-mlx` or ONNX runtime as fallbacks.
- **No CUDA**: This Mac has Apple Silicon GPU (Metal), not NVIDIA GPU. Do NOT use CUDA-specific code. Use CPU or MPS (Metal Performance Shaders) backend.
- **Audio permissions**: macOS requires microphone permission. The app may need to be run from Terminal first to trigger the permission dialog.
- **Telegram bot setup**: The user will need to create a bot via @BotFather and provide the token. Include clear setup instructions.
- **Each phase should be independently testable** — don't skip ahead. Confirm each phase works before moving to the next.
- **Keep it simple** — prefer simple, readable code over clever abstractions. The user needs to understand and maintain this.
