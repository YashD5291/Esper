import SwiftUI

@main
struct EsperApp: App {
    @State private var engine = TranscriptionEngine()
    @State private var launched = false
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(engine: engine)
                .onAppear { ensureLaunched() }
        } label: {
            Image(systemName: engine.status == .listening ? "waveform.circle.fill" : "waveform.circle")
        }

        WindowGroup("Esper", id: "main") {
            MainWindowView(engine: engine)
                .onAppear {
                    ensureLaunched()
                    NSApp.activate(ignoringOtherApps: true)
                }
        }
        .defaultSize(width: 520, height: 640)

        Settings {
            SettingsView(engine: engine)
        }
    }

    private func ensureLaunched() {
        guard !launched else { return }
        launched = true
        engine.launch()
    }

    init() {
        DispatchQueue.main.async { [self] in
            openWindow(id: "main")
        }
    }
}
