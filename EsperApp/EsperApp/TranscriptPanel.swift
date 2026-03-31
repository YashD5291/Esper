import AppKit
import SwiftUI

final class TranscriptPanel: NSPanel {
    private let vibrancyView = NSVisualEffectView()
    var onDragEnd: ((NSPoint) -> Void)?

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

        // Glass background via NSVisualEffectView
        vibrancyView.material = .hudWindow
        vibrancyView.blendingMode = .behindWindow
        vibrancyView.state = .active
        vibrancyView.wantsLayer = true
        vibrancyView.layer?.cornerRadius = 16
        vibrancyView.layer?.masksToBounds = true
        vibrancyView.autoresizingMask = [.width, .height]
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    func setSwiftUIContent(_ hostView: NSView) {
        vibrancyView.frame = contentView?.bounds ?? .zero
        hostView.frame = vibrancyView.bounds
        hostView.autoresizingMask = [.width, .height]

        // Control redraw timing — prevent continuous redraws during layout changes
        hostView.wantsLayer = true
        hostView.layerContentsRedrawPolicy = .onSetNeedsDisplay

        // Disable automatic intrinsic-size recalculation on every SwiftUI update
        if let hosting = hostView as? NSHostingView<TranscriptOverlayView> {
            hosting.sizingOptions = []
        }

        vibrancyView.addSubview(hostView)
        contentView?.addSubview(vibrancyView)
    }

    // MARK: - Placement modes

    func setDraggable(_ draggable: Bool) {
        ignoresMouseEvents = !draggable
        isMovableByWindowBackground = draggable
    }

    func reposition(to position: OverlayPosition) {
        guard let screen = NSScreen.main else { return }
        let origin = position.origin(
            panelSize: frame.size,
            screenFrame: screen.visibleFrame
        )
        setFrameOrigin(origin)
    }

    func repositionToCoordinate(x: Double, y: Double) {
        setFrameOrigin(NSPoint(x: x, y: y))
    }

    // Save position after drag
    override func mouseUp(with event: NSEvent) {
        super.mouseUp(with: event)
        onDragEnd?(frame.origin)
    }
}
