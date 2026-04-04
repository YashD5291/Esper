import AppKit
import SwiftUI

final class FlowButton: NSPanel {
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
        let settingsItem = NSMenuItem(title: "Settings\u{2026}", action: #selector(contextAction(_:)), keyEquivalent: ",")
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
        origin.y = screenFrame.minY + 16
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
