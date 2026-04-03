import KeyboardShortcuts
import QuartzCore
import Sparkle
import SwiftUI

extension Notification.Name {
    static let reopenMainWindow = Notification.Name("reopenMainWindow")
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        // MenuBarExtra makes hasVisibleWindows unreliable — it reports true even
        // when no real windows are on screen. Check for actual visible windows instead.
        let hasRealWindow = sender.windows.contains { window in
            window.isVisible && !window.className.contains("StatusBar") && !(window is NSPanel)
        }
        if !hasRealWindow {
            NotificationCenter.default.post(name: .reopenMainWindow, object: nil)
        }
        sender.activate(ignoringOtherApps: true)
        return true
    }
}

@main
struct EsperApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var engine = TranscriptionEngine()
    @State private var launched = false
    @State private var overlayController = OverlayController()
    private let updaterController: SPUStandardUpdaterController
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(engine: engine, updater: updaterController.updater)
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
                .onReceive(NotificationCenter.default.publisher(for: .reopenMainWindow)) { _ in
                    openWindow(id: "main")
                }
        }
        .defaultSize(width: 520, height: 640)

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
    private var lastColorHex: String = ""
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
            (engine.status == .listening || engine.status == .transcribing || previewMode)

        if shouldShow {
            ensurePanel(settings: settings)

            // Suppress implicit Core Animation layer transitions during SwiftUI updates
            CATransaction.begin()
            CATransaction.setDisableActions(true)

            // Only mutate when values actually changed to avoid unnecessary SwiftUI diffs
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

            CATransaction.commit()

            let isDraggable = !settings.overlayLockPosition
            panel?.setDraggable(isDraggable)

            if !(panel?.isVisible ?? false) {
                if settings.overlayDragX >= 0, settings.overlayDragY >= 0 {
                    panel?.repositionToCoordinate(x: settings.overlayDragX, y: settings.overlayDragY)
                } else {
                    panel?.reposition(to: settings.parsedOverlayPosition)
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
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 140),
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
                OverlayLine(id: "sample-\(i)", text: text, state: .finalized, confidence: 1.0)
            }
        }

        let sentenceCount = engine.sentences.count
        var raw: [(id: String, text: String, state: LineState)] = engine.sentences.suffix(maxLines).enumerated().map { i, text in
            let globalIndex = sentenceCount - min(maxLines, sentenceCount) + i
            return (id: "s-\(globalIndex)", text: text, state: .finalized)
        }

        let current = engine.currentText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !current.isEmpty, current != raw.last?.text {
            if raw.count >= maxLines { raw.removeFirst() }
            raw.append((id: "current", text: current, state: .draft))
        }

        return raw.map { item in
            OverlayLine(id: item.id, text: item.text, state: item.state, confidence: 1.0)
        }
    }
}
