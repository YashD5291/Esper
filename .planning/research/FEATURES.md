# Feature Landscape

**Domain:** Real-time VAD-gated Whisper transcription pipeline with Telegram relay
**Researched:** 2026-03-27
**Milestone:** v2.0 Pipeline Overhaul

---

## Table Stakes

Features the pipeline must have. Missing any of these means the v2.0 overhaul is incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Silero VAD speech boundary detection | Without VAD, every 100ms chunk goes to Whisper — 30-50x more inference calls, hallucinations on silence | Medium | Already used in The Professor; port that pattern directly |
| VAD-gated Whisper invocation | Whisper only runs after VAD detects end-of-utterance, not on every audio chunk | Medium | Depends on VAD being in place |
| Silence padding around utterances | VAD clips the very start/end of speech; 150–300ms padding on each side prevents word drop at boundaries | Low | Silero's training data includes this pattern; ~1600 samples at 16kHz |
| Whisper `no_speech_prob` gate | Whisper hallucinates on residual noise that passes VAD; gate on `no_speech_prob > 0.6` suppresses phantom text | Low | mlx-whisper exposes this field in segment output |
| Single `config.py` | Current architecture scatters config across `.env`, CLI args, and SwiftUI `@AppStorage`; one module-level constants file eliminates divergence | Low | The Professor pattern; straightforward to implement |
| Clean JSON-line IPC (no fd redirect) | Current `os.dup2(2, 1)` hack redirects fd 1 to stderr at C level; fragile and surprising to debug | Medium | New approach: use a dedicated fd (e.g. fd 3) opened via `--ipc-fd` flag, or keep stdout but never call `print()` after redirect |
| Watchdog timeouts on Whisper inference | MLX inference can hang; need a thread-level wall-clock timeout that kills and restarts | Medium | The Professor uses 8s TTS_MAX_SYNTHESIS_TIME_S; same pattern applies |
| Telegram session lifecycle (flush on stop) | Current `TelegramSender.stop()` sends a `None` sentinel and lets the thread drain naturally — works, but no guarantee the trailing draft buffer gets committed as a final message before process exits | Low | Already partially there: `_loop()` finally-block sends draft if non-empty; needs a `wait()` call with sufficient timeout in `_do_stop()` |
| Telegram draft committed on utterance end | Draft (`sendMessageDraft`) must be finalized as a permanent `sendMessage` when the utterance is complete, not left dangling | Low | Current code does this; verify it holds after VAD integration |

---

## Differentiators

Features that raise quality above baseline. Not expected, but meaningfully improve the product.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Dual-buffer VAD strategy | One "hot" buffer for low-latency draft output (processed speculatively), one "committed" buffer processed only after VAD end-of-speech — reduces perceived latency without sacrificing accuracy | High | Whisper streaming research (UFAL whisper_streaming) shows this halves perceived lag; overkill for v2.0, park for v3 |
| Adaptive silence threshold | Auto-calibrate VAD activation threshold from ambient noise floor on startup — avoids manual tuning for different mic/room combos | Medium | 500ms calibration sample at start; adjust `activation_threshold` dynamically |
| Compression ratio hallucination filter | After Whisper transcribes, check token count vs audio duration ratio; flag suspiciously high ratios as likely hallucination | Low | faster-whisper exposes `compression_ratio`; mlx-whisper may too — verify at implementation time |
| Energy level events to SwiftUI | The existing energy-emitter thread already emits `{"event": "energy", ...}` at 10 Hz — after VAD is added, emit VAD state too (`speaking: true/false`) so the menu bar icon can animate | Low | Trivial extension; high UI value |
| Graceful Whisper restart on failure | After N consecutive Whisper failures, restart the MLX worker subprocess rather than failing permanently — mirrors The Professor's 3-strike fallback | Medium | Follows established pattern from The Professor; copy and adapt |

---

## Anti-Features

Features to explicitly not build in this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Streaming partial Whisper output to transcript | Whisper is not natively streaming — you get output after the model finishes a segment, not token-by-token. Faking it with partial buffers adds complexity for no real gain | Gate Whisper on full VAD utterances; Telegram `sendMessageDraft` already handles the "streaming appearance" |
| Real-time diarization (multi-speaker) | PROJECT.md explicitly out-of-scopes this; single-speaker focus | Ignore |
| Cloud Whisper fallback | Violates the local-only constraint in PROJECT.md | If local Whisper fails, surface an error event; let user retry |
| Pydantic settings / ConfigArgParse | Adds a heavy dependency for a single-user tool; overkill vs a plain `config.py` with module-level constants | `config.py` with constants — no external config library |
| On-the-fly language detection | Adds 100ms+ to every Whisper call; user speaks English | Hard-code `language="en"` in Whisper call |
| Whisper word-level timestamps | Requires a second alignment pass; the transcript use case doesn't need word timing | Skip `word_timestamps=True` |
| Automatic retry loop in Telegram sender | Current `_MAX_RETRIES = 3` with exponential backoff is sufficient; an infinite retry loop will back up the queue during network outages | Keep the 3-retry cap; log and drop on failure |

---

## Feature Dependencies

```
AudioCapture (100ms chunks at 16kHz)
    └── Silero VAD (30ms frame evaluation, accumulate until end-of-speech)
            └── Whisper mlx inference (triggered once per utterance)
                    ├── no_speech_prob gate (suppress hallucinations)
                    └── TranscriptionUpdate callback
                            ├── JSON-line IPC → SwiftUI
                            └── TelegramSender (draft → finalized message lifecycle)

config.py
    └── imported by: VAD, Whisper loader, TelegramSender, server.py, audio_capture.py

Clean IPC protocol (no fd redirect)
    └── Required for: reliable SwiftUI ProcessBridge, debuggability, future CLI mode
```

Key dependency ordering for implementation:
1. `config.py` consolidation must happen first — everything imports it
2. Clean IPC must happen before VAD/Whisper, because adding new log output during Whisper will corrupt the current fd-redirect approach
3. VAD before Whisper — Whisper integration assumes VAD provides utterance boundaries
4. Telegram lifecycle cleanup can happen in parallel with VAD/Whisper work (isolated module)

---

## MVP Recommendation

For v2.0, build in this order:

1. **`config.py` consolidation** — removes fragmentation, unblocks everything else; low risk, high leverage
2. **Clean IPC protocol** — remove fd redirect hack before adding new log-heavy components (VAD logs, Whisper timing logs would corrupt current protocol stream)
3. **Silero VAD integration** — port directly from The Professor's `components/vad.py`; proven stable
4. **Whisper large-v3-turbo via mlx-whisper** — replace CoreML Parakeet; VAD must be in place first so Whisper is only called on detected utterances
5. **`no_speech_prob` gate + watchdog timeout** — one-line guards; add alongside Whisper integration
6. **Telegram lifecycle hardening** — flush draft on session stop; low complexity, do last

Defer to v3:
- Dual-buffer speculative transcription (high complexity, marginal gain for single-user tool)
- Adaptive silence threshold calibration (medium complexity, "good enough" static threshold for known mic)
- Graceful Whisper subprocess restart (medium complexity; watchdog timeout covers most failures)

---

## Complexity Notes

**VAD integration (Medium):** Silero VAD requires 30ms frame accumulation into a ring buffer, then probability scoring. The tricky part is managing the transition from "accumulating frames" to "utterance complete" with correct silence duration gating. The Professor's `VAD` class already solves this — direct port is the right approach, not a reimplementation.

**Clean IPC (Medium):** The current `os.dup2(2, 1)` trick works but is invisible to future contributors and breaks standard debuggers. The right replacement is to either: (a) open a new fd via a `--ipc-fd` flag and write JSON there, or (b) dedicate stdout to JSON and enforce that nothing in the Python codebase calls `print()` after startup. Option (b) is simpler for the existing SwiftUI integration. Lint enforcement (grep for `print(` in CI) catches regressions.

**Whisper `no_speech_prob` gate (Low):** mlx-whisper returns segment-level metadata including `no_speech_prob`. Discard any segment where `no_speech_prob > 0.6` (Whisper default). This is a one-line filter after transcription.

**Telegram draft lifecycle (Low):** The existing `TelegramSender._loop()` already has a `finally` block that flushes `_draft_buf`. The gap is that `_do_stop()` in `server.py` calls `_telegram_sender.wait(timeout=5.0)` — but only after calling `stop()` which enqueues a `None` sentinel. The chain is correct; verify the timeout is long enough for final HTTP round-trips (10s is safer than 5s given Telegram's occasional API latency).

**`sendMessageDraft` API status:** As of Bot API 9.5 (March 1, 2026), `sendMessageDraft` is available to all bots. Parameters: `chat_id`, `draft_id` (non-zero int32; same `draft_id` = animated in-place update), `text`, and standard message options. The current implementation already uses this correctly. Key lifecycle rule: a draft is visible until either (a) a `sendMessage` is issued replacing it, or (b) a new `sendMessageDraft` with a different `draft_id` is issued. Current code rotates `draft_id` on sentence finalization — this is correct behavior.

---

## Sources

- Silero VAD GitHub: https://github.com/snakers4/silero-vad
- PyTorch Hub — Silero VAD: https://pytorch.org/hub/snakers4_silero-vad_vad/
- mlx-whisper PyPI: https://pypi.org/project/mlx-whisper/
- UFAL whisper_streaming: https://github.com/ufal/whisper_streaming
- Whisper hallucination discussion: https://github.com/openai/whisper/discussions/679
- faster-whisper VAD implementation: https://github.com/SYSTRAN/faster-whisper
- Telegram Bot API changelog (9.3, 9.5): https://core.telegram.org/bots/api-changelog
- Telegram Bot API reference: https://core.telegram.org/bots/api
- WhisperX + Silero VAD guide: https://medium.com/@aidenkoh/how-to-implement-high-speed-voice-recognition-in-chatbot-systems-with-whisperx-silero-vad-cdd45ea30904
- Audio preprocessing for Whisper: https://medium.com/@developerjo0517/audio-pre-processings-for-better-results-in-the-transcription-pipeline-bab1e8f63334
- Calm-Whisper hallucination research: https://arxiv.org/html/2505.12969v1
- OpenClaw sendMessageDraft issue tracking: https://github.com/openclaw/openclaw/issues/32180
