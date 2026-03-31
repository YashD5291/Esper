# Overlay Panel Design Spec

**Date:** 2026-03-31
**Status:** Approved

## Goal

Floating always-on-top overlay that shows live transcription text over all windows, so the user can verify spoken words without switching to Telegram.

## Overlay Panel

### NSPanel Configuration

| Property | Value |
|---|---|
| Class | `TranscriptPanel` (NSPanel subclass) |
| styleMask | `.nonactivatingPanel`, `.borderless`, `.fullSizeContentView` |
| level | `.floating` |
| canBecomeKey | `false` |
| canBecomeMain | `false` |
| ignoresMouseEvents | `true` |
| isFloatingPanel | `true` |
| hidesOnDeactivate | `false` |
| isOpaque | `false` |
| backgroundColor | `.clear` |
| hasShadow | `false` |
| collectionBehavior | `.canJoinAllSpaces`, `.fullScreenAuxiliary`, `.stationary` |

### Content

- Hosted via `NSHostingView` wrapping `TranscriptOverlayView`
- Shows the last N lines (configurable, 1–9) from `engine.sentences` tail + `engine.currentText`
- Text rendered with drop shadow for readability on any background
- Transparent background (no pill, no blur)
- Panel width: ~660pt, height: dynamic based on line count

### Positioning

Six positions on screen, stored as a string enum:

| Value | Screen Position |
|---|---|
| `topLeft` | Top-left corner, inset from edges |
| `topCenter` | Top-center |
| `topRight` | Top-right corner |
| `bottomLeft` | Bottom-left corner |
| `bottomCenter` | Bottom-center (default) |
| `bottomRight` | Bottom-right corner |

Margin from screen edges: 60pt vertical, 40pt horizontal. Repositions when setting changes.

### Visibility

- Panel shows when `overlayEnabled == true` AND `engine.status == .listening`
- Panel hides when overlay is disabled or engine stops listening
- Exception: when Settings overlay tab is open, panel shows with sample text for live preview regardless of listening state

## Settings Storage

New `@AppStorage` keys in `AppSettings`:

| Key | Type | Default | Range |
|---|---|---|---|
| `overlayEnabled` | Bool | `false` | — |
| `overlayPosition` | String | `"bottomCenter"` | 6 enum values |
| `overlayTextSize` | String | `"medium"` | `small` (16pt) / `medium` (20pt) / `large` (26pt) |
| `overlayTextColor` | String | `"#FFFFFF"` | Hex color string |
| `overlayMaxLines` | Int | `3` | 1–9 |
| `overlayOpacity` | Double | `1.0` | 0.3–1.0 |

## Settings UI

### Location

New "Overlay" tab in `SettingsView` — 4th tab after General, Telegram, Advanced.

### Layout (top to bottom)

1. **Toggle** — "Show Overlay" with on/off switch
2. **Position** — Mini screen mockup (16:10 aspect ratio) with 6 clickable dots. Selected dot glows. Tiny preview text shown at selected position.
3. **Appearance section:**
   - **Text Size** — Segmented control: S / M / L
   - **Text Color** — 5 preset swatches (white, green, blue, orange, red) + divider + macOS `ColorPicker` for custom color
   - **Lines** — Numeric stepper with minus/plus buttons, displays current value, range 1–9
   - **Opacity** — Slider from 30% to 100%

### Live Preview

When the overlay tab is active and overlay is enabled, the actual `TranscriptPanel` appears on screen with sample text. All setting changes reflect immediately on the floating panel.

## New Files

| File | Purpose |
|---|---|
| `TranscriptPanel.swift` | NSPanel subclass — floating window setup, positioning logic |
| `Views/TranscriptOverlayView.swift` | SwiftUI view hosted in the panel — text rendering |
| `Views/OverlaySettingsTab.swift` | Settings tab UI — toggle, position picker, appearance controls |

## Integration Points

### EsperApp.swift

- Owns the `TranscriptPanel` instance
- Creates/destroys panel based on `settings.overlayEnabled`
- Passes `engine` and `settings` to the overlay view

### TranscriptionEngine.swift

- No changes to the engine itself
- Overlay view reads `engine.sentences` and `engine.currentText` directly via `@Observable`

### AppSettings.swift

- Add 6 new `@AppStorage` properties (listed above)

### SettingsView.swift

- Add 4th tab pointing to `OverlaySettingsTab`

## Out of Scope

- Drag-to-reposition (future enhancement)
- Background style options (user chose transparent only)
- Overlay over fullscreen apps (macOS limitation)
- Font family selection
