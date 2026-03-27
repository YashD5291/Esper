---
phase: 04-whisper-integration
plan: 03
subsystem: swift-app
tags: [swift, swiftui, protocol, data-model, transcription]
dependency_graph:
  requires: [04-01]
  provides: [swift-app-whisper-compatibility]
  affects: [EsperApp]
tech_stack:
  added: []
  patterns: [exhaustive-switch-on-enum, isLoading-computed-property]
key_files:
  created: []
  modified:
    - EsperApp/EsperApp/Models/Protocol.swift
    - EsperApp/EsperApp/Models/AppSettings.swift
    - EsperApp/EsperApp/TranscriptionEngine.swift
    - EsperApp/EsperApp/Views/TranscriptView.swift
    - EsperApp/EsperApp/Views/MainWindowView.swift
    - EsperApp/EsperApp/Views/SettingsView.swift
    - EsperApp/EsperApp/Views/StatusBadge.swift
decisions:
  - StatusBadge.swift had non-exhaustive switch on EngineStatus — updated to handle all 6 cases with orange for loading states and yellow for transcribing
  - isLoading computed property on TranscriptionEngine centralizes the 3-loading-state check rather than repeating switch logic in views
key_decisions:
  - "StatusBadge exhaustive switch fixed as part of Task 2 (Rule 1 deviation — would not compile)"
  - "isLoading computed property pattern chosen over repeating switch in each view"
metrics:
  duration: 6min
  completed: "2026-03-27"
  tasks: 2
  files: 7
requirements: [ARCH-04]
---

# Phase 04 Plan 03: Swift App Whisper Compatibility Summary

Updated SwiftUI app data models, engine, and views to match the new per-utterance transcript shape and 6-case status enum from the Whisper-based backend, removing all Parakeet-era engine picker and buffer settings.

## What Was Built

**Protocol.swift:** Updated EngineStatus with 3 new cases (`downloadingModel`, `compilingShaders`, `transcribing`), updated displayName extension for all 6 cases, replaced `TranscriptionPayload` with per-utterance shape (`text`, `finalizedText`, `sentences: [String]`, `noSpeechProb`, `durationS`), removed `SentencePayload` struct, updated transcript JSON parser to read new fields.

**AppSettings.swift:** Removed `engine` and `bufferSeconds` `@AppStorage` properties (Whisper-only backend, no engine selection).

**TranscriptionEngine.swift:** Replaced `finalizedSentences: [SentencePayload]` and `draftText` with `currentText`, `finalizedText`, and `sentences: [String]`. Removed `engine`/`buffer` keys from `startListening()` data dict. Added `isLoading: Bool` computed property covering `downloadingModel`, `compilingShaders`, `loadingModel`.

**TranscriptView.swift:** Simplified to accept `[String]` sentences only — no more `SentencePayload` or `draftText` display.

**MainWindowView.swift:** Passes `engine.sentences` to `TranscriptView`, replaced `engine.settings.engine.uppercased()` badge with hardcoded `"WHISPER"`, updated `buttonLabel`/`buttonIcon` computed properties to cover all 6 status cases, uses `engine.isLoading` for ProgressView and button `.disabled`.

**SettingsView.swift:** Removed the entire `Section("Engine")` block (Picker + buffer Slider).

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 35836ff | feat(04-03): update Protocol.swift + AppSettings.swift data models |
| Task 2 | 0b1bc0a | feat(04-03): update TranscriptionEngine + views for new per-utterance transcript shape |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed non-exhaustive switch in StatusBadge.swift**
- **Found during:** Task 2 (xcodebuild verification)
- **Issue:** `StatusBadge.color` switch had only 3 cases (`idle`, `loadingModel`, `listening`). Adding 3 new `EngineStatus` cases caused a compile error.
- **Fix:** Updated switch to handle all 6 cases: `.idle` → `.gray`, `.downloadingModel/.compilingShaders/.loadingModel` → `.orange`, `.transcribing` → `.yellow`, `.listening` → `.green`
- **Files modified:** `EsperApp/EsperApp/Views/StatusBadge.swift`
- **Commit:** 0b1bc0a (included in Task 2 commit)

## Known Stubs

None — all data flows wired from backend JSON events through Protocol.swift parsing to TranscriptionEngine properties to TranscriptView rendering.

## Self-Check: PASSED

Files verified:
- FOUND: EsperApp/EsperApp/Models/Protocol.swift
- FOUND: EsperApp/EsperApp/Models/AppSettings.swift
- FOUND: EsperApp/EsperApp/TranscriptionEngine.swift
- FOUND: EsperApp/EsperApp/Views/TranscriptView.swift
- FOUND: EsperApp/EsperApp/Views/MainWindowView.swift
- FOUND: EsperApp/EsperApp/Views/SettingsView.swift
- FOUND: EsperApp/EsperApp/Views/StatusBadge.swift

Commits verified:
- FOUND: 35836ff (Task 1)
- FOUND: 0b1bc0a (Task 2)

Build: xcodebuild exits 0 (BUILD SUCCEEDED)
