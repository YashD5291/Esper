import AppKit
import SwiftUI

// MARK: - Context Actions

enum EsperPanelContextAction {
    case textSize(String)
    case opacity(Double)
    case lockPosition
    case openSettings
    case stop
    case collapseToPill
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
    private let vibrancyView = NSVisualEffectView()

    /// When true, the overlay renders v3.3.0-style: HUD vibrancy background,
    /// corner radius 16, width 660. Pill mode is unaffected.
    var overlayUseMinimalStyle: Bool = false {
        didSet { applyBackgroundForCurrentMode() }
    }

    private let minimalOverlayCornerRadius: CGFloat = 16
    private let minimalOverlayWidth: CGFloat = 660

    // MARK: Spring Animation

    private var displayLink: Timer?
    private var spring = SpringState()
    private var targetPosition: CGFloat = 0
    private var lastTimestamp: CFTimeInterval = 0

    private var pillFrame: NSRect = .zero
    private var overlayFrame: NSRect = .zero

    // Spring parameters — tuned for smooth, deliberate morph
    private let expandStiffness: CGFloat = 140
    private let expandDamping: CGFloat = 18
    private let collapseStiffness: CGFloat = 160
    private let collapseDamping: CGFloat = 24

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
    private var exitWorkItem: DispatchWorkItem?
    private var isMouseInside = false
    private var isExpanding = false

    // Suppresses didMove snap-back during our own programmatic moves
    // (positioning, morph animations). Background-drag moves are driven by
    // the window server and never set this flag, so they get constrained.
    private var isProgrammaticMove = false

    // MARK: Init

    override init(
        contentRect: NSRect,
        styleMask: NSWindow.StyleMask,
        backing: NSWindow.BackingStoreType,
        defer flag: Bool
    ) {
        super.init(contentRect: contentRect, styleMask: styleMask, backing: backing, defer: flag)

        level = NSWindow.Level(rawValue: Int(CGShieldingWindowLevel()))
        isFloatingPanel = true
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
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

        // Vibrancy view for v3.3.0 "minimal" style — hidden by default.
        vibrancyView.material = .hudWindow
        vibrancyView.blendingMode = .behindWindow
        vibrancyView.state = .active
        vibrancyView.wantsLayer = true
        vibrancyView.layer?.cornerRadius = minimalOverlayCornerRadius
        vibrancyView.layer?.masksToBounds = true
        vibrancyView.layer?.borderWidth = 1
        vibrancyView.layer?.borderColor = NSColor.white.withAlphaComponent(0.10).cgColor
        vibrancyView.isHidden = true
        vibrancyView.autoresizingMask = [.width, .height]
        vibrancyView.frame = contentView?.bounds ?? .zero
        contentView?.addSubview(vibrancyView, positioned: .below, relativeTo: nil)

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(windowDidMoveNotif(_:)),
            name: NSWindow.didMoveNotification,
            object: self
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
        displayLink?.invalidate()
        fadeWorkItem?.cancel()
        exitWorkItem?.cancel()
    }

    @objc private func windowDidMoveNotif(_ note: Notification) {
        guard !isProgrammaticMove, currentMode == .pill else { return }
        constrainToBottomEdge()
        onDragEnd?(frame.origin.x)
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
        hostView.sizingOptions = []
        contentView?.addSubview(hostView)
        hostView.autoresizingMask = [.width, .height]
        hostView.frame = contentView?.bounds ?? .zero
        hostView.layerContentsRedrawPolicy = .onSetNeedsDisplay
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
        exitWorkItem?.cancel()
        if currentMode == .pill {
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.15
                ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
                self.animator().alphaValue = 1.0
            }
        } else {
            ignoresMouseEvents = false
            isMovableByWindowBackground = false
        }
    }

    override func mouseExited(with event: NSEvent) {
        isMouseInside = false
        if currentMode == .pill {
            scheduleAutoFade()
        } else {
            exitWorkItem?.cancel()
            let item = DispatchWorkItem { [weak self] in
                guard let self, !self.isMouseInside else { return }
                self.ignoresMouseEvents = true
                self.isMovableByWindowBackground = false
            }
            exitWorkItem = item
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

        let stopItem = NSMenuItem(title: "Stop Transcription", action: #selector(contextAction(_:)), keyEquivalent: "")
        stopItem.target = self
        stopItem.representedObject = EsperPanelContextAction.stop
        menu.addItem(stopItem)

        if currentMode == .overlay {
            let collapseItem = NSMenuItem(title: "Collapse to Pill", action: #selector(contextAction(_:)), keyEquivalent: "")
            collapseItem.target = self
            collapseItem.representedObject = EsperPanelContextAction.collapseToPill
            menu.addItem(collapseItem)
        }

        menu.addItem(.separator())

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

    /// The screen that owns the global menu bar — stable across launches and
    /// independent of where Settings windows ended up on external displays.
    private static var primaryScreen: NSScreen? {
        NSScreen.screens.first ?? NSScreen.main
    }

    /// Picks the screen whose visibleFrame contains the given x on its bottom
    /// edge, else the primary screen. Defends against stale saved X values
    /// from previous multi-monitor configurations.
    private static func screen(for savedX: Double?) -> NSScreen? {
        if let savedX {
            if let hit = NSScreen.screens.first(where: {
                let f = $0.visibleFrame
                return savedX >= f.minX && savedX <= f.maxX
            }) {
                return hit
            }
        }
        return primaryScreen
    }

    func positionAtBottom(x: Double? = nil) {
        guard let screen = Self.screen(for: x)?.visibleFrame else { return }
        let rawX = x ?? (screen.midX - frame.width / 2)
        let xPos = min(max(rawX, screen.minX + 16), screen.maxX - frame.width - 16)
        let yPos = screen.minY + 16
        isProgrammaticMove = true
        setFrameOrigin(NSPoint(x: xPos, y: yPos))
        isProgrammaticMove = false
    }

    func constrainToBottomEdge() {
        guard let screen = Self.screen(for: frame.origin.x)?.visibleFrame else { return }
        let y = screen.minY + 16
        let x = min(max(frame.origin.x, screen.minX + 16), screen.maxX - frame.width - 16)
        isProgrammaticMove = true
        setFrameOrigin(NSPoint(x: x, y: y))
        isProgrammaticMove = false
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

    /// Snap the overlay to its target size for the current style. Call when
    /// `overlayUseMinimalStyle` changes while already expanded — the overlay
    /// width differs between styles (560 vs 660), so we need to resize the
    /// panel frame to match the SwiftUI content and avoid clipping/gaps.
    func resyncOverlaySize(height: CGFloat) {
        guard currentMode == .overlay else { return }
        let screen = (Self.screen(for: frame.origin.x)?.visibleFrame)
            ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let width: CGFloat = overlayUseMinimalStyle ? minimalOverlayWidth : 560
        var x = max(screen.minX + 16, frame.midX - width / 2)
        if x + width > screen.maxX - 16 {
            x = screen.maxX - width - 16
        }
        let target = NSRect(x: x, y: frame.origin.y, width: width, height: height)
        pillFrame = NSRect(x: frame.midX - 80, y: frame.origin.y, width: 160, height: 36)
        overlayFrame = target
        isProgrammaticMove = true
        setFrame(target, display: true)
        isProgrammaticMove = false
    }

    func morphTo(_ mode: PanelMode, overlayHeight: CGFloat, animated: Bool = true) {
        guard mode != currentMode else { return }
        currentMode = mode
        applyBackgroundForCurrentMode()

        // Reset mouse state for the new mode
        exitWorkItem?.cancel()
        isExpanding = mode == .overlay
        if mode == .overlay {
            ignoresMouseEvents = false
            isMovableByWindowBackground = false
        } else {
            ignoresMouseEvents = false
            isMovableByWindowBackground = !isPositionLocked
        }

        // Calculate target frames — use the screen the pill is currently on,
        // not NSScreen.main (which may be a different display).
        let screen = (Self.screen(for: frame.origin.x)?.visibleFrame)
            ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let currentCenterX = frame.midX
        let bottomY = frame.origin.y

        pillFrame = NSRect(
            x: currentCenterX - 80,
            y: bottomY,
            width: 160,
            height: 36
        )

        let overlayWidth: CGFloat = overlayUseMinimalStyle ? minimalOverlayWidth : 560
        overlayFrame = NSRect(
            x: max(screen.minX + 16, currentCenterX - overlayWidth / 2),
            y: bottomY,
            width: overlayWidth,
            height: overlayHeight
        )
        // Clamp right edge
        if overlayFrame.maxX > screen.maxX - 16 {
            overlayFrame.origin.x = screen.maxX - overlayWidth - 16
        }

        let target: CGFloat = mode == .overlay ? 1.0 : 0.0

        // Check Reduce Motion
        let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion

        if !animated || reduceMotion {
            let targetFrame = mode == .overlay ? overlayFrame : pillFrame
            isProgrammaticMove = true
            setFrame(targetFrame, display: true)
            isProgrammaticMove = false
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

        lastTimestamp = CACurrentMediaTime()
        let link = Timer(timeInterval: 1.0 / 120.0, repeats: true) { [weak self] _ in
            self?.springStep()
        }
        RunLoop.main.add(link, forMode: .common)
        displayLink = link
    }

    private func springStep() {
        let now = CACurrentMediaTime()
        let dt = CGFloat(min(now - lastTimestamp, 1.0 / 30.0))
        lastTimestamp = now

        // Use direction set at morph start — avoids jitter during overshoot
        let stiffness = isExpanding ? expandStiffness : collapseStiffness
        let damping = isExpanding ? expandDamping : collapseDamping

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
        isProgrammaticMove = true
        setFrame(newFrame, display: false)
        isProgrammaticMove = false
    }

    private func applyLayerState(t: CGFloat) {
        let targetOverlayCornerRadius = (overlayUseMinimalStyle && currentMode == .overlay)
            ? minimalOverlayCornerRadius
            : overlayCornerRadius
        let radius = lerp(pillCornerRadius, targetOverlayCornerRadius, t)
        let bgAlpha = lerp(pillBgAlpha, overlayBgAlpha, t)

        // t=0 is pill, t=1 is overlay — always interpolate in this direction
        let borderColor = interpolateColor(from: pillBorderColor, to: overlayBorderColor, t: t)

        CATransaction.begin()
        CATransaction.setDisableActions(true)
        backgroundLayer.cornerRadius = radius
        backgroundLayer.backgroundColor = NSColor.black.withAlphaComponent(bgAlpha).cgColor
        backgroundLayer.borderColor = borderColor
        contentView?.layer?.cornerRadius = radius
        backgroundLayer.frame = contentView?.bounds ?? .zero
        if overlayUseMinimalStyle {
            vibrancyView.layer?.cornerRadius = radius
        }
        CATransaction.commit()
    }

    /// Toggles which background is visible based on `overlayUseMinimalStyle`.
    /// Only called when the style actually changes or after a morph completes —
    /// NOT on every spring frame.
    private func applyBackgroundForCurrentMode() {
        let useVibrancy = overlayUseMinimalStyle
        vibrancyView.isHidden = !useVibrancy
        backgroundLayer.isHidden = useVibrancy
        let radius = currentMode == .overlay ? minimalOverlayCornerRadius : pillCornerRadius
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        vibrancyView.layer?.cornerRadius = radius
        vibrancyView.frame = contentView?.bounds ?? .zero
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
