import SwiftUI

/// Single source of truth for all app state.
/// Consumes events from ProcessBridge and updates published properties.
@Observable
@MainActor
final class TranscriptionEngine {
    // State
    var status: EngineStatus = .idle
    var devices: [AudioDevice] = []
    var selectedDevice: Int?
    var energyLevel: Double = 0.0
    var finalizedSentences: [SentencePayload] = []
    var draftText: String = ""
    var finalizedText: String = ""
    var errorMessage: String?

    // Dependencies
    let bridge = ProcessBridge()
    let settings = AppSettings()

    @ObservationIgnored
    private var eventTask: Task<Void, Never>?

    // MARK: - Lifecycle

    func launch() {
        bridge.launch(
            pythonPath: settings.resolvedPythonPath,
            projectDir: settings.resolvedProjectDir
        )
        startConsuming()
        // Request device list after launch
        let b = bridge
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(500))
            guard self != nil else { return }
            b.send(cmd: "list_devices")
        }
    }

    func shutdown() {
        eventTask?.cancel()
        eventTask = nil
        bridge.send(cmd: "stop")
        let b = bridge
        Task.detached {
            try? await Task.sleep(for: .milliseconds(500))
            b.terminate()
        }
    }

    // MARK: - Commands

    func startListening() {
        var data: [String: Any] = [
            "engine": settings.engine,
            "buffer": settings.bufferSeconds,
        ]
        if let device = selectedDevice {
            data["device"] = device
        }
        if settings.telegramEnabled,
           !settings.telegramBotToken.isEmpty,
           !settings.telegramChatId.isEmpty {
            data["telegram"] = [
                "bot_token": settings.telegramBotToken,
                "chat_id": settings.telegramChatId,
            ]
        }
        // Clear previous transcript
        finalizedSentences = []
        draftText = ""
        finalizedText = ""
        errorMessage = nil

        bridge.send(cmd: "start", data: data)
    }

    func stopListening() {
        bridge.send(cmd: "stop")
    }

    func setDevice(_ deviceIndex: Int) {
        selectedDevice = deviceIndex
        if status == .listening {
            bridge.send(cmd: "set_device", data: ["device": deviceIndex])
        }
    }

    func restart() {
        shutdown()
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(1))
            self?.launch()
        }
    }

    // MARK: - Event Consumption

    private func startConsuming() {
        eventTask = Task { [weak self] in
            guard let self else { return }
            for await event in bridge.events {
                guard !Task.isCancelled else { break }
                self.handle(event)
            }
        }
    }

    private func handle(_ event: ServerEvent) {
        switch event {
        case .devices(let list):
            devices = list
            if selectedDevice == nil {
                selectedDevice = list.first(where: { $0.isDefault })?.index ?? list.first?.index
            }

        case .status(let newStatus):
            status = newStatus
            if newStatus == .idle {
                energyLevel = 0.0
            }
            errorMessage = nil

        case .transcript(let payload):
            finalizedText = payload.finalizedText
            draftText = payload.draftText
            finalizedSentences = payload.finalizedSentences

        case .energy(let level):
            energyLevel = level

        case .telegramSent:
            break

        case .error(let message):
            errorMessage = message

        case .unknown:
            break
        }
    }
}
