import AppKit
import SceneKit
import CoreImage
import GLTFSceneKit

/// Whimsical dress-up for Earth: a drifting NASA cloud layer and
/// cartoonishly oversized 3D trees rooted at forest latitudes.
enum EarthDecor {
    /// NASA's cloud map is white-on-black; convert luminance to alpha so
    /// only the clouds themselves render. Baked to a plain bitmap once —
    /// a live NSCIImageRep would keep the whole Core Image pipeline (and
    /// source JPEG) resident behind the texture.
    static func cloudImage() -> NSImage? {
        guard let url = Bundle.module.url(forResource: "clouds", withExtension: "jpg"),
              let ciImage = CIImage(contentsOf: url),
              let filter = CIFilter(name: "CIMaskToAlpha") else { return nil }
        filter.setValue(ciImage, forKey: kCIInputImageKey)
        guard let output = filter.outputImage,
              let baked = SunArt.ciContext.createCGImage(output, from: output.extent) else { return nil }
        return NSImage(cgImage: baked, size: NSSize(width: output.extent.width, height: output.extent.height))
    }

    /// Semi-transparent cloud shell, slightly above the surface,
    /// drifting slowly relative to the planet's own spin.
    /// Returns the node and its material so climate can restyle it.
    static func cloudLayer(surfaceRadius: CGFloat) -> (node: SCNNode, material: SCNMaterial)? {
        guard let clouds = cloudImage() else { return nil }
        let sphere = SCNSphere(radius: surfaceRadius * 1.045)
        sphere.segmentCount = 36
        let material = SCNMaterial()
        material.diffuse.contents = clouds
        material.transparency = 0.85
        material.lightingModel = .lambert
        material.writesToDepthBuffer = false
        // Fade the shell at grazing angles — otherwise its limb stacks up
        // into a hard white ring drawn around the planet.
        material.shaderModifiers = [
            .fragment: """
            float limb = abs(dot(normalize(_surface.view), normalize(_surface.normal)));
            _output.color *= pow(limb, 0.85);
            """
        ]
        sphere.materials = [material]
        let node = SCNNode(geometry: sphere)
        node.runAction(.repeatForever(.rotateBy(x: 0, y: CGFloat.pi * 2, z: 0, duration: 110)))
        return (node, material)
    }

    enum TreeKind {
        case leafy, pine, palm
    }

    /// Rough forest spots as (latitude, longitude) in degrees.
    private static let groves: [(lat: CGFloat, lon: CGFloat, kind: TreeKind)] = [
        (-4, -62, .leafy),   // Amazon
        (2, 24, .leafy),     // Congo
        (1, 114, .palm),     // Borneo
        (22, 79, .leafy),    // India
        (58, 95, .pine),     // Siberia
        (47, 8, .pine),      // Alps
        (42, -78, .leafy),   // North America
        (-22, 133, .palm),   // Australia
        (64, -110, .pine),   // Canada
        (-9, -150, .palm)    // Pacific island
    ]

    /// Plants proper 3D tree models on a sphere of the given radius,
    /// positioned and oriented to stand on the surface.
    static func trees(surfaceRadius: CGFloat) -> [SCNNode] {
        let templates: [TreeKind: SCNNode?] = [
            .leafy: loadTreeTemplate(resource: "tree_leafy"),
            .pine: loadTreeTemplate(resource: "tree_pine"),
            .palm: loadTreeTemplate(resource: "tree_palm")
        ]

        // A tight cluster of three reads as a little forest; a lone tree
        // sticking off the limb reads as an antenna.
        return groves.flatMap { grove -> [SCNNode] in
            guard let template = templates[grove.kind] ?? nil else { return [] }
            return (0..<3).map { _ in
                let tree = template.clone()
                let variation = CGFloat.random(in: 0.65...1.1)
                tree.scale = SCNVector3(variation, variation, variation)

                let lat = (grove.lat + CGFloat.random(in: -5...5)) * .pi / 180
                let lon = (grove.lon + CGFloat.random(in: -5...5)) * .pi / 180
                let up = simd_float3(
                    Float(cos(lat) * cos(lon)),
                    Float(sin(lat)),
                    Float(cos(lat) * sin(lon))
                )
                tree.simdPosition = up * Float(surfaceRadius * 0.99)
                tree.simdOrientation = simd_quatf(from: simd_float3(0, 1, 0), to: up)
                return tree
            }
        }
    }

    /// Loads a tree GLB and normalizes it: base at y=0, centered,
    /// cartoonishly big but not planet-dwarfing.
    private static func loadTreeTemplate(resource: String) -> SCNNode? {
        guard let url = Bundle.module.url(forResource: resource, withExtension: "glb") else { return nil }
        do {
            let scene = try GLTFSceneSource(url: url).scene()
            let holder = SCNNode()
            for child in scene.rootNode.childNodes {
                holder.addChildNode(child)
            }
            holder.enumerateHierarchy { node, _ in
                for material in node.geometry?.materials ?? [] {
                    // Same treatment as the planets: drop GLTFSceneKit's
                    // injected shader modifier and shade simply.
                    material.shaderModifiers = nil
                    material.lightingModel = .lambert
                    material.metalness.contents = 0.0
                    material.roughness.contents = 0.9
                }
            }
            let (minBox, maxBox) = holder.boundingBox
            let height = CGFloat(maxBox.y - minBox.y)
            guard height > 0 else { return nil }
            let scale = 0.13 / height
            holder.scale = SCNVector3(scale, scale, scale)
            holder.position = SCNVector3(
                -CGFloat(minBox.x + maxBox.x) / 2 * scale,
                -CGFloat(minBox.y) * scale,
                -CGFloat(minBox.z + maxBox.z) / 2 * scale
            )
            let wrapper = SCNNode()
            wrapper.addChildNode(holder)
            return wrapper
        } catch {
            NSLog("Failed to load \(resource).glb: \(error)")
            return nil
        }
    }

    /// Rain: streaks born just under the cloud deck, falling radially onto
    /// the surface and dying exactly on impact — reads as sheets of rain
    /// hugging the planet instead of dust floating in space.
    static func rainSystem(birthRate: CGFloat) -> SCNParticleSystem {
        let rain = SCNParticleSystem()
        rain.birthRate = birthRate
        rain.emitterShape = SCNSphere(radius: 1.02)
        rain.birthLocation = .surface
        rain.birthDirection = .surfaceNormal
        rain.particleVelocity = -0.55
        rain.particleVelocityVariation = 0.1
        // (1.02 - 0.82) / 0.55 ≈ 0.36s from cloud to ground.
        rain.particleLifeSpan = 0.36
        rain.particleLifeSpanVariation = 0.05
        rain.particleSize = 0.02
        rain.stretchFactor = 0.35
        rain.particleColor = NSColor(calibratedRed: 0.65, green: 0.78, blue: 1.0, alpha: 0.55)
        rain.particleColorVariation = SCNVector4(0, 0, 0, 0.2)
        rain.blendMode = .additive
        rain.isLightingEnabled = false
        return rain
    }

    /// Hand-drawn jagged lightning bolt on a transparent background.
    static func boltImage(size: CGFloat = 256) -> NSImage {
        let image = NSImage(size: NSSize(width: size / 2, height: size))
        image.lockFocus()
        let path = NSBezierPath()
        path.lineWidth = size * 0.035
        path.lineJoinStyle = .miter
        var x = size * 0.25
        var y = size
        path.move(to: NSPoint(x: x, y: y))
        // Zigzag downward with narrowing horizontal jitter.
        for step in 1...5 {
            let dy = size / 5.5
            y -= dy
            x += (step % 2 == 0 ? 1 : -1) * size * CGFloat.random(in: 0.05...0.11)
            path.line(to: NSPoint(x: x, y: y))
        }
        NSColor.white.setStroke()
        // Glow pass then core.
        path.lineWidth = size * 0.07
        NSColor(calibratedRed: 0.75, green: 0.85, blue: 1.0, alpha: 0.4).setStroke()
        path.stroke()
        path.lineWidth = size * 0.028
        NSColor.white.setStroke()
        path.stroke()
        image.unlockFocus()
        return image
    }
}
