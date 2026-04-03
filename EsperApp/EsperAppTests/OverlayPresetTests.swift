import XCTest
import SwiftUI
@testable import EsperApp

final class OverlayPresetTests: XCTestCase {

    func testMinimalValues() {
        let preset = OverlayPreset.minimal
        XCTAssertEqual(preset.textSize, "small")
        XCTAssertEqual(preset.opacity, 0.6, accuracy: 0.01)
        XCTAssertEqual(preset.textColor, "#FFFFFF")
        XCTAssertEqual(preset.maxLines, 2)
    }

    func testPresentationValues() {
        let preset = OverlayPreset.presentation
        XCTAssertEqual(preset.textSize, "large")
        XCTAssertEqual(preset.opacity, 0.95, accuracy: 0.01)
        XCTAssertEqual(preset.textColor, "#FFFFFF")
        XCTAssertEqual(preset.maxLines, 3)
    }

    func testHighContrastValues() {
        let preset = OverlayPreset.highContrast
        XCTAssertEqual(preset.textSize, "medium")
        XCTAssertEqual(preset.opacity, 1.0, accuracy: 0.01)
        XCTAssertEqual(preset.textColor, "#FFD60A")
        XCTAssertEqual(preset.maxLines, 3)
    }

    func testAllCasesExist() {
        let cases: [OverlayPreset] = [.minimal, .presentation, .highContrast, .custom]
        XCTAssertEqual(cases.count, 4)
    }

    func testRawValueRoundTrip() {
        for preset in OverlayPreset.allCases {
            XCTAssertEqual(OverlayPreset(rawValue: preset.rawValue), preset)
        }
    }
}
