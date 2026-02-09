import SwiftUI

struct SettingsSection: View {
    @Bindable var settings: AppSettings
    var devices: [AudioDevice] = []
    var selectedDevice: Int?
    var onSelectDevice: ((_ index: Int) -> Void)?
    var onRefreshDevices: (() -> Void)?
    var onTestTelegram: ((_ botToken: String, _ chatId: String) -> Void)?
    var telegramTestResult: TelegramTestResult?

    var body: some View {
        Form {
            // Input Device
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

            // Engine
            Section("Engine") {
                Picker("Backend", selection: $settings.engine) {
                    Text("CoreML").tag("coreml")
                    Text("MLX").tag("mlx")
                }
                .pickerStyle(.segmented)
                .help("CoreML runs on Apple Neural Engine (fastest). MLX runs on GPU (better sentence segmentation).")

                if settings.engine == "coreml" {
                    HStack {
                        Text("Buffer")
                        Slider(value: $settings.bufferSeconds, in: 1...15, step: 0.5)
                        Text("\(settings.bufferSeconds, specifier: "%.1f")s")
                            .monospacedDigit()
                            .frame(width: 36, alignment: .trailing)
                    }
                    .help("Seconds of audio to accumulate before transcribing. Lower = faster but less context.")
                }
            }

            // Telegram
            Section("Telegram") {
                Toggle("Send transcriptions to Telegram", isOn: $settings.telegramEnabled)
                    .help("Send transcribed text to a Telegram chat in real time.")

                if settings.telegramEnabled {
                    TextField("Bot Token", text: $settings.telegramBotToken)
                        .textFieldStyle(.roundedBorder)
                        .overlay(validationBorder(isValid: !settings.telegramBotToken.isEmpty))
                        .help("Create a bot via @BotFather on Telegram to get this token.")

                    TextField("Chat ID", text: $settings.telegramChatId)
                        .textFieldStyle(.roundedBorder)
                        .overlay(validationBorder(isValid: !settings.telegramChatId.isEmpty))
                        .help("The numeric ID of the Telegram chat to send messages to.")

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

            // Advanced
            Section("Advanced") {
                TextField("Python Path", text: $settings.pythonPath, prompt: Text(settings.resolvedPythonPath))
                    .textFieldStyle(.roundedBorder)
                    .overlay(pathValidationBorder(path: settings.resolvedPythonPath))
                    .help("Path to the Python interpreter with Esper's dependencies installed.")

                TextField("Project Directory", text: $settings.projectDir, prompt: Text(settings.resolvedProjectDir))
                    .textFieldStyle(.roundedBorder)
                    .overlay(pathValidationBorder(path: settings.resolvedProjectDir))
                    .help("Root directory of the Esper project (where src/ lives).")
            }
        }
        .formStyle(.grouped)
        .frame(maxHeight: 340)
    }

    @ViewBuilder
    private func validationBorder(isValid: Bool) -> some View {
        if !isValid {
            RoundedRectangle(cornerRadius: 5)
                .stroke(.red, lineWidth: 1)
        }
    }

    @ViewBuilder
    private func pathValidationBorder(path: String) -> some View {
        if !path.isEmpty && !FileManager.default.fileExists(atPath: path) {
            RoundedRectangle(cornerRadius: 5)
                .stroke(.red, lineWidth: 1)
        }
    }
}

struct TelegramTestResult {
    let success: Bool
    let error: String?
}
