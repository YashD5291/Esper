---
phase: 4
slug: whisper-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — Wave 0 installs if needed |
| **Quick run command** | `python -m pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | PIPE-04 | unit | `pytest tests/test_whisper_worker.py -k transcribe` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | PIPE-05 | unit | `pytest tests/test_whisper_worker.py -k subprocess` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | PIPE-06 | unit | `pytest tests/test_whisper_worker.py -k hallucination` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | ARCH-03 | unit | `pytest tests/test_whisper_worker.py -k watchdog` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | ARCH-04 | unit | `pytest tests/test_transcription_update.py` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 2 | ARCH-04 | integration | `pytest tests/test_consumers.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_whisper_worker.py` — stubs for PIPE-04, PIPE-05, PIPE-06, ARCH-03
- [ ] `tests/test_transcription_update.py` — stubs for ARCH-04 (new dataclass)
- [ ] `tests/test_consumers.py` — stubs for consumer migration (telegram, realtime_demo)
- [ ] `tests/conftest.py` — shared fixtures (mock audio, mock subprocess)

*pytest already in requirements.txt — no framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| <3s latency from utterance end | PIPE-04 | Requires live audio + MLX inference timing | Speak a sentence, measure time from silence to transcript appearing |
| Metal shader cold compilation <120s | CLEAN-03 | Requires clean Metal cache state | Delete ~/Library/Caches/com.apple.Metal, start transcription, measure load time |
| 50 utterances without crash | PIPE-05 | Requires extended live session | Run continuous transcription for 50+ utterances, verify no subprocess crash |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
