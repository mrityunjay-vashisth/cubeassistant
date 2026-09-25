import AppKit

enum Climate: String, CaseIterable {
    case sunny
    case cloudy
    case rainy
    case stormy

    var menuTitle: String {
        switch self {
        case .sunny: return "Sunny ☀️"
        case .cloudy: return "Cloudy ☁️"
        case .rainy: return "Rainy 🌧"
        case .stormy: return "Stormy ⛈"
        }
    }

    /// How solid the cloud shell renders.
    var cloudTransparency: CGFloat {
        switch self {
        case .sunny: return 0.3
        case .cloudy: return 0.95
        case .rainy: return 0.95
        case .stormy: return 1.0
        }
    }

    /// Tint multiplied into the cloud layer.
    var cloudTint: NSColor {
        switch self {
        case .sunny: return .white
        case .cloudy: return NSColor(calibratedWhite: 0.92, alpha: 1)
        case .rainy: return NSColor(calibratedWhite: 0.7, alpha: 1)
        case .stormy: return NSColor(calibratedWhite: 0.45, alpha: 1)
        }
    }

    /// Multipliers on the key/ambient lights while Earth is shown.
    var lightFactor: (key: CGFloat, ambient: CGFloat) {
        switch self {
        case .sunny: return (1.1, 1.15)
        case .cloudy: return (0.85, 0.9)
        case .rainy: return (0.68, 0.75)
        case .stormy: return (0.5, 0.6)
        }
    }

    var rainBirthRate: CGFloat {
        switch self {
        case .sunny, .cloudy: return 0
        case .rainy: return 320
        case .stormy: return 750
        }
    }

    var hasLightning: Bool {
        self == .stormy
    }
}
