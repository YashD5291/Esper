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
        overlayController.bind(engine: engine, settings: engine.settings)
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
    private let viewModel = OverlayViewModel()
    private var panelCreated = false
    private var updateTask: Task<Void, Never>?
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
        let shouldShow = settings.overlayEnabled &&
            (engine.status == .listening || previewMode)

        if shouldShow {
            ensurePanel(settings: settings)
            // Mutate view model — SwiftUI observes and diffs, no rootView replacement
            viewModel.lines = overlayLines(engine: engine, settings: settings)
            viewModel.fontSize = settings.overlayFontSize
            viewModel.textColor = settings.parsedOverlayColor
            viewModel.opacity = settings.overlayOpacity

            let isDraggable = settings.overlayPlacementMode == "draggable"
            panel?.setDraggable(isDraggable)

            if !isDraggable {
                panel?.reposition(to: settings.parsedOverlayPosition)
            }

            if !(panel?.isVisible ?? false) {
                if isDraggable, settings.overlayDragX >= 0, settings.overlayDragY >= 0 {
                    panel?.repositionToCoordinate(x: settings.overlayDragX, y: settings.overlayDragY)
                } else if isDraggable {
                    panel?.reposition(to: .bottomCenter)
                }
                panel?.orderFrontRegardless()
            }
        } else {
            panel?.orderOut(nil)
        }
    }

    private func ensurePanel(settings: AppSettings) {
        guard !panelCreated else { return }
        let panel = TranscriptPanel(
            contentRect: NSRect(x: 0, y: 0, width: 660, height: 140),
            styleMask: [],
            backing: .buffered,
            defer: false
        )
        let host = NSHostingView(rootView: TranscriptOverlayView(viewModel: viewModel))
        panel.setSwiftUIContent(host)
        panel.onDragEnd = { origin in
            settings.overlayDragX = origin.x
            settings.overlayDragY = origin.y
        }
        self.panel = panel
        panelCreated = true
    }

    private static let sampleLines = [
        "This is a preview of the overlay",
        "Transcription text will appear here",
        "Adjust settings to customize the look",
    ]

    private func overlayLines(engine: TranscriptionEngine, settings: AppSettings) -> [OverlayLine] {
        let maxLines = settings.overlayMaxLines
        if previewMode && engine.status != .listening {
            return Self.sampleLines.prefix(maxLines).enumerated().map { i, text in
                OverlayLine(id: "sample-\(i)", text: text, dimmed: i == 0 && maxLines > 1)
            }
        }

        let sentenceCount = engine.sentences.count
        var raw: [(id: String, text: String)] = engine.sentences.suffix(maxLines).enumerated().map { i, text in
            let globalIndex = sentenceCount - min(maxLines, sentenceCount) + i
            return (id: "s-\(globalIndex)", text: text)
        }

        let current = engine.currentText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !current.isEmpty, current != raw.last?.text {
            if raw.count >= maxLines { raw.removeFirst() }
            raw.append((id: "current", text: current))
        }

        let total = raw.count
        return raw.enumerated().map { i, item in
            let dimmed = total > 1 && i < total - 1
            return OverlayLine(id: item.id, text: item.text, dimmed: dimmed)
        }
    }
}
