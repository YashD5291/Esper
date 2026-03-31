import AppKit
import SwiftUI

// MARK: - Floating Panel

class TranscriptPanel: NSPanel {
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
}

// MARK: - View Model (ObservableObject for swiftc compatibility)

class TranscriptSimulator: ObservableObject {
    @Published var lines: [String] = []
    private let sentences = [
        "Hey, this is a demo of the Esper overlay",
        "It floats on top of all your windows",
        "You can keep working while seeing your transcription",
        "The text animates in smoothly as you speak",
        "Old lines fade out to keep it clean",
        "This is exactly how it would look in production",
        "Pretty cool right?",
        "It stays at the bottom of your screen",
        "Fully click-through — clicks pass right through",
        "No need to switch to Telegram to verify words",
    ]
    private var index = 0
    private var timer: Timer?

    func start() {
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            let sentence = self.sentences[self.index % self.sentences.count]
            self.lines.append(sentence)
            if self.lines.count > 3 {
                self.lines.removeFirst()
            }
            self.index += 1
        }
    }
}

// MARK: - SwiftUI Overlay View

struct TranscriptOverlayView: View {
    @ObservedObject var sim: TranscriptSimulator

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(sim.lines.enumerated()), id: \.element) { i, line in
                Text(line)
                    .font(.system(size: 20, weight: .medium, design: .rounded))
                    .foregroundColor(.white)
                    .shadow(color: Color.black.opacity(0.7), radius: 2, x: 1, y: 1)
                    .opacity(lineOpacity(index: i, total: sim.lines.count))
                    .animation(.easeOut(duration: 0.3), value: sim.lines.count)
            }
        }
        .padding(.horizontal, 28)
        .padding(.vertical, 16)
        .frame(width: 660, alignment: .leading)
        .background(Color.clear)
    }

    func lineOpacity(index: Int, total: Int) -> Double {
        if total <= 1 { return 1.0 }
        if index == 0 && total == 3 { return 0.45 }
        if index == 0 && total == 2 { return 0.7 }
        return 1.0
    }
}

// MARK: - App Delegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var panel: TranscriptPanel!
    var sim: TranscriptSimulator!

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        sim = TranscriptSimulator()

        let screenFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelWidth: CGFloat = 700
        let panelHeight: CGFloat = 140
        let x = screenFrame.midX - panelWidth / 2
        let y = screenFrame.minY + 80

        panel = TranscriptPanel(
            contentRect: NSRect(x: x, y: y, width: panelWidth, height: panelHeight),
            styleMask: [],
            backing: .buffered,
            defer: false
        )

        let hostView = NSHostingView(rootView: TranscriptOverlayView(sim: sim))
        hostView.frame = NSRect(x: 0, y: 0, width: panelWidth, height: panelHeight)
        panel.contentView = hostView
        panel.orderFrontRegardless()

        sim.start()

        // Auto-quit after 25 seconds
        DispatchQueue.main.asyncAfter(deadline: .now() + 25) {
            NSApp.terminate(nil)
        }
    }
}

// MARK: - Main

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
