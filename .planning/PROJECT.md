# Esper

## What This Is

A real-time voice-to-text app for macOS that captures microphone audio, transcribes it live, and optionally streams transcriptions to Telegram. Ships as both a CLI tool and a native SwiftUI menu bar app. Runs locally on Apple Silicon.

## Core Value

Real-time, accurate transcription of accented English speech — if the transcription isn't accurate for the speaker's accent, nothing else matters.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. Inferred from existing codebase. -->

- Audio capture via sounddevice (16kHz mono, 100ms chunks)
- Real-time transcription with streaming draft/finalized text
- SwiftUI menu bar app with ProcessBridge JSON-line IPC
- CLI mode (`python -m src.realtime_demo`)
- Telegram relay with sendMessage + sendMessageDraft streaming
- Audio device hot-swapping mid-session
- Optional session recording to WAV
- Dual-engine support (CoreML + MLX backends)

### Active

<!-- Current scope. Building toward these in v2.0. -->

- [x] Silero VAD for speech boundary detection — Validated in Phase 3: VAD Integration
- [ ] Whisper large-v3-turbo via mlx-whisper (Indian accent support)
- [x] Single config.py (consolidate .env + @AppStorage + CLI args) — Validated in Phase 1: Config Consolidation
- [x] Clean IPC protocol (remove stdout fd redirect hack) — Validated in Phase 2: IPC Cleanup
- [ ] Defensive error handling (watchdog timeouts, graceful fallbacks)
- [ ] Proper Telegram lifecycle (not bolted-on)

### Out of Scope

<!-- Explicit boundaries. -->

- Cloud inference — must stay local-only on Apple Silicon
- Voice cloning / TTS — that's The Professor's domain
- iOS / iPadOS port — macOS only for now
- Multi-speaker diarization — single speaker focus

## Context

- Existing codebase works end-to-end but feels fragile compared to The Professor
- The Professor's patterns (Silero VAD, single config, subprocess isolation, cascading timeouts) are the reference architecture
- User has Indian accent — Parakeet accuracy is insufficient, Whisper large-v3-turbo recommended
- Current architecture: Python backend as subprocess of SwiftUI app, JSON-line protocol over stdio with fd redirect hack
- CoreML Parakeet TDT v3 models (~200MB) in models/coreml/ — will be replaced by Whisper

## Constraints

- **Platform**: macOS 14+ with Apple Silicon (M1+) — local inference only
- **Latency**: Near real-time transcription (<500ms from speech to text)
- **Compatibility**: Must maintain both CLI and SwiftUI app interfaces
- **Model**: Whisper large-v3-turbo via mlx-whisper — confirmed choice
- **Reference**: The Professor's architecture patterns as quality baseline

## Current Milestone: v2.0 Pipeline Overhaul

**Goal:** Rebuild Esper's transcription pipeline with VAD, Whisper large-v3-turbo, and clean architecture.

**Target features:**
- Silero VAD for speech boundary detection
- Whisper large-v3-turbo via mlx-whisper
- Consolidated config.py
- Clean IPC protocol
- Hardened error handling
- Proper Telegram integration

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Whisper large-v3-turbo over Parakeet | Better Indian accent recognition, good speed/accuracy tradeoff on MLX | -- Pending |
| Silero VAD from The Professor | Proven stable (50+ generations zero hangs), lightweight | Validated — Phase 3 |
| Single config.py pattern | The Professor's pattern works well, eliminates config fragmentation | Validated — Phase 1 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
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
*Last updated: 2026-03-27 after Phase 3: VAD Integration complete*
