import Sparkle
import SwiftUI

struct MenuBarView: View {
    let engine: TranscriptionEngine
    let overlayController: OverlayController
    let updater: SPUUpdater
    @State private var flowButtonEnabled = true

    var body: some View {
        HStack {
            StatusBadge(status: engine.status)
            Text(engine.status.displayName)
        }
        .padding(.horizontal, 4)

        Divider()

        if engine.status == .listening {
            Button("Stop Listening") {
                engine.stopListening()
            }
        } else if engine.status == .idle {
            Button("Start Listening") {
                engine.startListening()
            }
        } else {
            Button("Start Listening") {
                engine.startListening()
            }
            .disabled(true)
        }

        Divider()

        if let error = engine.errorMessage {
            Label(error, systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
                .lineLimit(3)

            Button("Restart") {
                engine.restart()
            }

            Divider()
        }

        Button(flowButtonEnabled ? "Hide Flow Button" : "Show Flow Button") {
            flowButtonEnabled.toggle()
            engine.settings.flowButtonEnabled = flowButtonEnabled
        }

        Divider()

        CheckForUpdatesView(updater: updater)

        Divider()

        SettingsLink {
            Text("Settings...")
        }
        .keyboardShortcut(",")

        Button("Quit Esper") {
            engine.shutdown()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                NSApp.terminate(nil)
            }
        }
        .keyboardShortcut("q")
        .onAppear {
            flowButtonEnabled = engine.settings.flowButtonEnabled
        }
    }
}
