import KeyboardShortcuts
import QuartzCore
import Sparkle
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
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

// MARK: - Overlay Controller

@Observable
@MainActor
final class OverlayController {
    private var panel: TranscriptPanel?
    private let viewModel = OverlayViewModel()
    private var panelCreated = false
    private var updateTask: Task<Void, Never>?
    private var lastColorHex: String = ""
    private var panelVisible = false
    private var dismissed = false
    private var autoDismissTask: Task<Void, Never>?

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
            onToggle: {
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
