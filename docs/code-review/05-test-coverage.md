# Agent 5: Test Coverage & Quality Review

**Scope**: All files in `tests/` and corresponding `src/` files — coverage gaps, test quality, missing tests, correctness.

**Date**: 2026-03-28

---

## 1. Coverage Summary

| Module | Tests | Coverage | Quality | Integration |
|--------|-------|----------|---------|-------------|
| `config.py` | 24 | ~95% | Excellent | N/A |
| `vad.py` | 13 | ~85% | Good | Partial (synthetic audio only) |
| `transcriber.py` | 16 | ~80% | Good | Partial (no real subprocess) |
| `telegram_sender.py` | 13 | ~75% | Good | Partial (mocked HTTP) |
| `server.py` | 4 | **~15%** | Poor | Only IPC wire format |
| `audio_capture.py` | 0 | **0%** | N/A | Missing |
| `whisper_worker.py` | 0 | **0%** | N/A | Missing |
| `realtime_demo.py` | 0 | **0%** | N/A | Missing |
| **Total** | **71** | **~50%** | **Mixed** | **Poor** |

---

## 2. Completely Untested Modules

### `src/audio_capture.py` — ZERO TESTS

| Function | Status |
|----------|--------|
| `list_devices()` | Untested |
| `find_real_mic()` | Untested (loopback detection logic) |
| `auto_select_device()` | Untested (fallback logic) |
| `AudioCapture.__init__()` | Untested |
| `AudioCapture.start()` | Untested |
| `AudioCapture.stop()` | Untested |
| `AudioCapture.get_chunk()` | Untested (timeout behavior, sentinel) |
| `AudioCapture.energy` | Untested (thread-safe reads) |
| `AudioCapture._callback()` | Untested (RMS calculation, queue.Full) |

### `src/whisper_worker.py` — ZERO TESTS

| Function | Status |
|----------|--------|
| `_whisper_worker()` | Entry point never tested |
| Model loading | Never tested in actual subprocess |
| Audio queue `get()` | Never tested with None sentinel |
| `mlx_whisper.transcribe()` call | Parameters never verified |
| Exception handling | `ImportError` path never tested |

### `src/realtime_demo.py` — ZERO TESTS

| Function | Status |
|----------|--------|
| `ConsoleRenderer` | Never tested |
| CLI argument parsing | Never tested |
| Main loop | Never tested |
| `--record` flag | Never tested |

---

## 3. Partially Tested: `src/server.py` (~15% coverage)

Only IPC wire format tested (`test_server_ipc.py`). **Zero tests for any command handler**:

| Function | Status |
|----------|--------|
| `_list_devices()` | Untested |
| `_do_start()` | **CRITICAL** — full pipeline untested |
| `_do_stop()` | **CRITICAL** — cleanup sequence untested |
| `_do_set_device()` | Untested (hot-swap logic) |
| `_do_test_telegram()` | Untested |
| `_whisper_consumer()` | **CRITICAL** — core VAD->Whisper bridge untested |
| `_emit_energy()` | Untested |
| Command parsing main loop | Untested |
| JSON error handling | Untested |
| SIGTERM handler | Untested |

---

## 4. Test Quality Issues

### Issue A: Mock Models Don't Match Real Interfaces

`test_vad.py:39-44`:
```python
def make_mock_model(speech_prob: float = 0.9) -> MagicMock:
    model = MagicMock()
    model.return_value.item.return_value = speech_prob
```

- Mock doesn't verify actual tensor shapes
- `model.reset_states()` mocked but never verified to be called at right time
- Real Silero model is a torch object with different interface

### Issue B: Subprocess Tests Never Spawn Real Processes

`test_whisper_transcriber.py` patches `multiprocessing.get_context()` everywhere:
- Never tests spawn context actually works
- Never tests Queue pickling
- Never tests subprocess lifecycle
- Never tests IPC between parent and child
- If implementation changes from `SimpleQueue` to `Queue`, tests still pass

### Issue C: Tests That Always Pass

`test_config.py:158-164`:
```python
def test_chunk_samples_derived_correctly():
    config = get_config()
    expected = int(config.SAMPLE_RATE * config.CHUNK_DURATION)
    assert config.CHUNK_SAMPLES == expected
```
Reads from the same module — can't catch if value is wrong. Should hardcode expected value.

### Issue D: Private Implementation Details Tested

`test_telegram_sender.py:145-158`:
```python
item = sender._queue.get(timeout=0.5)
assert isinstance(item, str)
```
Accesses `_queue` (private). If queue is refactored to a list, test breaks even if behavior is correct.

### Issue E: Mock Side-Effects Don't Verify Call Order

`test_telegram_sender.py:164-190` — verifies `time.sleep(1)` was called but doesn't verify it was called *before* retry. Real behavior: test passes if sleep happens anywhere in the code.

---

## 5. Missing Critical Tests

### No Integration Tests (None Exist)

1. **Full pipeline round-trip**: command -> capture -> VAD -> Whisper -> event
2. **Concurrent commands**: start + set_device simultaneously
3. **Shutdown during transcription**
4. **Malformed command handling**
5. **Real subprocess spawn**: model loading in child, parent/child communication failure

### Missing Edge Cases

**VAD**:
- Audio exactly at energy threshold
- Utterance exactly at minimum duration
- Queue.Full during post-buffer collection
- Exception during processing

**Telegram**:
- `retry_after` missing from 429 response
- `retry_after` is 0 or non-numeric
- `httpx.Client()` constructor raises
- `resp.json()` raises JSONDecodeError

**Transcriber**:
- Concurrent `stop()` and `transcribe_utterance()`
- Worker crashes during first ready sentinel wait
- Queue deadlock scenarios

---

## 6. Test/Config Mismatch (Critical)

6 config values changed in production but tests still assert old values:

| Config | Current | Test expects | Test file:line |
|--------|---------|-------------|----------------|
| `VAD_SPEECH_THRESHOLD` | 0.3 | 0.5 | `test_config.py:57` |
| `VAD_SILENCE_THRESHOLD_MS` | 300 | 500 | `test_config.py:62` |
| `VAD_MIN_SPEECH_DURATION_MS` | 100 | 500 | `test_config.py:67` |
| `VAD_MIN_ENERGY` | 0.003 | 0.01 | `test_config.py:72` |
| `WHISPER_NO_SPEECH_THRESHOLD` | 0.8 | 0.6 | `test_whisper_transcriber.py:97` |
| `WHISPER_COMPRESSION_RATIO_THRESHOLD` | 3.0 | 2.4 | `test_whisper_transcriber.py:98` |

---

## 7. Untested Functions in Tested Modules

### `src/vad.py`
- `VadThread._run()` exception handling (line 139-140)
- `VadThread.stop()` — only indirectly tested
- `VadThread.wait()` timeout behavior
- State machine transitions: pre-buffer + post-buffer combined

### `src/transcriber.py`
- `WhisperTranscriber.stop()` in isolation
- `WhisperTranscriber.wait()`
- `_whisper_worker_entry()` wrapper
- Queue deadlock scenarios
- Generation counter overflow (>= MAX_GENERATIONS)

### `src/telegram_sender.py`
- Thread lifecycle (daemon thread actually starts)
- `_loop()` exception handling
- `stop()` and `on_update()` race condition
- Backoff reset after success
- Client timeout exceeded

---

## Recommendations

### Critical (Fix Immediately)
1. Update 6 test values to match current config
2. Add integration test for full server pipeline (`tests/test_integration.py`)
3. Add tests for `audio_capture.py` (`tests/test_audio_capture.py`)
4. Add tests for `_whisper_consumer()` in server.py

### High Priority
5. Add tests for `_do_start()` and `_do_stop()` commands
6. Add Whisper worker subprocess tests
7. Add VAD edge case tests (threshold boundaries)
8. Add Telegram edge case tests (missing retry_after)

### Medium Priority
9. Replace circular config test with hardcoded expected value
10. Add tests for `realtime_demo.py` CLI
11. Add concurrent `_send()` test to catch interleaving bug
12. Refactor test fixtures to reduce duplication
