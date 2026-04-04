import XCTest
import SwiftUI
@testable import EsperApp

final class AppSettingsOverlayTests: XCTestCase {

    private let overlayKeys = [
        "overlayEnabled", "overlayPosition",
        "overlayTextSize", "overlayTextColor", "overlayMaxLines",
        "overlayOpacity", "overlayDragX", "overlayDragY",
        "overlayPreset", "overlayShowTelegramStatus", "overlayLockPosition",
        "flowButtonEnabled", "flowButtonX",
        "overlayAutoDismiss", "overlayAutoDismissSeconds",
    ]

    override func setUp() {
        super.setUp()
        for key in overlayKeys {
            UserDefaults.standard.removeObject(forKey: key)
        }
    }

    override func tearDown() {
        for key in overlayKeys {
            UserDefaults.standard.removeObject(forKey: key)
        }
        super.tearDown()
    }

    func testDefaultValues() {
        let settings = AppSettings()
        XCTAssertFalse(settings.overlayEnabled)
        XCTAssertEqual(settings.overlayPosition, "bottomCenter")
        XCTAssertEqual(settings.overlayTextSize, "medium")
        XCTAssertEqual(settings.overlayTextColor, "#FFFFFF")
        XCTAssertEqual(settings.overlayMaxLines, 3)
        XCTAssertEqual(settings.overlayOpacity, 1.0, accuracy: 0.01)
        XCTAssertEqual(settings.overlayPreset, "custom")
        XCTAssertTrue(settings.overlayShowTelegramStatus)
        XCTAssertFalse(settings.overlayLockPosition)
        XCTAssertTrue(settings.flowButtonEnabled)
        XCTAssertEqual(settings.flowButtonX, -1.0, accuracy: 0.01)
        XCTAssertFalse(settings.overlayAutoDismiss)
        XCTAssertEqual(settings.overlayAutoDismissSeconds, 30)
    }

    func testParsedOverlayPosition() {
        let settings = AppSettings()
        settings.overlayPosition = "topLeft"
        XCTAssertEqual(settings.parsedOverlayPosition, .topLeft)
    }

    func testParsedOverlayPositionInvalidFallsBack() {
        let settings = AppSettings()
        settings.overlayPosition = "nonsense"
        XCTAssertEqual(settings.parsedOverlayPosition, .bottomCenter)
    }

    func testOverlayFontSize() {
        let settings = AppSettings()
        settings.overlayTextSize = "small"
        XCTAssertEqual(settings.overlayFontSize, 13)
        settings.overlayTextSize = "medium"
        XCTAssertEqual(settings.overlayFontSize, 15)
        settings.overlayTextSize = "large"
        XCTAssertEqual(settings.overlayFontSize, 22)
    }

    func testParsedOverlayColor() {
        let settings = AppSettings()
        settings.overlayTextColor = "#FF0000"
        let color = settings.parsedOverlayColor
        XCTAssertNotNil(color)
    }

    func testParsedOverlayColorInvalidFallsBackToWhite() {
        let settings = AppSettings()
        settings.overlayTextColor = "not-a-color"
        let resolved = NSColor(settings.parsedOverlayColor)
            .usingColorSpace(.sRGB)!
        let white = NSColor.white
            .usingColorSpace(.sRGB)!
        XCTAssertEqual(resolved.redComponent, white.redComponent, accuracy: 0.01)
        XCTAssertEqual(resolved.greenComponent, white.greenComponent, accuracy: 0.01)
        XCTAssertEqual(resolved.blueComponent, white.blueComponent, accuracy: 0.01)
    }
}
