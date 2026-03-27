import SwiftUI

@Observable
final class AppSettings {
    // Paths
    @ObservationIgnored
    @AppStorage("pythonPath") var pythonPath: String = ""

    @ObservationIgnored
    @AppStorage("projectDir") var projectDir: String = ""

    // Telegram
    @ObservationIgnored
    @AppStorage("telegramEnabled") var telegramEnabled: Bool = false

    @ObservationIgnored
    @AppStorage("telegramBotToken") var telegramBotToken: String = ""

    @ObservationIgnored
    @AppStorage("telegramChatId") var telegramChatId: String = ""

    // MARK: - Resolved paths (fall back to sensible defaults)

    var resolvedPythonPath: String {
        if !pythonPath.isEmpty { return pythonPath }
        // Bundled app: python inside Resources
        if let bundled = Bundle.main.resourcePath {
            let bundledPython = (bundled as NSString).appendingPathComponent("python/bin/python3")
            if FileManager.default.fileExists(atPath: bundledPython) {
                return bundledPython
            }
        }
        // Dev fallback: venv in project directory
        return (resolvedProjectDir as NSString).appendingPathComponent(".venv/bin/python3")
    }

    var resolvedProjectDir: String {
        if !projectDir.isEmpty { return projectDir }
        // Bundled app: src/ and models/ inside Resources
        if let bundled = Bundle.main.resourcePath {
            let bundledSrc = (bundled as NSString).appendingPathComponent("src")
            if FileManager.default.fileExists(atPath: bundledSrc) {
                return bundled
            }
        }
        // Dev fallback
        return (NSHomeDirectory() as NSString).appendingPathComponent("Codebase/Fun/Esper")
    }
}
