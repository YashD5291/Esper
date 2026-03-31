# Sparkle Auto-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic update delivery via Sparkle 2 so users receive new versions without manual DMG downloads.

**Architecture:** Sparkle 2 added via SPM. `SPUStandardUpdaterController` initialized at app startup handles the full update lifecycle. Appcast XML hosted on GitHub Pages advertises versions. EdDSA key pair signs/verifies updates.

**Tech Stack:** Sparkle 2 (SPM), SwiftUI, GitHub Pages, EdDSA signing

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `EsperApp.xcodeproj` | Modify | Add Sparkle SPM dependency |
| `EsperApp/EsperApp/Info.plist` | Create | Sparkle keys (SUFeedURL, SUPublicEDKey) — merged with auto-generated plist |
| `EsperApp/EsperApp/EsperApp.swift` | Modify | Initialize SPUStandardUpdaterController, pass updater to views |
| `EsperApp/EsperApp/Views/CheckForUpdatesView.swift` | Create | Reusable button that observes `canCheckForUpdates` via KVO |
| `EsperApp/EsperApp/Views/UpdateSettingsTab.swift` | Create | Updates tab: auto-check toggle, version label, check button |
| `EsperApp/EsperApp/Views/SettingsView.swift` | Modify | Add Updates tab |
| `EsperApp/EsperApp/Views/MenuBarView.swift` | Modify | Add "Check for Updates..." menu item |
| `docs/appcast.xml` | Create | Sparkle appcast for GitHub Pages |
| `EsperApp/EsperAppTests/UpdateSettingsTests.swift` | Create | Tests for version string extraction and update settings |

---

### Task 1: Add Sparkle SPM Dependency and Info.plist

**Files:**
- Modify: `EsperApp/EsperApp.xcodeproj/project.pbxproj`
- Create: `EsperApp/EsperApp/Info.plist`

- [ ] **Step 1: Add Sparkle package via xcodebuild**

Open the Xcode project and add Sparkle as a Swift Package dependency. Since SPM dependency addition via CLI is fragile, use Xcode's `xcodebuild -resolvePackageDependencies` after manually editing the project, OR add via Xcode GUI.

The most reliable approach for CLI: add the package reference to the project file.

Run in the Esper repo root:

```bash
# Open Xcode to add SPM dependency (most reliable)
open EsperApp/EsperApp.xcodeproj
```

In Xcode:
1. File > Add Package Dependencies
2. Enter: `https://github.com/sparkle-project/Sparkle`
3. Dependency Rule: "Up to Next Major Version" from `2.0.0`
4. Add to target: `EsperApp`
5. Select **only** the `Sparkle` library (not `SparkleTestSupport`)

- [ ] **Step 2: Create Info.plist with Sparkle keys**

Create `EsperApp/EsperApp/Info.plist`. The project already has `GENERATE_INFOPLIST_FILE = YES`, so Xcode will merge this file with the auto-generated keys. The EdDSA public key is a placeholder — it will be replaced after key generation in Task 6.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>SUFeedURL</key>
    <string>https://yashd5291.github.io/Esper/appcast.xml</string>
    <key>SUPublicEDKey</key>
    <string>PLACEHOLDER_WILL_BE_REPLACED_AFTER_KEY_GENERATION</string>
    <key>SUScheduledCheckInterval</key>
    <integer>86400</integer>
    <key>SUEnableAutomaticChecks</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 3: Set INFOPLIST_FILE in Xcode build settings**

In Xcode, select the EsperApp target > Build Settings > search "Info.plist File". Set it to `EsperApp/Info.plist` for both Debug and Release. Keep `GENERATE_INFOPLIST_FILE = YES` — Xcode merges both sources.

Alternatively via `sed` on the pbxproj (both Debug and Release configurations):

The build setting key is `INFOPLIST_FILE`. Add `INFOPLIST_FILE = EsperApp/Info.plist;` to both Debug and Release build settings in the project file.

- [ ] **Step 4: Verify build**

```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(error:|BUILD)'
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp.xcodeproj EsperApp/EsperApp/Info.plist
git commit -m "feat: add Sparkle 2 SPM dependency and Info.plist with update keys"
```

---

### Task 2: Create CheckForUpdatesView (KVO Bridge)

**Files:**
- Create: `EsperApp/EsperApp/Views/CheckForUpdatesView.swift`
- Test: `EsperApp/EsperAppTests/UpdateSettingsTests.swift`

Sparkle's `SPUUpdater.canCheckForUpdates` is KVO-compliant but not `@Published`. We need a small Combine bridge so SwiftUI can disable the button while a check is in progress.

- [ ] **Step 1: Write the test**

Create `EsperApp/EsperAppTests/UpdateSettingsTests.swift`:

```swift
import XCTest
@testable import EsperApp

final class UpdateSettingsTests: XCTestCase {

    func testAppVersionStringIsNotEmpty() {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        XCTAssertNotNil(version)
        // In test target, version comes from the test bundle or host app
        // This verifies the pattern we use in UpdateSettingsTab works
    }
}
```

- [ ] **Step 2: Run test to verify it passes**

```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp test 2>&1 | grep -E '(UpdateSettingsTests|SUCCEEDED|FAILED)'
```

Expected: PASS

- [ ] **Step 3: Create CheckForUpdatesView**

Create `EsperApp/EsperApp/Views/CheckForUpdatesView.swift`:

```swift
import Sparkle
import SwiftUI

/// Bridges SPUUpdater's KVO-based `canCheckForUpdates` to SwiftUI.
final class CheckForUpdatesViewModel: ObservableObject {
    @Published var canCheckForUpdates = false

    init(updater: SPUUpdater) {
        updater.publisher(for: \.canCheckForUpdates)
            .assign(to: &$canCheckForUpdates)
    }
}

/// A button that triggers a manual update check, disabled while a check is in progress.
struct CheckForUpdatesView: View {
    @ObservedObject private var viewModel: CheckForUpdatesViewModel
    private let updater: SPUUpdater

    init(updater: SPUUpdater) {
        self.updater = updater
        self.viewModel = CheckForUpdatesViewModel(updater: updater)
    }

    var body: some View {
        Button("Check for Updates...", action: updater.checkForUpdates)
            .disabled(!viewModel.canCheckForUpdates)
    }
}
```

- [ ] **Step 4: Verify build**

```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(error:|BUILD)'
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/Views/CheckForUpdatesView.swift EsperApp/EsperAppTests/UpdateSettingsTests.swift
git commit -m "feat: add CheckForUpdatesView with KVO bridge for Sparkle"
```

---

### Task 3: Create UpdateSettingsTab

**Files:**
- Create: `EsperApp/EsperApp/Views/UpdateSettingsTab.swift`

- [ ] **Step 1: Create UpdateSettingsTab view**

Create `EsperApp/EsperApp/Views/UpdateSettingsTab.swift`:

```swift
import Sparkle
import SwiftUI

struct UpdateSettingsTab: View {
    private let updater: SPUUpdater
    @State private var automaticallyChecksForUpdates: Bool

    init(updater: SPUUpdater) {
        self.updater = updater
        self.automaticallyChecksForUpdates = updater.automaticallyChecksForUpdates
    }

    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
    }

    var body: some View {
        Form {
            Section {
                Toggle("Automatically check for updates", isOn: $automaticallyChecksForUpdates)
                    .onChange(of: automaticallyChecksForUpdates) { _, newValue in
                        updater.automaticallyChecksForUpdates = newValue
                    }
            }

            Section {
                LabeledContent("Current Version", value: "v\(appVersion)")

                CheckForUpdatesView(updater: updater)
            }
        }
        .formStyle(.grouped)
    }
}
```

- [ ] **Step 2: Verify build**

```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(error:|BUILD)'
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 3: Commit**

```bash
git add EsperApp/EsperApp/Views/UpdateSettingsTab.swift
git commit -m "feat: add UpdateSettingsTab with auto-check toggle and version display"
```

---

### Task 4: Wire Sparkle into EsperApp, SettingsView, and MenuBarView

**Files:**
- Modify: `EsperApp/EsperApp/EsperApp.swift:1-44`
- Modify: `EsperApp/EsperApp/Views/SettingsView.swift:1-43`
- Modify: `EsperApp/EsperApp/Views/MenuBarView.swift:1-92`

- [ ] **Step 1: Initialize SPUStandardUpdaterController in EsperApp.swift**

In `EsperApp/EsperApp/EsperApp.swift`, add `import Sparkle` at the top and add the updater controller property. Pass the updater to SettingsView and MenuBarView.

The `EsperApp` struct should become:

```swift
import QuartzCore
import Sparkle
import SwiftUI

@main
struct EsperApp: App {
    @State private var engine = TranscriptionEngine()
    @State private var launched = false
    @State private var overlayController = OverlayController()
    @Environment(\.openWindow) private var openWindow

    private let updaterController: SPUStandardUpdaterController

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(engine: engine, updater: updaterController.updater)
                .onAppear { ensureLaunched() }
        } label: {
            Image(systemName: engine.status == .listening ? "waveform.circle.fill" : "waveform.circle")
        }

        WindowGroup("Esper", id: "main") {
            MainWindowView(engine: engine)
                .onAppear {
                    ensureLaunched()
                    NSApp.activate(ignoringOtherApps: true)
                }
        }
        .defaultSize(width: 520, height: 640)

        Settings {
            SettingsView(engine: engine, overlayController: overlayController, updater: updaterController.updater)
        }
    }

    private func ensureLaunched() {
        guard !launched else { return }
        launched = true
        engine.launch()
        overlayController.bind(engine: engine, settings: engine.settings)
    }

    init() {
        updaterController = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
        DispatchQueue.main.async { [self] in
            openWindow(id: "main")
        }
    }
}
```

- [ ] **Step 2: Add Updates tab to SettingsView.swift**

In `EsperApp/EsperApp/Views/SettingsView.swift`, add the `updater` parameter and the Updates tab:

```swift
import Sparkle
import SwiftUI

struct SettingsView: View {
    let engine: TranscriptionEngine
    var overlayController: OverlayController?
    let updater: SPUUpdater

    var body: some View {
        TabView {
            GeneralTab(
                settings: engine.settings,
                devices: engine.devices,
                selectedDevice: engine.selectedDevice,
                onSelectDevice: { engine.setDevice($0) },
                onRefreshDevices: { engine.refreshDevices() }
            )
            .tabItem { Label("General", systemImage: "gear") }

            TelegramTab(
                settings: engine.settings,
                onTestTelegram: { botToken, chatId in
                    engine.testTelegram(botToken: botToken, chatId: chatId)
                },
                telegramTestResult: engine.telegramTestResult
            )
            .tabItem { Label("Telegram", systemImage: "paperplane") }

            OverlaySettingsTab(settings: engine.settings, overlayController: overlayController)
                .tabItem { Label("Overlay", systemImage: "text.bubble") }

            UpdateSettingsTab(updater: updater)
                .tabItem { Label("Updates", systemImage: "arrow.triangle.2.circlepath") }

            AdvancedTab(settings: engine.settings)
            .tabItem { Label("Advanced", systemImage: "wrench.and.screwdriver") }
        }
        .frame(minWidth: 460, minHeight: 320)
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

- [ ] **Step 3: Add "Check for Updates" to MenuBarView.swift**

In `EsperApp/EsperApp/Views/MenuBarView.swift`, add the `updater` parameter and a "Check for Updates..." button. Add it between the overlay toggle and the "Open Window" button:

```swift
import Sparkle
import SwiftUI

struct MenuBarView: View {
    let engine: TranscriptionEngine
    let updater: SPUUpdater
    @Environment(\.openWindow) private var openWindow
    @State private var overlayEnabled = false

    var body: some View {
        HStack {
            StatusBadge(status: engine.status)
            Text(engine.status.displayName)
        }
        .padding(.horizontal, 4)

        Divider()

        if engine.status == .listening {
            Button("Stop Listening") {
                engine.stopListening()
            }
        } else if engine.status == .idle {
            Button("Start Listening") {
                engine.startListening()
            }
        } else {
            Text("Loading model...")
                .foregroundStyle(.secondary)
        }

        Divider()

        if !engine.devices.isEmpty {
            Text("Input Device")
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(engine.devices) { device in
                Button {
                    engine.setDevice(device.index)
                } label: {
                    HStack {
                        if engine.selectedDevice == device.index {
                            Image(systemName: "checkmark")
                        }
                        Text(device.name)
                    }
                }
            }

            Divider()
        }

        if let error = engine.errorMessage {
            Label(error, systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
                .lineLimit(3)

            Button("Restart") {
                engine.restart()
            }

            Divider()
        }

        Button(overlayEnabled ? "Hide Overlay" : "Show Overlay") {
            overlayEnabled.toggle()
            engine.settings.overlayEnabled = overlayEnabled
        }

        Divider()

        CheckForUpdatesView(updater: updater)

        Divider()

        Button("Open Window") {
            openWindow(id: "main")
            NSApp.activate(ignoringOtherApps: true)
        }
        .keyboardShortcut("o")

        SettingsLink {
            Text("Settings...")
        }
        .keyboardShortcut(",")

        Button("Quit Esper") {
            engine.shutdown()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                NSApp.terminate(nil)
            }
        }
        .keyboardShortcut("q")
        .onAppear { overlayEnabled = engine.settings.overlayEnabled }
    }
}
```

- [ ] **Step 4: Build and run tests**

```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug test 2>&1 | grep -E '(passed|failed|SUCCEEDED|FAILED)'
```

Expected: All tests pass, `** TEST SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/EsperApp.swift EsperApp/EsperApp/Views/SettingsView.swift EsperApp/EsperApp/Views/MenuBarView.swift
git commit -m "feat: wire Sparkle updater into app, settings, and menu bar"
```

---

### Task 5: Create Appcast and Enable GitHub Pages

**Files:**
- Create: `docs/appcast.xml`

- [ ] **Step 1: Create the appcast XML**

Create `docs/appcast.xml` with the current release (v3.0.1). The EdDSA signature and file size are placeholders — they'll be filled in when a signed release is published.

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Esper Updates</title>
    <link>https://yashd5291.github.io/Esper/appcast.xml</link>
    <description>Esper app updates</description>
    <language>en</language>
    <item>
      <title>Version 3.0.1</title>
      <sparkle:version>1</sparkle:version>
      <sparkle:shortVersionString>3.0.1</sparkle:shortVersionString>
      <description><![CDATA[
        <ul>
          <li>Fixed overlay blink during live transcription</li>
          <li>Rendering hardening for overlay panel</li>
        </ul>
      ]]></description>
      <pubDate>Mon, 31 Mar 2026 00:00:00 +0000</pubDate>
      <enclosure
        url="https://github.com/YashD5291/Esper/releases/download/v3.0.1/Esper.dmg"
        sparkle:edSignature="PLACEHOLDER_SIGN_WITH_GENERATE_APPCAST"
        length="0"
        type="application/octet-stream"
      />
    </item>
  </channel>
</rss>
```

Note: `sparkle:version` maps to `CFBundleVersion` (build number = "1"), `sparkle:shortVersionString` maps to `CFBundleShortVersionString` (marketing version = "3.0.1"). Sparkle compares `sparkle:version` to determine if an update is newer.

- [ ] **Step 2: Commit**

```bash
git add docs/appcast.xml
git commit -m "feat: add Sparkle appcast.xml for GitHub Pages"
```

- [ ] **Step 3: Enable GitHub Pages**

Enable GitHub Pages on the repo to serve from the `docs/` directory on `main`:

```bash
gh api repos/YashD5291/Esper/pages -X POST -f source.branch=main -f source.path=/docs 2>/dev/null || \
gh api repos/YashD5291/Esper/pages -X PUT -f source.branch=main -f source.path=/docs
```

Verify it's enabled:

```bash
gh api repos/YashD5291/Esper/pages --jq '.html_url'
```

Expected: `https://yashd5291.github.io/Esper/`

---

### Task 6: Generate EdDSA Keys and Update Info.plist

**Files:**
- Modify: `EsperApp/EsperApp/Info.plist`

This task requires the Sparkle tools from the SPM build. The `generate_keys` binary is inside the Sparkle artifact bundle in DerivedData.

- [ ] **Step 1: Locate Sparkle tools**

```bash
find ~/Library/Developer/Xcode/DerivedData/EsperApp-*/SourcePackages/artifacts -name "generate_keys" 2>/dev/null | head -1
```

If not found, download from Sparkle releases:

```bash
curl -L https://github.com/sparkle-project/Sparkle/releases/download/2.7.5/Sparkle-2.7.5.tar.xz -o /tmp/sparkle.tar.xz
mkdir -p /tmp/sparkle && tar xf /tmp/sparkle.tar.xz -C /tmp/sparkle
ls /tmp/sparkle/bin/generate_keys
```

- [ ] **Step 2: Generate EdDSA key pair**

```bash
/path/to/generate_keys
```

This prints the public key and stores the private key in your login Keychain. Copy the base64 public key string from the output.

- [ ] **Step 3: Update Info.plist with real public key**

Replace the placeholder in `EsperApp/EsperApp/Info.plist`:

```xml
<key>SUPublicEDKey</key>
<string>YOUR_ACTUAL_BASE64_PUBLIC_KEY_HERE</string>
```

- [ ] **Step 4: Build to verify**

```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(error:|BUILD)'
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/Info.plist
git commit -m "feat: add EdDSA public key for Sparkle update verification"
```

---

### Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add auto-update section to README**

Add a section under the existing features documenting that the app auto-updates via Sparkle. Include:
- The app checks for updates every 24 hours automatically
- Manual check available from menu bar ("Check for Updates...") and Settings > Updates
- Updates are downloaded, verified (EdDSA), and installed automatically

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add auto-update feature to README"
```

---

### Task 8: Final Integration Test

- [ ] **Step 1: Build release and run smoke test**

```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Release build CONFIGURATION_BUILD_DIR=/tmp/EsperBuild 2>&1 | tail -5
```

- [ ] **Step 2: Launch and verify**

```bash
open /tmp/EsperBuild/EsperApp.app
```

Verify:
1. App launches without errors
2. Settings > Updates tab shows version and "Check for Updates" button
3. Menu bar has "Check for Updates..." item
4. Clicking "Check for Updates" shows Sparkle dialog (will show "no updates" or connection error since appcast isn't signed yet — this is expected)
5. Auto-check toggle works

- [ ] **Step 3: Run all tests**

```bash
xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp test 2>&1 | grep -E '(passed|failed|SUCCEEDED|FAILED)'
```

Expected: All tests pass.

- [ ] **Step 4: Final commit and push**

```bash
git push origin main
```
