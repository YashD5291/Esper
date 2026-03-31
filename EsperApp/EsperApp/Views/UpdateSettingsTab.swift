import Sparkle
import SwiftUI

struct UpdateSettingsTab: View {
    private let updater: SPUUpdater
    @State private var automaticallyChecksForUpdates: Bool

    init(updater: SPUUpdater) {
        self.updater = updater
        self.automaticallyChecksForUpdates = updater.automaticallyChecksForUpdates
    }

    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
    }

    var body: some View {
        Form {
            Section {
                Toggle("Automatically check for updates", isOn: $automaticallyChecksForUpdates)
                    .onChange(of: automaticallyChecksForUpdates) { _, newValue in
                        updater.automaticallyChecksForUpdates = newValue
                    }
            }

            Section {
                LabeledContent("Current Version", value: "v\(appVersion)")

                CheckForUpdatesView(updater: updater)
            }
        }
        .formStyle(.grouped)
    }
}
