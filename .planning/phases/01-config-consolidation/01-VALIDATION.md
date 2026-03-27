---
phase: 1
slug: config-consolidation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None — smoke commands only (no test framework in project) |
| **Config file** | none — Wave 0 creates smoke scripts |
| **Quick run command** | `python -c "from src import config; print('config OK')"` |
| **Full suite command** | `python -c "from src.config import SAMPLE_RATE, VAD_FRAME_SIZE, WHISPER_MODEL_REPO, TELEGRAM_DRAFT_INTERVAL, ENERGY_EMIT_INTERVAL_S; print('all namespaces OK')"` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -c "from src import config; print('config OK')"`
- **After every plan wave:** Run full suite command + IPC JSON-parse test
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | ARCH-01 SC1 | smoke | `python -c "from src import config; assert config.SAMPLE_RATE == 16000"` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | ARCH-01 SC2 | manual | Start server, send start with telegram dict, verify no .env needed | N/A | ⬜ pending |
| 01-01-03 | 01 | 1 | ARCH-01 SC3 | smoke | `python -c "import ast; tree=ast.parse(open('src/audio_capture.py').read()); assert not any(isinstance(n,ast.Call) and getattr(n.func,'id','')==='print' for n in ast.walk(tree))"` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | ARCH-01 SC4 | smoke | `python -c "from src.config import VAD_FRAME_SIZE, WHISPER_MODEL_REPO, TELEGRAM_DRAFT_INTERVAL, ENERGY_EMIT_INTERVAL_S"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Smoke import test: `python -c "from src import config; assert config.SAMPLE_RATE == 16000"`
- [ ] Namespace presence test: `python -c "from src.config import VAD_FRAME_SIZE, WHISPER_MODEL_REPO, TELEGRAM_DRAFT_INTERVAL, ENERGY_EMIT_INTERVAL_S"`
- [ ] IPC JSON-parse smoke: `echo '{}' | python -m src.server 2>/dev/null | head -1 | python -m json.tool`

*No framework install needed — all smoke commands use stdlib only.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Telegram credentials via start command | ARCH-01 SC2 | Requires running SwiftUI app or manual JSON on stdin | 1. Start `python -m src.server` 2. Send `{"command":"start","data":{"telegram":{"bot_token":"test","chat_id":"test"}}}` 3. Verify config fields populated |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
