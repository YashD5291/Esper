import SwiftUI

@main
struct EsperApp: App {
    @State private var engine = TranscriptionEngine()
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(engine: engine)
        } label: {
            Image(systemName: engine.status == .listening ? "waveform.circle.fill" : "waveform.circle")
        }

        WindowGroup("Esper", id: "main") {
            MainWindowView(engine: engine)
                .task {
                    // Launch here — @State is fully wired, events reach the real engine
                    if !engine.bridge.isRunning {
                        engine.launch()
                    }
                    NSApp.activate(ignoringOtherApps: true)
                }
        }
        .defaultSize(width: 520, height: 640)

        Settings {
            SettingsView(engine: engine)
        }
    }
}
