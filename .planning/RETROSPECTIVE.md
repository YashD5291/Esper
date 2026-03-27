# Retrospective

## Milestone: v2.0 — Pipeline Overhaul

**Shipped:** 2026-03-27
**Phases:** 6 | **Plans:** 11 | **Tasks:** 15

### What Was Built
- Single config.py replacing scattered .env + @AppStorage + CLI args
- Clean IPC over dedicated POSIX pipe (`--protocol-fd`), eliminating stdout corruption risk
- Silero VAD with 300ms pre-buffer, energy gate, and min-duration filtering
- Whisper large-v3-turbo in isolated spawn subprocess with 15s watchdog + hallucination filter
- Per-utterance Telegram sender with 429 retry-after handling and 10s shutdown flush
- Full Parakeet/CoreML dead code removal — Whisper-only architecture

### What Worked
- TDD approach caught issues early (e.g., speech_frame_count vs buffer length in VAD)
- Phase dependency chain (1→2→3→4→5→6) prevented integration surprises
- The Professor's patterns as reference architecture provided clear design targets
- Subprocess isolation for Whisper proved essential — MLX thread safety still unfixed upstream

### What Was Inefficient
- CONTEXT.md D-02 said "delete transcriber.py" but Phase 4 had rewritten it — stale context caused confusion in Phase 6 planning
- Some SUMMARY.md one-liners were empty or just file names — extraction tooling could be more robust

### Patterns Established
- Entry-point mutation: `_do_start()` mutates `config.*` before constructing objects
- Module-import pattern: `from . import config` for runtime-visible mutations
- JSON-line protocol over `--protocol-fd` for subprocess IPC
- VadThread → speech_q → WhisperTranscriber pipeline with sentinel-based shutdown
- Per-utterance TranscriptionUpdate as the universal contract between components

### Key Lessons
- VAD silence detection + batch Whisper is <3s latency — sufficient for real-time use, no need for streaming tokens
- prebuf.append() must happen before energy gate to prevent first-phoneme clipping
- `multiprocessing.Queue` (not `SimpleQueue`) needed for timeout support on `get()`
- CLOEXEC must be explicitly cleared on macOS for fd inheritance through exec

---

## Cross-Milestone Trends

| Metric | v2.0 |
|--------|------|
| Phases | 6 |
| Plans | 11 |
| Tasks | 15 |
| Timeline | ~48 days |
| Python LOC | ~6,964 |
| Swift LOC | ~5,023 |
| Tests | 71 |
