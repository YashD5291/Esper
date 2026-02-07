import SwiftUI

struct MenuBarView: View {
    let engine: TranscriptionEngine
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        // Status
        HStack {
            StatusBadge(status: engine.status)
            Text(engine.status.displayName)
        }
        .padding(.horizontal, 4)

        Divider()

        // Start / Stop
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

        // Device picker
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

        // Error display
        if let error = engine.errorMessage {
            Label(error, systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
                .lineLimit(2)

            Button("Restart") {
                engine.restart()
            }

            Divider()
        }

        // Window / Quit
        Button("Open Window") {
            openWindow(id: "main")
            NSApp.activate(ignoringOtherApps: true)
        }
        .keyboardShortcut("o")

        Button("Quit Esper") {
            engine.shutdown()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                NSApp.terminate(nil)
            }
        }
        .keyboardShortcut("q")
    }
}

private extension EngineStatus {
    var displayName: String {
        switch self {
        case .idle: "Idle"
        case .loadingModel: "Loading Model"
        case .listening: "Listening"
        }
    }
}
