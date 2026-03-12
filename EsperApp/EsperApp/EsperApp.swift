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
                .onAppear {
                    NSApp.activate(ignoringOtherApps: true)
                }
        }
        .defaultSize(width: 520, height: 640)

        Settings {
            SettingsView(engine: engine)
        }
    }

    init() {
        DispatchQueue.main.async { [self] in
            engine.launch()
            openWindow(id: "main")
        }
    }
}
