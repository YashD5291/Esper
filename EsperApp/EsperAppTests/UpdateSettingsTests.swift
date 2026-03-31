import XCTest
@testable import EsperApp

final class UpdateSettingsTests: XCTestCase {

    func testAppVersionStringIsNotEmpty() {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        XCTAssertNotNil(version)
    }
}
