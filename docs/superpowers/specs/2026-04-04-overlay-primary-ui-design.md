# Overlay as Primary UI + Flow Button

**Date:** 2026-04-04
**Status:** Draft
**Scope:** Remove main window, add Wispr-inspired flow button, promote overlay to primary app surface

## Goal

Transform Esper from a windowed app with a floating overlay into a menu-bar + flow-button + overlay app. The main window is redundant now that the overlay shows full transcript history. Replace it with a compact flow button for start/stop control and move device picker + settings access into the overlay's top bar.

## Architecture

### App Surfaces (After)

| Surface | Purpose |
|---------|---------|
| **Flow Button** | 48px pill at bottom-center. Start/stop listening, status indicator, waveform animation. |
| **Overlay Panel** | Transcript + top bar (audio meter, device picker, gear, dismiss). Primary content surface. |
| **Menu Bar Extra** | Simplified controls: status, start/stop, show/hide overlay, show/hide flow button, settings, quit. |
| **Settings Window** | Unchanged (accessed via gear icon or menu bar). |

### Engine Lifecycle

- `engine.launch()` called in `EsperApp.ensureLaunched()` (triggered by `MenuBarExtra.onAppear`, same as current)
- `WindowGroup("Esper", id: "main")` removed entirely
- `openWindow(id: "main")` calls removed from `EsperApp.init()` and `AppDelegate.applicationShouldHandleReopen`
- Dock icon click opens Settings window
- `LSUIElement` stays `NO` (app visible in dock for discoverability)

## Flow Button

### Implementation

New `FlowButton` class — NSPanel subclass, similar pattern to TranscriptPanel:
- `styleMask: [.nonactivatingPanel, .borderless]`
- `level: .floating`, `hidesOnDeactivate: false`
- `collectionBehavior: [.canJoinAllSpaces, .fullScreenAuxiliary]`
- Non-activating (doesn't steal focus from active app)
- Content: `NSHostingView<FlowButtonView>`

### Dimensions

- Height: 36px
- Width: varies by state (~80px idle, ~160px listening)
- Corner radius: 18px (full pill)
- Position: bottom-center of screen, 16px above screen bottom edge
- Drag: constrained to bottom edge (horizontal only), position persisted in `AppSettings.flowButtonX`

### Visual States

| State | Dot/Icon | Label | Border | Opacity | Animation |
|-------|----------|-------|--------|---------|-----------|
| Idle | 8px gray circle | "Esper" at 50% white | `rgba(255,255,255,0.12)` | Fades to 40% after 5s inactivity, restores on hover | None |
| Listening | 5 white waveform bars (3px wide, animated with audio energy) | "Listening" in green | `rgba(52,199,89,0.3)` | 100% | Breathing glow shadow (green, 2s cycle) + waveform bars |
| Processing | 8px amber circle | "Processing" at 70% white | `rgba(255,159,10,0.3)` | 100% | Amber dot pulses |
| Error | 8px red circle | Error text truncated at 30 chars | `rgba(255,69,58,0.3)` | 100% | None |

### Waveform Bars (Listening State)

5 bars, each 3px wide, 2px gap. Heights animate independently based on `engine.energyLevel`:
- Bar heights map from energy 0.0-1.0 to 4px-20px
- Each bar has a slight phase offset for organic feel
- Animation: spring-based, 0.1s response time

### Stop Button (Listening State)

Red square (16x16px, 3px corner radius) with white inner square (8x8px). Appears to the right of "Listening" label. Click stops listening.

### Interactions

- **Click (idle):** Start listening → overlay appears, button transitions to listening state
- **Click stop button (listening):** Stop listening → button returns to idle, overlay persists
- **Right-click:** Context menu with: device picker (radio items), preset picker, separator, Settings...
- **Drag:** Horizontal only along bottom edge. Persists position to `AppSettings.flowButtonX`.
- **Hover (idle):** Restore from 40% to 100% opacity. Scale 1.0 → 1.05 over 0.15s.
- **Option+Space:** Same as click (global hotkey unchanged)

### Auto-Fade

When idle and no hover for 5 seconds:
- Fade to 40% opacity over 0.5s
- On mouseEntered: restore to 100% over 0.15s

## Overlay Panel Changes

### Top Bar (New)

32px height, always visible when overlay is shown. Contains:

**Left side:**
- Audio level meter: thin horizontal bar (80px wide, 3px tall), green fill proportional to `engine.energyLevel`

**Right side:**
- Device picker: compact dropdown (`NSPopUpButton` style, 11px font, shows current device name truncated to 20 chars)
- Gear icon: 12px, opens Settings window on click
- Dismiss X: 12px, closes overlay (stops showing until next session start or manual re-show)

Styling: `border-bottom: 1px solid rgba(255,255,255,0.06)`, padding 6px 12px.

### Dismiss Behavior

- **Manual (default):** Overlay stays visible after stopping. User clicks X to dismiss, or right-clicks flow button → "Hide Overlay".
- **Auto-dismiss (configurable):** When enabled, overlay fades out N seconds after engine stops. Configurable: 10s, 30s, 60s, 120s.
- **Re-show:** Clicking flow button to start listening always shows overlay. Menu bar "Show Overlay" also works.
- Starting a new session clears previous transcript and shows overlay fresh.

### Error Display

Red bar at bottom of overlay (below transcript area):
- Background: `rgba(255,69,58,0.15)`, top border: `1px solid rgba(255,69,58,0.2)`
- Warning icon + error text, 12px font
- Auto-dismisses when error clears (engine recovery or restart)
- Status strip turns red when error is active

## Menu Bar Simplification

### Remove
- Device picker (moved to overlay top bar + flow button right-click)
- Audio level display
- Error display (moved to overlay)

### Keep
- Status badge + status text
- Start/Stop Listening button
- Show/Hide Overlay toggle
- Check for Updates
- Settings (Cmd+,)
- Quit (Cmd+Q)

### Add
- Show/Hide Flow Button toggle

## Files

### Delete
- `EsperApp/EsperApp/Views/MainWindowView.swift`
- `EsperApp/EsperApp/Views/TranscriptView.swift`
- `EsperApp/EsperApp/Views/AudioLevelMeter.swift`

### Create
- `EsperApp/EsperApp/FlowButton.swift` — NSPanel subclass for pill button (positioning, drag, auto-fade, right-click menu)
- `EsperApp/EsperApp/Views/FlowButtonView.swift` — SwiftUI view (idle/listening/processing/error states, waveform bars, stop button)

### Modify
- `EsperApp/EsperApp/EsperApp.swift` — Remove WindowGroup scene, remove openWindow calls, add FlowButton lifecycle management to OverlayController
- `EsperApp/EsperApp/Views/TranscriptOverlayView.swift` — Add top bar (audio meter + device picker + gear + dismiss X)
- `EsperApp/EsperApp/TranscriptPanel.swift` — Add onDismiss callback
- `EsperApp/EsperApp/Models/AppSettings.swift` — Add: `flowButtonEnabled: Bool = true`, `flowButtonX: Double = -1`, `overlayAutoDismiss: Bool = false`, `overlayAutoDismissSeconds: Int = 30`
- `EsperApp/EsperApp/Views/MenuBarView.swift` — Remove device picker, remove audio level, add flow button toggle
- `EsperApp/EsperApp/Views/OverlaySettingsTab.swift` — Add auto-dismiss settings section, flow button toggle section
- `EsperApp/EsperApp/Views/SettingsView.swift` — Remove reference to MainWindowView if any
- `EsperApp/EsperApp/TranscriptionEngine.swift` — No changes (engine lifecycle already works via ensureLaunched)

### AppDelegate Changes

```swift
func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
    // Dock click opens Settings instead of main window
    NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
    sender.activate(ignoringOtherApps: true)
    return true
}
```

Remove the `reopenMainWindow` notification and its observer.

## Settings Additions

### Overlay Tab (additions)

**Dismiss section:**
- Toggle: "Auto-dismiss after stopping" (default: off)
- When on: picker for seconds (10 / 30 / 60 / 120), default 30

**Flow Button section:**
- Toggle: "Show Flow Button" (default: on)
- Help text: "Floating button for quick start/stop. You can also use Option+Space."

## Testing

### Swift XCTests
- AppSettings defaults for new properties (flowButtonEnabled, flowButtonX, overlayAutoDismiss, overlayAutoDismissSeconds)
- FlowButtonView state rendering (idle/listening/processing/error produce correct visual elements)
- Protocol/engine tests unchanged

### Manual Verification
- App launches with flow button visible, no main window
- Click flow button → starts listening, overlay appears with transcript
- Click stop → button returns to idle, overlay persists
- Click X on overlay → overlay dismisses
- Right-click flow button → device picker, preset, settings
- Drag flow button horizontally → position persists across restarts
- Flow button auto-fades after 5s idle, restores on hover
- Menu bar: start/stop works, show/hide overlay works, show/hide flow button works
- Settings: auto-dismiss toggle works with configured timeout
- Dock click → opens Settings
- Global hotkey (Option+Space) still toggles listening
- Waveform bars animate with audio energy
- Error shows in overlay bottom bar + flow button turns red
- Device picker in overlay top bar changes device
- Gear icon opens settings
