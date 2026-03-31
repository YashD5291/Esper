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
        guard updateTask == nil else { return }
        updateTask = Task { @MainActor [weak self] in
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
