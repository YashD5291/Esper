import AVFoundation
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
    var sentSentenceIndices: Set<Int> = []
    var lastNoSpeechProb: Double = 0.0

    // Dependencies
    let bridge = ProcessBridge()
    let settings = AppSettings()

    @ObservationIgnored
    private var eventTask: Task<Void, Never>?

    @ObservationIgnored
    private var watchdogTask: Task<Void, Never>?

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
        NSLog("[Engine] launch() called")
        bridge.launch(settings: settings)
        NSLog("[Engine] bridge.launch() done, isRunning=%d", bridge.isRunning ? 1 : 0)
        startConsuming()
        // Request device list after launch
        let b = bridge
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(500))
            guard self != nil else { return }
            NSLog("[Engine] sending list_devices")
            b.send(cmd: "list_devices")
        }
    }

    func shutdown() {
        cancelWatchdog()
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
        Task { @MainActor [weak self] in
            guard let self else { return }
            guard await self.checkMicrophonePermission() else { return }
            self.doStartListening()
        }
    }

    private func doStartListening() {
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
        sentSentenceIndices = []
        lastNoSpeechProb = 0.0

        // If bridge isn't running yet, launch it and retry after it's ready
        if !bridge.isRunning {
            launch()
            Task { @MainActor [weak self] in
                try? await Task.sleep(for: .seconds(1))
                guard let self, self.bridge.isRunning else { return }
                self.bridge.send(cmd: "start", data: data)
                self.startWatchdog(expecting: "listening status")
            }
            return
        }

        bridge.send(cmd: "start", data: data)
        startWatchdog(expecting: "listening status")
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

    // MARK: - Watchdog

    private func startWatchdog(timeout: TimeInterval = 30.0, expecting: String = "response") {
        watchdogTask?.cancel()
        watchdogTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(timeout))
            guard !Task.isCancelled, let self else { return }
            if self.status != .listening && self.status != .idle {
                self.errorMessage = "Python is unresponsive (no \(expecting) after \(Int(timeout))s). Restarting..."
                self.restart()
            }
        }
    }

    private func cancelWatchdog() {
        watchdogTask?.cancel()
        watchdogTask = nil
    }

    // MARK: - Event Consumption

    private func startConsuming() {
        guard eventTask == nil else { return }
        dlog("[Engine] startConsuming: creating event loop task")
        eventTask = Task { [weak self] in
            guard let self else { dlog("[Engine] startConsuming: self is nil, exiting"); return }
            dlog("[Engine] startConsuming: entering for-await loop")
            for await event in bridge.events {
                guard !Task.isCancelled else { dlog("[Engine] task cancelled"); break }
                self.handle(event)
            }
            dlog("[Engine] startConsuming: for-await loop exited")
        }
    }

    private func handle(_ event: ServerEvent) {
        dlog("[Engine] handle: \(event)")
        switch event {
        case .devices(let list):
            NSLog("[Engine] got %d devices", list.count)
            devices = list
            if selectedDevice == nil {
                selectedDevice = preferBuiltInDevice(from: list)
            }

        case .status(let newStatus):
            status = newStatus
            if newStatus == .listening || newStatus == .idle {
                cancelWatchdog()
            }
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
            lastNoSpeechProb = payload.noSpeechProb

        case .energy(let level):
            energyLevel = level

        case .telegramTest(let success, let error):
            telegramTestResult = TelegramTestResult(success: success, error: error)

        case .telegramSent(_, let index):
            sentSentenceIndices.insert(index)

        case .telegramFailed(let text, let error):
            NSLog("[Engine] Telegram send failed: %@ — %@", text, error)

        case .crashed(let exitCode):
            cancelWatchdog()
            status = .idle
            energyLevel = 0.0
            if restartAttempts < Self.maxRestartAttempts {
                restartAttempts += 1
                errorMessage = "Python crashed (exit \(exitCode)). Restarting (\(restartAttempts)/\(Self.maxRestartAttempts))..."
                Task { @MainActor [weak self] in
                    try? await Task.sleep(for: .seconds(2))
                    guard let self else { return }
                    guard self.restartAttempts <= Self.maxRestartAttempts else { return }
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

    private func checkMicrophonePermission() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return true
        case .notDetermined:
            return await AVCaptureDevice.requestAccess(for: .audio)
        case .denied, .restricted:
            errorMessage = "Microphone access denied. Go to System Settings > Privacy & Security > Microphone to enable it for Esper."
            return false
        @unknown default:
            return true
        }
    }

    /// Prefer built-in MacBook microphone over loopback/external devices.
    private func preferBuiltInDevice(from list: [AudioDevice]) -> Int? {
        let nonLoopback = list.filter {
            !$0.name.localizedCaseInsensitiveContains("loopback")
        }
        // MacBook Pro/Air Microphone
        if let d = nonLoopback.first(where: { $0.name.localizedCaseInsensitiveContains("MacBook") }) {
            return d.index
        }
        // Built-in or Internal Microphone
        if let d = nonLoopback.first(where: {
            $0.name.localizedCaseInsensitiveContains("Built-in") ||
            $0.name.localizedCaseInsensitiveContains("Internal")
        }) {
            return d.index
        }
        // System default (non-loopback)
        if let d = nonLoopback.first(where: { $0.isDefault }) {
            return d.index
        }
        return nonLoopback.first?.index ?? list.first?.index
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
