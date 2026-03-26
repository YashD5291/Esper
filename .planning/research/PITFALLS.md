# Domain Pitfalls: Esper v2.0 Pipeline Overhaul

**Domain:** Real-time STT pipeline on macOS Apple Silicon — adding VAD, replacing transcription engine, cleaning IPC, hardening error handling
**Researched:** 2026-03-27
**Overall confidence:** HIGH (MLX/VAD pitfalls verified against GitHub issues and official docs; IPC pitfalls from direct codebase analysis)

---

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or total pipeline breakage.

---

### Pitfall 1: MLX Metal Memory Leak with word_timestamps

**What goes wrong:** `mlx_whisper.transcribe()` with `word_timestamps=True` leaks ~10MB of Metal GPU cache per audio chunk. In a long transcription session (30+ minutes), this causes OOM-adjacent slowdowns and eventual Metal resource exhaustion.

**Why it happens:** The `find_alignment` function calls `model.forward_with_cross_qk()` which produces variable-shaped attention tensors. MLX's Metal cache treats each new shape as a distinct compilation artifact and accumulates them — it never evicts automatically unless told to.

**Consequences:** Application becomes progressively slower over a session. Memory pressure kicks other apps off GPU. Eventually crashes or stalls on shader submission. Reproduces reliably in a session lasting 20+ minutes.

**Prevention:**
```python
import mlx.core as mx
# After model load, cap the Metal cache
mx.metal.set_cache_limit(100 * 1024 * 1024)  # 100MB ceiling

# Periodically clear in the transcription loop (every ~50 chunks)
if chunk_count % 50 == 0:
    mx.metal.clear_cache()
```

**Detection:** Watch `mps_driver_allocated_mem` in Activity Monitor. If it climbs monotonically during a session, this is the cause.

**Phase:** Address in the mlx-whisper integration phase, before any Telegram streaming testing. A session that doesn't leak is a prerequisite for all other validation.

**Sources:** [mlx-examples issue #1254](https://github.com/ml-explore/mlx-examples/issues/1254) — confirmed by MLX maintainer as "expected cache growth," workaround validated.

---

### Pitfall 2: Whisper Hallucination on Silence and Low-Speech Audio

**What goes wrong:** When Whisper receives audio with no speech (low VAD confidence periods that slip through, brief gaps, HVAC noise), it hallucinates. Common outputs: "Thank you.", "Thank you for watching.", "You.", repetitive phrases, or fragments of training data captions. These get sent to Telegram as real transcription.

**Why it happens:** Whisper was trained on video subtitles. Audio segments with ambient noise look like video silence to the model, triggering trained closing phrases. Non-speech noise above the VAD threshold gets transcribed rather than rejected.

**Consequences:** Telegram chat fills with garbage. User loses trust in the tool immediately. TelegramSender's `_processed_chars` counter advances on hallucinations, corrupting the streaming state for the next real utterance.

**Prevention:**
1. VAD as the first gating layer — only pass confirmed speech segments to Whisper
2. Set `condition_on_prev_text=False` in `mlx_whisper.transcribe()` — reduces repetition loops
3. Post-transcription filter: reject outputs that are ONLY common hallucination phrases ("thank you", "you", "thanks for watching") with no other content
4. Minimum audio duration gate: don't send segments shorter than 500ms to Whisper even if VAD passed them

**Detection:** Log every Whisper output. Pattern-match against a blocklist of known hallucination phrases. If hit rate > 5% in a session, VAD threshold is too loose.

**Phase:** Must be addressed alongside VAD tuning. The hallucination filter is cheap to add and must be in place before Telegram integration is turned on in testing.

---

### Pitfall 3: Parakeet → Whisper TranscriptionUpdate Format Mismatch Breaks TelegramSender

**What goes wrong:** The current `TelegramSender` consumes `TranscriptionUpdate` directly — it accesses `update.finalized_text`, `update.finalized_sentences`, and uses `s.text` on sentence objects. The current Parakeet-based `StreamingTranscriber` produces these with sentence objects that have `.text` and `.end` attributes. If the new Whisper transcriber produces `TranscriptionUpdate` with a different sentence structure or without `.text`, `TelegramSender` will fail silently or crash.

**Why it happens:** `TelegramSender._process_streaming` trusts `update.finalized_text` as the source of truth and tracks position via `self._processed_chars`. If the new transcriber emits `finalized_text` that resets, repeats, or overlaps (e.g., each VAD segment produces a fresh string rather than an accumulating one), `_processed_chars` desynchronizes. The character pointer advances into invalid territory and `new_text = full[self._processed_chars:]` starts returning empty strings — Telegram goes silent without error.

**Consequences:** Telegram streaming silently stops working or sends duplicate messages. No exception is raised; it degrades invisibly.

**Prevention:**
1. Define the `TranscriptionUpdate` contract in one place before touching any transcriber code. Document whether `finalized_text` is cumulative (Parakeet pattern) or per-utterance (likely Whisper VAD pattern)
2. If switching to per-utterance semantics: rewrite `TelegramSender` to consume utterance strings, not the streaming diff model
3. Write a unit test that feeds two sequential `TranscriptionUpdate` objects and asserts the Telegram output is correct — before any live testing

**Detection:** Add a log line in `TelegramSender._process_streaming` that logs `self._processed_chars` and `len(full)` every update. If `self._processed_chars > len(full)`, the invariant is broken.

**Phase:** First thing to define before writing the new transcriber. The dataclass contract gates everything downstream.

---

### Pitfall 4: IPC Protocol Change Silently Breaks the SwiftUI App Without Error

**What goes wrong:** The SwiftUI app (`EsperApp`) parses JSON lines from Python stdout. If `server.py` adds new event types, renames fields, or changes the `data` payload shape, the Swift `Codable` decoder either silently drops unknown keys (best case) or throws a decode error that crashes the ProcessBridge (worst case — depends on how the Swift side handles `DecodingError`).

**Why it happens:** The current protocol is implicit — there's no schema. The Swift side likely has `struct`s that match the current field names. Any rename (e.g., changing `"status"` to `"state"`, or adding required fields to `"transcript"`) breaks the Swift decoder without any Python-side error.

**Consequences:** App shows no transcription, with no error event and no crash log visible to the user. Extremely hard to debug because the failure is silent on both sides.

**Prevention:**
1. Document the current IPC schema in a `PROTOCOL.md` before making any changes
2. Add new fields as optional, never rename or remove fields in the same phase as adding them
3. Test every new event type against the Swift app before merging, even informally
4. Keep the fd redirect hack (`os.dup(_proto_fd)`) until the Swift side is updated and tested — it is load-bearing for protocol isolation

**Detection:** The fd redirect (`os.dup2(2, 1)` → logging to stderr, protocol to saved fd) is subtle. Any new `print()` call added to the codebase before the redirect happens in `server.py` will corrupt the JSON stream with no error. Add a test: pipe server output to `python -c "import sys, json; [json.loads(l) for l in sys.stdin]"` and check every output line parses.

**Phase:** IPC cleanup must be atomic — define new schema, update Python, update Swift in one coordinated phase. Do not split across phases.

---

## Moderate Pitfalls

---

### Pitfall 5: VAD Threshold Clips Speech at Sentence Starts (Leading Phoneme Loss)

**What goes wrong:** Silero VAD's default threshold (0.5) combined with a missing pre-buffer causes the first 50–150ms of a spoken sentence to be lost. The user says "Hello, can you..." and Whisper receives "...can you..." — transcription quality degrades for sentence-initial words.

**Why it happens:** VAD probability ramps up from 0 → threshold during the onset of speech. By the time probability crosses the gate, the leading phonemes are already past and not captured in the buffer fed to Whisper.

**Prevention:** Maintain a ring buffer of the last 200–500ms of audio. When VAD fires, prepend that buffer to the current speech segment before sending to Whisper. The Silero authors call this `prefix_padding_duration`, LiveKit defaults it to 0.5s.

**Detection:** Record both the raw audio and the VAD-gated audio during a test session. Listen to the gated version. If you hear clipped words, the buffer is too short.

**Phase:** VAD integration phase. Tune with real speech from the target accent (Indian English) — the onset characteristics differ from training distributions.

---

### Pitfall 6: clip_timestamps Parameter Causes Severe MLX-Whisper Slowdowns

**What goes wrong:** Passing `clip_timestamps` to `mlx_whisper.transcribe()` causes a 7–10x processing slowdown. A 40-second segment takes 27–28 seconds with `clip_timestamps` vs 3–4 seconds without. For real-time transcription, this is catastrophic.

**Why it happens:** The parameter changes the internal processing path in MLX Whisper in a way that was not expected by maintainers. The behavior is confirmed as a bug, not intentional.

**Prevention:** Do not use `clip_timestamps` in the streaming path. If you need to limit the audio window fed to Whisper, trim the numpy array before calling `transcribe()` rather than relying on this parameter.

**Detection:** Time every `mlx_whisper.transcribe()` call. If any call on a < 60s segment takes > 10s, `clip_timestamps` or `word_timestamps` is the likely cause.

**Phase:** MLX Whisper integration phase. Establish a baseline latency benchmark (call duration vs audio duration) before adding any optional parameters.

---

### Pitfall 7: VAD Too Aggressive = Fragmented Utterances; Too Loose = Silence Fed to Whisper

**What goes wrong:** VAD is a tuning dial, not a binary right/wrong. Too aggressive (high threshold, short min silence): mid-sentence pauses create two separate "utterances," Whisper transcribes each without context → poor punctuation, split sentences, Telegram sends partial messages. Too loose (low threshold, long silence tolerance): 2–3 seconds of ambient noise get batched and sent to Whisper → hallucination (see Pitfall 2), high latency.

**Why it happens:** Default Silero parameters are tuned for clean studio speech, not ambient environments or accented speech with longer inter-word pauses.

**Prevention:**
- Start with threshold=0.5, min_silence_duration=500ms, min_speech_duration=500ms
- Test with the actual speaker in the actual environment (not a recording)
- The Professor's values are a validated starting point for this codebase/developer

**Detection:** Log the duration of each speech segment sent to Whisper. If segments are consistently < 1 second, VAD is fragmenting. If segments are consistently > 15 seconds, VAD is too loose.

**Phase:** VAD integration phase. Budget time for calibration — plan at least a 30-minute tuning session.

---

### Pitfall 8: MLX Cannot Share Metal Resources Cleanly with PyTorch MPS (If Both Are Active)

**What goes wrong:** If both `mlx-whisper` (MLX Metal) and Silero VAD (via PyTorch on MPS) run in the same process, they contend for Metal command queue resources. This is the same family of issue that caused 68+ second shader compilation hangs in The Professor when CoreML and MLX coexisted.

**Why it happens:** Metal does not provide pre-emptive GPU scheduling between frameworks. When two frameworks try to compile shaders concurrently, they serialize in the Metal driver, sometimes waiting for each other's compilation caches to complete.

**Prevention:**
1. Run Silero VAD via PyTorch on CPU (not MPS) — VAD is lightweight, CPU is fine
2. OR run Whisper in a subprocess with `multiprocessing.spawn` context (not `fork`) so each process owns one Metal context
3. Verify Silero loads with `torch.device("cpu")` explicitly, not the default

**Detection:** Add timing to the first inference call for both VAD and Whisper. If first VAD inference takes > 5 seconds, it's stalling on Metal. If first Whisper inference after VAD loads takes > 30 seconds, there's a shader compilation conflict.

**Phase:** Integration phase when VAD and Whisper are first combined. Test this before adding any other components.

---

### Pitfall 9: TelegramSender._processed_chars Never Resets Across VAD Utterances

**What goes wrong:** The current `TelegramSender` tracks `_processed_chars` as a monotonically increasing counter across the entire session. This was designed for Parakeet's streaming model where `finalized_text` is cumulative. If the new Whisper+VAD pipeline emits a fresh `finalized_text` per utterance (i.e., it resets to "" at the start of each speech segment), `_processed_chars` will be larger than `len(full)`, and `new_text = full[self._processed_chars:]` returns "". Telegram goes silent.

**Prevention:** Decide on the semantics of `finalized_text` before writing any code: cumulative (whole session) or per-utterance. If per-utterance, reset `_processed_chars = 0` on each new utterance and redesign `TelegramSender` accordingly.

**Detection:** Unit test. Feed the sender two `TranscriptionUpdate` objects with `finalized_text="Hello"` and then `finalized_text="World"` (simulating per-utterance). Assert two Telegram messages are sent. Without a fix, only one message is sent.

**Phase:** Transcriber contract definition. This must be resolved before Telegram integration begins.

---

### Pitfall 10: Model Loading Timeout Too Short for First MLX Compile

**What goes wrong:** The current `_MODEL_LOAD_TIMEOUT = 30` seconds in `server.py` was calibrated for CoreML Parakeet (fast, pre-compiled). MLX Whisper large-v3-turbo on first load triggers Metal shader compilation. This can take 45–90 seconds on a cold cache (first run ever, or after a macOS update that invalidates the shader cache). The timeout fires, the server emits `error`, and the SwiftUI app shows a failure — even though the model was about to succeed.

**Prevention:** Increase `_MODEL_LOAD_TIMEOUT` to at least 120 seconds for Whisper. Add a "compiling" status event so the UI shows progress rather than appearing frozen. After first load, subsequent loads hit the compiled shader cache and finish in ~5 seconds.

**Detection:** Time the first model load on a fresh machine or after `sudo find /var/folders -name "*.metallib" -delete`. If it exceeds 30s, the current timeout fires prematurely.

**Phase:** MLX Whisper integration phase. Update timeout before the first end-to-end test.

---

## Minor Pitfalls

---

### Pitfall 11: Telegram sendMessageDraft Rate Limiting

**What goes wrong:** `sendMessageDraft` became officially available to all bots in Bot API 9.5 (March 1, 2026). The current `_DRAFT_INTERVAL = 0.5` seconds (2 drafts/sec) should be safe, but the global 30 messages/second limit is shared across `sendMessage`, `sendMessageDraft`, and `editMessageText`. A burst of finalizations + drafts in the same second can hit the limit.

**Prevention:** Keep the `_DRAFT_INTERVAL` at 0.5s or higher. Do not lower it chasing "smoother streaming." Treat `429 Too Many Requests` responses and back off with exponential delay.

**Detection:** Log all non-200 Telegram responses. A `429` code means rate limited — add handling for `Retry-After` header.

**Phase:** Telegram hardening phase.

---

### Pitfall 12: Subprocess Multiprocessing Fork Corruption

**What goes wrong:** If Whisper inference is moved to a subprocess (The Professor's pattern) and `multiprocessing.set_start_method("fork")` is used (Python default on macOS before 3.12), the forked process inherits the parent's Metal context in a half-initialized state. Metal semaphores are leaked; the child process crashes on first GPU call.

**Prevention:** Always use `multiprocessing.set_start_method("spawn")` before any MLX import. This is the same fix The Professor uses. Put it at the very top of `server.py` before any other imports.

**Detection:** If the subprocess dies with `EXC_CRASH (SIGABRT)` or produces "leaked semaphore objects to clean up at shutdown" warnings, fork is being used instead of spawn.

**Phase:** If subprocess isolation is added in the hardening phase, set start method first.

---

### Pitfall 13: Config Consolidation Breaks the SwiftUI @AppStorage Keys

**What goes wrong:** The SwiftUI app uses `@AppStorage` with hard-coded key strings (e.g., `"telegram_bot_token"`, `"engine"`) to persist settings. If the Python `config.py` renames or reinterprets these keys, the Python side reads defaults while the Swift side reads stale `UserDefaults` values. The IPC `start` command payload carries these values at startup, so the mismatch is invisible until the wrong model is loaded.

**Prevention:** Treat the `start` command payload fields (the `data` dict) as the contract boundary. Python config defaults should not need to match Swift `@AppStorage` keys — Swift sends the values at runtime. But document which fields the `start` command must always include so config changes don't accidentally drop required fields.

**Detection:** Add a config validation step in `_do_start` that checks all required fields are present in the `data` dict before proceeding.

**Phase:** Config consolidation phase.

---

### Pitfall 14: audio_capture.py print() Call Corrupts the IPC Stream

**What goes wrong:** `audio_capture.py` line 75: `print(f"  Device: [{dev_idx}] {dev_name}")`. This is a plain `print()` call. The `server.py` fd redirect (`os.dup2(2, 1)`) must happen before this module is imported for the redirect to catch it. If any import path triggers `AudioCapture.start()` before the redirect is in place, this print goes to the real stdout and writes a non-JSON line into the protocol stream. The Swift app's JSON decoder chokes.

**Prevention:** The current `server.py` already does the redirect before imports — preserve this pattern. In `audio_capture.py`, change `print()` to `log.info()` as part of the cleanup. Never add new `print()` calls to any module in the `src/` package.

**Detection:** Run `python -m src.server` and pipe stdout through a JSON validator. Any non-JSON line is a bug.

**Phase:** Config/cleanup phase. Low risk, but the existing `print()` in `audio_capture.py` is a live landmine.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| VAD integration | Leading phoneme clipping (Pitfall 5) | Pre-buffer 300–500ms; tune on real accent |
| VAD integration | Whisper hallucination on loose VAD (Pitfall 2) | Add post-transcription hallucination filter |
| VAD + MLX Whisper combined | Metal resource contention (Pitfall 8) | Force Silero to CPU; test first inference timing |
| MLX Whisper integration | Memory leak with word_timestamps (Pitfall 1) | Set cache limit before first call |
| MLX Whisper integration | clip_timestamps slowdown (Pitfall 6) | Never use clip_timestamps in streaming path |
| MLX Whisper integration | Model load timeout fires too early (Pitfall 10) | Raise timeout to 120s; emit "compiling" status |
| Transcriber replacement | TranscriptionUpdate contract mismatch → Telegram silent (Pitfall 3, 9) | Define dataclass contract first; write unit test |
| IPC cleanup | New fields break Swift decoder silently (Pitfall 4) | Document schema; add only optional fields first |
| Config consolidation | AppStorage key mismatch (Pitfall 13) | Treat start command payload as the contract |
| Telegram integration | Draft rate limiting (Pitfall 11) | Keep _DRAFT_INTERVAL >= 0.5s; handle 429 |
| Error hardening | Fork vs spawn for subprocess (Pitfall 12) | spawn start method before any MLX import |
| Any phase | print() in src/ corrupts IPC stream (Pitfall 14) | Replace print() with log; validate JSON output |

---

## Sources

- [mlx-examples issue #1254 — word_timestamps memory leak](https://github.com/ml-explore/mlx-examples/issues/1254) — HIGH confidence (maintainer confirmed)
- [mlx-examples discussion #1275 — clip_timestamps slowdown](https://github.com/ml-explore/mlx-examples/discussions/1275) — HIGH confidence (maintainer identified root cause)
- [mlx-examples issue #1285 — unexpected processing times](https://github.com/ml-explore/mlx-examples/issues/1285) — HIGH confidence
- [mlx issue #755 — Memory leak in MLX/Metal/MPS](https://github.com/ml-explore/mlx/issues/755) — MEDIUM confidence
- [mlx issue #2457 — multiprocessing queues with mx.array](https://github.com/ml-explore/mlx/issues/2457) — HIGH confidence (spawn vs fork)
- [Silero VAD GitHub — snakers4/silero-vad](https://github.com/snakers4/silero-vad) — HIGH confidence (official)
- [LiveKit Silero VAD plugin — prefix_padding_duration](https://docs.livekit.io/agents/logic/turns/vad/) — MEDIUM confidence
- [Whisper hallucination discussion — openai/whisper #679](https://github.com/openai/whisper/discussions/679) — HIGH confidence (confirmed pattern)
- [WhisperLive issue #185 — hallucination on near-threshold noise](https://github.com/collabora/WhisperLive/issues/185) — MEDIUM confidence
- [Telegram Bot API 9.5 sendMessageDraft](https://core.telegram.org/bots/api-changelog) — HIGH confidence (official)
- Codebase analysis of `server.py`, `telegram_sender.py`, `transcriber.py`, `audio_capture.py` — HIGH confidence (direct observation)
- The Professor codebase patterns (same developer, same hardware) — HIGH confidence (production-validated)
