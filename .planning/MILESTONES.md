# Milestones

## v2.0 Pipeline Overhaul (Shipped: 2026-03-27)

**Phases completed:** 6 phases, 11 plans, 15 tasks

**Key accomplishments:**

- src/config.py with 5 namespaced sections (Audio, VAD, Whisper, Telegram, IPC) replacing scattered module constants; audio_capture.py IPC print() landmine eliminated
- Telegram credentials, model timeout, engine default, and audio constants unified into config.py — all entry points mutate config at startup, no module defines its own tunables
- One-liner:
- ProcessBridge now reads JSON events from a dedicated POSIX pipe (--protocol-fd) instead of stdout, eliminating any risk of stray print() output corrupting the IPC protocol
- Silero VAD daemon thread with 300ms pre-buffer, 200ms post-buffer, energy gate, and min-duration filter emitting float32 utterances to speech_q
- VadThread wired into server.py replacing _pump_audio — audio now flows AudioCapture -> audio_q -> VadThread -> speech_q -> bridge -> transcriber.push_audio() with VAD gating
- src/transcriber.py
- server.py, telegram_sender.py, and realtime_demo.py all wired to WhisperTranscriber with per-utterance transcript shape, replacing the Parakeet streaming model end-to-end
- Protocol.swift:
- One-liner:

---
