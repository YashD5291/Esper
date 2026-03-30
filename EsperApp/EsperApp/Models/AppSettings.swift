import SwiftUI

@Observable
final class AppSettings {
    // Telegram
    @ObservationIgnored
    @AppStorage("telegramEnabled") var telegramEnabled: Bool = false

    var telegramBotToken: String {
        get { KeychainHelper.load(for: "telegramBotToken") }
        set { KeychainHelper.save(newValue, for: "telegramBotToken") }
    }

    var telegramChatId: String {
        get { KeychainHelper.load(for: "telegramChatId") }
        set { KeychainHelper.save(newValue, for: "telegramChatId") }
    }

    init() {
        // Migrate from UserDefaults to Keychain (one-time)
        let defaults = UserDefaults.standard
        if let oldToken = defaults.string(forKey: "telegramBotToken"), !oldToken.isEmpty,
           KeychainHelper.load(for: "telegramBotToken").isEmpty {
            KeychainHelper.save(oldToken, for: "telegramBotToken")
            defaults.removeObject(forKey: "telegramBotToken")
        }
        if let oldChatId = defaults.string(forKey: "telegramChatId"), !oldChatId.isEmpty,
           KeychainHelper.load(for: "telegramChatId").isEmpty {
            KeychainHelper.save(oldChatId, for: "telegramChatId")
            defaults.removeObject(forKey: "telegramChatId")
        }
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
        (NSHomeDirectory() as NSString).appendingPathComponent("Codebase/Fun/Esper")
    }
}
