import SwiftUI

@main
struct EsperApp: App {
    @State private var engine = TranscriptionEngine()

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(engine: engine)
        } label: {
            Image(systemName: engine.status == .listening ? "waveform.circle.fill" : "waveform.circle")
        }

        WindowGroup("Esper", id: "main") {
            MainWindowView(engine: engine)
        }
        .defaultSize(width: 520, height: 640)
    }

    init() {
        // Launch Python process on app start
        DispatchQueue.main.async { [self] in
            engine.launch()
        }
    }
}
