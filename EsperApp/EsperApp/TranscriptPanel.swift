import AppKit
import SwiftUI

final class TranscriptPanel: NSPanel {
    var onDragEnd: ((NSPoint) -> Void)?
    var onHoverChanged: ((Bool) -> Void)?
    var onContextAction: ((OverlayContextAction) -> Void)?

    private var trackingArea: NSTrackingArea?
    private var isMouseInside = false
    private var mouseExitWorkItem: DispatchWorkItem?
    private let backgroundLayer = CALayer()

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
        hasShadow = true
        ignoresMouseEvents = true
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]

        contentView?.wantsLayer = true
        guard let rootLayer = contentView?.layer else { return }
        backgroundLayer.backgroundColor = NSColor.black.withAlphaComponent(0.82).cgColor
        backgroundLayer.cornerRadius = 12
        backgroundLayer.masksToBounds = true
        backgroundLayer.borderWidth = 1
        backgroundLayer.borderColor = NSColor.white.withAlphaComponent(0.08).cgColor
        backgroundLayer.autoresizingMask = [.layerWidthSizable, .layerHeightSizable]
        backgroundLayer.frame = rootLayer.bounds
        rootLayer.addSublayer(backgroundLayer)

        rootLayer.cornerRadius = 12
        rootLayer.masksToBounds = true
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    func setSwiftUIContent(_ hostView: NSView) {
        hostView.frame = contentView?.bounds ?? .zero
        hostView.autoresizingMask = [.width, .height]
        hostView.wantsLayer = true
        hostView.layerContentsRedrawPolicy = .onSetNeedsDisplay
        if let hosting = hostView as? NSHostingView<TranscriptOverlayView> {
            hosting.sizingOptions = []
        }
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
        mouseExitWorkItem?.cancel()
        guard !isMouseInside else { return }
        isMouseInside = true
        ignoresMouseEvents = false
        isMovableByWindowBackground = true
        onHoverChanged?(true)
    }

    override func mouseExited(with event: NSEvent) {
        let workItem = DispatchWorkItem { [weak self] in
            guard let self, self.isMouseInside else { return }
            self.isMouseInside = false
            self.ignoresMouseEvents = true
            self.isMovableByWindowBackground = false
            self.onHoverChanged?(false)
        }
        mouseExitWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: workItem)
    }

    override func mouseUp(with event: NSEvent) {
        super.mouseUp(with: event)
        onDragEnd?(frame.origin)
    }

    // MARK: - Context Menu

    override func rightMouseDown(with event: NSEvent) {
        guard let cv = contentView else { return }
        let menu = buildContextMenu()
        NSMenu.popUpContextMenu(menu, with: event, for: cv)
    }

    private func buildContextMenu() -> NSMenu {
        let menu = NSMenu()

        let sizeMenu = NSMenu()
        for (label, value) in [("Small", "small"), ("Medium", "medium"), ("Large", "large")] {
            let item = NSMenuItem(title: label, action: #selector(contextMenuAction(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = ActionBox(.textSize(value))
            sizeMenu.addItem(item)
        }
        let sizeItem = NSMenuItem(title: "Text Size", action: nil, keyEquivalent: "")
        sizeItem.submenu = sizeMenu
        menu.addItem(sizeItem)

        let opacityMenu = NSMenu()
        for (label, value) in [("25%", 0.25), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0)] {
            let item = NSMenuItem(title: label, action: #selector(contextMenuAction(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = ActionBox(.opacity(value))
            opacityMenu.addItem(item)
        }
        let opacityItem = NSMenuItem(title: "Opacity", action: nil, keyEquivalent: "")
        opacityItem.submenu = opacityMenu
        menu.addItem(opacityItem)

        let presetMenu = NSMenu()
        for preset in OverlayPreset.allCases where preset != .custom {
            let item = NSMenuItem(title: preset.displayName, action: #selector(contextMenuAction(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = ActionBox(.preset(preset))
            presetMenu.addItem(item)
        }
        let presetItem = NSMenuItem(title: "Preset", action: nil, keyEquivalent: "")
        presetItem.submenu = presetMenu
        menu.addItem(presetItem)

        let posMenu = NSMenu()
        for pos in OverlayPosition.allCases {
            let item = NSMenuItem(title: pos.rawValue, action: #selector(contextMenuAction(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = ActionBox(.position(pos))
            posMenu.addItem(item)
        }
        let posItem = NSMenuItem(title: "Position", action: nil, keyEquivalent: "")
        posItem.submenu = posMenu
        menu.addItem(posItem)

        menu.addItem(NSMenuItem.separator())

        let lockItem = NSMenuItem(title: "Lock Position", action: #selector(contextMenuAction(_:)), keyEquivalent: "")
        lockItem.target = self
        lockItem.representedObject = ActionBox(.lockPosition)
        menu.addItem(lockItem)

        menu.addItem(NSMenuItem.separator())

        let settingsItem = NSMenuItem(title: "Settings…", action: #selector(contextMenuAction(_:)), keyEquivalent: ",")
        settingsItem.target = self
        settingsItem.representedObject = ActionBox(.openSettings)
        menu.addItem(settingsItem)

        return menu
    }

    @objc private func contextMenuAction(_ sender: NSMenuItem) {
        guard let action = (sender.representedObject as? ActionBox)?.action else { return }
        onContextAction?(action)
    }

    // MARK: - Legacy (removed in Task 6)

    func setDraggable(_ draggable: Bool) {
        ignoresMouseEvents = !draggable
        isMovableByWindowBackground = draggable
    }

    // MARK: - Positioning

    func reposition(to position: OverlayPosition) {
        guard let screen = NSScreen.main else { return }
        let origin = position.origin(panelSize: frame.size, screenFrame: screen.visibleFrame)
        setFrameOrigin(origin)
    }

    func repositionToCoordinate(x: Double, y: Double) {
        setFrameOrigin(NSPoint(x: x, y: y))
    }

    // MARK: - Animations

    func animateIn() {
        alphaValue = 0
        contentView?.layer?.transform = CATransform3DMakeScale(0.97, 0.97, 1)
        orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
            animator().alphaValue = 1
            contentView?.layer?.transform = CATransform3DIdentity
        }
    }

    func animateOut(completion: (() -> Void)? = nil) {
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.15
            ctx.timingFunction = CAMediaTimingFunction(name: .easeIn)
            animator().alphaValue = 0
            contentView?.layer?.transform = CATransform3DMakeScale(0.97, 0.97, 1)
        }, completionHandler: {
            self.orderOut(nil)
            self.alphaValue = 1
            self.contentView?.layer?.transform = CATransform3DIdentity
            completion?()
        })
    }
}

// MARK: - Context Menu Actions

enum OverlayContextAction {
    case textSize(String)
    case opacity(Double)
    case preset(OverlayPreset)
    case position(OverlayPosition)
    case lockPosition
    case openSettings
}

// MARK: - ObjC-compatible box for enum associated values

private final class ActionBox: NSObject {
    let action: OverlayContextAction
    init(_ action: OverlayContextAction) { self.action = action }
}
