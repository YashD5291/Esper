import KeyboardShortcuts
import SwiftUI

struct ShortcutsTab: View {
    var body: some View {
        Form {
            Section("Global Hotkey") {
                KeyboardShortcuts.Recorder("Toggle Listening:", name: .toggleListening)

                Text("Press this shortcut from any app to start or stop transcription.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }
}
