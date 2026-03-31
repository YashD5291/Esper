# Overlay Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable floating overlay panel that shows live transcription text on top of all windows, with a settings tab for customization and live preview.

**Architecture:** NSPanel subclass hosts a SwiftUI view via NSHostingView. Settings stored via @AppStorage in AppSettings. New "Overlay" tab in SettingsView configures position, text size, color, lines, opacity. The panel observes TranscriptionEngine state directly and repositions/restyles reactively.

**Tech Stack:** SwiftUI, AppKit (NSPanel), @Observable, @AppStorage, ColorPicker

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `EsperApp/EsperApp/Models/AppSettings.swift` | Modify | Add 6 overlay @AppStorage properties |
| `EsperApp/EsperApp/Models/OverlayPosition.swift` | Create | Enum for 6 screen positions + screen coordinate calculation |
| `EsperApp/EsperApp/TranscriptPanel.swift` | Create | NSPanel subclass — floating window config, positioning |
| `EsperApp/EsperApp/Views/TranscriptOverlayView.swift` | Create | SwiftUI content inside panel — text rendering with settings |
| `EsperApp/EsperApp/Views/OverlaySettingsTab.swift` | Create | Settings tab UI — toggle, position picker, appearance |
| `EsperApp/EsperApp/Views/SettingsView.swift` | Modify | Add 4th Overlay tab |
| `EsperApp/EsperApp/EsperApp.swift` | Modify | Own TranscriptPanel, show/hide based on state |
| `EsperApp/EsperAppTests/OverlayPositionTests.swift` | Create | Unit tests for position enum and coordinate math |
| `EsperApp/EsperAppTests/AppSettingsOverlayTests.swift` | Create | Unit tests for overlay settings defaults and color parsing |

---

### Task 1: OverlayPosition Enum

**Files:**
- Create: `EsperApp/EsperApp/Models/OverlayPosition.swift`
- Test: `EsperApp/EsperAppTests/OverlayPositionTests.swift`

- [ ] **Step 1: Write the failing tests**

Create `EsperApp/EsperAppTests/OverlayPositionTests.swift`:

```swift
import XCTest
@testable import EsperApp

final class OverlayPositionTests: XCTestCase {

    func testAllCasesHaveRawValues() {
        let cases: [OverlayPosition] = [
            .topLeft, .topCenter, .topRight,
            .bottomLeft, .bottomCenter, .bottomRight
        ]
        let rawValues = cases.map(\.rawValue)
        XCTAssertEqual(rawValues, [
            "topLeft", "topCenter", "topRight",
            "bottomLeft", "bottomCenter", "bottomRight"
        ])
    }

    func testFromRawValueRoundTrips() {
        for position in OverlayPosition.allCases {
            XCTAssertEqual(OverlayPosition(rawValue: position.rawValue), position)
        }
    }

    func testFrameBottomCenter() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.bottomCenter.origin(
            panelSize: panelSize, screenFrame: screen
        )
        // Centered horizontally
        XCTAssertEqual(origin.x, (1440 - 660) / 2, accuracy: 1)
        // Near bottom with margin
        XCTAssertEqual(origin.y, 60, accuracy: 1)
    }

    func testFrameTopLeft() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.topLeft.origin(
            panelSize: panelSize, screenFrame: screen
        )
        // Left with margin
        XCTAssertEqual(origin.x, 40, accuracy: 1)
        // Top with margin (macOS y goes up, so top = maxY - height - margin)
        XCTAssertEqual(origin.y, 900 - 100 - 60, accuracy: 1)
    }

    func testFrameTopRight() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.topRight.origin(
            panelSize: panelSize, screenFrame: screen
        )
        // Right with margin
        XCTAssertEqual(origin.x, 1440 - 660 - 40, accuracy: 1)
        // Top with margin
        XCTAssertEqual(origin.y, 900 - 100 - 60, accuracy: 1)
    }

    func testFrameBottomLeft() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.bottomLeft.origin(
            panelSize: panelSize, screenFrame: screen
        )
        XCTAssertEqual(origin.x, 40, accuracy: 1)
        XCTAssertEqual(origin.y, 60, accuracy: 1)
    }

    func testFrameBottomRight() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.bottomRight.origin(
            panelSize: panelSize, screenFrame: screen
        )
        XCTAssertEqual(origin.x, 1440 - 660 - 40, accuracy: 1)
        XCTAssertEqual(origin.y, 60, accuracy: 1)
    }

    func testFrameTopCenter() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.topCenter.origin(
            panelSize: panelSize, screenFrame: screen
        )
        XCTAssertEqual(origin.x, (1440 - 660) / 2, accuracy: 1)
        XCTAssertEqual(origin.y, 900 - 100 - 60, accuracy: 1)
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `xcodebuild test -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -only-testing:EsperAppTests/OverlayPositionTests 2>&1 | tail -20`
Expected: Compile error — `OverlayPosition` not defined.

- [ ] **Step 3: Write the implementation**

Create `EsperApp/EsperApp/Models/OverlayPosition.swift`:

```swift
import AppKit

enum OverlayPosition: String, CaseIterable {
    case topLeft, topCenter, topRight
    case bottomLeft, bottomCenter, bottomRight

    private static let horizontalMargin: CGFloat = 40
    private static let verticalMargin: CGFloat = 60

    func origin(panelSize: NSSize, screenFrame: NSRect) -> NSPoint {
        let hMargin = Self.horizontalMargin
        let vMargin = Self.verticalMargin

        let x: CGFloat
        let y: CGFloat

        switch self {
        case .topLeft:
            x = screenFrame.minX + hMargin
            y = screenFrame.maxY - panelSize.height - vMargin
        case .topCenter:
            x = screenFrame.midX - panelSize.width / 2
            y = screenFrame.maxY - panelSize.height - vMargin
        case .topRight:
            x = screenFrame.maxX - panelSize.width - hMargin
            y = screenFrame.maxY - panelSize.height - vMargin
        case .bottomLeft:
            x = screenFrame.minX + hMargin
            y = screenFrame.minY + vMargin
        case .bottomCenter:
            x = screenFrame.midX - panelSize.width / 2
            y = screenFrame.minY + vMargin
        case .bottomRight:
            x = screenFrame.maxX - panelSize.width - hMargin
            y = screenFrame.minY + vMargin
        }

        return NSPoint(x: x, y: y)
    }
}
```

- [ ] **Step 4: Add both files to Xcode project**

Run: Add `OverlayPosition.swift` to the EsperApp target and `OverlayPositionTests.swift` to the EsperAppTests target in the Xcode project.

- [ ] **Step 5: Run tests to verify they pass**

Run: `xcodebuild test -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -only-testing:EsperAppTests/OverlayPositionTests 2>&1 | tail -20`
Expected: All 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add EsperApp/EsperApp/Models/OverlayPosition.swift EsperApp/EsperAppTests/OverlayPositionTests.swift EsperApp/EsperApp.xcodeproj
git commit -m "feat(overlay): add OverlayPosition enum with screen coordinate math"
```

---

### Task 2: Overlay Settings in AppSettings

**Files:**
- Modify: `EsperApp/EsperApp/Models/AppSettings.swift`
- Test: `EsperApp/EsperAppTests/AppSettingsOverlayTests.swift`

- [ ] **Step 1: Write the failing tests**

Create `EsperApp/EsperAppTests/AppSettingsOverlayTests.swift`:

```swift
import XCTest
import SwiftUI
@testable import EsperApp

final class AppSettingsOverlayTests: XCTestCase {

    func testDefaultValues() {
        let settings = AppSettings()
        XCTAssertFalse(settings.overlayEnabled)
        XCTAssertEqual(settings.overlayPosition, "bottomCenter")
        XCTAssertEqual(settings.overlayTextSize, "medium")
        XCTAssertEqual(settings.overlayTextColor, "#FFFFFF")
        XCTAssertEqual(settings.overlayMaxLines, 3)
        XCTAssertEqual(settings.overlayOpacity, 1.0, accuracy: 0.01)
    }

    func testParsedOverlayPosition() {
        let settings = AppSettings()
        settings.overlayPosition = "topLeft"
        XCTAssertEqual(settings.parsedOverlayPosition, .topLeft)
    }

    func testParsedOverlayPositionInvalidFallsBack() {
        let settings = AppSettings()
        settings.overlayPosition = "nonsense"
        XCTAssertEqual(settings.parsedOverlayPosition, .bottomCenter)
    }

    func testOverlayFontSize() {
        let settings = AppSettings()
        settings.overlayTextSize = "small"
        XCTAssertEqual(settings.overlayFontSize, 16)
        settings.overlayTextSize = "medium"
        XCTAssertEqual(settings.overlayFontSize, 20)
        settings.overlayTextSize = "large"
        XCTAssertEqual(settings.overlayFontSize, 26)
    }

    func testParsedOverlayColor() {
        let settings = AppSettings()
        settings.overlayTextColor = "#FF0000"
        let color = settings.parsedOverlayColor
        // Should be red
        XCTAssertNotNil(color)
    }

    func testParsedOverlayColorInvalidFallsBackToWhite() {
        let settings = AppSettings()
        settings.overlayTextColor = "not-a-color"
        let resolved = NSColor(settings.parsedOverlayColor)
        let white = NSColor.white
        XCTAssertEqual(
            resolved.redComponent, white.redComponent, accuracy: 0.01
        )
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `xcodebuild test -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -only-testing:EsperAppTests/AppSettingsOverlayTests 2>&1 | tail -20`
Expected: Compile error — overlay properties not defined on AppSettings.

- [ ] **Step 3: Add overlay properties to AppSettings**

Add to `EsperApp/EsperApp/Models/AppSettings.swift`, after the Telegram `@AppStorage` properties:

```swift
    // Overlay
    @ObservationIgnored
    @AppStorage("overlayEnabled") var overlayEnabled: Bool = false

    @ObservationIgnored
    @AppStorage("overlayPosition") var overlayPosition: String = "bottomCenter"

    @ObservationIgnored
    @AppStorage("overlayTextSize") var overlayTextSize: String = "medium"

    @ObservationIgnored
    @AppStorage("overlayTextColor") var overlayTextColor: String = "#FFFFFF"

    @ObservationIgnored
    @AppStorage("overlayMaxLines") var overlayMaxLines: Int = 3

    @ObservationIgnored
    @AppStorage("overlayOpacity") var overlayOpacity: Double = 1.0

    // MARK: - Overlay Computed Helpers

    var parsedOverlayPosition: OverlayPosition {
        OverlayPosition(rawValue: overlayPosition) ?? .bottomCenter
    }

    var overlayFontSize: CGFloat {
        switch overlayTextSize {
        case "small": return 16
        case "large": return 26
        default: return 20
        }
    }

    var parsedOverlayColor: Color {
        guard overlayTextColor.hasPrefix("#"),
              overlayTextColor.count == 7,
              let hex = UInt64(overlayTextColor.dropFirst(), radix: 16)
        else { return .white }
        let r = Double((hex >> 16) & 0xFF) / 255
        let g = Double((hex >> 8) & 0xFF) / 255
        let b = Double(hex & 0xFF) / 255
        return Color(red: r, green: g, blue: b)
    }
```

- [ ] **Step 4: Add test file to Xcode project**

Add `AppSettingsOverlayTests.swift` to the EsperAppTests target.

- [ ] **Step 5: Run tests to verify they pass**

Run: `xcodebuild test -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -only-testing:EsperAppTests/AppSettingsOverlayTests 2>&1 | tail -20`
Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add EsperApp/EsperApp/Models/AppSettings.swift EsperApp/EsperAppTests/AppSettingsOverlayTests.swift EsperApp/EsperApp.xcodeproj
git commit -m "feat(overlay): add overlay settings to AppSettings with defaults and helpers"
```

---

### Task 3: TranscriptPanel (NSPanel Subclass)

**Files:**
- Create: `EsperApp/EsperApp/TranscriptPanel.swift`

- [ ] **Step 1: Create the NSPanel subclass**

Create `EsperApp/EsperApp/TranscriptPanel.swift`:

```swift
import AppKit
import SwiftUI

final class TranscriptPanel: NSPanel {
    override init(
        contentRect: NSRect,
        styleMask: NSWindow.StyleMask,
        backing: NSWindow.BackingStoreType,
        defer flag: Bool
    ) {
        super.init(
            contentRect: contentRect,
            styleMask: [.nonactivatingPanel, .fullSizeContentView, .borderless],
            backing: .buffered,
            defer: false
        )
        isFloatingPanel = true
        level = .floating
        hidesOnDeactivate = false
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        ignoresMouseEvents = true
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    func reposition(to position: OverlayPosition) {
        guard let screen = NSScreen.main else { return }
        let origin = position.origin(
            panelSize: frame.size,
            screenFrame: screen.visibleFrame
        )
        setFrameOrigin(origin)
    }
}
```

- [ ] **Step 2: Add file to Xcode project**

Add `TranscriptPanel.swift` to the EsperApp target.

- [ ] **Step 3: Build to verify it compiles**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp 2>&1 | tail -10`
Expected: BUILD SUCCEEDED.

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/TranscriptPanel.swift EsperApp/EsperApp.xcodeproj
git commit -m "feat(overlay): add TranscriptPanel NSPanel subclass"
```

---

### Task 4: TranscriptOverlayView (SwiftUI Content)

**Files:**
- Create: `EsperApp/EsperApp/Views/TranscriptOverlayView.swift`

- [ ] **Step 1: Create the overlay SwiftUI view**

Create `EsperApp/EsperApp/Views/TranscriptOverlayView.swift`:

```swift
import SwiftUI

struct TranscriptOverlayView: View {
    let lines: [String]
    let fontSize: CGFloat
    let textColor: Color
    let opacity: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(lines.enumerated()), id: \.element) { index, line in
                Text(line)
                    .font(.system(size: fontSize, weight: .medium, design: .rounded))
                    .foregroundStyle(textColor)
                    .shadow(color: .black.opacity(0.7), radius: 2, x: 1, y: 1)
                    .opacity(lineOpacity(index: index, total: lines.count))
            }
        }
        .opacity(opacity)
        .padding(.horizontal, 28)
        .padding(.vertical, 16)
        .frame(width: 660, alignment: .leading)
        .background(Color.clear)
    }

    private func lineOpacity(index: Int, total: Int) -> Double {
        guard total > 1 else { return 1.0 }
        let position = Double(total - 1 - index) / Double(total - 1)
        // Oldest line dims to 0.45, newest is 1.0
        return 0.45 + 0.55 * (1.0 - position)
    }
}
```

- [ ] **Step 2: Add file to Xcode project**

Add `TranscriptOverlayView.swift` to the EsperApp target.

- [ ] **Step 3: Build to verify it compiles**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp 2>&1 | tail -10`
Expected: BUILD SUCCEEDED.

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/Views/TranscriptOverlayView.swift EsperApp/EsperApp.xcodeproj
git commit -m "feat(overlay): add TranscriptOverlayView SwiftUI content"
```

---

### Task 5: OverlaySettingsTab

**Files:**
- Create: `EsperApp/EsperApp/Views/OverlaySettingsTab.swift`
- Modify: `EsperApp/EsperApp/Views/SettingsView.swift`

- [ ] **Step 1: Create the settings tab view**

Create `EsperApp/EsperApp/Views/OverlaySettingsTab.swift`:

```swift
import SwiftUI

struct OverlaySettingsTab: View {
    @Bindable var settings: AppSettings
    var overlayController: OverlayController?

    var body: some View {
        Form {
            Section {
                Toggle("Show Overlay", isOn: $settings.overlayEnabled)
            }

            if settings.overlayEnabled {
                Section("Position") {
                    positionPicker
                }

                Section("Appearance") {
                    textSizeControl
                    textColorControl
                    linesControl
                    opacityControl
                }
            }
        }
        .formStyle(.grouped)
        .onAppear { overlayController?.previewMode = true }
        .onDisappear { overlayController?.previewMode = false }
    }

    // MARK: - Position Picker (Mini Screen)

    private var positionPicker: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8)
                .fill(Color(nsColor: .controlBackgroundColor).opacity(0.5))
                .aspectRatio(16.0 / 10.0, contentMode: .fit)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.secondary.opacity(0.3), lineWidth: 1)
                )
                .overlay(positionDots)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
    }

    private var positionDots: some View {
        GeometryReader { geo in
            let margin: CGFloat = 16
            let dotSize: CGFloat = 12
            let positions: [(OverlayPosition, CGFloat, CGFloat)] = [
                (.topLeft, margin, margin),
                (.topCenter, geo.size.width / 2 - dotSize / 2, margin),
                (.topRight, geo.size.width - margin - dotSize, margin),
                (.bottomLeft, margin, geo.size.height - margin - dotSize),
                (.bottomCenter, geo.size.width / 2 - dotSize / 2, geo.size.height - margin - dotSize),
                (.bottomRight, geo.size.width - margin - dotSize, geo.size.height - margin - dotSize),
            ]

            ForEach(positions, id: \.0) { pos, x, y in
                let isSelected = settings.parsedOverlayPosition == pos
                Circle()
                    .fill(isSelected ? Color.accentColor : Color.secondary.opacity(0.3))
                    .frame(width: dotSize, height: dotSize)
                    .shadow(color: isSelected ? Color.accentColor.opacity(0.6) : .clear, radius: 4)
                    .position(x: x + dotSize / 2, y: y + dotSize / 2)
                    .onTapGesture {
                        settings.overlayPosition = pos.rawValue
                    }
            }
        }
    }

    // MARK: - Appearance Controls

    private var textSizeControl: some View {
        HStack {
            Text("Text Size")
            Spacer()
            Picker("", selection: $settings.overlayTextSize) {
                Text("S").tag("small")
                Text("M").tag("medium")
                Text("L").tag("large")
            }
            .pickerStyle(.segmented)
            .frame(width: 120)
        }
    }

    private var textColorControl: some View {
        HStack {
            Text("Text Color")
            Spacer()
            let presets: [(String, Color)] = [
                ("#FFFFFF", .white),
                ("#4CAF50", .green),
                ("#42A5F5", .blue),
                ("#FFA726", .orange),
                ("#EF5350", .red),
            ]
            ForEach(presets, id: \.0) { hex, color in
                Circle()
                    .fill(color)
                    .frame(width: 22, height: 22)
                    .overlay(
                        Circle()
                            .stroke(
                                settings.overlayTextColor == hex ? Color.accentColor : Color.clear,
                                lineWidth: 2
                            )
                    )
                    .onTapGesture { settings.overlayTextColor = hex }
            }

            Divider().frame(height: 18)

            ColorPicker("", selection: Binding(
                get: { settings.parsedOverlayColor },
                set: { newColor in
                    if let hex = newColor.toHex() {
                        settings.overlayTextColor = hex
                    }
                }
            ), supportsOpacity: false)
            .labelsHidden()
            .frame(width: 22)
        }
    }

    private var linesControl: some View {
        HStack {
            Text("Lines")
            Spacer()
            Stepper(
                value: $settings.overlayMaxLines,
                in: 1...9
            ) {
                Text("\(settings.overlayMaxLines)")
                    .monospacedDigit()
                    .frame(minWidth: 20, alignment: .center)
            }
        }
    }

    private var opacityControl: some View {
        HStack {
            Text("Opacity")
            Spacer()
            Text("\(Int(settings.overlayOpacity * 100))%")
                .foregroundStyle(.secondary)
                .monospacedDigit()
                .frame(width: 40, alignment: .trailing)
            Slider(value: $settings.overlayOpacity, in: 0.3...1.0, step: 0.05)
                .frame(width: 140)
        }
    }
}

// MARK: - Color Hex Conversion

extension Color {
    func toHex() -> String? {
        guard let nsColor = NSColor(self).usingColorSpace(.sRGB) else { return nil }
        let r = Int(nsColor.redComponent * 255)
        let g = Int(nsColor.greenComponent * 255)
        let b = Int(nsColor.blueComponent * 255)
        return String(format: "#%02X%02X%02X", r, g, b)
    }
}
```

- [ ] **Step 2: Add 4th tab to SettingsView**

In `EsperApp/EsperApp/Views/SettingsView.swift`, add `overlayController` property and the Overlay tab. Replace the struct:

```swift
struct SettingsView: View {
    let engine: TranscriptionEngine
    var overlayController: OverlayController?

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

            AdvancedTab(settings: engine.settings)
            .tabItem { Label("Advanced", systemImage: "wrench.and.screwdriver") }
        }
        .frame(width: 460, height: 380)
    }
```

Note: frame height increased from 320 to 380 to accommodate the position picker.

- [ ] **Step 3: Add file to Xcode project**

Add `OverlaySettingsTab.swift` to the EsperApp target.

- [ ] **Step 4: Build to verify it compiles**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp 2>&1 | tail -10`
Expected: BUILD SUCCEEDED.

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/Views/OverlaySettingsTab.swift EsperApp/EsperApp/Views/SettingsView.swift EsperApp/EsperApp.xcodeproj
git commit -m "feat(overlay): add Overlay settings tab with position picker and appearance controls"
```

---

### Task 6: Wire Panel into EsperApp

**Files:**
- Modify: `EsperApp/EsperApp/EsperApp.swift`

- [ ] **Step 1: Add panel management to EsperApp**

Replace `EsperApp/EsperApp/EsperApp.swift` with:

```swift
import SwiftUI

@main
struct EsperApp: App {
    @State private var engine = TranscriptionEngine()
    @State private var launched = false
    @State private var overlayController = OverlayController()
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(engine: engine)
                .onAppear { ensureLaunched() }
        } label: {
            Image(systemName: engine.status == .listening ? "waveform.circle.fill" : "waveform.circle")
        }

        WindowGroup("Esper", id: "main") {
            MainWindowView(engine: engine)
                .onAppear {
                    ensureLaunched()
                    NSApp.activate(ignoringOtherApps: true)
                    overlayController.bind(engine: engine, settings: engine.settings)
                }
        }
        .defaultSize(width: 520, height: 640)

        Settings {
            SettingsView(engine: engine, overlayController: overlayController)
        }
    }

    private func ensureLaunched() {
        guard !launched else { return }
        launched = true
        engine.launch()
    }

    init() {
        DispatchQueue.main.async { [self] in
            openWindow(id: "main")
        }
    }
}

// MARK: - Overlay Controller

@Observable
@MainActor
final class OverlayController {
    private var panel: TranscriptPanel?
    private var hostView: NSHostingView<TranscriptOverlayView>?
    private var updateTask: Task<Void, Never>?
    var previewMode = false

    func bind(engine: TranscriptionEngine, settings: AppSettings) {
        // Avoid duplicate binding
        guard updateTask == nil else { return }
        updateTask = Task { @MainActor [weak self] in
            // Poll-free reactive loop using withObservationTracking
            while !Task.isCancelled {
                guard let self else { return }
                let shouldShow = settings.overlayEnabled &&
                    (engine.status == .listening || self.previewMode)
                let lines = self.overlayLines(engine: engine, settings: settings)
                let position = settings.parsedOverlayPosition
                let fontSize = settings.overlayFontSize
                let textColor = settings.parsedOverlayColor
                let opacity = settings.overlayOpacity

                if shouldShow {
                    self.showPanel(
                        lines: lines,
                        position: position,
                        fontSize: fontSize,
                        textColor: textColor,
                        opacity: opacity
                    )
                } else {
                    self.hidePanel()
                }

                // Wait for next change
                await withCheckedContinuation { continuation in
                    withObservationTracking {
                        _ = settings.overlayEnabled
                        _ = settings.overlayPosition
                        _ = settings.overlayTextSize
                        _ = settings.overlayTextColor
                        _ = settings.overlayMaxLines
                        _ = settings.overlayOpacity
                        _ = engine.status
                        _ = engine.sentences
                        _ = engine.currentText
                    } onChange: {
                        continuation.resume()
                    }
                }
            }
        }
    }

    private static let sampleLines = [
        "This is a preview of the overlay",
        "Transcription text will appear here",
        "Adjust settings to customize the look",
    ]

    private func overlayLines(engine: TranscriptionEngine, settings: AppSettings) -> [String] {
        let maxLines = settings.overlayMaxLines
        if previewMode && engine.status != .listening {
            return Array(Self.sampleLines.prefix(maxLines))
        }
        var lines = Array(engine.sentences.suffix(maxLines))
        let current = engine.currentText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !current.isEmpty {
            if lines.count >= maxLines {
                lines.removeFirst()
            }
            lines.append(current)
        }
        return lines
    }

    private func showPanel(
        lines: [String],
        position: OverlayPosition,
        fontSize: CGFloat,
        textColor: Color,
        opacity: Double
    ) {
        let view = TranscriptOverlayView(
            lines: lines,
            fontSize: fontSize,
            textColor: textColor,
            opacity: opacity
        )

        if let hostView {
            hostView.rootView = view
        } else {
            let panel = TranscriptPanel(
                contentRect: NSRect(x: 0, y: 0, width: 660, height: 140),
                styleMask: [],
                backing: .buffered,
                defer: false
            )
            let host = NSHostingView(rootView: view)
            panel.contentView = host
            self.panel = panel
            self.hostView = host
        }

        panel?.reposition(to: position)

        if !(panel?.isVisible ?? false) {
            panel?.orderFrontRegardless()
        }
    }

    private func hidePanel() {
        panel?.orderOut(nil)
    }
}
```

- [ ] **Step 2: Build to verify it compiles**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp 2>&1 | tail -10`
Expected: BUILD SUCCEEDED.

- [ ] **Step 3: Run all tests**

Run: `xcodebuild test -project EsperApp/EsperApp.xcodeproj -scheme EsperApp 2>&1 | tail -20`
Expected: All tests PASS (existing + new).

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/EsperApp.swift
git commit -m "feat(overlay): wire TranscriptPanel into app with reactive show/hide"
```

---

### Task 7: Manual Smoke Test & Polish

- [ ] **Step 1: Build and run the app**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug 2>&1 | tail -5`

Then open the built app from Xcode or the build directory.

- [ ] **Step 2: Verify overlay toggle**

1. Open Settings → Overlay tab
2. Toggle "Show Overlay" ON
3. Start listening
4. Verify: floating text appears on screen at bottom-center
5. Toggle OFF → text disappears

- [ ] **Step 3: Verify position picker**

Click each of the 6 dots → overlay moves to the correct screen position.

- [ ] **Step 4: Verify appearance controls**

1. Change text size S/M/L → text resizes
2. Click color swatches → text color changes
3. Use color picker → custom color applies
4. Adjust lines stepper (1–9) → line count changes
5. Drag opacity slider → text fades/brightens

- [ ] **Step 5: Verify click-through**

Click on the overlay area → clicks should pass through to the window underneath.

- [ ] **Step 6: Fix any issues found, commit**

```bash
git add -A
git commit -m "fix(overlay): polish from smoke testing"
```

---

### Task 8: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add overlay section to README**

Add a section under the features area documenting:
- Floating overlay feature description
- How to enable (Settings → Overlay)
- Available configuration options (position, text size, color, lines, opacity)

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add overlay panel feature to README"
```
