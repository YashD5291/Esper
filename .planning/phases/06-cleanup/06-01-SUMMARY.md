---
phase: 06-cleanup
plan: 01
subsystem: cleanup
tags: [cleanup, dead-code, parakeet, coreml, dependencies]
dependency_graph:
  requires: []
  provides: [clean-codebase, whisper-only-architecture]
  affects: [src/transcriber.py, src/config.py, src/server.py, requirements.txt]
tech_stack:
  added: []
  patterns: [delete-dead-code, tdd-absence-assertions]
key_files:
  created:
    - tests/test_cleanup.py
  modified:
    - src/transcriber.py
    - src/config.py
    - src/server.py
    - tests/test_config.py
    - tests/test_whisper_transcriber.py
    - requirements.txt
  deleted:
    - src/coreml_transcriber.py
    - tests/test_stt.py
    - models/coreml/ (untracked, deleted from disk)
decisions:
  - requirements.txt cleaned in Task 1 commit alongside code changes (tests required it to pass)
  - models/coreml/ was gitignored (entire models/ dir ignored) — removed from disk only, no git rm needed
metrics:
  duration: 5min
  completed: 2026-03-27
  tasks: 2
  files: 8
---

# Phase 6 Plan 1: Parakeet/CoreML Dead Code Removal Summary

**One-liner:** Deleted Parakeet transcriber, CoreML models, stale test file, backward-compat fields, engine selection globals, and 3 dead pip dependencies — codebase now Whisper-only.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write cleanup assertions, delete dead files, remove stale code | 7984940 | tests/test_cleanup.py (new), src/coreml_transcriber.py (deleted), tests/test_stt.py (deleted), src/transcriber.py, src/config.py, src/server.py, tests/test_config.py, tests/test_whisper_transcriber.py |
| 2 | Remove dead dependencies and verify clean install | 7e4c161 | requirements.txt |

## What Was Done

### Task 1: Dead Code Removal (TDD)

**RED phase:** Created `tests/test_cleanup.py` with 11 assertions verifying absence of dead code. All 10 non-requirements tests failed (1 passed: `test_existing_tests_pass` already passed since it runs the broader suite).

**GREEN phase:**
- `git rm src/coreml_transcriber.py` — deleted Parakeet/CoreML transcription engine
- `git rm tests/test_stt.py` — deleted Parakeet-specific test suite
- `rm -rf models/coreml/` — removed CoreML model artifacts from disk (directory was gitignored)
- Removed backward-compat fields `draft_text`, `finalized_sentences`, `draft_sentences` from `TranscriptionUpdate` dataclass
- Removed backward-compat docstring block from `TranscriptionUpdate`
- Removed `DEFAULT_ENGINE: str = "coreml"` from `src/config.py`
- Removed `_engine_name: str = "whisper"` global from `src/server.py`
- Removed `engine = data.get("engine", ...)` and `_engine_name = engine` from `_do_start()` in `src/server.py`
- Removed `_engine_name` from global statement in `_do_start()`
- Updated log.info in `_do_start()` from `"Starting: engine=%s, device=%s"` to `"Starting: device=%s"`
- Deleted `test_default_engine` from `tests/test_config.py`
- Removed backward-compat field assertions from `test_transcription_update_fields` in `tests/test_whisper_transcriber.py`
- Deleted `test_transcription_update_backward_compat` from `tests/test_whisper_transcriber.py`
- Cleaned `requirements.txt` (parakeet-mlx, coremltools, scipy removed)

**Result:** 71 tests pass.

### Task 2: Dependency Cleanup Verification

- Confirmed `pip install -r requirements.txt` completes cleanly
- Confirmed `from src.transcriber import TranscriptionUpdate, WhisperTranscriber` imports successfully
- All 11 cleanup tests pass

## Verification Results

```
Dead files removed: src/coreml_transcriber.py, models/coreml/, tests/test_stt.py
No stale references in .py files (coreml_transcriber, DEFAULT_ENGINE, _engine_name)
71 passed in 20.46s
All clean (import chain + no DEFAULT_ENGINE)
```

## Deviations from Plan

### Minor scheduling deviation

**Found during:** Task 1
**Issue:** `test_cleanup.py` includes requirements assertions (`test_no_parakeet_in_requirements`, etc.) and `pytest tests/ -x -q` runs all cleanup tests as the Task 1 verify step. Editing requirements.txt in Task 2 would have caused Task 1 verify to fail on those assertions.
**Fix:** Cleaned `requirements.txt` in Task 1 alongside the code changes. Task 2 commit covers only the verification confirmation (requirements.txt diff was staged and committed in Task 2).
**Impact:** None — all success criteria met, both commits exist.

### models/coreml/ not tracked by git

**Found during:** Task 1
**Issue:** `git rm -r models/coreml/` failed — entire `models/` directory is in `.gitignore`.
**Fix:** Removed directory from disk with `rm -rf models/coreml/`. Test assertion (`test_no_coreml_models_dir`) checks filesystem existence, not git tracking — passes correctly.

## Known Stubs

None.

## Self-Check: PASSED
