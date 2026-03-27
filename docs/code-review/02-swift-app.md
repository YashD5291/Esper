# Agent 2: SwiftUI App Architecture Review

**Scope**: All files in `EsperApp/EsperApp/` — @Observable, @MainActor, ProcessBridge, views, app lifecycle.

**Date**: 2026-03-28

---

## 1. Architecture & Design

### @Observable Pattern
**Status: Correct**

- `TranscriptionEngine` (`TranscriptionEngine.swift:5`) and `AppSettings` (`AppSettings.swift:3`) correctly use `@Observable`
- `@ObservationIgnored` properly applied to `eventTask` (line 23) and `restartAttempts` (line 26-27)
- `AppSettings` correctly marks `@AppStorage` properties with `@ObservationIgnored` (lines 6, 9, 13, 16, 19)

### @MainActor Usage
**Status: Partially Correct**

- `TranscriptionEngine` correctly annotated with `@MainActor` (line 6)
- `ProcessBridge` marked `@unchecked Sendable` (line 5) — problematic (see section 2)
- `handle(_ event:)` at line 150 is called from async stream consumer in `startConsuming()` (line 145). The closure runs in a `Task { [weak self] }` which inherits @MainActor context — technically correct but fragile.

### Separation of Concerns
**Status: Good**

- ProcessBridge: subprocess lifecycle, pipe I/O, protocol parsing only
- TranscriptionEngine: orchestrates bridge, exposes app state
- Views: purely reactive, read engine state, call engine methods
- No circular dependencies

### Retain Cycles
**Status: Clean**

- ProcessBridge has no references to TranscriptionEngine
- Event handler uses `[weak self]` properly (line 141)
- Views pass engine as parameter, no back-references

---

## 2. ProcessBridge.swift (Critical IPC Layer)

### Subprocess Spawning
**Status: Correct**

- Proper `Process` initialization (lines 28-95)
- Environment setup with `PYTHONUNBUFFERED` and `PATH` (lines 35-44)
- All three pipes properly configured

### Pipe Management
**Status: Potential Leak**

1. **stderr readabilityHandler never cleared in `terminate()`** (lines 65-72 set it, lines 116-127 don't clear it)
   - Creates potential retain cycle: `stderrPipe` -> NSFileHandle -> closure -> captured `handle`
   - Fix: Add `stderrPipe?.fileHandleForReading.readabilityHandler = nil` in `terminate()`

2. **Pipes not closed on exception** (lines 88-93)
   - If `proc.run()` throws, catch block yields error but never closes the 3 pipes created at lines 46-48
   - FD leak on launch failure

### Reader Thread
**Status: Potential Deadlock**

1. **`handle.availableData` is blocking** (line 140) — if Python crashes before writing to stdout, thread hangs forever with no timeout
2. **`continuation?.finish()` called off main thread** (line 163) — AsyncStream.Continuation `finish()` from background thread is not explicitly documented as thread-safe
3. **No timeout mechanism** — while loop blocks indefinitely

**Deadlock scenario**: Python blocks on stderr write (full pipe buffer), reader thread waiting on stdout, stderr readabilityHandler waiting to write — process deadlocked.

### AsyncStream Usage
**Status: Correct with caveats**

- Proper initialization (lines 20-23)
- Continuation stored for later use
- `yield()` is documented as thread-safe
- `finish()` from background thread is undocumented — should dispatch to main

### @unchecked Sendable
**Status: Hiding Bugs**

Line 5: `final class ProcessBridge: @unchecked Sendable`

Property access is not synchronized (no locks). Multiple threads access simultaneously:
- Reader thread reads from `eventContinuation`
- Main thread calls `send()` which writes to `stdinPipe`
- View thread calls methods

**Data race scenario**: Main thread calls `send(cmd:)` writing to `stdinPipe` while `terminate()` clears `stdinPipe` simultaneously.

Works in practice because operations are short and don't overlap much, but **not correct** per Swift Concurrency Model.

---

## 3. TranscriptionEngine.swift

### Event Handling
**Status: Complete**

All `ServerEvent` cases handled (lines 150-205):
- `.devices()`, `.status()`, `.transcript()`, `.energy()`, `.telegramSent`, `.telegramTest()`, `.crashed()`, `.error()`, `.unknown`

### Restart Logic
**Status: Robust (minor off-by-one)**

- Max 3 restart attempts enforced (line 28)
- 2-second backoff (line 191)
- Counter resets on successful listening (line 166)
- **Off-by-one**: Line 192 checks `self.restartAttempts <= Self.maxRestartAttempts` — should be `<` not `<=`. Allows 4th restart attempt.

### Race Conditions
**Status: Minimal**

- `launch()` vs `shutdown()` — mitigated by `launched` flag and `eventTask` cancellation
- `startListening` while bridge loading — mitigated by `isRunning` check
- `restart()` called multiple times — no lock, but operations are mostly idempotent

### Memory Management
**Status: Correct**

- Proper `[weak self]` in all Task closures
- `eventTask` stored for cancellation
- Proper cancellation in shutdown

---

## 4. Views

### Reactivity
**Status: Excellent**

All views properly reactive to `@Observable` state. No unnecessary constant computed properties.

### Device Picker
**Status: Correct**

- `MainWindowView:38-50` — proper Binding with custom get/set
- Filters -1 sentinel, calls `setDevice()`

### Re-renders
**Status: Minimal**

- Device list wrapped in `if !engine.devices.isEmpty`
- Error message wrapped in `if let`
- Transcript uses `.id()` for list identity

### Settings Persistence
**Status: Correct**

`@AppStorage` with `@Bindable` — changes auto-save to UserDefaults.

---

## 5. App Lifecycle (EsperApp.swift)

### @State + @Environment Pattern
**Status: Correct**

- `@State` creates persistent engine instance
- `launched` flag prevents double-launch
- Both `onAppear` calls happen on main thread — no data races

### openWindow in init()
**Status: Fragile**

Lines 41-46:
```swift
init() {
    DispatchQueue.main.async { [self] in
        openWindow(id: "main")
    }
}
```

- Captures `self` during init — unconventional
- Creates temporal dependency: if window doesn't open, `onAppear` won't fire, launch won't happen
- Works in practice but not elegant

---

## 6. Protocol.swift / Models

### JSON Parsing
**Status: Good**

- Proper `guard` statements with fallbacks
- Missing data handled gracefully (defaults for channels, isDefault, etc.)
- Unknown events return `.unknown` (silently ignored)

### Edge Cases

1. Transcript parsing: if `sentences` comes as wrong type, returns `nil` — silent failure
2. Device list: malformed device objects silently dropped via `compactMap`
3. Unknown status values silently become `.idle` — could hide bugs

---

## Summary

| Component | Rating | Critical Issues |
|-----------|--------|-----------------|
| Architecture | 8.5/10 | @unchecked Sendable hiding data races |
| ProcessBridge | 6.5/10 | Blocking reader, no timeout, pipe leak on exception |
| TranscriptionEngine | 8.5/10 | Minor off-by-one in restart |
| Views | 9/10 | None |
| App Lifecycle | 7.5/10 | Fragile openWindow in init() |
| Protocol Parsing | 8/10 | Silent parse failures |
