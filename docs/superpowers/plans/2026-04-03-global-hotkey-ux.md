# Global Hotkey & Settings Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global Option+Space hotkey to toggle transcription from any app, and redesign Settings from horizontal tabs to a vertical sidebar layout.

**Architecture:** KeyboardShortcuts SPM package provides the global hotkey (Carbon RegisterEventHotKey — no Accessibility permission). The hotkey handler calls existing `startListening()`/`stopListening()` on TranscriptionEngine. Settings switches from `TabView` to `NavigationSplitView` with a new Shortcuts tab containing the shortcut recorder.

**Tech Stack:** Swift, SwiftUI, KeyboardShortcuts (sindresorhus/KeyboardShortcuts), macOS 14+

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `EsperApp/EsperApp/GlobalHotkey.swift` | Shortcut name definition + handler registration |
| Create | `EsperApp/EsperApp/Views/ShortcutsTab.swift` | Settings tab with KeyboardShortcuts.Recorder |
| Modify | `EsperApp/EsperApp/EsperApp.swift` | Register hotkey handler on launch |
| Modify | `EsperApp/EsperApp/Views/SettingsView.swift` | Replace TabView with NavigationSplitView sidebar |
| Modify | `EsperApp/EsperApp.xcodeproj/project.pbxproj` | Add KeyboardShortcuts SPM dependency + new files |

---

### Task 1: Add KeyboardShortcuts SPM Dependency

**Files:**
- Modify: `EsperApp/EsperApp.xcodeproj/project.pbxproj` (via Xcode SPM UI or `xcodebuild`)

- [ ] **Step 1: Add the package via swift package resolve**

Open the Xcode project and add the SPM dependency. From the command line:

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild -resolvePackageDependencies -project EsperApp.xcodeproj
```

Since SPM dependencies are easier to add via Xcode GUI (File > Add Package Dependencies > `https://github.com/sindresorhus/KeyboardShortcuts` > Add to target EsperApp), do this step in Xcode. Alternatively, add a `Package.swift` or edit the `.xcodeproj` directly.

The simplest reliable approach: use the `xcodebuild` command after manually adding the package reference to the project file. **Open Xcode, add the package, then return here.**

- [ ] **Step 2: Verify the dependency resolves**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild -project EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | tail -5
```

Expected: Build succeeds (or at least the package resolves — full build may fail until we add code).

- [ ] **Step 3: Commit**

```bash
git add EsperApp/EsperApp.xcodeproj/
git commit -m "feat: add KeyboardShortcuts SPM dependency"
```

---

### Task 2: Define Global Hotkey Name and Handler

**Files:**
- Create: `EsperApp/EsperApp/GlobalHotkey.swift`

- [ ] **Step 1: Create the hotkey definition file**

```swift
import KeyboardShortcuts

extension KeyboardShortcuts.Name {
    static let toggleListening = Self(
        "toggleListening",
        default: .init(.space, modifiers: .option)
    )
}
```

This sets Option+Space as the default. Users can reconfigure via the Recorder in Settings.

- [ ] **Step 2: Verify file compiles**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild -project EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add EsperApp/EsperApp/GlobalHotkey.swift
git commit -m "feat: define global hotkey name with Option+Space default"
```

---

### Task 3: Register Hotkey Handler in EsperApp

**Files:**
- Modify: `EsperApp/EsperApp/EsperApp.swift:1` (add import)
- Modify: `EsperApp/EsperApp/EsperApp.swift:35-41` (register handler in `ensureLaunched`)

- [ ] **Step 1: Add import and register the hotkey handler**

Add `import KeyboardShortcuts` at the top of `EsperApp.swift` (after the existing imports on line 1-3):

```swift
import KeyboardShortcuts
import QuartzCore
import Sparkle
import SwiftUI
```

Add hotkey registration at the end of `ensureLaunched()` (after line 39 `overlayController.bind(...)`):

```swift
private func ensureLaunched() {
    guard !launched else { return }
    launched = true
    engine.launch()
    overlayController.bind(engine: engine, settings: engine.settings)

    KeyboardShortcuts.onKeyDown(for: .toggleListening) { [self] in
        if engine.status == .listening {
            engine.stopListening()
        } else if engine.status == .idle {
            engine.startListening()
        }
        // Ignore during loading states — do nothing
    }
}
```

- [ ] **Step 2: Build and verify**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild -project EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Manual test**

Run the app (Cmd+R in Xcode or from the build output). Once it launches:
1. Open any other app (e.g., Terminal or Safari)
2. Press Option+Space
3. Verify Esper starts listening (menu bar icon changes to filled, overlay appears if enabled)
4. Press Option+Space again
5. Verify Esper stops listening (menu bar icon returns to outline)

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/EsperApp.swift
git commit -m "feat: register global hotkey handler for toggle listening"
```

---

### Task 4: Create ShortcutsTab View

**Files:**
- Create: `EsperApp/EsperApp/Views/ShortcutsTab.swift`

- [ ] **Step 1: Create the Shortcuts settings tab**

```swift
import KeyboardShortcuts
import SwiftUI

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

- [ ] **Step 2: Build and verify**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild -project EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
git add EsperApp/EsperApp/Views/ShortcutsTab.swift
git commit -m "feat: add ShortcutsTab with keyboard shortcut recorder"
```

---

### Task 5: Redesign SettingsView with Vertical Sidebar

**Files:**
- Modify: `EsperApp/EsperApp/Views/SettingsView.swift:1-48` (replace body)

- [ ] **Step 1: Rewrite SettingsView to use NavigationSplitView**

Replace the entire `SettingsView` struct (lines 1-48) with:

```swift
import KeyboardShortcuts
import Sparkle
import SwiftUI

enum SettingsTab: String, CaseIterable, Identifiable {
    case general = "General"
    case shortcuts = "Shortcuts"
    case telegram = "Telegram"
    case overlay = "Overlay"
    case updates = "Updates"
    case advanced = "Advanced"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .general: "gear"
        case .shortcuts: "keyboard"
        case .telegram: "paperplane"
        case .overlay: "text.bubble"
        case .updates: "arrow.triangle.2.circlepath"
        case .advanced: "wrench.and.screwdriver"
        }
    }
}

struct SettingsView: View {
    let engine: TranscriptionEngine
    var overlayController: OverlayController?
    let updater: SPUUpdater

    @State private var selectedTab: SettingsTab = .general

    var body: some View {
        NavigationSplitView {
            List(SettingsTab.allCases, selection: $selectedTab) { tab in
                Label(tab.rawValue, systemImage: tab.icon)
                    .tag(tab)
            }
            .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(min: 160, ideal: 180, max: 220)
        } detail: {
            switch selectedTab {
            case .general:
                GeneralTab(
                    settings: engine.settings,
                    devices: engine.devices,
                    selectedDevice: engine.selectedDevice,
                    onSelectDevice: { engine.setDevice($0) },
                    onRefreshDevices: { engine.refreshDevices() }
                )
            case .shortcuts:
                ShortcutsTab()
            case .telegram:
                TelegramTab(
                    settings: engine.settings,
                    onTestTelegram: { botToken, chatId in
                        engine.testTelegram(botToken: botToken, chatId: chatId)
                    },
                    telegramTestResult: engine.telegramTestResult
                )
            case .overlay:
                OverlaySettingsTab(settings: engine.settings, overlayController: overlayController)
            case .updates:
                UpdateSettingsTab(updater: updater)
            case .advanced:
                AdvancedTab(settings: engine.settings)
            }
        }
        .frame(minWidth: 560, minHeight: 400)
        .onAppear {
            DispatchQueue.main.async {
                if let window = NSApp.windows.first(where: { $0.title == "Settings" || $0.identifier?.rawValue == "com_apple_SwiftUI_Settings_window" }) {
                    window.styleMask.insert(.resizable)
                }
            }
        }
    }
}
```

The `GeneralTab`, `TelegramTab`, and `AdvancedTab` private structs below this (lines 50-210) remain unchanged.

- [ ] **Step 2: Build and verify**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild -project EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Manual test**

Run the app. Open Settings (Cmd+,). Verify:
1. Vertical sidebar appears on the left with 6 items: General, Shortcuts, Telegram, Overlay, Updates, Advanced
2. Clicking each sidebar item shows the corresponding content on the right
3. Shortcuts tab shows the KeyboardShortcuts.Recorder with "Option+Space" as default
4. Click the recorder, press a new key combo — verify it saves
5. Press the new hotkey from another app — verify it toggles listening
6. All other tabs render identically to before

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/Views/SettingsView.swift
git commit -m "feat: redesign Settings to vertical sidebar with NavigationSplitView"
```

---

### Task 6: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add hotkey documentation to README**

Find the usage/features section in README.md and add:

```markdown
### Global Hotkey

Press **Option+Space** from any app to toggle transcription on/off. No need to switch to the Esper window.

Customize the shortcut in **Settings > Shortcuts**.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add global hotkey to README"
```

---

### Task 7: Final Integration Test

- [ ] **Step 1: Clean build**

```bash
cd /Users/yashdesai/Codebase/Fun/Esper/EsperApp
xcodebuild -project EsperApp.xcodeproj -scheme EsperApp -configuration Release clean build 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 2: Run full verification checklist**

Launch the Release build and verify each item:

1. **Hotkey from idle**: Open Safari, press Option+Space → Esper starts listening (green badge, overlay appears)
2. **Hotkey to stop**: Press Option+Space again → Esper stops listening (gray badge, overlay hides)
3. **Hotkey during loading**: Start listening, quit Python backend manually, press Option+Space during model loading → nothing happens (ignored)
4. **Main window button**: Click "Start Listening" in main window → works as before
5. **Menu bar**: Click menu bar dropdown → Start/Stop buttons work as before
6. **Settings sidebar**: Open Settings → 6 tabs in vertical sidebar, all render correctly
7. **Shortcut recorder**: Settings > Shortcuts → change hotkey to Cmd+Shift+E → verify new hotkey works
8. **Reset shortcut**: Right-click the recorder → "Reset to Default" → Option+Space works again
9. **Overlay auto-show**: Enable overlay in Settings, press hotkey → overlay appears. Press again → overlay hides.
10. **No Accessibility prompt**: At no point should macOS ask for Accessibility permission.

- [ ] **Step 3: Commit any fixes if needed**
