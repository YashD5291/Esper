import SwiftUI

@Observable
final class AppSettings {
    // Telegram
    @ObservationIgnored
    @AppStorage("telegramEnabled") var telegramEnabled: Bool = false

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
        (NSHomeDirectory() as NSString).appendingPathComponent("Codebase/Fun/Esper")
    }
}
