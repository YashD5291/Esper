import SwiftUI

@Observable
final class AppSettings {
    // Telegram
    @ObservationIgnored
    @AppStorage("telegramEnabled") var telegramEnabled: Bool = false

    // NOTE: Keychain storage requires a proper Apple Developer certificate.
    // With ad-hoc signing, every Keychain access triggers a user prompt.
    // Using @AppStorage (UserDefaults) until a developer cert is available.
    @ObservationIgnored
    @AppStorage("telegramBotToken") var telegramBotToken: String = ""

    @ObservationIgnored
    @AppStorage("telegramChatId") var telegramChatId: String = ""

    // Overlay
    @ObservationIgnored
    @AppStorage("overlayTextSize") var overlayTextSize: String = "medium"

    @ObservationIgnored
    @AppStorage("overlayTextColor") var overlayTextColor: String = "#FFFFFF"

    @ObservationIgnored
    @AppStorage("overlayMaxLines") var overlayMaxLines: Int = 3

    @ObservationIgnored
    @AppStorage("overlayOpacity") var overlayOpacity: Double = 1.0

    @ObservationIgnored
    @AppStorage("overlayPreset") var overlayPreset: String = "custom"

    @ObservationIgnored
    @AppStorage("overlayShowTelegramStatus") var overlayShowTelegramStatus: Bool = true

    @ObservationIgnored
    @AppStorage("overlayLockPosition") var overlayLockPosition: Bool = false

    @ObservationIgnored
    @AppStorage("flowButtonEnabled") var flowButtonEnabled: Bool = true

    @ObservationIgnored
    @AppStorage("flowButtonX") var flowButtonX: Double = -1

    @ObservationIgnored
    @AppStorage("overlayAutoDismiss") var overlayAutoDismiss: Bool = false

    @ObservationIgnored
    @AppStorage("overlayAutoDismissSeconds") var overlayAutoDismissSeconds: Int = 30

    // MARK: - Overlay Computed Helpers

    var overlayFontSize: CGFloat {
        switch overlayTextSize {
        case "small": return 13
        case "large": return 22
        default: return 15
        }
    }

    var parsedOverlayColor: Color {
        Color.fromHex(overlayTextColor)
    }

    // MARK: - Server executable path

    /// Path to the frozen esper-server binary (bundled mode), or nil for dev mode.
    var frozenServerPath: String? {
        guard let resources = Bundle.main.resourcePath else { return nil }
        let path = (resources as NSString).appendingPathComponent("esper-server/esper-server")
        return FileManager.default.fileExists(atPath: path) ? path : nil
    }

    /// Dev-mode Python path (venv in project directory).
    var devPythonPath: String {
        (devProjectDir as NSString).appendingPathComponent(".venv/bin/python3")
    }

    /// Dev-mode project directory.
    var devProjectDir: String {
        let fm = FileManager.default
        func hasServer(_ dir: String) -> Bool {
            fm.fileExists(atPath: (dir as NSString).appendingPathComponent("src/server.py"))
        }

        // 1. Environment variable override
        if let envDir = ProcessInfo.processInfo.environment["ESPER_PROJECT_DIR"], hasServer(envDir) {
            return envDir
        }
        // 2. Infer from executable location (works if launched from project)
        let projectDir = (Bundle.main.bundlePath as NSString).deletingLastPathComponent
        if hasServer(projectDir) {
            return projectDir
        }
        // 3. Walk up from the built .app through DerivedData to find the repo
        var searchDir = (Bundle.main.bundlePath as NSString).deletingLastPathComponent
        for _ in 0..<10 {
            if hasServer(searchDir) { return searchDir }
            let parent = (searchDir as NSString).deletingLastPathComponent
            if parent == searchDir { break }
            searchDir = parent
        }
        // 5. Current working directory
        let cwd = fm.currentDirectoryPath
        if hasServer(cwd) {
            return cwd
        }
        // 6. Hardcoded common locations
        let home = NSHomeDirectory()
        let candidates = [
            (home as NSString).appendingPathComponent("Codebase/Fun/Esper"),
            (home as NSString).appendingPathComponent("Developer/Esper"),
            (home as NSString).appendingPathComponent("Projects/Esper"),
        ]
        for dir in candidates {
            if hasServer(dir) { return dir }
        }
        return cwd
    }
}
