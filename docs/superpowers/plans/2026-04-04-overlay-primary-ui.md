# Overlay as Primary UI + Flow Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the main window, add a Wispr-inspired flow button for start/stop control, promote the overlay to the primary app surface with top bar (device picker, gear, audio meter, dismiss).

**Architecture:** Delete MainWindowView/TranscriptView/AudioLevelMeter. Create FlowButton (NSPanel) and FlowButtonView (SwiftUI). Add top bar to TranscriptOverlayView. Rewire EsperApp to remove WindowGroup and manage flow button lifecycle alongside overlay. Simplify MenuBarView.

**Tech Stack:** SwiftUI, AppKit (NSPanel, NSTrackingArea, NSHostingView), CALayer animations

**Spec:** `docs/superpowers/specs/2026-04-04-overlay-primary-ui-design.md`

---

## File Structure

**Delete:**
- `EsperApp/EsperApp/Views/MainWindowView.swift`
- `EsperApp/EsperApp/Views/TranscriptView.swift`
- `EsperApp/EsperApp/Views/AudioLevelMeter.swift`

**Create:**
- `EsperApp/EsperApp/FlowButton.swift` — NSPanel subclass (pill button window, drag, auto-fade, right-click menu)
- `EsperApp/EsperApp/Views/FlowButtonView.swift` — SwiftUI view (idle/listening/processing/error states, waveform bars)

**Modify:**
- `EsperApp/EsperApp/Models/AppSettings.swift` — add 4 new settings
- `EsperApp/EsperApp/Views/TranscriptOverlayView.swift` — add top bar, dismiss button, error bar
- `EsperApp/EsperApp/TranscriptPanel.swift` — add onDismiss callback
- `EsperApp/EsperApp/EsperApp.swift` — remove WindowGroup, rewire OverlayController to manage flow button + overlay + auto-dismiss
- `EsperApp/EsperApp/Views/MenuBarView.swift` — simplify (remove device picker, add flow button toggle)
- `EsperApp/EsperApp/Views/OverlaySettingsTab.swift` — add auto-dismiss + flow button sections
- `EsperApp/EsperApp/Views/SettingsView.swift` — remove GeneralTab device picker (moved to overlay)

---

### Task 1: AppSettings — Add New Properties

**Files:**
- Modify: `EsperApp/EsperApp/Models/AppSettings.swift`
- Modify: `EsperApp/EsperAppTests/AppSettingsOverlayTests.swift`

- [ ] **Step 1: Add new settings properties**

In `EsperApp/EsperApp/Models/AppSettings.swift`, add after the existing overlay properties (after `overlayLockPosition`):

```swift
@ObservationIgnored
@AppStorage("flowButtonEnabled") var flowButtonEnabled: Bool = true

@ObservationIgnored
@AppStorage("flowButtonX") var flowButtonX: Double = -1

@ObservationIgnored
@AppStorage("overlayAutoDismiss") var overlayAutoDismiss: Bool = false

@ObservationIgnored
@AppStorage("overlayAutoDismissSeconds") var overlayAutoDismissSeconds: Int = 30
```

- [ ] **Step 2: Update tests**

In `EsperApp/EsperAppTests/AppSettingsOverlayTests.swift`, add the new keys to `overlayKeys`:

```swift
private let overlayKeys = [
    "overlayEnabled", "overlayPosition",
    "overlayTextSize", "overlayTextColor", "overlayMaxLines",
    "overlayOpacity", "overlayDragX", "overlayDragY",
    "overlayPreset", "overlayShowTelegramStatus", "overlayLockPosition",
    "flowButtonEnabled", "flowButtonX",
    "overlayAutoDismiss", "overlayAutoDismissSeconds",
]
```

Add assertions to `testDefaultValues`:

```swift
XCTAssertTrue(settings.flowButtonEnabled)
XCTAssertEqual(settings.flowButtonX, -1.0, accuracy: 0.01)
XCTAssertFalse(settings.overlayAutoDismiss)
XCTAssertEqual(settings.overlayAutoDismissSeconds, 30)
```

- [ ] **Step 3: Build and test**

Run: `xcodebuild test -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -only-testing:EsperAppTests/AppSettingsOverlayTests 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/Models/AppSettings.swift EsperApp/EsperAppTests/AppSettingsOverlayTests.swift
git commit -m "feat(settings): add flow button and auto-dismiss settings"
```

---

### Task 2: FlowButton — NSPanel + FlowButtonView

**Files:**
- Create: `EsperApp/EsperApp/FlowButton.swift`
- Create: `EsperApp/EsperApp/Views/FlowButtonView.swift`

- [ ] **Step 1: Create FlowButtonView.swift**

Create `EsperApp/EsperApp/Views/FlowButtonView.swift`:

```swift
import SwiftUI

// MARK: - Flow Button View Model

@Observable
@MainActor
final class FlowButtonViewModel {
    var engineStatus: EngineStatus = .idle
    var energyLevel: Double = 0.0
    var errorMessage: String?
}

// MARK: - Flow Button View

struct FlowButtonView: View {
    let viewModel: FlowButtonViewModel
    var onToggle: (() -> Void)?
    var onStop: (() -> Void)?

    var body: some View {
        HStack(spacing: 8) {
            switch viewModel.engineStatus {
            case .listening:
                waveformBars
                Text("Listening")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.green)
                Button(action: { onStop?() }) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(.red)
                        .frame(width: 16, height: 16)
                        .overlay(
                            RoundedRectangle(cornerRadius: 1)
                                .fill(.white)
                                .frame(width: 8, height: 8)
                        )
                }
                .buttonStyle(.plain)

            case .transcribing:
                Circle()
                    .fill(.orange)
                    .frame(width: 8, height: 8)
                Text("Processing")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.white.opacity(0.7))

            case .idle:
                if let error = viewModel.errorMessage {
                    Circle()
                        .fill(.red)
                        .frame(width: 8, height: 8)
                    Text(String(error.prefix(30)))
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.white.opacity(0.7))
                        .lineLimit(1)
                } else {
                    Circle()
                        .fill(Color(white: 0.55))
                        .frame(width: 8, height: 8)
                    Text("Esper")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.white.opacity(0.5))
                }

            default:
                Circle()
                    .fill(.orange)
                    .frame(width: 8, height: 8)
                Text(viewModel.engineStatus.displayName)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.white.opacity(0.7))
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .onTapGesture { onToggle?() }
    }

    // MARK: - Waveform Bars

    private var waveformBars: some View {
        HStack(spacing: 2) {
            ForEach(0..<5, id: \.self) { i in
                WaveBar(energy: viewModel.energyLevel, index: i)
            }
        }
        .frame(height: 20)
    }
}

// MARK: - Waveform Bar

private struct WaveBar: View {
    let energy: Double
    let index: Int

    private var barHeight: CGFloat {
        let base = 4.0
        let maxExtra = 16.0
        let phase = Double(index) * 0.2
        let wave = sin(Date.now.timeIntervalSinceReferenceDate * 8 + phase)
        let modulated = energy * (0.5 + 0.5 * wave)
        return base + maxExtra * min(modulated * 3, 1.0)
    }

    var body: some View {
        RoundedRectangle(cornerRadius: 1.5)
            .fill(.white)
            .frame(width: 3, height: barHeight)
            .animation(.linear(duration: 0.1), value: energy)
    }
}
```

- [ ] **Step 2: Create FlowButton.swift**

Create `EsperApp/EsperApp/FlowButton.swift`:

```swift
import AppKit
import SwiftUI

final class FlowButton: NSPanel {
    var onToggle: (() -> Void)?
    var onStop: (() -> Void)?
    var onDragEnd: ((Double) -> Void)?
    var onContextAction: ((FlowButtonAction) -> Void)?

    private var trackingArea: NSTrackingArea?
    private var isMouseInside = false
    private var fadeWorkItem: DispatchWorkItem?
    private let backgroundLayer = CALayer()

    override init(
        contentRect: NSRect,
        styleMask: NSWindow.StyleMask,
        backing: NSWindow.BackingStoreType,
        defer flag: Bool
    ) {
        super.init(
            contentRect: contentRect,
            styleMask: [.nonactivatingPanel, .borderless],
            backing: .buffered,
            defer: false
        )
        isFloatingPanel = true
        level = .floating
        hidesOnDeactivate = false
        isOpaque = false
        backgroundColor = .clear
        hasShadow = true
        isMovableByWindowBackground = true
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        contentView?.wantsLayer = true
        guard let rootLayer = contentView?.layer else { return }
        backgroundLayer.backgroundColor = NSColor.black.withAlphaComponent(0.75).cgColor
        backgroundLayer.cornerRadius = 18
        backgroundLayer.masksToBounds = true
        backgroundLayer.borderWidth = 1
        backgroundLayer.borderColor = NSColor.white.withAlphaComponent(0.12).cgColor
        backgroundLayer.autoresizingMask = [.layerWidthSizable, .layerHeightSizable]
        backgroundLayer.frame = rootLayer.bounds
        rootLayer.addSublayer(backgroundLayer)
        rootLayer.cornerRadius = 18
        rootLayer.masksToBounds = true
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    func setSwiftUIContent(_ hostView: NSView) {
        hostView.frame = contentView?.bounds ?? .zero
        hostView.autoresizingMask = [.width, .height]
        hostView.wantsLayer = true
        contentView?.addSubview(hostView)
    }

    // MARK: - Tracking Area

    func installTrackingArea() {
        guard let cv = contentView else { return }
        if let existing = trackingArea {
            cv.removeTrackingArea(existing)
        }
        let area = NSTrackingArea(
            rect: cv.bounds,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        cv.addTrackingArea(area)
        trackingArea = area
    }

    override func mouseEntered(with event: NSEvent) {
        fadeWorkItem?.cancel()
        isMouseInside = true
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.15
            animator().alphaValue = 1.0
        }
    }

    override func mouseExited(with event: NSEvent) {
        isMouseInside = false
        scheduleAutoFade()
    }

    override func mouseUp(with event: NSEvent) {
        super.mouseUp(with: event)
        onDragEnd?(frame.origin.x)
        // Constrain to bottom edge after drag
        constrainToBottomEdge()
    }

    // MARK: - Context Menu

    override func rightMouseDown(with event: NSEvent) {
        guard let cv = contentView else { return }
        let menu = buildContextMenu()
        NSMenu.popUpContextMenu(menu, with: event, for: cv)
    }

    private func buildContextMenu() -> NSMenu {
        let menu = NSMenu()

        let settingsItem = NSMenuItem(title: "Settings…", action: #selector(contextAction(_:)), keyEquivalent: ",")
        settingsItem.target = self
        settingsItem.representedObject = FlowButtonAction.openSettings
        menu.addItem(settingsItem)

        return menu
    }

    @objc private func contextAction(_ sender: NSMenuItem) {
        guard let action = sender.representedObject as? FlowButtonAction else { return }
        onContextAction?(action)
    }

    // MARK: - Positioning

    func positionAtBottom(x: Double? = nil) {
        guard let screen = NSScreen.main else { return }
        let screenFrame = screen.visibleFrame
        let buttonX = x ?? Double(screenFrame.midX - frame.width / 2)
        let buttonY = Double(screenFrame.minY + 16)
        setFrameOrigin(NSPoint(x: buttonX, y: buttonY))
    }

    private func constrainToBottomEdge() {
        guard let screen = NSScreen.main else { return }
        let screenFrame = screen.visibleFrame
        var origin = frame.origin
        // Keep on bottom edge
        origin.y = screenFrame.minY + 16
        // Keep within horizontal bounds
        origin.x = max(screenFrame.minX + 16, min(origin.x, screenFrame.maxX - frame.width - 16))
        setFrameOrigin(origin)
    }

    // MARK: - Auto-Fade

    func scheduleAutoFade() {
        fadeWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.isMouseInside else { return }
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.5
                self.animator().alphaValue = 0.4
            }
        }
        fadeWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 5, execute: work)
    }

    // MARK: - Show/Hide

    func showButton() {
        alphaValue = 0
        orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
            animator().alphaValue = 1
        }
        scheduleAutoFade()
    }

    func hideButton() {
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.15
            animator().alphaValue = 0
        }, completionHandler: {
            self.orderOut(nil)
        })
    }

    // MARK: - Listening State Border

    func setListeningBorder(_ listening: Bool) {
        if listening {
            backgroundLayer.borderColor = NSColor(red: 0.2, green: 0.78, blue: 0.35, alpha: 0.3).cgColor
        } else {
            backgroundLayer.borderColor = NSColor.white.withAlphaComponent(0.12).cgColor
        }
    }
}

// MARK: - Flow Button Actions

@objc enum FlowButtonAction: Int {
    case openSettings
}
```

- [ ] **Step 3: Add both files to Xcode project**

Ensure `FlowButton.swift` and `FlowButtonView.swift` are added to the EsperApp target in the Xcode project. If the project uses folder references, files are auto-discovered. Otherwise, add to `project.pbxproj`.

- [ ] **Step 4: Build**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -quiet 2>&1 | tail -10`
Expected: BUILD SUCCEEDED.

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/FlowButton.swift EsperApp/EsperApp/Views/FlowButtonView.swift EsperApp/EsperApp.xcodeproj/project.pbxproj
git commit -m "feat: add FlowButton NSPanel and FlowButtonView with waveform animation"
```

---

### Task 3: Overlay Top Bar — Device Picker, Gear, Audio Meter, Dismiss

**Files:**
- Modify: `EsperApp/EsperApp/Views/TranscriptOverlayView.swift`
- Modify: `EsperApp/EsperApp/TranscriptPanel.swift`

- [ ] **Step 1: Add top bar properties to OverlayViewModel**

In `EsperApp/EsperApp/Views/TranscriptOverlayView.swift`, add to `OverlayViewModel`:

```swift
var energyLevel: Double = 0.0
var devices: [AudioDevice] = []
var selectedDevice: Int? = nil
var errorMessage: String? = nil
var onSelectDevice: ((Int) -> Void)?
var onDismiss: (() -> Void)?
var onOpenSettings: (() -> Void)?
```

- [ ] **Step 2: Add top bar to TranscriptOverlayView body**

Replace the `body` in `TranscriptOverlayView` to include a top bar between the status strip and the scroll view:

```swift
var body: some View {
    HStack(spacing: 0) {
        statusStrip
        VStack(spacing: 0) {
            topBar
            ScrollViewReader { proxy in
                ScrollView(.vertical, showsIndicators: true) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(viewModel.lines) { line in
                            lineView(line)
                        }
                    }
                    .padding(.horizontal, 18)
                    .padding(.vertical, 14)
                }
                .onChange(of: viewModel.lines.last?.id) { _, newID in
                    if let id = newID {
                        proxy.scrollTo(id, anchor: .bottom)
                    }
                }
            }
            if let error = viewModel.errorMessage {
                errorBar(error)
            }
        }
    }
    .frame(width: 560, alignment: .leading)
    .frame(maxHeight: maxHeight)
    .compositingGroup()
    .opacity(viewModel.opacity)
    .transaction { $0.disablesAnimations = true }
}
```

- [ ] **Step 3: Add top bar view**

Add to `TranscriptOverlayView`:

```swift
// MARK: - Top Bar

private var topBar: some View {
    HStack(spacing: 8) {
        // Audio level meter
        GeometryReader { _ in
            RoundedRectangle(cornerRadius: 1.5)
                .fill(.white.opacity(0.08))
                .frame(width: 80, height: 3)
                .overlay(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(.green)
                        .frame(width: 80 * min(viewModel.energyLevel * 3, 1.0), height: 3)
                }
        }
        .frame(width: 80, height: 3)

        Spacer()

        // Device picker
        if !viewModel.devices.isEmpty {
            Picker("", selection: Binding(
                get: { viewModel.selectedDevice ?? -1 },
                set: { if $0 != -1 { viewModel.onSelectDevice?($0) } }
            )) {
                ForEach(viewModel.devices) { device in
                    Text(device.name).tag(device.index)
                }
            }
            .labelsHidden()
            .fixedSize()
            .font(.system(size: 10))
            .controlSize(.mini)
        }

        // Gear icon
        Button(action: { viewModel.onOpenSettings?() }) {
            Image(systemName: "gear")
                .font(.system(size: 11))
                .foregroundStyle(.white.opacity(0.4))
        }
        .buttonStyle(.plain)

        // Dismiss X
        Button(action: { viewModel.onDismiss?() }) {
            Image(systemName: "xmark")
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.white.opacity(0.4))
        }
        .buttonStyle(.plain)
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 6)
    .frame(height: 32)
    .background(
        Rectangle()
            .fill(.white.opacity(0.02))
    )
    .overlay(alignment: .bottom) {
        Rectangle().fill(.white.opacity(0.06)).frame(height: 1)
    }
}
```

- [ ] **Step 4: Add error bar view**

Add to `TranscriptOverlayView`:

```swift
// MARK: - Error Bar

private func errorBar(_ message: String) -> some View {
    HStack(spacing: 6) {
        Image(systemName: "exclamationmark.triangle")
            .font(.system(size: 11))
        Text(message)
            .font(.system(size: 12))
            .lineLimit(2)
    }
    .foregroundStyle(Color(red: 1, green: 0.27, blue: 0.23))
    .padding(.horizontal, 14)
    .padding(.vertical, 6)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Color(red: 1, green: 0.27, blue: 0.23).opacity(0.15))
    .overlay(alignment: .top) {
        Rectangle().fill(Color(red: 1, green: 0.27, blue: 0.23).opacity(0.2)).frame(height: 1)
    }
}
```

- [ ] **Step 5: Update maxHeight to account for top bar**

Update the `maxHeight` computed property:

```swift
private var maxHeight: CGFloat {
    let lineHeight = viewModel.fontSize * 1.4
    let spacing: CGFloat = 6
    let padding: CGFloat = 28
    let topBarHeight: CGFloat = 32
    let errorHeight: CGFloat = viewModel.errorMessage != nil ? 34 : 0
    return topBarHeight + CGFloat(viewModel.maxLines) * (lineHeight + spacing) - spacing + padding + errorHeight
}
```

- [ ] **Step 6: Build**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -quiet 2>&1 | tail -10`
Expected: BUILD SUCCEEDED.

- [ ] **Step 7: Commit**

```bash
git add EsperApp/EsperApp/Views/TranscriptOverlayView.swift
git commit -m "feat(overlay): add top bar with device picker, gear, audio meter, dismiss, error bar"
```

---

### Task 4: EsperApp — Remove Main Window, Wire Flow Button + Overlay

**Files:**
- Modify: `EsperApp/EsperApp/EsperApp.swift`

This is the largest task. It:
1. Removes `WindowGroup` and `openWindow` calls
2. Rewires `AppDelegate` to open Settings on dock click
3. Adds flow button lifecycle to `OverlayController`
4. Wires top bar callbacks (device picker, gear, dismiss)
5. Adds auto-dismiss logic

- [ ] **Step 1: Rewrite AppDelegate**

Replace the `AppDelegate` class and remove the `reopenMainWindow` notification:

```swift
// Remove this line entirely:
// extension Notification.Name {
//     static let reopenMainWindow = Notification.Name("reopenMainWindow")
// }

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        sender.activate(ignoringOtherApps: true)
        return true
    }
}
```

- [ ] **Step 2: Rewrite EsperApp body**

Remove `WindowGroup`, remove `openWindow` environment, remove `openWindow(id: "main")` from init:

```swift
@main
struct EsperApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var engine = TranscriptionEngine()
    @State private var launched = false
    @State private var overlayController = OverlayController()
    private let updaterController: SPUStandardUpdaterController

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(engine: engine, overlayController: overlayController, updater: updaterController.updater)
                .onAppear { ensureLaunched() }
        } label: {
            Image(systemName: engine.status == .listening ? "waveform.circle.fill" : "waveform.circle")
        }

        Settings {
            SettingsView(engine: engine, overlayController: overlayController, updater: updaterController.updater)
        }
    }

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
        }
    }

    init() {
        updaterController = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
    }
}
```

- [ ] **Step 3: Rebuild OverlayController with flow button management**

Replace the entire `OverlayController` class. Key changes:
- Add `FlowButton` and `FlowButtonViewModel` management
- Wire top bar callbacks (onSelectDevice, onDismiss, onOpenSettings)
- Add auto-dismiss logic
- Update flow button state in the polling loop
- Show overlay when listening starts, dismiss on X click

```swift
@Observable
@MainActor
final class OverlayController {
    private var panel: TranscriptPanel?
    private let viewModel = OverlayViewModel()
    private var panelCreated = false
    private var updateTask: Task<Void, Never>?
    private var lastColorHex: String = ""
    private var panelVisible = false
    private var dismissed = false // user manually dismissed
    private var autoDismissTask: Task<Void, Never>?

    // Flow button
    private var flowButton: FlowButton?
    private let flowViewModel = FlowButtonViewModel()
    private var flowButtonCreated = false

    var previewMode = false

    func bind(engine: TranscriptionEngine, settings: AppSettings) {
        guard updateTask == nil else { return }
        updateTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                self.update(engine: engine, settings: settings)
                try? await Task.sleep(for: .milliseconds(200))
            }
        }
    }

    private func update(engine: TranscriptionEngine, settings: AppSettings) {
        // --- Flow Button ---
        updateFlowButton(engine: engine, settings: settings)

        // --- Overlay ---
        let isActive = engine.status == .listening || engine.status == .transcribing
        let hasContent = !engine.sentences.isEmpty || !engine.currentText.isEmpty

        // Un-dismiss when starting a new session
        if isActive && dismissed {
            dismissed = false
            autoDismissTask?.cancel()
        }

        let shouldShow = settings.overlayEnabled && !dismissed &&
            (isActive || hasContent || previewMode)

        if shouldShow {
            ensurePanel(engine: engine, settings: settings)

            CATransaction.begin()
            CATransaction.setDisableActions(true)

            let newLines = overlayLines(engine: engine, settings: settings)
            if newLines != viewModel.lines { viewModel.lines = newLines }

            let newStatus = engine.status
            if newStatus != viewModel.engineStatus { viewModel.engineStatus = newStatus }

            let newSize = settings.overlayFontSize
            if newSize != viewModel.fontSize { viewModel.fontSize = newSize }

            let newOpacity = settings.overlayOpacity
            if newOpacity != viewModel.opacity { viewModel.opacity = newOpacity }

            let newColorHex = settings.overlayTextColor
            if newColorHex != lastColorHex {
                lastColorHex = newColorHex
                viewModel.textColor = settings.parsedOverlayColor
            }

            let newMaxLines = settings.overlayMaxLines
            if newMaxLines != viewModel.maxLines { viewModel.maxLines = newMaxLines }

            viewModel.showTelegramStatus = settings.overlayShowTelegramStatus && settings.telegramEnabled
            viewModel.energyLevel = engine.energyLevel
            viewModel.devices = engine.devices
            viewModel.selectedDevice = engine.selectedDevice
            viewModel.errorMessage = engine.errorMessage

            panel?.isPositionLocked = settings.overlayLockPosition

            CATransaction.commit()

            if !panelVisible {
                let locked = settings.overlayLockPosition
                if !locked, settings.overlayDragX >= 0, settings.overlayDragY >= 0 {
                    panel?.repositionToCoordinate(x: settings.overlayDragX, y: settings.overlayDragY)
                } else {
                    panel?.reposition(to: settings.parsedOverlayPosition)
                }
                panel?.animateIn()
                panelVisible = true
            }

            // Auto-dismiss: schedule when engine goes idle with content
            if !isActive && hasContent && settings.overlayAutoDismiss {
                scheduleAutoDismiss(seconds: settings.overlayAutoDismissSeconds)
            } else {
                autoDismissTask?.cancel()
            }
        } else if panelVisible {
            panel?.animateOut()
            panelVisible = false
        }
    }

    // MARK: - Flow Button

    private func updateFlowButton(engine: TranscriptionEngine, settings: AppSettings) {
        if settings.flowButtonEnabled {
            ensureFlowButton(engine: engine, settings: settings)
            flowViewModel.engineStatus = engine.status
            flowViewModel.energyLevel = engine.energyLevel
            flowViewModel.errorMessage = engine.errorMessage
            flowButton?.setListeningBorder(engine.status == .listening)

            // Cancel auto-fade while listening
            if engine.status == .listening {
                flowButton?.alphaValue = 1.0
            }
        } else {
            flowButton?.hideButton()
        }
    }

    private func ensureFlowButton(engine: TranscriptionEngine, settings: AppSettings) {
        guard !flowButtonCreated else { return }
        let btn = FlowButton(
            contentRect: NSRect(x: 0, y: 0, width: 160, height: 36),
            styleMask: [],
            backing: .buffered,
            defer: false
        )
        let host = NSHostingView(rootView: FlowButtonView(
            viewModel: flowViewModel,
            onToggle: { [weak self] in
                if engine.status == .listening {
                    engine.stopListening()
                } else if engine.status == .idle {
                    engine.startListening()
                }
            },
            onStop: {
                engine.stopListening()
            }
        ))
        btn.setSwiftUIContent(host)
        btn.installTrackingArea()

        btn.onDragEnd = { x in
            settings.flowButtonX = x
        }
        btn.onContextAction = { action in
            switch action {
            case .openSettings:
                NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
            }
        }

        let savedX = settings.flowButtonX >= 0 ? settings.flowButtonX : nil
        btn.positionAtBottom(x: savedX)
        btn.showButton()

        flowButton = btn
        flowButtonCreated = true
    }

    // MARK: - Overlay Panel

    private func ensurePanel(engine: TranscriptionEngine, settings: AppSettings) {
        guard !panelCreated else { return }
        let panel = TranscriptPanel(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 140),
            styleMask: [],
            backing: .buffered,
            defer: false
        )

        // Wire top bar callbacks
        viewModel.onSelectDevice = { index in
            engine.setDevice(index)
        }
        viewModel.onDismiss = { [weak self] in
            self?.dismissOverlay()
        }
        viewModel.onOpenSettings = {
            NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        }

        let host = NSHostingView(rootView: TranscriptOverlayView(viewModel: viewModel))
        panel.setSwiftUIContent(host)
        panel.installTrackingArea()

        panel.onDragEnd = { origin in
            settings.overlayDragX = origin.x
            settings.overlayDragY = origin.y
        }
        panel.onHoverChanged = { _ in }
        panel.onContextAction = { [weak self] action in
            self?.handleContextAction(action, settings: settings)
        }

        self.panel = panel
        panelCreated = true
    }

    private func dismissOverlay() {
        dismissed = true
        panel?.animateOut()
        panelVisible = false
    }

    // MARK: - Auto-Dismiss

    private func scheduleAutoDismiss(seconds: Int) {
        autoDismissTask?.cancel()
        autoDismissTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(seconds))
            guard !Task.isCancelled, let self, self.panelVisible else { return }
            self.dismissOverlay()
        }
    }

    // MARK: - Context Menu

    private func handleContextAction(_ action: OverlayContextAction, settings: AppSettings) {
        switch action {
        case .textSize(let size):
            settings.overlayTextSize = size
            settings.overlayPreset = "custom"
        case .opacity(let value):
            settings.overlayOpacity = value
            settings.overlayPreset = "custom"
        case .preset(let preset):
            preset.apply(to: settings)
        case .position(let pos):
            settings.overlayPosition = pos.rawValue
            panel?.reposition(to: pos)
        case .lockPosition:
            settings.overlayLockPosition.toggle()
        case .openSettings:
            NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
        }
    }

    // MARK: - Overlay Lines

    private static let sampleLines = [
        "This is a preview of the overlay",
        "Transcription text will appear here",
        "Adjust settings to customize the look",
    ]

    private func overlayLines(engine: TranscriptionEngine, settings: AppSettings) -> [OverlayLine] {
        let maxLines = settings.overlayMaxLines
        let telegramEnabled = settings.telegramEnabled && !settings.telegramBotToken.isEmpty

        if previewMode && engine.status != .listening {
            return Self.sampleLines.prefix(maxLines).enumerated().map { i, text in
                let state: LineState = i == 0 ? .sent : (i == 1 ? .queued : .draft)
                return OverlayLine(id: "sample-\(i)", text: text, state: state, confidence: 1.0)
            }
        }

        var raw: [OverlayLine] = engine.sentences.enumerated().map { i, text in
            let state: LineState
            if engine.sentSentenceIndices.contains(i) {
                state = .sent
            } else if telegramEnabled {
                state = .queued
            } else {
                state = .finalized
            }
            return OverlayLine(id: "s-\(i)", text: text, state: state, confidence: 1.0)
        }

        let current = engine.currentText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !current.isEmpty, current != raw.last?.text {
            let confidence = 1.0 - engine.lastNoSpeechProb
            raw.append(OverlayLine(id: "current", text: current, state: .draft, confidence: confidence))
        }

        return raw
    }
}
```

- [ ] **Step 4: Build**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -quiet 2>&1 | tail -10`

Fix any compile errors — likely references to `MainWindowView` in other files. If `StatusBadge` is only used by `MainWindowView` and `MenuBarView`, keep it (MenuBarView still uses it).

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/EsperApp.swift
git commit -m "feat: remove main window, wire flow button and overlay lifecycle"
```

---

### Task 5: MenuBarView — Simplify

**Files:**
- Modify: `EsperApp/EsperApp/Views/MenuBarView.swift`

- [ ] **Step 1: Rewrite MenuBarView**

Replace entire contents of `MenuBarView.swift`:

```swift
import Sparkle
import SwiftUI

struct MenuBarView: View {
    let engine: TranscriptionEngine
    let overlayController: OverlayController
    let updater: SPUUpdater
    @State private var overlayEnabled = false
    @State private var flowButtonEnabled = true

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

        Button(flowButtonEnabled ? "Hide Flow Button" : "Show Flow Button") {
            flowButtonEnabled.toggle()
            engine.settings.flowButtonEnabled = flowButtonEnabled
        }

        Divider()

        CheckForUpdatesView(updater: updater)

        Divider()

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
        .onAppear {
            overlayEnabled = engine.settings.overlayEnabled
            flowButtonEnabled = engine.settings.flowButtonEnabled
        }
    }
}
```

- [ ] **Step 2: Build**

Run: `xcodebuild build -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -quiet 2>&1 | tail -10`
Expected: BUILD SUCCEEDED.

- [ ] **Step 3: Commit**

```bash
git add EsperApp/EsperApp/Views/MenuBarView.swift
git commit -m "feat(menubar): simplify — remove device picker, add flow button toggle"
```

---

### Task 6: Settings — Add Auto-Dismiss + Flow Button Sections, Clean Up

**Files:**
- Modify: `EsperApp/EsperApp/Views/OverlaySettingsTab.swift`
- Modify: `EsperApp/EsperApp/Views/SettingsView.swift`

- [ ] **Step 1: Add new sections to OverlaySettingsTab**

In `OverlaySettingsTab.swift`, add state variables:

```swift
@State private var autoDismiss = false
@State private var autoDismissSeconds = 30
@State private var flowButtonEnabled = true
```

Add sections to the body (inside the `if enabled` block, after the existing "Indicators" section):

```swift
Section("Dismiss") {
    Toggle("Auto-dismiss after stopping", isOn: $autoDismiss)
    if autoDismiss {
        Picker("After", selection: $autoDismissSeconds) {
            Text("10 seconds").tag(10)
            Text("30 seconds").tag(30)
            Text("60 seconds").tag(60)
            Text("2 minutes").tag(120)
        }
    }
}

Section("Flow Button") {
    Toggle("Show Flow Button", isOn: $flowButtonEnabled)
    Text("Floating button for quick start/stop. You can also use Option+Space.")
        .font(.caption)
        .foregroundStyle(.secondary)
}
```

Add onChange handlers:

```swift
.onChange(of: autoDismiss) { _, val in settings.overlayAutoDismiss = val }
.onChange(of: autoDismissSeconds) { _, val in settings.overlayAutoDismissSeconds = val }
.onChange(of: flowButtonEnabled) { _, val in settings.flowButtonEnabled = val }
```

Update `loadFromSettings()`:

```swift
autoDismiss = settings.overlayAutoDismiss
autoDismissSeconds = settings.overlayAutoDismissSeconds
flowButtonEnabled = settings.flowButtonEnabled
```

- [ ] **Step 2: Remove GeneralTab device picker from SettingsView**

The GeneralTab in `SettingsView.swift` has a device picker that's now in the overlay. Either remove GeneralTab entirely or replace it with a minimal stub. Since the General tab is still useful for device selection as a fallback, keep it but simplify the label:

Actually, keep GeneralTab as-is — it's the fallback when overlay is hidden. No change needed.

- [ ] **Step 3: Build and test**

Run: `xcodebuild test -project EsperApp/EsperApp.xcodeproj -scheme EsperApp 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/Views/OverlaySettingsTab.swift
git commit -m "feat(settings): add auto-dismiss and flow button toggle sections"
```

---

### Task 7: Delete Old Files + Final Integration

**Files:**
- Delete: `EsperApp/EsperApp/Views/MainWindowView.swift`
- Delete: `EsperApp/EsperApp/Views/TranscriptView.swift`
- Delete: `EsperApp/EsperApp/Views/AudioLevelMeter.swift`

- [ ] **Step 1: Delete the files**

```bash
rm EsperApp/EsperApp/Views/MainWindowView.swift
rm EsperApp/EsperApp/Views/TranscriptView.swift
rm EsperApp/EsperApp/Views/AudioLevelMeter.swift
```

- [ ] **Step 2: Remove from Xcode project**

If using explicit file references in pbxproj, remove the three files. If folder references, they're auto-removed.

- [ ] **Step 3: Grep for remaining references**

Search for `MainWindowView`, `TranscriptView`, `AudioLevelMeter` in all Swift files. Remove any remaining references or imports.

- [ ] **Step 4: Build and test**

Run: `xcodebuild test -project EsperApp/EsperApp.xcodeproj -scheme EsperApp 2>&1 | tail -30`
Expected: All tests PASS, BUILD SUCCEEDED.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: delete MainWindowView, TranscriptView, AudioLevelMeter — overlay is primary UI"
```

- [ ] **Step 6: Manual verification checklist**

- [ ] App launches with flow button at bottom-center, no main window
- [ ] Click flow button → starts listening, overlay appears
- [ ] Click stop on flow button → stops listening, overlay persists
- [ ] Click X on overlay → overlay dismisses
- [ ] Device picker in overlay top bar works
- [ ] Gear icon opens Settings
- [ ] Flow button auto-fades after 5s idle
- [ ] Flow button right-click → Settings
- [ ] Menu bar: start/stop, show/hide overlay, show/hide flow button all work
- [ ] Settings: auto-dismiss + flow button toggles work
- [ ] Global hotkey (Option+Space) still works
- [ ] Dock click opens Settings
- [ ] Waveform bars animate during listening
