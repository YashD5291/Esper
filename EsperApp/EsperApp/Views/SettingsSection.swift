import SwiftUI

struct SettingsSection: View {
    @Bindable var settings: AppSettings

    var body: some View {
        Form {
            // Engine
            Section("Engine") {
                Picker("Backend", selection: $settings.engine) {
                    Text("CoreML").tag("coreml")
                    Text("MLX").tag("mlx")
                }
                .pickerStyle(.segmented)

                if settings.engine == "coreml" {
                    HStack {
                        Text("Buffer")
                        Slider(value: $settings.bufferSeconds, in: 1...15, step: 0.5)
                        Text("\(settings.bufferSeconds, specifier: "%.1f")s")
                            .monospacedDigit()
                            .frame(width: 36, alignment: .trailing)
                    }
                }
            }

            // Telegram
            Section("Telegram") {
                Toggle("Send transcriptions to Telegram", isOn: $settings.telegramEnabled)

                if settings.telegramEnabled {
                    TextField("Bot Token", text: $settings.telegramBotToken)
                        .textFieldStyle(.roundedBorder)
                    TextField("Chat ID", text: $settings.telegramChatId)
                        .textFieldStyle(.roundedBorder)
                }
            }

            // Advanced
            Section("Advanced") {
                TextField("Python Path", text: $settings.pythonPath, prompt: Text(settings.resolvedPythonPath))
                    .textFieldStyle(.roundedBorder)
                TextField("Project Directory", text: $settings.projectDir, prompt: Text(settings.resolvedProjectDir))
                    .textFieldStyle(.roundedBorder)
            }
        }
        .formStyle(.grouped)
        .frame(maxHeight: 340)
    }
}
