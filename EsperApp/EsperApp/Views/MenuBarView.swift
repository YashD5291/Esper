import Sparkle
import SwiftUI

struct MenuBarView: View {
    let engine: TranscriptionEngine
    let updater: SPUUpdater
    @Environment(\.openWindow) private var openWindow
    @State private var overlayEnabled = false

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
            Text("Loading model...")
                .foregroundStyle(.secondary)
        }

        Divider()

        if !engine.devices.isEmpty {
            Text("Input Device")
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(engine.devices) { device in
                Button {
                    engine.setDevice(device.index)
                } label: {
                    HStack {
                        if engine.selectedDevice == device.index {
                            Image(systemName: "checkmark")
                        }
                        Text(device.name)
                    }
                }
            }

            Divider()
        }

        if let error = engine.errorMessage {
            Label(error, systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
                .lineLimit(3)

            Button("Restart") {
                engine.restart()
            }

            Divider()
        }

        Button(overlayEnabled ? "Hide Overlay" : "Show Overlay") {
            overlayEnabled.toggle()
            engine.settings.overlayEnabled = overlayEnabled
        }

        Divider()

        CheckForUpdatesView(updater: updater)

        Divider()

        Button("Open Window") {
            openWindow(id: "main")
            NSApp.activate(ignoringOtherApps: true)
        }
        .keyboardShortcut("o")

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
        .onAppear { overlayEnabled = engine.settings.overlayEnabled }
    }
}
