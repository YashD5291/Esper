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
        // 4. Last resort: home directory assumption (will fail gracefully at launch)
        return (NSHomeDirectory() as NSString).appendingPathComponent("Codebase/Fun/Esper")
    }
}
