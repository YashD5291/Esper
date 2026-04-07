# Morphing Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the separate flow button and transcript overlay with a single NSPanel that morphs between a compact pill and a full transcript overlay using spring animation.

**Architecture:** One `EsperPanel` (NSPanel subclass) hosts one `EsperPanelView` (SwiftUI) that switches between pill and overlay modes via a `PanelMode` enum. A display-link-driven spring solver animates the panel frame, while `withAnimation(.spring(...))` handles SwiftUI content cross-fade. Layer properties (cornerRadius, backgroundColor, borderColor) are updated per-frame inside the display-link callback.

**Tech Stack:** SwiftUI, AppKit (NSPanel), Core Animation, CADisplayLink

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `EsperApp/EsperApp/Views/TranscriptOverlayView.swift` | Modify | Add `PanelMode` enum, extend `OverlayViewModel` with pill/morph properties, add traffic light top bar, scope `disablesAnimations` |
| `EsperApp/EsperApp/EsperPanel.swift` | Create | Unified NSPanel subclass with spring morph animation, positioning, tracking, context menus |
| `EsperApp/EsperApp/Views/EsperPanelView.swift` | Create | SwiftUI view with pill/overlay mode switch and cross-fade transition |
| `EsperApp/EsperApp/EsperApp.swift` | Modify | Rewrite `OverlayController` to use single `EsperPanel` |
| `EsperApp/EsperApp/FlowButton.swift` | Delete | Replaced by EsperPanel |
| `EsperApp/EsperApp/Views/FlowButtonView.swift` | Delete | Replaced by EsperPanelView pill mode |
| `EsperApp/EsperApp/TranscriptPanel.swift` | Delete | Replaced by EsperPanel |
| `EsperApp/EsperApp/Models/OverlayPosition.swift` | Delete | Overlay position now derived from pill |
| `EsperApp/EsperApp/Models/AppSettings.swift` | Modify | Remove `overlayDragX`, `overlayDragY`, `overlayPosition`, `parsedOverlayPosition`; keep `flowButtonX` |
| `EsperApp/EsperAppTests/OverlayPositionTests.swift` | Delete | Tests for removed OverlayPosition |
| `EsperApp/EsperAppTests/AppSettingsOverlayTests.swift` | Modify | Remove tests for removed properties |

### Dependencies

```
Task 1 → Task 2 (parallel) ─┐
Task 1 → Task 3 → Task 4 ───┼→ Task 5 → Task 6
```

---

### Task 1: Add PanelMode and Extend OverlayViewModel

**Files:**
- Modify: `EsperApp/EsperApp/Views/TranscriptOverlayView.swift`

- [ ] **Step 1: Add `PanelMode` enum at the top of TranscriptOverlayView.swift**

Add after the existing imports (line 2), before `LineState`:

```swift
// MARK: - Panel Mode

enum PanelMode: Equatable {
    case pill
    case overlay
}
```

- [ ] **Step 2: Add new properties to OverlayViewModel**

In `OverlayViewModel` (currently at line ~15), add these properties after the existing ones:

```swift
    // Panel morph state
    var mode: PanelMode = .pill
    var overlayDismissed = false

    // Additional callbacks
    var onToggle: (() -> Void)?
    var onStop: (() -> Void)?
    var onCollapse: (() -> Void)?
```

- [ ] **Step 3: Build and verify**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(BUILD|error:)' | tail -5`

Expected: `BUILD SUCCEEDED` — new properties are optional/have defaults, so existing code is unaffected.

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/Views/TranscriptOverlayView.swift
git commit -m "feat: add PanelMode enum and extend OverlayViewModel for morphing panel"
```

---

### Task 2: Create EsperPanel NSPanel

**Files:**
- Create: `EsperApp/EsperApp/EsperPanel.swift`

- [ ] **Step 1: Create EsperPanel.swift with basic panel setup**

Create `EsperApp/EsperApp/EsperPanel.swift`:

```swift
import AppKit
import SwiftUI

// MARK: - Context Actions

enum EsperPanelContextAction {
    case textSize(String)
    case opacity(Double)
    case preset(OverlayPreset)
    case lockPosition
    case openSettings
}

// MARK: - Spring State

private struct SpringState {
    var position: CGFloat = 0   // 0 = pill, 1 = overlay
    var velocity: CGFloat = 0
}

// MARK: - Esper Panel

final class EsperPanel: NSPanel {

    // MARK: Callbacks

    var onDragEnd: ((Double) -> Void)?
    var onContextAction: ((EsperPanelContextAction) -> Void)?

    // MARK: State

    private(set) var currentMode: PanelMode = .pill
    var isPositionLocked = false

    // MARK: Layer

    private let backgroundLayer = CALayer()

    // MARK: Spring Animation

    private var displayLink: CADisplayLink?
    private var spring = SpringState()
    private var targetPosition: CGFloat = 0
    private var lastTimestamp: CFTimeInterval = 0

    private var pillFrame: NSRect = .zero
    private var overlayFrame: NSRect = .zero

    // Spring parameters
    private let expandStiffness: CGFloat = 280
    private let expandDamping: CGFloat = 22
    private let collapseStiffness: CGFloat = 280
    private let collapseDamping: CGFloat = 34

    // Visual targets per mode
    private let pillCornerRadius: CGFloat = 18
    private let overlayCornerRadius: CGFloat = 12
    private let pillBgAlpha: CGFloat = 0.75
    private let overlayBgAlpha: CGFloat = 0.82
    private let pillBorderColor = NSColor.white.withAlphaComponent(0.12).cgColor
    private let overlayBorderColor = NSColor.white.withAlphaComponent(0.08).cgColor
    private let listeningBorderColor = NSColor(red: 0.2, green: 0.78, blue: 0.35, alpha: 0.3).cgColor

    // MARK: Auto-Fade

    private var fadeWorkItem: DispatchWorkItem?
    private var isMouseInside = false

    // MARK: Init

    override init(
        contentRect: NSRect,
        styleMask: NSWindow.StyleMask,
        backing: NSWindow.BackingStoreType,
        defer flag: Bool
    ) {
        super.init(contentRect: contentRect, styleMask: styleMask, backing: backing, defer: flag)

        level = .floating
        isFloatingPanel = true
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        backgroundColor = .clear
        isOpaque = false
        hasShadow = true
        hidesOnDeactivate = false
        isMovableByWindowBackground = true
        ignoresMouseEvents = false

        let rootLayer = CALayer()
        rootLayer.masksToBounds = true
        rootLayer.cornerRadius = pillCornerRadius
        contentView?.wantsLayer = true
        contentView?.layer = rootLayer

        backgroundLayer.cornerRadius = pillCornerRadius
        backgroundLayer.backgroundColor = NSColor.black.withAlphaComponent(pillBgAlpha).cgColor
        backgroundLayer.borderWidth = 1
        backgroundLayer.borderColor = pillBorderColor
        rootLayer.addSublayer(backgroundLayer)
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    override func layoutIfNeeded() {
        super.layoutIfNeeded()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        backgroundLayer.frame = contentView?.bounds ?? .zero
        CATransaction.commit()
    }

    // MARK: - SwiftUI Content

    func setSwiftUIContent(_ hostView: NSHostingView<some View>) {
        hostView.translatesAutoresizingMaskIntoConstraints = false
        hostView.sizingOptions = []
        contentView?.addSubview(hostView)
        hostView.autoresizingMask = [.width, .height]
        hostView.frame = contentView?.bounds ?? .zero

        if let layer = hostView.layer {
            layer.layerContentsRedrawPolicy = .onSetNeedsDisplay
        }
    }

    // MARK: - Tracking Area

    private var trackingArea: NSTrackingArea?

    func installTrackingArea() {
        if let existing = trackingArea {
            contentView?.removeTrackingArea(existing)
        }
        let area = NSTrackingArea(
            rect: .zero,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        contentView?.addTrackingArea(area)
        trackingArea = area
    }

    // MARK: - Mouse Events

    override func mouseEntered(with event: NSEvent) {
        isMouseInside = true
        fadeWorkItem?.cancel()
        if currentMode == .pill {
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.15
                ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
                self.animator().alphaValue = 1.0
            }
        } else {
            ignoresMouseEvents = false
            isMovableByWindowBackground = !isPositionLocked
        }
    }

    override func mouseExited(with event: NSEvent) {
        isMouseInside = false
        if currentMode == .pill {
            scheduleAutoFade()
        } else {
            let item = DispatchWorkItem { [weak self] in
                guard let self, !self.isMouseInside else { return }
                self.ignoresMouseEvents = true
                self.isMovableByWindowBackground = false
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: item)
        }
    }

    override func mouseUp(with event: NSEvent) {
        super.mouseUp(with: event)
        onDragEnd?(frame.origin.x)
        constrainToBottomEdge()
    }

    override func rightMouseDown(with event: NSEvent) {
        let menu = NSMenu()

        if currentMode == .overlay {
            // Text Size submenu
            let sizeMenu = NSMenu()
            for size in ["small", "medium", "large"] {
                let item = NSMenuItem(title: size.capitalized, action: #selector(contextAction(_:)), keyEquivalent: "")
                item.target = self
                item.representedObject = EsperPanelContextAction.textSize(size)
                sizeMenu.addItem(item)
            }
            let sizeItem = NSMenuItem(title: "Text Size", action: nil, keyEquivalent: "")
            sizeItem.submenu = sizeMenu
            menu.addItem(sizeItem)

            // Opacity submenu
            let opacityMenu = NSMenu()
            for (label, value) in [("25%", 0.25), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0)] {
                let item = NSMenuItem(title: label, action: #selector(contextAction(_:)), keyEquivalent: "")
                item.target = self
                item.representedObject = EsperPanelContextAction.opacity(value)
                opacityMenu.addItem(item)
            }
            let opacityItem = NSMenuItem(title: "Opacity", action: nil, keyEquivalent: "")
            opacityItem.submenu = opacityMenu
            menu.addItem(opacityItem)

            // Preset submenu
            let presetMenu = NSMenu()
            for preset in OverlayPreset.allCases where preset != .custom {
                let item = NSMenuItem(title: preset.displayName, action: #selector(contextAction(_:)), keyEquivalent: "")
                item.target = self
                item.representedObject = EsperPanelContextAction.preset(preset)
                presetMenu.addItem(item)
            }
            let presetItem = NSMenuItem(title: "Preset", action: nil, keyEquivalent: "")
            presetItem.submenu = presetMenu
            menu.addItem(presetItem)

            // Lock Position
            let lockItem = NSMenuItem(
                title: isPositionLocked ? "Unlock Position" : "Lock Position",
                action: #selector(contextAction(_:)),
                keyEquivalent: ""
            )
            lockItem.target = self
            lockItem.representedObject = EsperPanelContextAction.lockPosition
            menu.addItem(lockItem)

            menu.addItem(.separator())
        }

        // Settings (both modes)
        let settingsItem = NSMenuItem(title: "Settings…", action: #selector(contextAction(_:)), keyEquivalent: "")
        settingsItem.target = self
        settingsItem.representedObject = EsperPanelContextAction.openSettings
        menu.addItem(settingsItem)

        NSMenu.popUpContextMenu(menu, with: event, for: contentView!)
    }

    @objc private func contextAction(_ sender: NSMenuItem) {
        guard let action = sender.representedObject as? EsperPanelContextAction else { return }
        onContextAction?(action)
    }

    // MARK: - Positioning

    func positionAtBottom(x: Double? = nil) {
        guard let screen = NSScreen.main?.visibleFrame else { return }
        let xPos = x ?? (screen.midX - frame.width / 2)
        let yPos = screen.minY + 16
        setFrameOrigin(NSPoint(x: xPos, y: yPos))
    }

    func constrainToBottomEdge() {
        guard let screen = NSScreen.main?.visibleFrame else { return }
        let y = screen.minY + 16
        let x = min(max(frame.origin.x, screen.minX + 16), screen.maxX - frame.width - 16)
        setFrameOrigin(NSPoint(x: x, y: y))
    }

    // MARK: - Auto-Fade (Pill Mode Only)

    private func scheduleAutoFade() {
        fadeWorkItem?.cancel()
        let item = DispatchWorkItem { [weak self] in
            guard let self, !self.isMouseInside, self.currentMode == .pill else { return }
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.5
                ctx.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                self.animator().alphaValue = 0.4
            }
        }
        fadeWorkItem = item
        DispatchQueue.main.asyncAfter(deadline: .now() + 5, execute: item)
    }

    // MARK: - Show / Hide

    func showPanel() {
        alphaValue = 0
        orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
            self.animator().alphaValue = 1.0
        }
        scheduleAutoFade()
    }

    func hidePanel() {
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.15
            ctx.timingFunction = CAMediaTimingFunction(name: .easeIn)
            self.animator().alphaValue = 0
        }, completionHandler: {
            self.orderOut(nil)
        })
    }

    // MARK: - Listening Border

    func setListeningBorder(_ listening: Bool) {
        guard currentMode == .pill else { return }
        backgroundLayer.borderColor = listening ? listeningBorderColor : pillBorderColor
    }

    // MARK: - Spring Morph Animation

    func morphTo(_ mode: PanelMode, overlayHeight: CGFloat, animated: Bool = true) {
        guard mode != currentMode else { return }
        currentMode = mode

        // Calculate target frames
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let currentCenterX = frame.midX
        let bottomY = frame.origin.y

        pillFrame = NSRect(
            x: currentCenterX - 80,
            y: bottomY,
            width: 160,
            height: 36
        )

        overlayFrame = NSRect(
            x: max(screen.minX + 16, currentCenterX - 280),
            y: bottomY,
            width: 560,
            height: overlayHeight
        )
        // Clamp right edge
        if overlayFrame.maxX > screen.maxX - 16 {
            overlayFrame.origin.x = screen.maxX - 560 - 16
        }

        let target: CGFloat = mode == .overlay ? 1.0 : 0.0

        // Check Reduce Motion
        let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion

        if !animated || reduceMotion {
            let targetFrame = mode == .overlay ? overlayFrame : pillFrame
            setFrame(targetFrame, display: true)
            applyLayerState(t: target)
            spring.position = target
            spring.velocity = 0
            layoutIfNeeded()
            return
        }

        targetPosition = target
        startDisplayLink()
    }

    private func startDisplayLink() {
        displayLink?.invalidate()

        let link = CADisplayLink(target: self, selector: #selector(springStep(_:)))
        link.add(to: .main, forMode: .common)
        displayLink = link
        lastTimestamp = CACurrentMediaTime()
    }

    @objc private func springStep(_ link: CADisplayLink) {
        let now = CACurrentMediaTime()
        let dt = CGFloat(min(now - lastTimestamp, 1.0 / 30.0))
        lastTimestamp = now

        // Choose spring params based on direction
        let stiffness = targetPosition > spring.position ? expandStiffness : collapseStiffness
        let damping = targetPosition > spring.position ? expandDamping : collapseDamping

        // Damped spring (semi-implicit Euler)
        let displacement = spring.position - targetPosition
        let springForce = -stiffness * displacement
        let dampingForce = -damping * spring.velocity
        let acceleration = springForce + dampingForce

        spring.velocity += acceleration * dt
        spring.position += spring.velocity * dt

        // Check if settled
        if abs(displacement) < 0.001 && abs(spring.velocity) < 0.05 {
            spring.position = targetPosition
            spring.velocity = 0
            displayLink?.invalidate()
            displayLink = nil
        }

        applySpringFrame(t: spring.position)
        applyLayerState(t: spring.position)
    }

    private func applySpringFrame(t: CGFloat) {
        let w = lerp(pillFrame.width, overlayFrame.width, t)
        let h = lerp(pillFrame.height, overlayFrame.height, t)
        let centerX = lerp(pillFrame.midX, overlayFrame.midX, t)
        let bottomY = pillFrame.origin.y

        let newFrame = NSRect(
            x: centerX - w / 2,
            y: bottomY,
            width: w,
            height: h
        )
        setFrame(newFrame, display: false)
    }

    private func applyLayerState(t: CGFloat) {
        let radius = lerp(pillCornerRadius, overlayCornerRadius, t)
        let bgAlpha = lerp(pillBgAlpha, overlayBgAlpha, t)

        let fromBorder = currentMode == .overlay ? pillBorderColor : overlayBorderColor
        let toBorder = currentMode == .overlay ? overlayBorderColor : pillBorderColor
        let borderColor = interpolateColor(from: fromBorder, to: toBorder, t: t)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        backgroundLayer.cornerRadius = radius
        backgroundLayer.backgroundColor = NSColor.black.withAlphaComponent(bgAlpha).cgColor
        backgroundLayer.borderColor = borderColor
        contentView?.layer?.cornerRadius = radius
        backgroundLayer.frame = contentView?.bounds ?? .zero
        CATransaction.commit()
    }

    // MARK: - Helpers

    private func lerp(_ a: CGFloat, _ b: CGFloat, _ t: CGFloat) -> CGFloat {
        a + (b - a) * t
    }

    private func interpolateColor(from: CGColor, to: CGColor, t: CGFloat) -> CGColor {
        guard let f = from.components, let t2 = to.components,
              f.count >= 4, t2.count >= 4 else { return to }
        let r = lerp(f[0], t2[0], t)
        let g = lerp(f[1], t2[1], t)
        let b = lerp(f[2], t2[2], t)
        let a = lerp(f[3], t2[3], t)
        return CGColor(red: r, green: g, blue: b, alpha: a)
    }
}
```

- [ ] **Step 2: Add to Xcode project**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(BUILD|error:)' | tail -5`

If there's a build error about the file not being in the target, you may need to add it. Since this project uses automatic file discovery (no explicit file list in pbxproj for Swift files in the target directory), placing it alongside the other files should be sufficient.

Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: Commit**

```bash
git add EsperApp/EsperApp/EsperPanel.swift
git commit -m "feat: create EsperPanel — unified NSPanel with spring morph animation"
```

---

### Task 3: Modify TranscriptOverlayView — Traffic Lights + Scoped Animations

**Files:**
- Modify: `EsperApp/EsperApp/Views/TranscriptOverlayView.swift`

- [ ] **Step 1: Replace the top bar with traffic lights when `onStop` is set**

Find the current `topBar` computed property. Replace the `gear + dismiss buttons` section (inside the top bar HStack, the trailing buttons) with a conditional:

Replace the entire `topBar` property with:

```swift
    private var topBar: some View {
        HStack(spacing: 0) {
            if viewModel.onStop != nil {
                // Traffic lights mode (morphing panel)
                trafficLights
                    .padding(.leading, 10)
                Spacer()
            }

            // Audio level meter
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(.white.opacity(0.08))
                    .frame(width: 80, height: 3)
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(.green)
                    .frame(width: 80 * min(viewModel.energyLevel * 3, 1.0), height: 3)
            }

            if !viewModel.devices.isEmpty {
                Picker("", selection: Binding(
                    get: { viewModel.selectedDevice ?? 0 },
                    set: { viewModel.onSelectDevice?($0) }
                )) {
                    ForEach(Array(viewModel.devices.enumerated()), id: \.offset) { index, device in
                        Text(device.name).tag(index)
                    }
                }
                .labelsHidden()
                .controlSize(.mini)
                .font(.system(size: 10))
                .frame(maxWidth: 140)
                .padding(.leading, 6)
            }

            if viewModel.onStop == nil {
                Spacer()
                // Legacy mode — gear + dismiss
                Button(action: { viewModel.onOpenSettings?() }) {
                    Image(systemName: "gearshape")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.white.opacity(0.35))
                }
                .buttonStyle(.plain)
                .padding(.trailing, 4)

                Button(action: { viewModel.onDismiss?() }) {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.35))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .frame(height: topBarHeight)
        .background(.white.opacity(0.02))
        .overlay(alignment: .bottom) {
            Rectangle().fill(.white.opacity(0.06)).frame(height: 1)
        }
    }
```

- [ ] **Step 2: Add traffic lights view**

Add this computed property after `topBar`:

```swift
    private var trafficLights: some View {
        HStack(spacing: 7) {
            // Red — stop listening
            Button(action: { viewModel.onStop?() }) {
                Circle()
                    .fill(Color.red)
                    .frame(width: 12, height: 12)
            }
            .buttonStyle(.plain)

            // Yellow — collapse to pill
            Button(action: { viewModel.onCollapse?() }) {
                Circle()
                    .fill(Color.yellow)
                    .frame(width: 12, height: 12)
            }
            .buttonStyle(.plain)

            // Green — open settings
            Button(action: { viewModel.onOpenSettings?() }) {
                Circle()
                    .fill(Color.green)
                    .frame(width: 12, height: 12)
            }
            .buttonStyle(.plain)
        }
    }
```

- [ ] **Step 3: Scope `disablesAnimations` to transcript content only**

Find the line that wraps the whole view with `.transaction { $0.disablesAnimations = true }`. It's near the end of the `body` property. Remove it from the outer view and add it only to the `ScrollView` content.

Find:
```swift
        .transaction { $0.disablesAnimations = true }
```

This should be on the outermost container. Remove it. Instead, add it to the `ScrollViewReader` content VStack inside the body. Find the VStack inside `ScrollViewReader` that contains the `ForEach` of lines, and add `.transaction { $0.disablesAnimations = true }` to just that VStack.

The scroll view section should look like:

```swift
            ScrollViewReader { proxy in
                ScrollView(.vertical, showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(viewModel.lines) { line in
                            lineView(line)
                                .id(line.id)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .transaction { $0.disablesAnimations = true }
                }
                .onChange(of: viewModel.lines.last?.id) { _, _ in
                    if let lastID = viewModel.lines.last?.id {
                        proxy.scrollTo(lastID, anchor: .bottom)
                    }
                }
            }
```

- [ ] **Step 4: Build and verify**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(BUILD|error:)' | tail -5`

Expected: `BUILD SUCCEEDED` — the legacy top bar still shows when `onStop` is nil (existing OverlayController doesn't set it).

- [ ] **Step 5: Commit**

```bash
git add EsperApp/EsperApp/Views/TranscriptOverlayView.swift
git commit -m "feat: add traffic lights to overlay top bar, scope disablesAnimations to transcript"
```

---

### Task 4: Create EsperPanelView

**Files:**
- Create: `EsperApp/EsperApp/Views/EsperPanelView.swift`

- [ ] **Step 1: Create EsperPanelView.swift**

```swift
import SwiftUI

// MARK: - Esper Panel View

struct EsperPanelView: View {
    let viewModel: OverlayViewModel

    var body: some View {
        ZStack {
            if viewModel.mode == .pill {
                pillContent
                    .transition(.opacity)
            } else {
                overlayContent
                    .transition(.opacity.combined(with: .scale(scale: 0.97, anchor: .bottom)))
            }
        }
        .animation(.easeInOut(duration: 0.15), value: viewModel.mode)
        .clipped()
    }

    // MARK: - Pill Content

    private var pillContent: some View {
        HStack(spacing: 8) {
            switch viewModel.engineStatus {
            case .listening, .transcribing, .downloadingModel, .compilingShaders, .loadingModel:
                HStack(spacing: 0) {
                    // Left zone: waveform + chevron + label
                    HStack(spacing: 8) {
                        waveformBars
                        if viewModel.overlayDismissed {
                            Image(systemName: "chevron.up")
                                .font(.system(size: 9, weight: .medium))
                                .foregroundStyle(Color.blue.opacity(0.6))
                        }
                        Text("Listening")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.green)
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        if viewModel.overlayDismissed {
                            viewModel.onToggle?()
                        }
                    }

                    // Separator
                    Rectangle()
                        .fill(.white.opacity(0.08))
                        .frame(width: 1, height: 16)
                        .padding(.horizontal, 6)

                    // Right zone: stop button
                    Button(action: { viewModel.onStop?() }) {
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
                }

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
                EmptyView()
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .onTapGesture {
            if viewModel.engineStatus == .idle {
                viewModel.onToggle?()
            }
        }
    }

    // MARK: - Overlay Content

    private var overlayContent: some View {
        TranscriptOverlayView(viewModel: viewModel)
    }

    // MARK: - Waveform Bars

    private var waveformBars: some View {
        HStack(spacing: 2) {
            ForEach(0..<5, id: \.self) { i in
                PillWaveBar(energy: viewModel.energyLevel, index: i)
            }
        }
        .frame(height: 20)
    }
}

// MARK: - Pill Wave Bar

private struct PillWaveBar: View {
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

- [ ] **Step 2: Build and verify**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(BUILD|error:)' | tail -5`

Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: Commit**

```bash
git add EsperApp/EsperApp/Views/EsperPanelView.swift
git commit -m "feat: create EsperPanelView with pill/overlay mode cross-fade"
```

---

### Task 5: Rewrite OverlayController

**Files:**
- Modify: `EsperApp/EsperApp/EsperApp.swift`

- [ ] **Step 1: Replace the entire OverlayController class**

Replace everything from `// MARK: - Overlay Controller` (line ~117) through the end of the file with:

```swift
// MARK: - Overlay Controller

@Observable
@MainActor
final class OverlayController {
    private var panel: EsperPanel?
    private let viewModel = OverlayViewModel()
    private var panelCreated = false
    private var updateTask: Task<Void, Never>?
    private var lastColorHex: String = ""
    private var wasActive = false
    private var autoDismissTask: Task<Void, Never>?

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

    // MARK: - Update Loop

    private func update(engine: TranscriptionEngine, settings: AppSettings) {
        guard settings.flowButtonEnabled else {
            panel?.hidePanel()
            return
        }

        ensurePanel(engine: engine, settings: settings)

        let isActive = engine.status == .listening || engine.status == .transcribing
        let isLoading = engine.status == .downloadingModel || engine.status == .compilingShaders || engine.status == .loadingModel
        let hasContent = !engine.sentences.isEmpty || !engine.currentText.isEmpty

        // Transition: idle → active — clear dismiss, expand
        if (isActive || isLoading) && !wasActive {
            if viewModel.mode == .pill {
                // Brief delay then expand
                viewModel.mode = .pill  // ensure pill shows listening state first
                expandAfterDelay(engine: engine, settings: settings)
            }
        }

        // Transition: active → idle — start auto-dismiss
        if !isActive && !isLoading && wasActive {
            if hasContent && settings.overlayAutoDismiss {
                scheduleAutoDismiss(seconds: settings.overlayAutoDismissSeconds, settings: settings)
            } else if !hasContent {
                collapseToPill(settings: settings)
            }
        }

        wasActive = isActive || isLoading

        // Update view model
        updateViewModel(engine: engine, settings: settings)

        // Update panel state
        panel?.isPositionLocked = settings.overlayLockPosition
        if isActive {
            panel?.alphaValue = 1.0
        }
        panel?.setListeningBorder(isActive || isLoading)
    }

    // MARK: - View Model Sync

    private func updateViewModel(engine: TranscriptionEngine, settings: AppSettings) {
        viewModel.engineStatus = engine.status
        viewModel.energyLevel = engine.energyLevel
        viewModel.errorMessage = engine.errorMessage
        viewModel.overlayDismissed = viewModel.mode == .pill && (engine.status == .listening || engine.status == .transcribing)

        // Overlay-specific updates (only when expanded or has content)
        let newLines = overlayLines(engine: engine, settings: settings)
        if newLines != viewModel.lines { viewModel.lines = newLines }

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
        viewModel.devices = engine.devices
        viewModel.selectedDevice = engine.selectedDevice
    }

    // MARK: - Panel Lifecycle

    private func ensurePanel(engine: TranscriptionEngine, settings: AppSettings) {
        guard !panelCreated else { return }

        let panel = EsperPanel(
            contentRect: NSRect(x: 0, y: 0, width: 160, height: 36),
            styleMask: [],
            backing: .buffered,
            defer: false
        )

        // Wire callbacks
        viewModel.onToggle = { [weak self] in
            if engine.status == .listening || engine.status == .transcribing {
                // Re-expand overlay from pill
                self?.expandToOverlay(settings: settings)
            } else if engine.status == .idle {
                engine.startListening()
            }
        }
        viewModel.onStop = {
            engine.stopListening()
        }
        viewModel.onCollapse = { [weak self] in
            self?.collapseToPill(settings: settings)
        }
        viewModel.onDismiss = { [weak self] in
            self?.collapseToPill(settings: settings)
        }
        viewModel.onSelectDevice = { index in
            engine.setDevice(index)
        }
        viewModel.onOpenSettings = {
            openSettingsWindow()
        }

        let host = NSHostingView(rootView: EsperPanelView(viewModel: viewModel))
        panel.setSwiftUIContent(host)
        panel.installTrackingArea()

        panel.onDragEnd = { x in
            settings.flowButtonX = x
        }
        panel.onContextAction = { [weak self] action in
            self?.handleContextAction(action, settings: settings)
        }

        let savedX = settings.flowButtonX >= 0 ? settings.flowButtonX : nil
        panel.positionAtBottom(x: savedX)
        panel.showPanel()

        self.panel = panel
        panelCreated = true
    }

    // MARK: - Morph Transitions

    private func expandToOverlay(settings: AppSettings) {
        autoDismissTask?.cancel()
        let height = overlayHeight(settings: settings)
        withAnimation(.easeInOut(duration: 0.15)) {
            viewModel.mode = .overlay
        }
        panel?.morphTo(.overlay, overlayHeight: height)
    }

    private func collapseToPill(settings: AppSettings) {
        let height = overlayHeight(settings: settings)
        withAnimation(.easeInOut(duration: 0.15)) {
            viewModel.mode = .pill
        }
        panel?.morphTo(.pill, overlayHeight: height)
    }

    private func expandAfterDelay(engine: TranscriptionEngine, settings: AppSettings) {
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(500))
            guard let self else { return }
            let isActive = engine.status == .listening || engine.status == .transcribing
            let isLoading = engine.status == .downloadingModel || engine.status == .compilingShaders || engine.status == .loadingModel
            if isActive || isLoading {
                self.expandToOverlay(settings: settings)
            }
        }
    }

    private func overlayHeight(settings: AppSettings) -> CGFloat {
        let fontSize = settings.overlayFontSize
        let maxLines = settings.overlayMaxLines
        let lineHeight = fontSize * 1.4 + 6
        let topBarHeight: CGFloat = 32
        let padding: CGFloat = 28
        return topBarHeight + CGFloat(maxLines) * lineHeight - 6 + padding
    }

    // MARK: - Auto-Dismiss

    private func scheduleAutoDismiss(seconds: Int, settings: AppSettings) {
        autoDismissTask?.cancel()
        autoDismissTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(seconds))
            guard !Task.isCancelled, let self, self.viewModel.mode == .overlay else { return }
            self.collapseToPill(settings: settings)
        }
    }

    // MARK: - Context Menu

    private func handleContextAction(_ action: EsperPanelContextAction, settings: AppSettings) {
        switch action {
        case .textSize(let size):
            settings.overlayTextSize = size
            settings.overlayPreset = "custom"
        case .opacity(let value):
            settings.overlayOpacity = value
            settings.overlayPreset = "custom"
        case .preset(let preset):
            preset.apply(to: settings)
        case .lockPosition:
            settings.overlayLockPosition.toggle()
        case .openSettings:
            openSettingsWindow()
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

- [ ] **Step 2: Remove old FlowButton references from EsperApp**

In the `EsperApp` struct body, the `ensureLaunched()` function calls `overlayController.bind(engine:settings:)` — this stays the same. No changes needed to `EsperApp` struct itself.

- [ ] **Step 3: Build and verify**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(BUILD|error:)' | tail -5`

Expected: `BUILD SUCCEEDED`

- [ ] **Step 4: Commit**

```bash
git add EsperApp/EsperApp/EsperApp.swift
git commit -m "feat: rewrite OverlayController for unified morphing panel"
```

---

### Task 6: Delete Old Files, Clean Up Settings, Verify

**Files:**
- Delete: `EsperApp/EsperApp/FlowButton.swift`
- Delete: `EsperApp/EsperApp/Views/FlowButtonView.swift`
- Delete: `EsperApp/EsperApp/TranscriptPanel.swift`
- Delete: `EsperApp/EsperApp/Models/OverlayPosition.swift`
- Delete: `EsperApp/EsperAppTests/OverlayPositionTests.swift`
- Modify: `EsperApp/EsperApp/Models/AppSettings.swift`
- Modify: `EsperApp/EsperAppTests/AppSettingsOverlayTests.swift`

- [ ] **Step 1: Delete old panel and view files**

```bash
rm EsperApp/EsperApp/FlowButton.swift
rm EsperApp/EsperApp/Views/FlowButtonView.swift
rm EsperApp/EsperApp/TranscriptPanel.swift
rm EsperApp/EsperApp/Models/OverlayPosition.swift
rm EsperApp/EsperAppTests/OverlayPositionTests.swift
```

- [ ] **Step 2: Clean up AppSettings**

In `EsperApp/EsperApp/Models/AppSettings.swift`, remove these properties:

```swift
    @ObservationIgnored @AppStorage("overlayPosition")
    var overlayPosition: String = "bottomCenter"

    @ObservationIgnored @AppStorage("overlayDragX")
    var overlayDragX: Double = -1

    @ObservationIgnored @AppStorage("overlayDragY")
    var overlayDragY: Double = -1
```

Also remove the `parsedOverlayPosition` computed property:

```swift
    var parsedOverlayPosition: OverlayPosition {
        OverlayPosition(rawValue: overlayPosition) ?? .bottomCenter
    }
```

Keep `overlayLockPosition` — it now controls whether the pill is draggable.

- [ ] **Step 3: Update AppSettingsOverlayTests**

In `EsperApp/EsperAppTests/AppSettingsOverlayTests.swift`, remove any test cases that reference `overlayDragX`, `overlayDragY`, `overlayPosition`, or `parsedOverlayPosition`.

- [ ] **Step 5: Build and verify**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Debug build 2>&1 | grep -E '(BUILD|error:)' | tail -5`

Expected: `BUILD SUCCEEDED`

- [ ] **Step 6: Run tests**

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp test -destination 'platform=macOS' 2>&1 | grep -E '(passed|failed|BUILD)' | tail -10`

Fix any test failures related to removed properties (e.g., `AppSettingsOverlayTests` may test `overlayDragX`/`overlayDragY`). Remove those test cases.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove FlowButton/FlowButtonView, clean up overlay position settings"
```

- [ ] **Step 8: Manual verification**

Build a Debug DMG or run from Xcode and verify:
1. Idle: pill shows at bottom center with gray dot + "Esper"
2. Click pill: starts listening, pill shows waveform + "Listening" + stop
3. After ~0.5s: pill smoothly morphs into expanded overlay with spring animation
4. Overlay shows: traffic lights (red/yellow/green) + audio meter + device picker + transcript
5. Click yellow traffic light: overlay smoothly collapses back to listening pill
6. Click chevron on pill: overlay re-expands
7. Click red traffic light: overlay lingers, then collapses to idle pill
8. Right-click pill: "Settings…" menu
9. Right-click overlay: Text Size, Opacity, Preset, Lock Position, Settings
10. Drag pill horizontally: stays at bottom edge
11. Reduce Motion enabled: instant frame change, no spring morph
12. Auto-fade: pill fades to 40% after 5s of no hover

Run: `xcodebuild -project EsperApp/EsperApp.xcodeproj -scheme EsperApp -configuration Release archive -archivePath build/EsperApp.xcarchive 2>&1 | grep -E '(ARCHIVE|error:)' | tail -5`

- [ ] **Step 9: Final commit**

```bash
git add -A
git commit -m "feat: unified morphing panel — pill-to-overlay spring animation"
```
