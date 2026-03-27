import Foundation

// MARK: - Engine Status

enum EngineStatus: String {
    case idle
    case downloadingModel = "downloading_model"
    case compilingShaders = "compiling_shaders"
    case loadingModel = "loading_model"
    case transcribing
    case listening
}

extension EngineStatus {
    var displayName: String {
        switch self {
        case .idle: "Ready"
        case .downloadingModel: "Downloading Model"
        case .compilingShaders: "Compiling Shaders"
        case .loadingModel: "Loading Model"
        case .transcribing: "Transcribing"
        case .listening: "Listening"
        }
    }
}

// MARK: - Audio Device

struct AudioDevice: Identifiable, Hashable {
    let index: Int
    let name: String
    let channels: Int
    let isDefault: Bool

    var id: Int { index }
}

// MARK: - Transcription

struct TranscriptionPayload: Sendable {
    var text: String = ""
    var finalizedText: String = ""
    var sentences: [String] = []
    var noSpeechProb: Double = 0.0
    var durationS: Double = 0.0
}

// MARK: - Telegram

struct TelegramTestResult {
    let success: Bool
    let error: String?
}

// MARK: - Server Events

enum ServerEvent {
    case devices([AudioDevice])
    case status(EngineStatus)
    case transcript(TranscriptionPayload)
    case energy(Double)
    case telegramTest(Bool, String?)
    case crashed(Int32)
    case error(String)
    case unknown

    // MARK: - Parsing

    static func parse(json data: Data) -> ServerEvent? {
        guard
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let event = obj["event"] as? String
        else { return nil }

        let payload = obj["data"]

        switch event {
        case "devices":
            guard let list = payload as? [[String: Any]] else { return .devices([]) }
            let devices = list.compactMap { d -> AudioDevice? in
                guard
                    let index = d["index"] as? Int,
                    let name = d["name"] as? String
                else { return nil }
                let channels = d["channels"] as? Int ?? 1
                let isDefault = d["is_default"] as? Bool ?? false
                return AudioDevice(index: index, name: name, channels: channels, isDefault: isDefault)
            }
            return .devices(devices)

        case "status":
            let statusStr = payload as? String ?? ""
            let status = EngineStatus(rawValue: statusStr) ?? .idle
            return .status(status)

        case "transcript":
            guard let d = payload as? [String: Any] else { return nil }
            let text = d["text"] as? String ?? ""
            let finalizedText = d["finalized_text"] as? String ?? ""
            let sentences = d["sentences"] as? [String] ?? []
            let noSpeechProb = d["no_speech_prob"] as? Double ?? 0.0
            let durationS = d["duration_s"] as? Double ?? 0.0
            return .transcript(TranscriptionPayload(
                text: text,
                finalizedText: finalizedText,
                sentences: sentences,
                noSpeechProb: noSpeechProb,
                durationS: durationS
            ))

        case "energy":
            guard let d = payload as? [String: Any],
                  let level = d["level"] as? Double else { return nil }
            return .energy(level)

        case "telegram_test":
            guard let d = payload as? [String: Any],
                  let success = d["success"] as? Bool else { return nil }
            let error = d["error"] as? String
            return .telegramTest(success, error)

        case "crashed":
            let code = (payload as? Int32) ?? -1
            return .crashed(code)

        case "error":
            guard let d = payload as? [String: Any],
                  let message = d["message"] as? String else {
                return .error(payload as? String ?? "Unknown error")
            }
            return .error(message)

        default:
            return .unknown
        }
    }
}
