import Foundation

/// Polls the real-time position of the International Space Station.
/// Public API, no auth: https://wheretheiss.at
final class ISSFetcher {
    private static let url = URL(string: "https://api.wheretheiss.at/v1/satellites/25544")!
    private static let pollInterval: TimeInterval = 10

    /// (latitude, longitude) in degrees.
    var onUpdate: ((Double, Double) -> Void)?
    private var timer: Timer?

    /// When false (Earth not showing, window covered), polling is skipped
    /// so an idle app makes zero network calls for the ISS.
    var isActive = true {
        didSet {
            if isActive && !oldValue {
                fetch()
            }
        }
    }

    func start() {
        fetch()
        timer = Timer.scheduledTimer(withTimeInterval: Self.pollInterval, repeats: true) { [weak self] _ in
            self?.fetch()
        }
        timer?.tolerance = 2
    }

    private func fetch() {
        guard isActive else { return }
        let task = URLSession.shared.dataTask(with: Self.url) { [weak self] data, _, _ in
            guard let self, let data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let lat = json["latitude"] as? Double,
                  let lon = json["longitude"] as? Double else { return }
            DispatchQueue.main.async {
                self.onUpdate?(lat, lon)
            }
        }
        task.resume()
    }
}
