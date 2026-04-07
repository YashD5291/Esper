# Overlay Reopen via Flow Button

**Date:** 2026-04-07
**Status:** Draft
**Scope:** Add split-zone tap behavior to flow button for reopening dismissed overlay during listening

## Goal

Let users quickly reopen a dismissed overlay during active listening by tapping the left zone of the flow button, without disrupting the stop button or changing idle state behavior.

## Problem

After dismissing the overlay (X button) during a listening session, there is no quick way to reopen it. The user must stop and restart listening to get the overlay back.

## Design

### Split Zones (listening state only)

The flow button's listening state already has two visual regions: the waveform+label area and the stop button. This design makes both tappable independently.

| Zone | Visual | Tap Action |
|------|--------|------------|
| **Left** (waveform + label) | Waveform bars + chevron indicator + "Listening" | Reopens overlay if dismissed. No-op if already visible. |
| **Right** (stop button) | Red square with white inner square | Stops transcription |

### Dismissed Indicator

When the overlay is dismissed during listening, a small **▲ chevron** (SF Symbol `chevron.up`, 9px, blue at 60% opacity) appears between the waveform bars and "Listening" label. The chevron disappears when the overlay becomes visible again.

### State Table

| Engine State | Overlay | Flow Button Appearance | Left Tap | Right Tap |
|---|---|---|---|---|
| Idle | — | Gray dot + "Esper" | Start listening | — |
| Listening | Visible | Waveform + "Listening" + stop | No-op | Stop |
| Listening | Dismissed | Waveform + **▲** + "Listening" + stop | Reopen overlay | Stop |
| Processing | — | Amber dot + "Processing" | — | — |
| Error | — | Red dot + error text | — | — |

### Idle State

No change. Click starts listening, overlay auto-appears. No reopen needed in idle.

## Files

### Modify

- `EsperApp/EsperApp/Views/FlowButtonView.swift`
  - Add `overlayDismissed: Bool` to `FlowButtonViewModel`
  - Add `onReopen: (() -> Void)?` callback to `FlowButtonView`
  - Split listening state body into two tap zones (left HStack + right Button)
  - Show chevron in left zone when `viewModel.overlayDismissed` is true
  - Left zone tap: call `onReopen` if dismissed, no-op otherwise
  - Right zone tap: call `onStop` (unchanged behavior)

- `EsperApp/EsperApp/EsperApp.swift` (OverlayController)
  - In `updateFlowButton()`: set `flowViewModel.overlayDismissed = dismissed` when listening
  - In `ensureFlowButton()`: wire `onReopen` callback to set `dismissed = false`
  - Add `reopenOverlay()` method that sets `dismissed = false` (next poll cycle shows overlay)

### No changes

- `FlowButton.swift` — NSPanel unchanged
- `TranscriptOverlayView.swift` — dismiss X button unchanged
- `TranscriptPanel.swift` — panel behavior unchanged
- `AppSettings.swift` — no new settings
- `MenuBarView.swift` — no changes
- `OverlaySettingsTab.swift` — no changes

## Testing

### Manual Verification

1. Start listening → overlay appears → click X to dismiss → flow button shows ▲ chevron
2. Tap left zone of flow button → overlay reappears, chevron disappears
3. Tap left zone when overlay is already visible → nothing happens
4. Tap stop button (right zone) → stops transcription, works regardless of overlay state
5. Idle state → no chevron, no split zones, click starts listening as before
6. Dismiss overlay → stop listening → start listening again → overlay auto-appears fresh (no stale chevron)
