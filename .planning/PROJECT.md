# Esper

## What This Is

A real-time voice-to-text app for macOS that captures microphone audio, transcribes it using Whisper large-v3-turbo, and streams transcriptions to Telegram. Ships as both a CLI tool and a native SwiftUI menu bar app. Runs locally on Apple Silicon with VAD-gated batch inference.

## Core Value

Real-time, accurate transcription of accented English speech — if the transcription isn't accurate for the speaker's accent, nothing else matters.

## Requirements

### Validated

- Audio capture via sounddevice (16kHz mono, 512-sample blocks)
- Whisper large-v3-turbo transcription via mlx-whisper in isolated subprocess — v2.0
- Silero VAD for speech boundary detection with pre/post-buffer — v2.0
- Single config.py as source of truth for all tunables — v2.0
- Clean IPC protocol over dedicated fd (`--protocol-fd`) — v2.0
- SwiftUI menu bar app with ProcessBridge JSON-line IPC
- CLI mode (`python -m src.realtime_demo`)
- Per-utterance Telegram relay with 429 retry and 10s shutdown flush — v2.0
- Watchdog timeouts and subprocess auto-restart (15s inference timeout, 3-strike crash limit) — v2.0
- Audio device hot-swapping mid-session
- Optional session recording to WAV (speech-only utterances from speech_q)

### Active

(No active requirements — next milestone TBD)

### Out of Scope

- Cloud inference — must stay local-only on Apple Silicon
- Voice cloning / TTS — that's The Professor's domain
- iOS / iPadOS port — macOS only for now
- Multi-speaker diarization — single speaker focus
- Streaming word-level tokens — mlx-whisper is batch-only; VAD gating makes this acceptable
- Dual-engine support — removed in v2.0 (Whisper-only architecture)

## Context

- v2.0 Pipeline Overhaul shipped 2026-03-27 — full pipeline rebuild complete
- Architecture: Python backend as subprocess of SwiftUI app, JSON-line protocol over `--protocol-fd`
- Pipeline: AudioCapture → VadThread (Silero) → speech_q → WhisperTranscriber (subprocess) → TranscriptionUpdate → consumers
- Codebase: ~6,964 Python LOC + ~5,023 Swift LOC
- All Parakeet/CoreML code removed — Whisper is the only transcription engine
- The Professor's patterns (Silero VAD, single config, subprocess isolation) successfully adopted

## Constraints

- **Platform**: macOS 14+ with Apple Silicon (M1+) — local inference only
- **Latency**: <3 seconds from utterance end to transcription (VAD silence detection + Whisper inference)
- **Compatibility**: Must maintain both CLI and SwiftUI app interfaces
- **Model**: Whisper large-v3-turbo via mlx-whisper — confirmed and validated
- **Reference**: The Professor's architecture patterns as quality baseline

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Whisper large-v3-turbo over Parakeet | Better Indian accent recognition, good speed/accuracy tradeoff on MLX | Validated — Phase 4, Parakeet removed Phase 6 |
| Silero VAD from The Professor | Proven stable (50+ generations zero hangs), lightweight | Validated — Phase 3 |
| Single config.py pattern | The Professor's pattern works well, eliminates config fragmentation | Validated — Phase 1 |
| Spawn-context subprocess for Whisper | MLX thread safety unfixed upstream, process isolation prevents Metal crashes | Validated — Phase 4 |
| Per-utterance TranscriptionUpdate | Simpler than streaming draft/finalized model, natural fit with VAD boundaries | Validated — Phase 4 |
| --protocol-fd over stdout redirect | Eliminates print() corruption of IPC stream, safe for log-heavy components | Validated — Phase 2 |

## Shipped Milestones

- **v2.0 Pipeline Overhaul** (2026-03-27) — 6 phases, 11 plans. Full pipeline rebuild with VAD, Whisper, clean IPC, hardened Telegram, Parakeet removal.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check -- still the right priority?
3. Audit Out of Scope -- reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-27 after v2.0 Pipeline Overhaul milestone complete*
