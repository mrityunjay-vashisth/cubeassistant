import AppKit

/// Pulls the latest full-disk image of the sun from NASA's Solar Dynamics
/// Observatory (AIA 171Å — the iconic gold channel) and refreshes it
/// periodically. Falls back to a bundled snapshot when offline.
final class SunFetcher {
    private static let liveURL = URL(string: "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0171.jpg")!
    private static let refreshInterval: TimeInterval = 15 * 60

    var onUpdate: ((NSImage) -> Void)?
    private var timer: Timer?

    private let cacheURL: URL = {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("CubeAssistant", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        // Channel-specific name so a cached frame from the old red 304Å
        // channel can never resurface.
        return dir.appendingPathComponent("sun-latest-171.jpg")
    }()

    /// Best image available right now, without hitting the network:
    /// last cached download, else the bundled snapshot.
    func bestAvailableImage() -> NSImage? {
        if let cached = NSImage(contentsOf: cacheURL), Self.looksLikeTheSun(cached) {
            return cached
        }
        if let bundled = Bundle.module.url(forResource: "sun171", withExtension: "jpg") {
            return NSImage(contentsOf: bundled)
        }
        return nil
    }

    /// SDO occasionally publishes all-black calibration/data-gap frames.
    /// Reject anything without meaningful brightness.
    private static func looksLikeTheSun(_ image: NSImage) -> Bool {
        guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return false }
        let side = 16
        guard let ctx = CGContext(
            data: nil, width: side, height: side,
            bitsPerComponent: 8, bytesPerRow: side * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return false }
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: side, height: side))
        guard let data = ctx.data else { return false }
        let pixels = data.bindMemory(to: UInt8.self, capacity: side * side * 4)
        var total = 0
        for i in 0..<(side * side) {
            total += Int(pixels[i * 4]) + Int(pixels[i * 4 + 1]) + Int(pixels[i * 4 + 2])
        }
        let average = Double(total) / Double(side * side * 3)
        return average > 10
    }

    func start() {
        fetch()
        timer = Timer.scheduledTimer(withTimeInterval: Self.refreshInterval, repeats: true) { [weak self] _ in
            self?.fetch()
        }
        timer?.tolerance = 120
    }

    private func fetch() {
        let task = URLSession.shared.dataTask(with: Self.liveURL) { [weak self] data, _, _ in
            guard let self, let data, let image = NSImage(data: data),
                  Self.looksLikeTheSun(image) else { return }
            try? data.write(to: self.cacheURL)
            DispatchQueue.main.async {
                self.onUpdate?(image)
            }
        }
        task.resume()
    }
}
