import Foundation

// MARK: - Engine Status

enum EngineStatus: String {
    case idle
    case loadingModel = "loading_model"
    case listening
}

extension EngineStatus {
    var displayName: String {
        switch self {
        case .idle: "Ready"
        case .loadingModel: "Loading Model"
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
    var finalizedText: String = ""
    var draftText: String = ""
    var finalizedSentences: [SentencePayload] = []
}

struct SentencePayload: Identifiable, Sendable {
    let text: String
    let confidence: Double

    var id: String { text }
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
    case telegramSent
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
            let finalizedText = d["finalized_text"] as? String ?? ""
            let draftText = d["draft_text"] as? String ?? ""
            var sentences: [SentencePayload] = []
            if let rawSentences = d["finalized_sentences"] as? [[String: Any]] {
                sentences = rawSentences.compactMap { s -> SentencePayload? in
                    guard let text = s["text"] as? String else { return nil }
                    let confidence = s["confidence"] as? Double ?? 1.0
                    return SentencePayload(text: text, confidence: confidence)
                }
            }
            return .transcript(TranscriptionPayload(
                finalizedText: finalizedText,
                draftText: draftText,
                finalizedSentences: sentences
            ))

        case "energy":
            guard let d = payload as? [String: Any],
                  let level = d["level"] as? Double else { return nil }
            return .energy(level)

        case "telegram_sent":
            return .telegramSent

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
