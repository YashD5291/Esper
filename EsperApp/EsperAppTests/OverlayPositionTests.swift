import XCTest
@testable import EsperApp

final class OverlayPositionTests: XCTestCase {

    func testAllCasesHaveRawValues() {
        let cases: [OverlayPosition] = [
            .topLeft, .topCenter, .topRight,
            .bottomLeft, .bottomCenter, .bottomRight
        ]
        let rawValues = cases.map(\.rawValue)
        XCTAssertEqual(rawValues, [
            "topLeft", "topCenter", "topRight",
            "bottomLeft", "bottomCenter", "bottomRight"
        ])
    }

    func testFromRawValueRoundTrips() {
        for position in OverlayPosition.allCases {
            XCTAssertEqual(OverlayPosition(rawValue: position.rawValue), position)
        }
    }

    func testFrameBottomCenter() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.bottomCenter.origin(panelSize: panelSize, screenFrame: screen)
        XCTAssertEqual(origin.x, (1440 - 660) / 2, accuracy: 1)
        XCTAssertEqual(origin.y, 60, accuracy: 1)
    }

    func testFrameTopLeft() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.topLeft.origin(panelSize: panelSize, screenFrame: screen)
        XCTAssertEqual(origin.x, 40, accuracy: 1)
        XCTAssertEqual(origin.y, 900 - 100 - 60, accuracy: 1)
    }

    func testFrameTopRight() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.topRight.origin(panelSize: panelSize, screenFrame: screen)
        XCTAssertEqual(origin.x, 1440 - 660 - 40, accuracy: 1)
        XCTAssertEqual(origin.y, 900 - 100 - 60, accuracy: 1)
    }

    func testFrameBottomLeft() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.bottomLeft.origin(panelSize: panelSize, screenFrame: screen)
        XCTAssertEqual(origin.x, 40, accuracy: 1)
        XCTAssertEqual(origin.y, 60, accuracy: 1)
    }

    func testFrameBottomRight() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.bottomRight.origin(panelSize: panelSize, screenFrame: screen)
        XCTAssertEqual(origin.x, 1440 - 660 - 40, accuracy: 1)
        XCTAssertEqual(origin.y, 60, accuracy: 1)
    }

    func testFrameTopCenter() {
        let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
        let panelSize = NSSize(width: 660, height: 100)
        let origin = OverlayPosition.topCenter.origin(panelSize: panelSize, screenFrame: screen)
        XCTAssertEqual(origin.x, (1440 - 660) / 2, accuracy: 1)
        XCTAssertEqual(origin.y, 900 - 100 - 60, accuracy: 1)
    }
}
