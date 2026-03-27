# Requirements: Esper

**Defined:** 2026-03-27
**Core Value:** Real-time, accurate transcription of accented English speech

## v2.0 Requirements

Requirements for pipeline overhaul. Each maps to roadmap phases.

### Pipeline

- [ ] **PIPE-01**: VAD detects speech boundaries using Silero VAD with configurable silence threshold
- [ ] **PIPE-02**: VAD applies 150-300ms silence padding before/after utterances to prevent word clipping
- [ ] **PIPE-03**: VAD rejects low-energy chunks below configurable noise floor
- [ ] **PIPE-04**: Whisper large-v3-turbo transcribes VAD-gated utterances via mlx-whisper
- [ ] **PIPE-05**: Whisper runs in isolated spawn-context subprocess for MLX thread safety
- [ ] **PIPE-06**: Hallucination guard filters outputs using no_speech_prob and compression_ratio thresholds

### Architecture

- [x] **ARCH-01**: Single config.py replaces .env + @AppStorage + CLI args as source of truth
- [x] **ARCH-02**: IPC uses dedicated fd (--protocol-fd) instead of stdout redirect hack
- [ ] **ARCH-03**: Cascading watchdog timeouts at per-utterance and process level
- [ ] **ARCH-04**: TranscriptionUpdate dataclass defines clear contract between Whisper and all consumers

### Integration

- [ ] **INTG-01**: Telegram sender works with new per-utterance TranscriptionUpdate contract
- [ ] **INTG-02**: Telegram shutdown flush uses 10s timeout for API latency spikes
- [x] **INTG-03**: SwiftUI ProcessBridge updated for fd-based IPC protocol

### Cleanup

- [ ] **CLEAN-01**: Parakeet CoreML models and transcriber code removed
- [ ] **CLEAN-02**: Dead dependencies removed (parakeet-mlx, coremltools, scipy)
- [ ] **CLEAN-03**: Model load timeout updated from 30s to 120s for Whisper cold Metal compilation

## Future Requirements

### Performance

- **PERF-01**: Dual-buffer speculative transcription for reduced perceived latency
- **PERF-02**: Adaptive noise floor calibration based on ambient environment

### Features

- **FEAT-01**: Multi-language detection and transcription
- **FEAT-02**: Speaker diarization for multi-speaker scenarios

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cloud inference | Must stay local-only on Apple Silicon |
| Voice cloning / TTS | That's The Professor's domain |
| iOS / iPadOS port | macOS only for now |
| Streaming word-level tokens | mlx-whisper is batch-only; VAD gating makes this acceptable |
| whisper_streaming (SimulStreaming) | Significantly more complex; batch-after-VAD is sufficient |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ARCH-01 | Phase 1 | Complete |
| ARCH-02 | Phase 2 | Complete |
| INTG-03 | Phase 2 | Complete |
| PIPE-01 | Phase 3 | Pending |
| PIPE-02 | Phase 3 | Pending |
| PIPE-03 | Phase 3 | Pending |
| PIPE-04 | Phase 4 | Pending |
| PIPE-05 | Phase 4 | Pending |
| PIPE-06 | Phase 4 | Pending |
| ARCH-03 | Phase 4 | Pending |
| ARCH-04 | Phase 4 | Pending |
| CLEAN-03 | Phase 4 | Pending |
| INTG-01 | Phase 5 | Pending |
| INTG-02 | Phase 5 | Pending |
| CLEAN-01 | Phase 6 | Pending |
| CLEAN-02 | Phase 6 | Pending |

**Coverage:**
- v2.0 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 after roadmap creation*
