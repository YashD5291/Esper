import Sparkle
import SwiftUI

struct SettingsView: View {
    let engine: TranscriptionEngine
    var overlayController: OverlayController?
    let updater: SPUUpdater

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

            OverlaySettingsTab(settings: engine.settings, overlayController: overlayController)
                .tabItem { Label("Overlay", systemImage: "text.bubble") }

            UpdateSettingsTab(updater: updater)
                .tabItem { Label("Updates", systemImage: "arrow.triangle.2.circlepath") }

            AdvancedTab(settings: engine.settings)
            .tabItem { Label("Advanced", systemImage: "wrench.and.screwdriver") }
        }
        .frame(minWidth: 460, minHeight: 320)
        .onAppear {
            // Make Settings window resizable (Settings scene doesn't support this natively)
            DispatchQueue.main.async {
                if let window = NSApp.windows.first(where: { $0.title == "Settings" || $0.identifier?.rawValue == "com_apple_SwiftUI_Settings_window" }) {
                    window.styleMask.insert(.resizable)
                }
            }
        }
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
        }
        .formStyle(.grouped)
    }
}

// MARK: - Telegram

private struct TelegramTab: View {
    var settings: AppSettings
    var onTestTelegram: ((String, String) -> Void)?
    var telegramTestResult: TelegramTestResult?

    @State private var botToken: String = ""
    @State private var chatId: String = ""
    @State private var enabled: Bool = false
    @State private var saved: Bool = false

    private var hasChanges: Bool {
        botToken != settings.telegramBotToken ||
        chatId != settings.telegramChatId ||
        enabled != settings.telegramEnabled
    }

    private var canTest: Bool {
        !botToken.trimmingCharacters(in: .whitespaces).isEmpty &&
        !chatId.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        Form {
            Section {
                Toggle("Send transcriptions to Telegram", isOn: $enabled)
                    .help("Relay transcribed text to a Telegram chat in real time.")
            }

            if enabled {
                Section("Credentials") {
                    TextField("Bot Token", text: $botToken)
                        .textFieldStyle(.roundedBorder)
                        .help("Create a bot via @BotFather on Telegram to get this token.")

                    TextField("Chat ID", text: $chatId)
                        .textFieldStyle(.roundedBorder)
                        .help("Numeric ID of the Telegram chat to send messages to.")
                }

                Section {
                    HStack {
                        Button("Save") {
                            settings.telegramEnabled = enabled
                            settings.telegramBotToken = botToken.trimmingCharacters(in: .whitespaces)
                            settings.telegramChatId = chatId.trimmingCharacters(in: .whitespaces)
                            saved = true
                            DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                                saved = false
                            }
                        }
                        .disabled(!hasChanges)

                        Button("Test Connection") {
                            // Save first, then test
                            settings.telegramBotToken = botToken.trimmingCharacters(in: .whitespaces)
                            settings.telegramChatId = chatId.trimmingCharacters(in: .whitespaces)
                            settings.telegramEnabled = enabled
                            onTestTelegram?(settings.telegramBotToken, settings.telegramChatId)
                        }
                        .disabled(!canTest)

                        if saved {
                            Label("Saved", systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                                .font(.caption)
                                .transition(.opacity)
                        }

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
        .onAppear {
            botToken = settings.telegramBotToken
            chatId = settings.telegramChatId
            enabled = settings.telegramEnabled
        }
        .onChange(of: enabled) { _, newValue in
            settings.telegramEnabled = newValue
        }
    }
}

// MARK: - Advanced

private struct AdvancedTab: View {
    var settings: AppSettings

    var body: some View {
        Form {
            Section("Server") {
                if let frozenPath = settings.frozenServerPath {
                    LabeledContent("Mode", value: "Bundled")
                    LabeledContent("Binary", value: frozenPath)
                        .textSelection(.enabled)
                } else {
                    LabeledContent("Mode", value: "Dev")
                    LabeledContent("Python", value: settings.devPythonPath)
                        .textSelection(.enabled)
                    LabeledContent("Project Dir", value: settings.devProjectDir)
                        .textSelection(.enabled)
                }
            }
        }
        .formStyle(.grouped)
    }
}
