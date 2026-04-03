# Global Hotkey & UX Improvements — Design Spec

## Goal

Add a global keyboard shortcut to start/stop transcription from any app, and redesign the Settings window to use a vertical sidebar layout.

## Decisions

| Decision | Choice |
|----------|--------|
| Interaction model | Toggle (press to start, press to stop) |
| Default hotkey | Option+Space |
| Configurable | Yes, via Settings > Shortcuts tab |
| Library | KeyboardShortcuts (sindresorhus/KeyboardShortcuts) via SPM |
| Audio feedback | None — visual only |
| Menu bar icon | Keep current behavior (outline → filled swap) |
| Overlay on hotkey | Auto-show on start, auto-hide on stop |
| Existing controls | Keep all (main window button, menu bar dropdown, hotkey) |
| Settings layout | Vertical sidebar (NavigationSplitView) replacing horizontal TabView |

## 1. Global Hotkey

### Behavior

- **Option+Space** toggles transcription on/off from any app, even when Esper has no visible window.
- Uses Carbon `RegisterEventHotKey` via KeyboardShortcuts — no Accessibility permission required.
- When toggled ON: calls `TranscriptionEngine.startListening()`, auto-shows overlay if overlay is enabled in settings.
- When toggled OFF: calls `TranscriptionEngine.stopListening()`, auto-hides overlay.
- Hotkey works when app is running as menu bar agent (no dock icon needed).
- Hotkey does nothing during loading states (downloadingModel, compilingShaders, loadingModel). Only fires from `.idle` (to start) or `.listening` (to stop).

### KeyboardShortcuts Integration

- Add `KeyboardShortcuts` SPM package: `https://github.com/sindresorhus/KeyboardShortcuts`
- Define shortcut name:
  ```swift
  extension KeyboardShortcuts.Name {
      static let toggleListening = Self("toggleListening", default: .init(.space, modifiers: .option))
  }
  ```
- Register handler in `TranscriptionEngine` or `EsperApp`:
  ```swift
  KeyboardShortcuts.onKeyDown(for: .toggleListening) {
      if engine.status == .listening {
          engine.stopListening()
      } else if engine.status == .idle {
          engine.startListening()
      }
  }
  ```

### Overlay Auto-Show/Hide

- On hotkey start: if `settings.overlayEnabled` is true, show the overlay panel.
- On hotkey stop: hide the overlay panel.
- This matches existing behavior when starting from the main window button — the overlay already shows/hides with listening state. The hotkey just triggers the same code path.

## 2. Settings Redesign

### Layout Change

Replace the current `TabView` with `NavigationSplitView`:

```
┌─────────────────────────────────────────┐
│  ┌──────────┐  ┌──────────────────────┐ │
│  │ General   │  │                      │ │
│  │ Shortcuts │  │   Content area       │ │
│  │ Telegram  │  │   (selected tab)     │ │
│  │ Overlay   │  │                      │ │
│  │ Updates   │  │                      │ │
│  │ Advanced  │  │                      │ │
│  └──────────┘  └──────────────────────┘ │
└─────────────────────────────────────────┘
```

### Implementation

- `SettingsView` body changes from `TabView { ... .tabItem {} }` to `NavigationSplitView { sidebar } detail: { content }`.
- Sidebar uses `List(selection: $selectedTab)` with an enum for tab identity.
- Each row: SF Symbol icon + label text. Selected row highlighted with accent color.
- Existing tab structs (GeneralTab, TelegramTab, OverlaySettingsTab, UpdateSettingsTab, AdvancedTab) remain unchanged — only the outer container changes.
- Window min size: 560x400 (wider to accommodate sidebar + content).

### Tabs

| Tab | Icon | Content |
|-----|------|---------|
| General | `gear` | Input device picker + refresh |
| Shortcuts | `keyboard` | KeyboardShortcuts.Recorder for toggle hotkey |
| Telegram | `paperplane` | Bot token, chat ID, enable toggle, test button |
| Overlay | `text.bubble` | Position, size, color, opacity, line count |
| Updates | `arrow.triangle.2.circlepath` | Sparkle auto-update controls |
| Advanced | `wrench.and.screwdriver` | Server mode, paths |

### New Shortcuts Tab

```swift
struct ShortcutsTab: View {
    var body: some View {
        Form {
            Section("Global Hotkey") {
                KeyboardShortcuts.Recorder("Toggle Listening:", name: .toggleListening)
                Text("Press this shortcut from any app to start or stop transcription.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }
}
```

## 3. What Does NOT Change

- Main window start/stop button — stays as-is.
- Menu bar dropdown start/stop — stays as-is.
- Menu bar icon behavior — stays as-is (outline → filled).
- TranscriptionEngine state machine — no changes.
- Python backend IPC protocol — no changes.
- Overlay appearance/styling — no changes (only auto-show/hide trigger is new).
- Audio level meter, transcript view, error handling — all unchanged.

## 4. Dependencies

- **KeyboardShortcuts** (sindresorhus/KeyboardShortcuts): MIT license, SPM-compatible, macOS 10.15+. Adds via Xcode SPM: File > Add Package > `https://github.com/sindresorhus/KeyboardShortcuts`.

## 5. Testing

- Verify hotkey starts/stops transcription from a different app (e.g., Terminal, Safari).
- Verify hotkey is ignored during loading states.
- Verify overlay auto-shows on start and auto-hides on stop.
- Verify shortcut recorder in Settings saves and restores custom bindings.
- Verify default Option+Space works on fresh install.
- Verify existing main window button and menu bar controls still work.
- Verify Settings sidebar navigation works — all 6 tabs render correctly.
- Verify no Accessibility permission prompt appears (Carbon hotkeys don't need it).
