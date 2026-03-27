---
phase: 2
slug: ipc-cleanup
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-27
---

# Phase 2 -- Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (tests/ directory created in Phase 1) |
| **Config file** | none |
| **Quick run command** | `pytest tests/test_server_ipc.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** `grep -n "os.dup" src/server.py` (must exit 1 = no matches)
- **After every plan wave:** `pytest tests/test_server_ipc.py -x`
- **Before `/gsd:verify-work`:** Full suite must be green + manual SwiftUI launch test
- **Max feedback latency:** 5 seconds (for Python tests; xcodebuild cold builds are one-time ~30s but incremental builds are under 5s)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | ARCH-02 | unit | `pytest tests/test_server_ipc.py::test_protocol_fd_mode -x` | W0 (created in TDD RED phase) | pending |
| 02-01-02 | 01 | 1 | ARCH-02 | static | `grep -n "os.dup2" src/server.py; test $? -eq 1` | N/A | pending |
| 02-01-03 | 01 | 1 | ARCH-02 | static | `python -c "import ast; tree=ast.parse(open('src/server.py').read()); assert not any(isinstance(n,ast.Call) and getattr(n.func,'id','')==='print' for n in ast.walk(tree))"` | N/A | pending |
| 02-02-01 | 02 | 2 | INTG-03 | build | `xcodebuild ... build 2>&1 \| grep -E '(BUILD SUCCEEDED\|BUILD FAILED\|error:)'` | N/A | pending |
| 02-02-02 | 02 | 2 | INTG-03 | manual | Build Xcode app, launch, observe idle event within 3s | N/A | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [x] `tests/test_server_ipc.py` -- created as first action in Plan 01's TDD RED phase (no separate Wave 0 plan needed)
- [x] pytest available in venv (`.venv/bin/pytest`) -- confirmed present from Phase 1

*Wave 0 is satisfied by the TDD task's RED phase, which creates the test file before any GREEN implementation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| ProcessBridge passes --protocol-fd and receives idle event | INTG-03 | Requires Xcode build + SwiftUI app launch | 1. Build EsperApp in Xcode 2. Launch app 3. Verify idle status appears in UI within 3s |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s (Python tests; xcodebuild incremental builds < 5s, cold builds one-time)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved
