import Foundation

enum Mood {
    case idle
    case thinking
    case happy
    case error

    /// How hard the sun surface glows (no effect on the PBR Earth).
    var emissionIntensity: CGFloat {
        switch self {
        case .idle:     return 1.0
        case .thinking: return 1.4
        case .happy:    return 1.6
        case .error:    return 0.8
        }
    }
}
