# Roadmap: Esper

## Overview

v2.0 Pipeline Overhaul rebuilds Esper's transcription stack from scratch: a consolidated config.py, a clean IPC protocol, Silero VAD for speech boundary detection, Whisper large-v3-turbo in a subprocess for MLX Metal isolation, a hardened Telegram integration anchored by an explicit TranscriptionUpdate contract, and a final sweep removing all dead Parakeet code. Each phase delivers a coherent, independently verifiable capability — and each depends strictly on the one before it.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Config Consolidation** - Single config.py replaces .env + @AppStorage + CLI args
- [x] **Phase 2: IPC Cleanup** - Replace stdout fd redirect hack with --protocol-fd argument (completed 2026-03-27)
- [ ] **Phase 3: VAD Integration** - Silero VAD provides utterance boundaries that gate Whisper
- [ ] **Phase 4: Whisper Integration** - Whisper large-v3-turbo runs in isolated spawn subprocess
- [ ] **Phase 5: Telegram Hardening** - TranscriptionUpdate contract locked, Telegram lifecycle fixed
- [ ] **Phase 6: Cleanup** - Remove Parakeet code, CoreML models, and dead dependencies

## Phase Details

### Phase 1: Config Consolidation
**Goal**: All tunables live in a single config.py that every component imports, eliminating silent config divergence between CLI and SwiftUI modes
**Depends on**: Nothing (first phase)
**Requirements**: ARCH-01
**Success Criteria** (what must be TRUE):
  1. Running the CLI and the SwiftUI app reads all tunable values from the same config.py — no .env file or @AppStorage key can override a config constant without going through config.py
  2. Telegram credentials are passed via the `start` command data dict at runtime, not read from a .env file at import time
  3. All `print()` calls in audio_capture.py that were corrupting the IPC stream are replaced with log calls
  4. The VAD, Whisper, Telegram, and IPC constant namespaces are present in config.py with documented defaults, ready for later phases to consume
**Plans:** 2 plans
Plans:
- [x] 01-01-PLAN.md — Create config.py and migrate leaf modules (audio_capture, transcriber, coreml_transcriber)
- [x] 01-02-PLAN.md — Migrate entry points (server.py, realtime_demo.py) and telegram_sender.py

### Phase 2: IPC Cleanup
**Goal**: The Python backend communicates with SwiftUI exclusively over a dedicated file descriptor, making it safe to add log-heavy VAD and Whisper components without corrupting the protocol stream
**Depends on**: Phase 1
**Requirements**: ARCH-02, INTG-03
**Success Criteria** (what must be TRUE):
  1. The SwiftUI app launches the Python backend with a `--protocol-fd N` argument and receives JSON-line messages on that fd — no stdout redirect
  2. The `os.dup2(2, 1)` hack is absent from server.py
  3. No `print()` call anywhere in `src/` can corrupt the JSON protocol channel — all output goes through logging
  4. The ProcessBridge in the SwiftUI app is updated to open and read from the protocol fd rather than stdout
**Plans:** 2/2 plans complete
Plans:
- [x] 02-01-PLAN.md — TDD: Replace os.dup2 hack with --protocol-fd argparse in server.py
- [x] 02-02-PLAN.md — Update ProcessBridge.swift for protocol pipe IPC + end-to-end verification

### Phase 3: VAD Integration
**Goal**: Silero VAD owns the audio loop and emits complete utterance buffers to speech_q, so Whisper is never called on silence or sub-threshold fragments
**Depends on**: Phase 2
**Requirements**: PIPE-01, PIPE-02, PIPE-03
**Success Criteria** (what must be TRUE):
  1. Silence between sentences produces no entries in speech_q — Whisper is not invoked on quiet gaps
  2. Each utterance emitted to speech_q includes a 300-500ms pre-buffer so the first phoneme of a sentence is not clipped
  3. Low-energy ambient noise chunks are rejected before they reach speech_q
  4. AudioCapture uses 512-sample blocks (required by Silero VADIterator) and Silero runs on CPU, not MPS
**Plans:** 1/2 plans executed
Plans:
- [x] 03-01-PLAN.md — TDD: VadThread implementation (config update, tests, Silero state machine)
- [ ] 03-02-PLAN.md — Wire VadThread into server.py, replace _pump_audio, live verification

### Phase 4: Whisper Integration
**Goal**: Whisper large-v3-turbo transcribes every utterance from speech_q, running in an isolated spawn-context subprocess with Metal safety, watchdog timeouts, and hallucination filtering
**Depends on**: Phase 3
**Requirements**: PIPE-04, PIPE-05, PIPE-06, ARCH-03, ARCH-04, CLEAN-03
**Success Criteria** (what must be TRUE):
  1. Speaking a sentence produces a transcription in under 3 seconds from utterance end, with no MLX thread-safety crashes after extended use
  2. The Whisper subprocess restarts cleanly after 50 utterances without requiring a full pipeline restart
  3. A Whisper inference that hangs is killed and reported as an error within 15 seconds — the pipeline continues processing new utterances
  4. Whisper output with no_speech_prob above threshold is silently discarded and does not reach consumers
  5. The model load on cold start (first MLX shader compilation) completes within 120 seconds without a timeout error
**Plans**: TBD

### Phase 5: Telegram Hardening
**Goal**: Telegram integration works reliably with the new per-utterance TranscriptionUpdate contract and flushes cleanly on session stop
**Depends on**: Phase 4
**Requirements**: INTG-01, INTG-02
**Success Criteria** (what must be TRUE):
  1. Two sequential utterances both appear in Telegram — the second utterance is not silently swallowed by stale _processed_chars state from the first
  2. Stopping the pipeline flushes any buffered draft to Telegram within 10 seconds even under API latency spikes
  3. A Telegram 429 rate-limit response is handled without crashing the pipeline — subsequent messages are retried
**Plans**: TBD

### Phase 6: Cleanup
**Goal**: All Parakeet code, CoreML model artifacts, and dead dependencies are removed, leaving the codebase consistent with the v2.0 architecture
**Depends on**: Phase 5
**Requirements**: CLEAN-01, CLEAN-02
**Success Criteria** (what must be TRUE):
  1. `src/coreml_transcriber.py` and `src/transcriber.py` are deleted and no import anywhere references them
  2. `models/coreml/` directory and its contents are absent from the repository
  3. `parakeet-mlx`, `coremltools`, and the explicit `scipy` pin are removed from requirements.txt and the app installs and runs cleanly without them
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Config Consolidation | 2/2 | Complete | 2026-03-26 |
| 2. IPC Cleanup | 2/2 | Complete   | 2026-03-27 |
| 3. VAD Integration | 1/2 | In Progress|  |
| 4. Whisper Integration | 0/? | Not started | - |
| 5. Telegram Hardening | 0/? | Not started | - |
| 6. Cleanup | 0/? | Not started | - |
