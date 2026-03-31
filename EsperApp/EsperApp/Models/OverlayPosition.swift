import AppKit

enum OverlayPosition: String, CaseIterable {
    case topLeft, topCenter, topRight
    case bottomLeft, bottomCenter, bottomRight

    private static let horizontalMargin: CGFloat = 40
    private static let verticalMargin: CGFloat = 60

    func origin(panelSize: NSSize, screenFrame: NSRect) -> NSPoint {
        let hMargin = Self.horizontalMargin
        let vMargin = Self.verticalMargin

        let x: CGFloat
        let y: CGFloat

        switch self {
        case .topLeft:
            x = screenFrame.minX + hMargin
            y = screenFrame.maxY - panelSize.height - vMargin
        case .topCenter:
            x = screenFrame.midX - panelSize.width / 2
            y = screenFrame.maxY - panelSize.height - vMargin
        case .topRight:
            x = screenFrame.maxX - panelSize.width - hMargin
            y = screenFrame.maxY - panelSize.height - vMargin
        case .bottomLeft:
            x = screenFrame.minX + hMargin
            y = screenFrame.minY + vMargin
        case .bottomCenter:
            x = screenFrame.midX - panelSize.width / 2
            y = screenFrame.minY + vMargin
        case .bottomRight:
            x = screenFrame.maxX - panelSize.width - hMargin
            y = screenFrame.minY + vMargin
        }

        return NSPoint(x: x, y: y)
    }
}
