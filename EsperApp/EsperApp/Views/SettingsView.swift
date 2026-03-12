import SwiftUI

struct SettingsView: View {
    let engine: TranscriptionEngine

    var body: some View {
        TabView {
            GeneralTab(
                settings: engine.settings,
                devices: engine.devices,
                selectedDevice: engine.selectedDevice,
                onSelectDevice: { engine.setDevice($0) },
                onRefreshDevices: { engine.refreshDevices() }
            )
            .tabItem { Label("General", systemImage: "gear") }

            TelegramTab(
                settings: engine.settings,
                onTestTelegram: { botToken, chatId in
                    engine.testTelegram(botToken: botToken, chatId: chatId)
                },
                telegramTestResult: engine.telegramTestResult
            )
            .tabItem { Label("Telegram", systemImage: "paperplane") }

            AdvancedTab(settings: engine.settings)
            .tabItem { Label("Advanced", systemImage: "wrench.and.screwdriver") }
        }
        .frame(width: 460, height: 320)
    }
}

// MARK: - General

private struct GeneralTab: View {
    @Bindable var settings: AppSettings
    var devices: [AudioDevice]
    var selectedDevice: Int?
    var onSelectDevice: ((Int) -> Void)?
    var onRefreshDevices: (() -> Void)?

    var body: some View {
        Form {
            Section("Input Device") {
                HStack {
                    Picker("Microphone", selection: Binding(
                        get: { selectedDevice ?? -1 },
                        set: { if $0 != -1 { onSelectDevice?($0) } }
                    )) {
                        if devices.isEmpty {
                            Text("No devices").tag(-1)
                        }
                        ForEach(devices) { device in
                            Text(device.name).tag(device.index)
                        }
                    }

                    Button {
                        onRefreshDevices?()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.borderless)
                    .help("Refresh device list")
                }
            }

            Section("Engine") {
                Picker("Backend", selection: $settings.engine) {
                    Text("CoreML").tag("coreml")
                    Text("MLX").tag("mlx")
                }
                .pickerStyle(.segmented)
                .help("CoreML uses Apple Neural Engine (fastest). MLX uses GPU.")

                if settings.engine == "coreml" {
                    HStack {
                        Text("Buffer")
                        Slider(value: $settings.bufferSeconds, in: 1...15, step: 0.5)
                        Text("\(settings.bufferSeconds, specifier: "%.1f")s")
                            .monospacedDigit()
                            .frame(width: 36, alignment: .trailing)
                    }
                    .help("Seconds of audio to buffer before transcribing. Lower = faster, less context.")
                }
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Telegram

private struct TelegramTab: View {
    @Bindable var settings: AppSettings
    var onTestTelegram: ((String, String) -> Void)?
    var telegramTestResult: TelegramTestResult?

    var body: some View {
        Form {
            Section {
                Toggle("Send transcriptions to Telegram", isOn: $settings.telegramEnabled)
                    .help("Relay transcribed text to a Telegram chat in real time.")
            }

            if settings.telegramEnabled {
                Section("Credentials") {
                    TextField("Bot Token", text: $settings.telegramBotToken)
                        .textFieldStyle(.roundedBorder)
                        .help("Create a bot via @BotFather on Telegram to get this token.")

                    TextField("Chat ID", text: $settings.telegramChatId)
                        .textFieldStyle(.roundedBorder)
                        .help("Numeric ID of the Telegram chat to send messages to.")
                }

                Section {
                    HStack {
                        Button("Test Connection") {
                            onTestTelegram?(settings.telegramBotToken, settings.telegramChatId)
                        }
                        .disabled(settings.telegramBotToken.isEmpty || settings.telegramChatId.isEmpty)

                        if let result = telegramTestResult {
                            if result.success {
                                Label("Connected", systemImage: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                                    .font(.caption)
                            } else {
                                Label(result.error ?? "Failed", systemImage: "xmark.circle.fill")
                                    .foregroundStyle(.red)
                                    .font(.caption)
                                    .lineLimit(2)
                            }
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Advanced

private struct AdvancedTab: View {
    @Bindable var settings: AppSettings

    var body: some View {
        Form {
            Section("Paths") {
                LabeledContent("Python") {
                    TextField("", text: $settings.pythonPath, prompt: Text(settings.resolvedPythonPath))
                        .textFieldStyle(.roundedBorder)
                        .overlay(pathBorder(settings.resolvedPythonPath))
                }
                .help("Path to the Python interpreter with Esper's dependencies.")

                LabeledContent("Project Dir") {
                    TextField("", text: $settings.projectDir, prompt: Text(settings.resolvedProjectDir))
                        .textFieldStyle(.roundedBorder)
                        .overlay(pathBorder(settings.resolvedProjectDir))
                }
                .help("Root directory of the Esper project (where src/ lives).")
            }
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    private func pathBorder(_ path: String) -> some View {
        if !path.isEmpty && !FileManager.default.fileExists(atPath: path) {
            RoundedRectangle(cornerRadius: 5)
                .stroke(.red, lineWidth: 1)
        }
    }
}
