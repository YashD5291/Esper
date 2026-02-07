import SwiftUI

struct MainWindowView: View {
    let engine: TranscriptionEngine
    @State private var showSettings = false

    var body: some View {
        VStack(spacing: 0) {
            // Top bar
            HStack {
                StatusBadge(status: engine.status)
                Text(engine.status == .listening ? "Listening" : engine.status == .loadingModel ? "Loading..." : "Idle")
                    .font(.headline)

                Spacer()

                Text(engine.settings.engine.uppercased())
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(.quaternary)
                    .clipShape(Capsule())
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            // Audio level meter
            AudioLevelMeter(level: engine.energyLevel)
                .padding(.horizontal, 16)

            Divider()
                .padding(.top, 8)

            // Transcript
            TranscriptView(
                sentences: engine.finalizedSentences,
                draftText: engine.draftText
            )

            Divider()

            // Bottom bar
            HStack {
                if engine.status == .listening {
                    Button("Stop") {
                        engine.stopListening()
                    }
                    .buttonStyle(.bordered)
                } else if engine.status == .idle {
                    Button("Start") {
                        engine.startListening()
                    }
                    .buttonStyle(.borderedProminent)
                } else {
                    ProgressView()
                        .controlSize(.small)
                    Text("Loading model...")
                        .foregroundStyle(.secondary)
                }

                Spacer()

                // Error indicator
                if let error = engine.errorMessage {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                        .font(.caption)
                        .lineLimit(3)
                        .help(error)

                    Button("Restart") {
                        engine.restart()
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }

                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showSettings.toggle()
                    }
                } label: {
                    Image(systemName: "gear")
                }
                .buttonStyle(.borderless)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            // Settings panel (collapsible)
            if showSettings {
                Divider()
                SettingsSection(
                    settings: engine.settings,
                    onTestTelegram: { botToken, chatId in
                        engine.testTelegram(botToken: botToken, chatId: chatId)
                    },
                    telegramTestResult: engine.telegramTestResult
                )
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .frame(minWidth: 420, minHeight: 400)
    }
}
