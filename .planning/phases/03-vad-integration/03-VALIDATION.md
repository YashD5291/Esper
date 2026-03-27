---
phase: 3
slug: vad-integration
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-27
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | none — run from project root |
| **Quick run command** | `python -m pytest tests/test_vad.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

Baseline: 29 tests pass (test_config.py + test_server_ipc.py).

---

## Sampling Rate

- **After every task commit:** `python -m pytest tests/test_config.py -q`
- **After every plan wave:** `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | PIPE-01 | unit | `pytest tests/test_vad.py::test_silence_produces_no_utterance -x` | W0 (TDD RED) | ⬜ pending |
| 03-01-02 | 01 | 1 | PIPE-02 | unit | `pytest tests/test_vad.py::test_prebuffer_prepended_to_utterance -x` | W0 (TDD RED) | ⬜ pending |
| 03-01-03 | 01 | 1 | PIPE-03 | unit | `pytest tests/test_vad.py::test_low_energy_frames_rejected -x` | W0 (TDD RED) | ⬜ pending |
| 03-01-04 | 01 | 1 | D-08 | unit | `pytest tests/test_vad.py::test_short_utterance_discarded -x` | W0 (TDD RED) | ⬜ pending |
| 03-02-01 | 02 | 2 | D-01 | unit | `pytest tests/test_config.py::test_chunk_samples -x` | Existing (update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_vad.py` — created in TDD RED phase of Plan 01
- [x] pytest available in venv — confirmed from Phase 1
- [x] `silero-vad`, `torch`, `torchaudio` — installed as first task action

*Wave 0 is satisfied by dependency installation + TDD RED phase.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real mic speech produces utterances | PIPE-01 | Requires live audio input | 1. Run realtime_demo.py 2. Speak a sentence, pause 2s, speak again 3. Verify two separate utterances appear |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved
