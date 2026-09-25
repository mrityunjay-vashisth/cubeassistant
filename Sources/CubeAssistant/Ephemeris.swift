import Foundation

/// Simplified Keplerian ephemeris — good to a degree or two, plenty for a
/// desktop ornament. Mean longitudes at J2000 epoch + mean motion.
enum Ephemeris {
    /// (mean longitude at J2000 in degrees, orbital period in days)
    private static let elements: [Body: (L0: Double, periodDays: Double)] = [
        .mercury: (252.25, 87.969),
        .venus:   (181.98, 224.70),
        .earth:   (100.46, 365.256),
        .mars:    (355.45, 686.98),
        .jupiter: (34.40, 4332.59),
        .saturn:  (49.94, 10759.22),
        .uranus:  (313.23, 30688.5),
        .neptune: (304.88, 60182.0)
    ]

    /// J2000.0 epoch: 2000-01-01 12:00 UTC (close enough to TT for us).
    private static let j2000 = Date(timeIntervalSince1970: 946_728_000)

    static func periodDays(_ body: Body) -> Double? {
        elements[body]?.periodDays
    }

    /// Current heliocentric mean longitude, radians 0..2π.
    static func currentLongitude(_ body: Body, at date: Date = Date()) -> CGFloat? {
        guard let e = elements[body] else { return nil }
        let days = date.timeIntervalSince(j2000) / 86_400
        var deg = (e.L0 + 360.0 / e.periodDays * days).truncatingRemainder(dividingBy: 360)
        if deg < 0 { deg += 360 }
        return CGFloat(deg * .pi / 180)
    }

    /// Moon phase fraction: 0 = new, 0.5 = full, 1 = next new.
    /// Anchored to the new moon of 2000-01-06 18:14 UTC.
    static func moonPhase(at date: Date = Date()) -> Double {
        let newMoonEpoch = Date(timeIntervalSince1970: 947_182_440)
        let synodicMonth = 29.530588853
        var phase = (date.timeIntervalSince(newMoonEpoch) / 86_400 / synodicMonth)
            .truncatingRemainder(dividingBy: 1)
        if phase < 0 { phase += 1 }
        return phase
    }
}
