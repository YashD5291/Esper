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
    @AppStorage("overlayEnabled") var overlayEnabled: Bool = false

    @ObservationIgnored
    @AppStorage("overlayPosition") var overlayPosition: String = "bottomCenter"

    @ObservationIgnored
    @AppStorage("overlayDragX") var overlayDragX: Double = -1

    @ObservationIgnored
    @AppStorage("overlayDragY") var overlayDragY: Double = -1

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

    var parsedOverlayPosition: OverlayPosition {
        OverlayPosition(rawValue: overlayPosition) ?? .bottomCenter
    }

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
        // 1. Environment variable override (for any developer)
        if let envDir = ProcessInfo.processInfo.environment["ESPER_PROJECT_DIR"] {
            return envDir
        }
        // 2. Infer from executable location (works if launched from project)
        let execDir = Bundle.main.bundlePath
        let projectDir = (execDir as NSString).deletingLastPathComponent
        if FileManager.default.fileExists(atPath: (projectDir as NSString).appendingPathComponent("src/server.py")) {
            return projectDir
        }
        // 3. Final fallback: current working directory
        let cwd = FileManager.default.currentDirectoryPath
        if FileManager.default.fileExists(atPath: (cwd as NSString).appendingPathComponent("src/server.py")) {
            return cwd
        }
        // 4. Last resort: current working directory (will fail gracefully at launch)
        return cwd
    }
}
