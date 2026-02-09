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
    }

    init() {
        // Launch Python process on app start
        DispatchQueue.main.async { [self] in
            engine.launch()
            // Open the main window automatically on launch
            openWindow(id: "main")
        }
    }
}
