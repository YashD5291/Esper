import XCTest
@testable import EsperApp

final class ProtocolTests: XCTestCase {

    // MARK: - Status

    func testStatusIdleParsed() throws {
        let json = #"{"event":"status","data":"idle"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .status(let s) = event else { return XCTFail("Expected .status") }
        XCTAssertEqual(s, .idle)
    }

    func testStatusListeningParsed() throws {
        let json = #"{"event":"status","data":"listening"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .status(let s) = event else { return XCTFail("Expected .status") }
        XCTAssertEqual(s, .listening)
    }

    func testStatusTranscribingParsed() throws {
        let json = #"{"event":"status","data":"transcribing"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .status(let s) = event else { return XCTFail("Expected .status") }
        XCTAssertEqual(s, .transcribing)
    }

    func testStatusDownloadingModelParsed() throws {
        let json = #"{"event":"status","data":"downloading_model"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .status(let s) = event else { return XCTFail("Expected .status") }
        XCTAssertEqual(s, .downloadingModel)
    }

    func testStatusUnknownValueFallsBackToIdle() throws {
        let json = #"{"event":"status","data":"some_new_status"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .status(let s) = event else { return XCTFail("Expected .status") }
        XCTAssertEqual(s, .idle)
    }

    // MARK: - Devices

    func testDevicesParsed() throws {
        let json = """
        {"event":"devices","data":[{"index":0,"name":"Mic","channels":1,"is_default":true}]}
        """.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .devices(let list) = event else { return XCTFail("Expected .devices") }
        XCTAssertEqual(list.count, 1)
        XCTAssertEqual(list[0].name, "Mic")
        XCTAssertEqual(list[0].index, 0)
        XCTAssertEqual(list[0].channels, 1)
        XCTAssertTrue(list[0].isDefault)
    }

    func testDevicesEmptyArrayParsed() throws {
        let json = #"{"event":"devices","data":[]}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .devices(let list) = event else { return XCTFail("Expected .devices") }
        XCTAssertTrue(list.isEmpty)
    }

    func testDevicesMultipleParsed() throws {
        let json = """
        {"event":"devices","data":[{"index":0,"name":"Built-in","channels":1,"is_default":true},{"index":2,"name":"Loopback","channels":2,"is_default":false}]}
        """.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .devices(let list) = event else { return XCTFail("Expected .devices") }
        XCTAssertEqual(list.count, 2)
        XCTAssertEqual(list[1].name, "Loopback")
        XCTAssertEqual(list[1].channels, 2)
        XCTAssertFalse(list[1].isDefault)
    }

    func testDevicesNonArrayDataReturnsEmptyList() throws {
        let json = #"{"event":"devices","data":"bad"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .devices(let list) = event else { return XCTFail("Expected .devices") }
        XCTAssertTrue(list.isEmpty)
    }

    // MARK: - Transcript

    func testTranscriptParsed() throws {
        let json = """
        {"event":"transcript","data":{"text":"hello","finalized_text":"hello world","sentences":["hello","world"],"no_speech_prob":0.1,"duration_s":1.5}}
        """.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .transcript(let p) = event else { return XCTFail("Expected .transcript") }
        XCTAssertEqual(p.text, "hello")
        XCTAssertEqual(p.finalizedText, "hello world")
        XCTAssertEqual(p.sentences, ["hello", "world"])
        XCTAssertEqual(p.noSpeechProb, 0.1, accuracy: 0.001)
        XCTAssertEqual(p.durationS, 1.5, accuracy: 0.001)
    }

    func testTranscriptMinimalFieldsParsed() throws {
        let json = #"{"event":"transcript","data":{}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .transcript(let p) = event else { return XCTFail("Expected .transcript") }
        XCTAssertEqual(p.text, "")
        XCTAssertEqual(p.finalizedText, "")
        XCTAssertTrue(p.sentences.isEmpty)
        XCTAssertEqual(p.noSpeechProb, 0.0, accuracy: 0.001)
        XCTAssertEqual(p.durationS, 0.0, accuracy: 0.001)
    }

    func testTranscriptNonDictDataReturnsNil() throws {
        let json = #"{"event":"transcript","data":"bad"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }

    // MARK: - Energy

    func testEnergyParsed() throws {
        let json = #"{"event":"energy","data":{"level":0.42}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .energy(let level) = event else { return XCTFail("Expected .energy") }
        XCTAssertEqual(level, 0.42, accuracy: 0.001)
    }

    func testEnergyMissingLevelReturnsNil() throws {
        let json = #"{"event":"energy","data":{}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }

    // MARK: - Telegram Test

    func testTelegramTestSuccessParsed() throws {
        let json = #"{"event":"telegram_test","data":{"success":true}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .telegramTest(let ok, let err) = event else { return XCTFail("Expected .telegramTest") }
        XCTAssertTrue(ok)
        XCTAssertNil(err)
    }

    func testTelegramTestFailureParsed() throws {
        let json = #"{"event":"telegram_test","data":{"success":false,"error":"bad token"}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .telegramTest(let ok, let err) = event else { return XCTFail("Expected .telegramTest") }
        XCTAssertFalse(ok)
        XCTAssertEqual(err, "bad token")
    }

    func testTelegramTestMissingSuccessReturnsNil() throws {
        let json = #"{"event":"telegram_test","data":{}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }

    // MARK: - Telegram Sent

    func testTelegramSentParsed() throws {
        let json = #"{"event":"telegram_sent","v":1,"data":{"text":"hello","sentence_index":0}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .telegramSent(let text, let index) = event else { return XCTFail("Expected .telegramSent") }
        XCTAssertEqual(text, "hello")
        XCTAssertEqual(index, 0)
    }

    func testTelegramSentMissingFieldsReturnsNil() throws {
        let json = #"{"event":"telegram_sent","v":1,"data":{}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }

    func testTelegramFailedParsed() throws {
        let json = #"{"event":"telegram_failed","v":1,"data":{"text":"hello","error":"timeout"}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .telegramFailed(let text, let error) = event else { return XCTFail("Expected .telegramFailed") }
        XCTAssertEqual(text, "hello")
        XCTAssertEqual(error, "timeout")
    }

    func testTelegramFailedMissingFieldsReturnsNil() throws {
        let json = #"{"event":"telegram_failed","v":1,"data":{}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }

    // MARK: - Crashed

    func testCrashedParsed() throws {
        let json = #"{"event":"crashed","data":1}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .crashed(let code) = event else { return XCTFail("Expected .crashed") }
        XCTAssertEqual(code, 1)
    }

    func testCrashedMissingDataDefaultsToNegativeOne() throws {
        let json = #"{"event":"crashed","data":null}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .crashed(let code) = event else { return XCTFail("Expected .crashed") }
        XCTAssertEqual(code, -1)
    }

    // MARK: - Error

    func testErrorWithMessageParsed() throws {
        let json = #"{"event":"error","data":{"message":"something broke"}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .error(let msg) = event else { return XCTFail("Expected .error") }
        XCTAssertEqual(msg, "something broke")
    }

    func testErrorWithStringDataParsed() throws {
        let json = #"{"event":"error","data":"plain error"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .error(let msg) = event else { return XCTFail("Expected .error") }
        XCTAssertEqual(msg, "plain error")
    }

    // MARK: - Unknown / Malformed

    func testUnknownEventReturnsUnknown() throws {
        let json = #"{"event":"future_event","data":{}}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        guard case .unknown = event else { return XCTFail("Expected .unknown") }
    }

    func testMalformedJsonReturnsNil() throws {
        let json = "not json at all".data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }

    func testMissingEventKeyReturnsNil() throws {
        let json = #"{"data":"idle"}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }

    func testEmptyJsonObjectReturnsNil() throws {
        let json = #"{}"#.data(using: .utf8)!
        let event = ServerEvent.parse(json: json)
        XCTAssertNil(event)
    }
}
