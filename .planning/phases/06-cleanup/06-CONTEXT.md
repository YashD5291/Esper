# Phase 6: Cleanup - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove all Parakeet/CoreML code, model artifacts, and dead dependencies from the codebase. After this phase, only the v2.0 Whisper-based architecture remains. The dual-engine abstraction is eliminated — Whisper is the only transcription engine.

</domain>

<decisions>
## Implementation Decisions

### File deletion
- **D-01:** Delete `src/coreml_transcriber.py` entirely — all CoreML/Parakeet inference code.
- **D-02:** Delete `src/transcriber.py` entirely — MLX Parakeet engine and the old `TranscriptionUpdate` dataclass (replaced in Phase 4).
- **D-03:** Delete `models/coreml/` directory and all contents via `git rm -r`. Do NOT rewrite git history — the models aren't secret, and history rewriting is destructive/complex for no real benefit.
- **D-04:** Delete `tests/test_stt.py` entirely — it's a Parakeet-specific smoke test. Whisper testing belongs in Phase 4's test suite.

### Dual-engine removal
- **D-05:** Remove `--engine` CLI flag from `realtime_demo.py` entirely. No engine choice — Whisper is the only backend.
- **D-06:** Remove `--buffer` CLI arg from `realtime_demo.py` — it was CoreML-specific (chunk buffering).
- **D-07:** Remove dual-engine branching in `server.py` (lines 153-162) — no CoreML/MLX conditional imports.
- **D-08:** Remove `DEFAULT_ENGINE` from `config.py` — no engine selection concept.

### SwiftUI updates
- **D-09:** Remove `engine` @AppStorage from `AppSettings.swift` — no engine picker needed.
- **D-10:** Remove engine picker section and CoreML-specific UI from `SettingsView.swift`.

### Dependency cleanup
- **D-11:** Remove `parakeet-mlx` from `requirements.txt`.
- **D-12:** Remove `coremltools` from `requirements.txt`.
- **D-13:** Remove explicit `scipy` pin from `requirements.txt` — it was a transitive dependency of Parakeet.

### Test updates
- **D-14:** Update `tests/test_config.py` to remove `DEFAULT_ENGINE` assertion (line 143).
- **D-15:** Verify no remaining imports reference `coreml_transcriber` or `transcriber` (old module) anywhere.

### Dead config sweep
- **D-16:** Remove any dead config constants from `config.py` that became obsolete in prior phases but weren't cleaned up (e.g., `DEFAULT_ENGINE`). Phase 5 should have already handled `TELEGRAM_DRAFT_INTERVAL` and `TELEGRAM_STREAM` — verify and clean if not.

### Claude's Discretion
- Order of operations for deletion vs. update (whatever minimizes broken intermediate states)
- Whether to consolidate remaining test files or leave as-is
- Any additional dead imports discovered during cleanup

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — CLEAN-01 (delete transcriber files), CLEAN-02 (remove dead deps)

### Files to delete
- `src/coreml_transcriber.py` — CoreML Parakeet engine (380 lines)
- `src/transcriber.py` — MLX Parakeet engine + old TranscriptionUpdate
- `models/coreml/` — Compiled ML model bundles (~12 files)
- `tests/test_stt.py` — Parakeet-specific smoke test

### Files to update
- `src/server.py` — Dual-engine branching at lines 153-162, imports at line 32
- `src/realtime_demo.py` — `--engine` flag (line 89), `--buffer` arg (line 91), CoreML branch (lines 137-147), MLX branch (lines 154-162), imports (line 30, 138)
- `src/config.py` — `DEFAULT_ENGINE` at line 39
- `EsperApp/EsperApp/Models/AppSettings.swift` — `engine` @AppStorage at line 7
- `EsperApp/EsperApp/Views/SettingsView.swift` — Engine picker at lines 70-76
- `tests/test_config.py` — `DEFAULT_ENGINE` assertion at line 143
- `requirements.txt` — Remove `parakeet-mlx`, `coremltools`, `scipy`

### Prior phase context
- `.planning/phases/04-whisper-integration/04-CONTEXT.md` — D-01 defines new TranscriptionUpdate, D-03 defines per-utterance Telegram model
- `.planning/phases/05-telegram-hardening/05-CONTEXT.md` — Dead Telegram config cleanup

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — this phase removes code, doesn't add any

### Established Patterns
- `git rm -r` for tracked directory removal
- Module-import pattern in `config.py` — just delete the dead constants
- Entry-point mutation pattern — simplify `_do_start()` once dual-engine branching is gone

### Integration Points
- `server.py _load_model_with_timeout()` — after Phase 4, this loads Whisper only. Remove CoreML branch.
- `realtime_demo.py main()` — after Phase 4, this uses Whisper only. Remove engine selection entirely.
- SwiftUI `AppSettings.engine` — referenced by ProcessBridge for `start` command. Phase 4 SwiftUI updates should have already simplified this. Verify and clean.

</code_context>

<specifics>
## Specific Ideas

- User deferred all technical decisions — Claude has full discretion on cleanup implementation
- `models/coreml/` stays in git history (no rewrite) — just `git rm -r`

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-cleanup*
*Context gathered: 2026-03-27*
