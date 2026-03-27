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
    var currentText: String = ""
    var finalizedText: String = ""
    var sentences: [String] = []
    var errorMessage: String?
    var telegramTestResult: TelegramTestResult?

    // Dependencies
    let bridge = ProcessBridge()
    let settings = AppSettings()

    @ObservationIgnored
    private var eventTask: Task<Void, Never>?

    @ObservationIgnored
    private var restartAttempts = 0
    private static let maxRestartAttempts = 3

    // MARK: - Computed

    var isLoading: Bool {
        switch status {
        case .downloadingModel, .compilingShaders, .loadingModel:
            return true
        default:
            return false
        }
    }

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
        var data: [String: Any] = [:]
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
        currentText = ""
        finalizedText = ""
        sentences = []
        errorMessage = nil

        // If bridge isn't running yet, launch it and retry after it's ready
        if !bridge.isRunning {
            launch()
            Task { @MainActor [weak self] in
                try? await Task.sleep(for: .seconds(1))
                guard let self, self.bridge.isRunning else { return }
                self.bridge.send(cmd: "start", data: data)
            }
            return
        }

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

    func refreshDevices() {
        bridge.send(cmd: "list_devices")
    }

    func testTelegram(botToken: String, chatId: String) {
        telegramTestResult = nil
        bridge.send(cmd: "test_telegram", data: [
            "bot_token": botToken,
            "chat_id": chatId,
        ])
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
            if newStatus == .listening {
                restartAttempts = 0
            }
            errorMessage = nil

        case .transcript(let payload):
            currentText = payload.text
            finalizedText = payload.finalizedText
            sentences = payload.sentences

        case .energy(let level):
            energyLevel = level

        case .telegramSent:
            break

        case .telegramTest(let success, let error):
            telegramTestResult = TelegramTestResult(success: success, error: error)

        case .crashed(let exitCode):
            status = .idle
            energyLevel = 0.0
            if restartAttempts < Self.maxRestartAttempts {
                restartAttempts += 1
                errorMessage = "Python crashed (exit \(exitCode)). Restarting (\(restartAttempts)/\(Self.maxRestartAttempts))..."
                Task { @MainActor [weak self] in
                    try? await Task.sleep(for: .seconds(2))
                    guard let self, self.restartAttempts <= Self.maxRestartAttempts else { return }
                    self.restart()
                }
            } else {
                errorMessage = "Python crashed repeatedly. Restart manually."
            }

        case .error(let message):
            errorMessage = Self.friendlyError(message)

        case .unknown:
            break
        }
    }

    private static func friendlyError(_ message: String) -> String {
        let lower = message.lowercased()
        if lower.contains("model not found") || lower.contains("no such file") && lower.contains("model") {
            return "Model files missing. Run the download command from the README."
        }
        if lower.contains("no audio device") || lower.contains("no input device") || lower.contains("invalid device") {
            return "No microphone detected. Check System Settings > Sound."
        }
        return message
    }
}
