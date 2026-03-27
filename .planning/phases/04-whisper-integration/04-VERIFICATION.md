---
phase: 04-whisper-integration
verified: 2026-03-27T00:00:00Z
status: gaps_found
score: 4/5 success criteria verified
gaps:
  - truth: "Speaking a sentence produces a transcription in under 3 seconds from utterance end, with no MLX thread-safety crashes after extended use"
    status: partial
    reason: "Core engine is wired and tested, but realtime_demo.py --record path contains a NameError: bare SAMPLE_RATE on line 191 (undefined name — config.SAMPLE_RATE is the correct reference). The pipeline itself works; only the recording save is broken."
    artifacts:
      - path: "src/realtime_demo.py"
        issue: "Line 191: `duration = len(audio) / SAMPLE_RATE` — SAMPLE_RATE is not imported or defined at module scope; should be `config.SAMPLE_RATE` (same as line 190). Causes NameError when --record is used and audio chunks were captured."
    missing:
      - "Fix line 191: change `SAMPLE_RATE` to `config.SAMPLE_RATE` in src/realtime_demo.py"
human_verification:
  - test: "End-to-end transcription latency under 3 seconds from utterance end"
    expected: "Whisper returns transcription text within 3s of speech ending on warm model"
    why_human: "Requires live microphone, running Whisper model, and real-time measurement — not testable programmatically without the full runtime"
  - test: "No MLX thread-safety crashes after extended use (50+ utterances)"
    expected: "Subprocess isolation prevents Metal assertion failures under concurrent use"
    why_human: "Requires extended real-world session, not provable from code inspection alone"
---

# Phase 4: Whisper Integration Verification Report

**Phase Goal:** Whisper large-v3-turbo transcribes every utterance from speech_q, running in an isolated spawn-context subprocess with Metal safety, watchdog timeouts, and hallucination filtering
**Verified:** 2026-03-27
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Speaking a sentence produces transcription under 3s, no MLX crashes | PARTIAL | Engine wired and tested. realtime_demo.py --record has a NameError on line 191 (bare `SAMPLE_RATE`). Latency/crash-freedom requires human verification. |
| 2 | Whisper subprocess restarts cleanly after 50 utterances without full pipeline restart | VERIFIED | `test_generation_restart` covers this; `WHISPER_MAX_GENERATIONS_BEFORE_RESTART=50` in config; `_generation_count >= config.WHISPER_MAX_GENERATIONS_BEFORE_RESTART` triggers `_kill_worker()` + `_spawn_worker()` in `transcribe_utterance()` |
| 3 | A hanging Whisper inference is killed and reported as error within 15 seconds | VERIFIED | `WHISPER_SUBPROCESS_TIMEOUT_S=15.0`; `result_q.get(timeout=config.WHISPER_SUBPROCESS_TIMEOUT_S)` raises `queue.Empty` → `_kill_worker()` + `_on_status("error")` + `_on_failure()` per D-06; tested by `test_watchdog_timeout` and `test_watchdog_timeout_emits_error_event` |
| 4 | Whisper output with no_speech_prob above threshold is silently discarded | VERIFIED | `_is_hallucination()` checks `avg_no_speech > config.WHISPER_NO_SPEECH_THRESHOLD (0.6)` and `avg_compression > config.WHISPER_COMPRESSION_RATIO_THRESHOLD (2.4)`; tested by `test_hallucination_filter_no_speech`, `test_hallucination_filter_compression`, `test_hallucination_filter_empty_text` |
| 5 | Model load on cold start completes within 120 seconds without timeout error | VERIFIED | `MODEL_LOAD_TIMEOUT_S=120.0`; `start()` raises `RuntimeError` on `queue.Empty` after that timeout; tested by `test_model_load_timeout` |

**Score:** 4/5 truths verified (SC1 is partial due to realtime_demo.py --record bug and human-verification items)

---

## Required Artifacts

### Plan 01 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/transcriber.py` | WhisperTranscriber + TranscriptionUpdate | VERIFIED | Contains `class WhisperTranscriber` and `class TranscriptionUpdate` with all 8 fields (5 new + 3 backward-compat). No `StreamingTranscriber`, no `load_model`. |
| `src/whisper_worker.py` | Subprocess worker loop | VERIFIED | Contains `_whisper_worker(audio_q, result_q)`. Calls `mlx_whisper.transcribe()` with `word_timestamps=False`. No `clip_timestamps`. Emits ready sentinel `{"ok": True, "ready": True}`. |
| `src/config.py` | Hallucination filter thresholds | VERIFIED | `WHISPER_NO_SPEECH_THRESHOLD: float = 0.6` and `WHISPER_COMPRESSION_RATIO_THRESHOLD: float = 2.4` present. `MODEL_LOAD_TIMEOUT_S: float = 120.0` present (CLEAN-03). |
| `tests/test_whisper_transcriber.py` | 16+ unit tests | VERIFIED | 16 tests, all passing (0.07s). Covers PIPE-04/05/06, ARCH-03/04. |
| `requirements.txt` | mlx-whisper dependency | VERIFIED | `mlx-whisper==0.4.3` present. |

### Plan 02 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/server.py` | WhisperTranscriber integration, new status events, new transcript shape | VERIFIED | Contains `WhisperTranscriber`, `_whisper_consumer`, `_on_status`. `_on_update` emits `text`, `finalized_text`, `sentences`, `no_speech_prob`, `duration_s`. No `StreamingTranscriber`, `_bridge_speech_q`, `_load_model_with_timeout`, or `draft_text` in payload. |
| `src/telegram_sender.py` | Per-utterance Telegram sending | VERIFIED | `on_update` uses `update.text.strip()`. No `_processed_chars`, `_process_streaming`, `_send_draft`, or `_draft_buf`. `_queue: queue.Queue[str | None]` type. |
| `src/realtime_demo.py` | Per-utterance CLI rendering | STUB (minor) | Contains `WhisperTranscriber`, `VadThread`, `ConsoleRenderer` (simplified). No `--engine`, no `draft_sentences`. Bug on line 191: bare `SAMPLE_RATE` should be `config.SAMPLE_RATE` — NameError at runtime when `--record` is used. |
| `tests/test_telegram_sender.py` | 7 TDD tests, per-utterance model | VERIFIED | 156 lines, 7 tests, all passing (0.10s). |

### Plan 03 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `EsperApp/EsperApp/Models/Protocol.swift` | Updated EngineStatus + TranscriptionPayload | VERIFIED | All 6 EngineStatus cases (idle, downloadingModel, compilingShaders, loadingModel, transcribing, listening). TranscriptionPayload: `text`, `finalizedText`, `sentences: [String]`, `noSpeechProb`, `durationS`. No `SentencePayload`, no `draftText`. |
| `EsperApp/EsperApp/TranscriptionEngine.swift` | Updated event handling | VERIFIED | `var currentText`, `var finalizedText`, `var sentences: [String]`. `var isLoading: Bool` computed property covers 3 loading states. No `finalizedSentences`, no `draftText`. No `"engine"` key in `startListening()`. |
| `EsperApp/EsperApp/Views/TranscriptView.swift` | Per-utterance sentence list | VERIFIED | `let sentences: [String]`. No `SentencePayload`, no `draftText`. |
| `EsperApp/EsperApp/Views/MainWindowView.swift` | Updated engine property references | VERIFIED | `TranscriptView(sentences: engine.sentences)`. `buttonLabel` has all 6 cases. `engine.isLoading` used for ProgressView and `.disabled`. Hardcoded `"WHISPER"` badge. |
| `EsperApp/EsperApp/Views/SettingsView.swift` | Removed Engine picker section | VERIFIED | No `Section("Engine")`, no `settings.engine`, no `bufferSeconds`. |
| `EsperApp/EsperApp/Models/AppSettings.swift` | Removed engine and bufferSeconds | VERIFIED | No `engine` property, no `bufferSeconds` property. |

---

## Key Link Verification

### Plan 01 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/whisper_worker.py` | `mlx_whisper.transcribe()` | direct call in worker loop | VERIFIED | `mlx_whisper.transcribe(audio, ...)` called in the loop body; `word_timestamps=False`, no `clip_timestamps` |
| `src/transcriber.py WhisperTranscriber` | `src/whisper_worker.py _whisper_worker` | multiprocessing spawn context Process target | VERIFIED | `ctx.Process(target=_whisper_worker_entry, ...)` where `_whisper_worker_entry` imports and calls `_whisper_worker` |
| `src/transcriber.py WhisperTranscriber` | `TranscriptionUpdate` | `_build_update` constructs dataclass | VERIFIED | `return TranscriptionUpdate(text=text, finalized_text=..., sentences=..., ...)` in `_build_update()` |

### Plan 02 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/server.py` | `WhisperTranscriber` | import and construct in `_do_start` | VERIFIED | `from .transcriber import TranscriptionUpdate, WhisperTranscriber`; `_transcriber = WhisperTranscriber(...)` |
| `src/server.py _whisper_consumer` | `WhisperTranscriber.transcribe_utterance` | loop reading speech_q | VERIFIED | `result = _transcriber.transcribe_utterance(utterance)` inside while loop |
| `src/telegram_sender.py on_update` | `TranscriptionUpdate.text` | direct send of update.text | VERIFIED | `text = update.text.strip()` then `self._queue.put(text)` |

### Plan 03 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `Protocol.swift ServerEvent.parse` | Python server.py `_send('transcript', ...)` | JSON parsing of transcript event | VERIFIED | Parses `d["text"]`, `d["finalized_text"]`, `d["sentences"]`, `d["no_speech_prob"]`, `d["duration_s"]` — exact match to server.py `_on_update` payload |
| `Protocol.swift EngineStatus` | Python server.py `_send('status', ...)` | rawValue matching | VERIFIED | `case transcribing` present; all 6 rawValues match Python status strings |
| `MainWindowView.swift` | `TranscriptionEngine.swift` | reads engine.sentences | VERIFIED | `TranscriptView(sentences: engine.sentences)` present |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `TranscriptView.swift` | `sentences: [String]` | `engine.sentences` (TranscriptionEngine) | Yes — set in `handle(.transcript(let payload))` from `payload.sentences` parsed from server JSON | FLOWING |
| `src/server.py _on_update` | transcript event payload | `WhisperTranscriber.transcribe_utterance()` result | Yes — `_build_update()` constructs from real Whisper inference result | FLOWING |
| `src/telegram_sender.py on_update` | `update.text` | TranscriptionUpdate from WhisperTranscriber | Yes — `update.text.strip()` enqueued and sent via httpx | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| WhisperTranscriber unit tests pass | `.venv/bin/python -m pytest tests/test_whisper_transcriber.py -x -q` | 16 passed in 0.07s | PASS |
| TelegramSender tests pass | `.venv/bin/python -m pytest tests/test_telegram_sender.py -x -q` | 7 passed in 0.10s | PASS |
| Full test suite passes | `.venv/bin/python -m pytest tests/ -x -q` | 58 passed in 8.75s | PASS |
| Key module exports importable | `from src.transcriber import TranscriptionUpdate, WhisperTranscriber` etc. | Import OK | PASS |
| Config constants correct | `config.WHISPER_NO_SPEECH_THRESHOLD == 0.6` etc. | All values correct | PASS |
| Swift project builds | `xcodebuild -scheme EsperApp ... build` | BUILD SUCCEEDED | PASS |
| realtime_demo --record path | `SAMPLE_RATE` bare name on line 191 | NameError at runtime | FAIL |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PIPE-04 | 04-01, 04-02 | Whisper large-v3-turbo transcribes VAD-gated utterances via mlx-whisper | SATISFIED | `_whisper_worker` calls `mlx_whisper.transcribe()`; wired into `_whisper_consumer` reading `speech_q` |
| PIPE-05 | 04-01 | Whisper runs in isolated spawn-context subprocess | SATISFIED | `multiprocessing.get_context("spawn")` used in `_spawn_worker()`; tested by `test_spawn_context` |
| PIPE-06 | 04-01 | Hallucination guard filters using no_speech_prob and compression_ratio | SATISFIED | `_is_hallucination()` checks both thresholds; tested by 4 hallucination filter tests |
| ARCH-03 | 04-01 | Cascading watchdog timeouts at per-utterance and process level | SATISFIED | 15s per-utterance timeout (`WHISPER_SUBPROCESS_TIMEOUT_S`); 120s model load timeout (`MODEL_LOAD_TIMEOUT_S`); both raise/kill correctly |
| ARCH-04 | 04-01, 04-02, 04-03 | TranscriptionUpdate dataclass defines clear contract between Whisper and all consumers | SATISFIED | `TranscriptionUpdate` with 5 new fields; server.py, telegram_sender.py, realtime_demo.py, Swift app all consume it |
| CLEAN-03 | 04-01 | Model load timeout updated from 30s to 120s for Whisper cold Metal compilation | SATISFIED | `MODEL_LOAD_TIMEOUT_S: float = 120.0` in config.py |

All 6 requirements declared in phase plans are accounted for and satisfied by implementation. Requirements.md marks all 6 as `[x]` complete — consistent with implementation evidence.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/realtime_demo.py` | 191 | `duration = len(audio) / SAMPLE_RATE` — bare `SAMPLE_RATE` undefined; line 190 already uses `config.SAMPLE_RATE` correctly | Warning | Runtime NameError when `--record` flag is used and audio was captured. Does not affect IPC/server mode or transcription pipeline. |
| `src/config.py` | 41 | `DEFAULT_ENGINE: str = "coreml"` — stale constant from pre-Phase 4; server.py now defaults to "whisper" | Info | Dead config value. Not used by server.py (`_engine_name: str = "whisper"` hardcoded). No functional impact but should be cleaned up in Phase 6. |

---

## Human Verification Required

### 1. End-to-End Transcription Latency

**Test:** Run `python -m src.realtime_demo`, speak a short sentence (3-5 words), measure time from end of speech to text appearing in terminal.
**Expected:** Transcription appears within 3 seconds of utterance end on warm model.
**Why human:** Requires live microphone, running Whisper model, and real-time timing measurement — cannot be verified from code inspection alone.

### 2. MLX Thread-Safety Under Extended Use

**Test:** Run `python -m src.realtime_demo` for 10+ minutes with continuous speech; verify no Metal assertion failures or crashes.
**Expected:** No `Assertion failed` errors in stderr, transcription continues working after 50+ utterances (subprocess recycle point).
**Why human:** Requires extended real-world session. The spawn-context isolation is the architectural mitigation but crash-freedom cannot be proved statically.

### 3. Recording Save Correctness (after --record bug is fixed)

**Test:** Run `python -m src.realtime_demo --record` for 30 seconds, verify the saved WAV file contains only speech (not silence), plays back correctly, and has the correct duration.
**Expected:** Speech-only WAV file with correct sample rate (16kHz) and audible content.
**Why human:** Requires microphone input and audio playback verification.

---

## Gaps Summary

One gap identified, one informational finding:

**Gap (Warning — --record path broken):** `src/realtime_demo.py` line 191 uses the bare name `SAMPLE_RATE` which is not defined at module scope. Line 190 immediately above it correctly uses `config.SAMPLE_RATE`. This is a copy-paste error introduced during the Phase 4 Plan 02 rewrite. The fix is one character change: `SAMPLE_RATE` → `config.SAMPLE_RATE`. This does not affect the server IPC mode, the transcription pipeline, or Telegram sending — only the `--record` flag's duration calculation line in the CLI.

**Info (stale config constant):** `DEFAULT_ENGINE: str = "coreml"` remains in `config.py` line 41 despite server.py now defaulting to "whisper". This is harmless dead code but creates confusion. Appropriate for Phase 6 cleanup.

The phase goal is substantively achieved: Whisper large-v3-turbo is fully wired via a spawn-context subprocess, all consumers (server.py, telegram_sender.py, realtime_demo.py, SwiftUI app) use the new per-utterance TranscriptionUpdate contract, the watchdog timeouts and hallucination filter are implemented and tested, and the Swift project builds cleanly. The single code-level gap is a one-line fix in the CLI recording path.

---

*Verified: 2026-03-27*
*Verifier: Claude (gsd-verifier)*
