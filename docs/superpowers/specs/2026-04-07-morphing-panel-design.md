# Morphing Panel — Design Spec

**Date:** 2026-04-07
**Goal:** Unify the flow button and overlay into a single morphing NSPanel that transitions between a compact pill (idle/collapsed) and a full transcript overlay (expanded/listening).

**Motivation:** Users currently see two separate floating windows — a pill-shaped flow button and a transcript overlay. This creates visual clutter and a disconnected experience. A single element that morphs between states is cleaner, more intuitive, and feels premium.

---

## State Machine

```
                 click / start listening
  IDLE PILL ──────────────────────────────► LISTENING PILL
  (160×36)                                   (160×36, green border)
     ▲                                            │
     │                                   auto-expand (~0.5s delay)
     │                                            │
     │                                            ▼
     │         red (stop) + auto-dismiss    EXPANDED OVERLAY
     └──────────────────────────────────── (560×dynamic)
                                                  │
                                          yellow (collapse)
                                                  │
                                                  ▼
                                           LISTENING PILL
                                           (keeps listening)
                                                  │
                                          chevron tap / click
                                                  │
                                                  ▼
                                           EXPANDED OVERLAY
                                           (re-expands)
```

### States

| State | Size | Corner Radius | Background | Border | Content |
|-------|------|---------------|------------|--------|---------|
| Idle Pill | 160×36 | 18pt | black 75% | white 12% | Gray dot + "Esper" |
| Listening Pill | 160×36 | 18pt | black 75% | green 30% | Waveform + "Listening" + separator + stop |
| Expanded Overlay | 560×dynamic | 12pt | black 82% | white 8% | Traffic lights + audio meter + device picker + transcript |

### Transitions

| From | To | Trigger | Animation |
|------|----|---------|-----------|
| Idle Pill | Listening Pill | User clicks pill / starts listening via menu bar / hotkey | Instant: green border, content swap |
| Listening Pill | Expanded Overlay | Automatic after engine is ready (~0.5s) | Spring morph (0.35s, bounce 0.12) |
| Expanded Overlay | Listening Pill | Yellow traffic light (collapse) | Spring morph (0.28s, bounce 0.0) |
| Expanded Overlay | Idle Pill | Red traffic light (stop) | Overlay lingers with transcript (auto-dismiss per settings), then spring collapse to idle pill |
| Listening Pill | Expanded Overlay | Tap left zone / chevron | Spring morph (0.35s, bounce 0.12) |
| Listening Pill | Idle Pill | Stop button on pill | Instant collapse to idle |

---

## Expanded Overlay Layout

### Top Bar (Traffic Lights)

```
┌─────────────────────────────────────────────────────────────┐
│ 🔴 🟡 🟢        ┃████░░░░░░░░┃  MacBook Mic ▾             │
│ stop collapse    audio meter      device picker              │
│  settings                                                    │
├─────────────────────────────────────────────────────────────┤
│ █ This is a preview of the overlay                     ✓    │
│ █ Transcription text will appear here                  ●    │
│ █ Current text being spoken...                         |    │
└─────────────────────────────────────────────────────────────┘
```

**Traffic lights (left):**
- **Red** (12pt circle) — Stop listening. Triggers auto-dismiss → collapse to idle pill.
- **Yellow** (12pt circle) — Collapse to listening pill. Keeps listening.
- **Green** (12pt circle) — Open settings window.

**Right side:**
- Audio level meter (80×3pt, green fill)
- Device picker dropdown (10pt font)

**Spacing:** 7pt between traffic light dots, 12pt right margin after green dot. Standard macOS traffic light positioning.

### Status Strip

Left edge, 3pt wide — same colors as current:
- Listening: green (65% opacity)
- Transcribing: orange
- Idle: gray
- Error: red

### Transcript Area

Unchanged from current `TranscriptOverlayView` — lines with state indicators, auto-scroll, confidence styling.

### Error Bar

Unchanged — red background at bottom when error exists.

---

## Animation Specification

### Approach: NSAnimationContext.animate(with:) + SwiftUI withAnimation

Uses the macOS 15+ WWDC24 API that bridges SwiftUI `Animation` types to AppKit. Both the panel frame and SwiftUI content use the exact same spring parameters for perfect synchronization.

```swift
// Orchestration pattern:
func morphTo(_ newMode: PanelMode) {
    let spring: Animation = newMode == .overlay
        ? .spring(duration: 0.35, bounce: 0.12)   // expand
        : .spring(duration: 0.28, bounce: 0.0)     // collapse

    // SwiftUI content cross-fade
    withAnimation(spring) {
        mode = newMode
    }

    // Panel frame morph (same spring)
    NSAnimationContext.animate(with: spring) {
        panel.animator().setFrame(targetFrame, display: true)
    }
}
```

### Expand Animation (Pill → Overlay)

| Property | From | To | Duration | Easing |
|----------|------|----|----------|--------|
| Width | 160pt | 560pt | 0.35s | spring(bounce: 0.12) |
| Height | 36pt | dynamic | 0.35s | spring(bounce: 0.12) |
| Corner radius | 18pt | 12pt | 0.35s | spring(bounce: 0.12) |
| Background alpha | 0.75 | 0.82 | 0.35s | spring(bounce: 0.12) |
| Border | white 12% | white 8% | 0.35s | spring(bounce: 0.12) |
| Anchor | Bottom edge fixed, grows upward from pill position | | | |

### Collapse Animation (Overlay → Pill)

| Property | From | To | Duration | Easing |
|----------|------|----|----------|--------|
| Width | 560pt | 160pt | 0.28s | spring(bounce: 0.0) |
| Height | dynamic | 36pt | 0.28s | spring(bounce: 0.0) |
| Corner radius | 12pt | 18pt | 0.28s | spring(bounce: 0.0) |
| Background alpha | 0.82 | 0.75 | 0.28s | spring(bounce: 0.0) |
| Border | white 8% | green 30% (listening) or white 12% (stopped) | 0.28s | spring(bounce: 0.0) |
| Anchor | Collapses downward to bottom edge | | | |

### Content Cross-fade

| Element | In Pill | In Overlay | Transition Method |
|---------|---------|------------|-------------------|
| Waveform / Audio meter | Bars (20pt tall) | Level bar (3pt tall) | matchedGeometryEffect |
| Stop button | Red square (16pt) | Red traffic light (12pt circle) | matchedGeometryEffect |
| "Listening" label | Green text | — | Fade out |
| Chevron (▲) | When dismissed | — | Fade out |
| Traffic lights | — | Red/Yellow/Green dots | Fade in |
| Transcript text | — | ScrollView | Fade in + scale(0.97) |
| Device picker | — | Dropdown | Fade in |
| Status strip | — | Left edge bar | Fade in |

### Layer Property Animation

Corner radius, background color, and border color are animated via `CAAnimationGroup` synchronized with the frame animation:

```swift
func animateLayerProperties(cornerRadius: CGFloat, borderColor: CGColor,
                            backgroundColor: CGColor, duration: TimeInterval) {
    let current = backgroundLayer.presentation() ?? backgroundLayer

    let cornerAnim = CABasicAnimation(keyPath: "cornerRadius")
    cornerAnim.fromValue = current.cornerRadius

    let borderAnim = CABasicAnimation(keyPath: "borderColor")
    borderAnim.fromValue = current.borderColor

    let bgAnim = CABasicAnimation(keyPath: "backgroundColor")
    bgAnim.fromValue = current.backgroundColor

    let group = CAAnimationGroup()
    group.animations = [cornerAnim, borderAnim, bgAnim]
    group.duration = duration
    group.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)

    // Set model values first
    backgroundLayer.cornerRadius = cornerRadius
    backgroundLayer.borderColor = borderColor
    backgroundLayer.backgroundColor = backgroundColor

    backgroundLayer.add(group, forKey: "morphTransition")
}
```

Reading from `presentation()` layer enables smooth mid-animation interruption — no snap if the user reverses direction.

### Retargetability

Spring animations in SwiftUI are inherently retargetable. If the user taps collapse mid-expand, the animation reverses from its current position with preserved velocity. No special handling needed — this is built into `withAnimation(.spring(...))`.

### Accessibility: Reduce Motion

When `NSWorkspace.shared.accessibilityDisplayShouldReduceMotion` is true:
- Skip the spring morph entirely
- Instant frame change + 0.15s opacity cross-fade only
- No matchedGeometryEffect movement

---

## Positioning

### Pill Position
- Bottom of screen, 16pt above visible screen minimum
- Horizontally: centered by default, user-draggable (horizontal only, constrained to bottom edge)
- Saved to `settings.flowButtonX`

### Overlay Expansion
- Expands **upward from the pill's current position**
- Bottom edge stays anchored at pill's Y position
- Horizontally centered on pill's center X
- If overlay would extend off-screen, clamp to screen bounds

### Position Persistence
- Pill X position: saved to UserDefaults (`flowButtonX`)
- Overlay always expands from pill, no separate overlay position needed
- Simplifies settings — removes `overlayDragX`, `overlayDragY`, `overlayPosition` settings

---

## Architecture

### Files to Delete
- `FlowButton.swift` — replaced by EsperPanel
- `Views/FlowButtonView.swift` — replaced by EsperPanelView pill mode

### Files to Create
- **`EsperPanel.swift`** — unified NSPanel subclass
  - Combines FlowButton and TranscriptPanel functionality
  - Single background layer with animatable properties
  - `morphTo(_:)` method orchestrates frame + layer + SwiftUI animation
  - Mouse tracking, drag handling, context menu
  - Bottom-edge anchored positioning

- **`Views/EsperPanelView.swift`** — unified SwiftUI view
  - `@Observable EsperPanelViewModel` with mode (.pill / .overlay), engineStatus, energyLevel, transcript lines, etc.
  - Uses `@Namespace` for matchedGeometryEffect between states
  - `ZStack` with `if mode == .pill { PillContent } else { OverlayContent }`
  - `.transition(.opacity)` for cross-fade
  - Callbacks: `onToggle`, `onStop`, `onCollapse`, `onReopen`, `onSelectDevice`, `onOpenSettings`

### Files to Modify
- **`EsperApp.swift` (OverlayController)** — simplify to manage one panel
  - Remove separate FlowButton management
  - Merge FlowButtonViewModel and OverlayViewModel into EsperPanelViewModel
  - `morphTo(.overlay)` when engine starts listening
  - `morphTo(.pill)` on collapse/dismiss
  - Remove `panelCreated`/`flowButtonCreated` — just `panelCreated`

- **`Views/TranscriptOverlayView.swift`** — scope `disablesAnimations`
  - Move `.transaction { $0.disablesAnimations = true }` from the entire view to only the transcript ScrollView content
  - Chrome/container must be free to animate for the morph

- **`Models/AppSettings.swift`** — clean up position settings
  - Remove `overlayDragX`, `overlayDragY` (overlay position derived from pill)
  - Keep `flowButtonX` for pill horizontal position

### View Model Consolidation

```swift
@Observable
@MainActor
final class EsperPanelViewModel {
    // Panel state
    var mode: PanelMode = .pill       // .pill or .overlay
    var engineStatus: EngineStatus = .idle
    var energyLevel: Double = 0.0
    var errorMessage: String?

    // Overlay content
    var lines: [OverlayLine] = []
    var fontSize: CGFloat = 15
    var textColor: Color = .white
    var opacity: Double = 1.0
    var maxLines: Int = 3
    var showTelegramStatus: Bool = true

    // Device selection
    var devices: [AudioDevice] = []
    var selectedDevice: Int? = nil

    // Callbacks
    var onSelectDevice: ((Int) -> Void)?
    var onOpenSettings: (() -> Void)?
}
```

---

## Fallback Approaches

If approach C (single morphing panel) proves problematic during implementation:

### Fallback A: Expand Upward In Place (Two Panels)
- Keep FlowButton and TranscriptPanel as separate NSPanels
- When expanding: fade out FlowButton while fading in TranscriptPanel at the same position
- Simpler architecture (no single-panel morph) but less fluid animation
- No matchedGeometryEffect possible across panels

### Fallback B: Fly to Overlay Position (Two Panels)
- FlowButton at bottom, TranscriptPanel at configurable position
- Expansion: FlowButton flies to overlay position while morphing shape
- Most complex animation (translate + scale + morph across two panels)
- Preserves user's overlay position preference but highest implementation risk

### Fallback: Display-Link-Driven Spring (Pre-macOS 15)
If `NSAnimationContext.animate(with:)` doesn't work as expected:
- Use `CADisplayLink` / `NSWindow.displayLink(target:selector:)` to drive a manual spring solver
- Evaluate spring physics each frame, call `setFrame(_:display:false)` directly
- Update layer properties in `CATransaction` with disabled actions
- Same visual result but more code. Reference: CocoaSprings (MacPaw), Advance (timdonnelly).

Spring parameters for display-link fallback:
- Stiffness: 280, Damping: 26, Mass: 1.0 (expand — slight overshoot)
- Stiffness: 280, Damping: 34, Mass: 1.0 (collapse — critically damped)

---

## Behavioral Details

### Auto-Fade (Idle Pill Only)
- Pill fades to 40% opacity after 5 seconds of no mouse hover (same as current FlowButton)
- Mouse enter: animate to 100% opacity
- Does NOT apply to expanded overlay — overlay stays at full opacity while visible

### Dragging
- **Pill state:** horizontal-only drag along bottom edge (same as current FlowButton)
- **Expanded overlay:** NOT draggable. Position is derived from pill. This simplifies the unified panel.
- Overlay position settings (overlayDragX/Y, overlayPosition presets) are removed.

### Context Menu (Right-Click)
- **Pill state:** "Settings..." only (same as current FlowButton)
- **Expanded overlay:** Text Size, Opacity, Preset, Lock Position (locks pill drag), Settings (same as current overlay, minus Position submenu since position is pill-derived)

---

## Edge Cases

1. **Rapid toggle:** User starts listening then immediately stops before overlay expands. Cancel the pending expansion, stay as pill, transition to idle.

2. **Auto-dismiss during listening:** If user has auto-dismiss enabled and overlay is showing post-stop content, the auto-dismiss timer triggers collapse to idle pill after configured seconds.

3. **Screen change:** If the display arrangement changes (external monitor connected/disconnected), reposition pill to primary screen bottom center.

4. **First launch:** No saved `flowButtonX` — pill appears centered at bottom of main screen.

5. **Model loading states:** `.downloadingModel`, `.compilingShaders`, `.loadingModel` all show the listening pill immediately (waveform + "Listening") — same as current behavior. Expansion to overlay happens once engine reaches `.listening`.

6. **Error during listening:** Error bar appears in expanded overlay. If collapsed to pill, pill shows red dot + truncated error (same as current).
