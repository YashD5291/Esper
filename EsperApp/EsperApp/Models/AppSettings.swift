import SwiftUI

@Observable
final class AppSettings {
    // Engine
    @ObservationIgnored
    @AppStorage("engine") var engine: String = "coreml"

    // Buffer
    @ObservationIgnored
    @AppStorage("bufferSeconds") var bufferSeconds: Double = 1.5

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
        // Default: venv Python in the project directory
        return (resolvedProjectDir as NSString).appendingPathComponent(".venv/bin/python3")
    }

    var resolvedProjectDir: String {
        if !projectDir.isEmpty { return projectDir }
        // Default: ~/Codebase/Fun/Esper (the project's known location)
        return (NSHomeDirectory() as NSString).appendingPathComponent("Codebase/Fun/Esper")
    }
}
