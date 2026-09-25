import AppKit

/// Image helpers for the sun surface.
enum SunArt {
    /// One Core Image context for the whole app — each CIContext carries
    /// its own Metal state, so creating one per call (e.g. every 15-minute
    /// sun refresh) slowly stacks up wasted memory.
    static let ciContext = CIContext()
    /// Soft radial glow for the sun's corona in solar-system mode.
    static func glowImage(color: NSColor, size: CGFloat = 256) -> NSImage {
        let image = NSImage(size: NSSize(width: size, height: size))
        image.lockFocus()
        let center = NSPoint(x: size / 2, y: size / 2)
        if let gradient = NSGradient(colors: [
            color.withAlphaComponent(0.9),
            color.withAlphaComponent(0.25),
            NSColor.clear
        ], atLocations: [0.0, 0.4, 1.0], colorSpace: .deviceRGB) {
            gradient.draw(fromCenter: center, radius: 0, toCenter: center, radius: size / 2, options: [])
        }
        image.unlockFocus()
        return image
    }

    /// One-time exposure lift for textures that ship darker than they
    /// should display (NASA's Blue Marble, notably).
    static func brightened(_ image: NSImage, ev: CGFloat) -> NSImage {
        guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil),
              let filter = CIFilter(name: "CIExposureAdjust") else { return image }
        filter.setValue(CIImage(cgImage: cg), forKey: kCIInputImageKey)
        filter.setValue(ev, forKey: kCIInputEVKey)
        guard let output = filter.outputImage,
              let result = ciContext.createCGImage(output, from: output.extent) else { return image }
        return NSImage(cgImage: result, size: image.size)
    }

    /// Saturn's rings as a flat annulus texture: translucent C ring,
    /// bright B ring, the Cassini division, then the A ring with a hint
    /// of the Encke gap. Drawn as concentric strokes so the bands stay
    /// perfectly smooth at any size.
    static func saturnRingImage(size: CGFloat = 512) -> NSImage {
        let image = NSImage(size: NSSize(width: size, height: size))
        image.lockFocus()
        let center = size / 2
        let step: CGFloat = 0.002
        for fraction in stride(from: CGFloat(0.585), through: 1.0, by: step) {
            let (white, alpha) = ringShade(fraction)
            guard alpha > 0.01 else { continue }
            NSColor(
                calibratedRed: white,
                green: white * 0.955,
                blue: white * 0.875,
                alpha: alpha
            ).setStroke()
            let radius = fraction * center
            let path = NSBezierPath(ovalIn: NSRect(
                x: center - radius, y: center - radius,
                width: radius * 2, height: radius * 2
            ))
            path.lineWidth = step * center * 1.7
            path.stroke()
        }
        image.unlockFocus()
        return image
    }

    /// Brightness and opacity of the ring at a given fraction of the
    /// outer radius (globe surface sits near 0.48).
    private static func ringShade(_ f: CGFloat) -> (white: CGFloat, alpha: CGFloat) {
        // Gentle radial shimmer so the bands aren't laser-flat.
        let ripple = 0.92 + 0.08 * sin(f * 210)
        switch f {
        case ..<0.60: return (0.75, 0.16 * (f - 0.585) / 0.015 * ripple)  // C ring rises
        case ..<0.655: return (0.78, 0.22 * ripple)                        // C ring
        case ..<0.85: return (0.95, 0.9 * ripple)                          // B ring
        case ..<0.872: return (0.85, 0.1)                                  // Cassini division
        case ..<0.945: return (0.9, 0.62 * ripple)                         // A ring
        case ..<0.955: return (0.85, 0.28)                                 // Encke gap
        case ..<0.985: return (0.88, 0.55 * ripple)                        // outer A
        default: return (0.85, 0.55 * max(0, (1.0 - f) / 0.015))           // rim fade
        }
    }

    /// Horizontal white-to-clear gradient for comet trails.
    static func trailImage(size: CGFloat = 128) -> NSImage {
        let image = NSImage(size: NSSize(width: size, height: size / 8))
        image.lockFocus()
        if let gradient = NSGradient(
            starting: NSColor.white.withAlphaComponent(0.9),
            ending: .clear
        ) {
            gradient.draw(in: NSRect(x: 0, y: 0, width: size, height: size / 8), angle: 0)
        }
        image.unlockFocus()
        return image
    }

    /// SDO publishes a head-on photo of the full solar disk. The center of the
    /// disk is a usable patch of surface detail — crop it and let the sphere
    /// wrap it. Also conveniently drops the black corners and caption text.
    /// The raw 171Å channel is a muddy ochre; push exposure and saturation
    /// so the sphere glows molten gold instead of mustard.
    static func surfaceTexture(fromDisk image: NSImage, fraction: CGFloat = 0.5) -> NSImage {
        guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
            return image
        }
        let w = CGFloat(cg.width)
        let h = CGFloat(cg.height)
        let side = min(w, h) * fraction
        let rect = CGRect(x: (w - side) / 2, y: (h - side) / 2, width: side, height: side)
        guard let cropped = cg.cropping(to: rect) else { return image }

        var ciImage = CIImage(cgImage: cropped)
        if let exposure = CIFilter(name: "CIExposureAdjust") {
            exposure.setValue(ciImage, forKey: kCIInputImageKey)
            exposure.setValue(1.2, forKey: kCIInputEVKey)
            ciImage = exposure.outputImage ?? ciImage
        }
        if let controls = CIFilter(name: "CIColorControls") {
            controls.setValue(ciImage, forKey: kCIInputImageKey)
            controls.setValue(1.25, forKey: kCIInputSaturationKey)
            ciImage = controls.outputImage ?? ciImage
        }
        if let boosted = ciContext.createCGImage(ciImage, from: ciImage.extent) {
            return NSImage(cgImage: boosted, size: NSSize(width: side, height: side))
        }
        return NSImage(cgImage: cropped, size: NSSize(width: side, height: side))
    }
}
