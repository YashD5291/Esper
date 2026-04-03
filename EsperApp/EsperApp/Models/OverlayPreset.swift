import Foundation

enum OverlayPreset: String, CaseIterable {
    case minimal
    case presentation
    case highContrast
    case custom

    var textSize: String {
        switch self {
        case .minimal: "small"
        case .presentation: "large"
        case .highContrast: "medium"
        case .custom: "medium"
        }
    }

    var opacity: Double {
        switch self {
        case .minimal: 0.6
        case .presentation: 0.95
        case .highContrast: 1.0
        case .custom: 1.0
        }
    }

    var textColor: String {
        switch self {
        case .minimal: "#FFFFFF"
        case .presentation: "#FFFFFF"
        case .highContrast: "#FFD60A"
        case .custom: "#FFFFFF"
        }
    }

    var maxLines: Int {
        switch self {
        case .minimal: 2
        case .presentation: 3
        case .highContrast: 3
        case .custom: 3
        }
    }

    var displayName: String {
        switch self {
        case .minimal: "Minimal"
        case .presentation: "Presentation"
        case .highContrast: "High Contrast"
        case .custom: "Custom"
        }
    }

    func apply(to settings: AppSettings) {
        guard self != .custom else { return }
        settings.overlayTextSize = textSize
        settings.overlayOpacity = opacity
        settings.overlayTextColor = textColor
        settings.overlayMaxLines = maxLines
        settings.overlayPreset = rawValue
    }
}
