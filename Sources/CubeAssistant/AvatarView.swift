import AppKit
import SceneKit
import GLTFSceneKit

enum Body: String, CaseIterable {
    case sun
    case mercury
    case venus
    case earth
    case mars
    case jupiter
    case saturn
    case uranus
    case neptune
    case moon
    case system

    static var planets: [Body] {
        [.mercury, .venus, .earth, .mars, .jupiter, .saturn, .uranus, .neptune]
    }

    var menuTitle: String {
        switch self {
        case .sun: return "Sun (Live NASA SDO)"
        case .mercury: return "Mercury"
        case .venus: return "Venus"
        case .earth: return "Earth"
        case .mars: return "Mars"
        case .jupiter: return "Jupiter"
        case .saturn: return "Saturn"
        case .uranus: return "Uranus"
        case .neptune: return "Neptune"
        case .moon: return "Moon (Tonight's Phase)"
        case .system: return "Solar System"
        }
    }

    var statusEmoji: String {
        switch self {
        case .sun: return "☀️"
        case .mercury: return "☿"
        case .venus: return "♀"
        case .earth: return "🌍"
        case .mars: return "🔴"
        case .jupiter: return "🟠"
        case .saturn: return "🪐"
        case .uranus: return "🔵"
        case .neptune: return "🌀"
        case .moon: return "🌙"
        case .system: return "🌌"
        }
    }

    /// Bundled NASA model resource; nil for the live-textured sun
    /// and the composite solar system.
    var glbResource: String? {
        (self == .sun || self == .system) ? nil : rawValue
    }

    /// Axial tilt, degrees. Venus's ~177° flip gives it its retrograde spin;
    /// Uranus famously rolls on its side.
    var tilt: CGFloat {
        switch self {
        case .sun: return 7.25
        case .mercury: return 0.03
        case .venus: return 177.4
        case .earth: return 23.44
        case .mars: return 25.19
        case .jupiter: return 3.13
        case .saturn: return 26.73
        case .uranus: return 97.77
        case .neptune: return 28.32
        case .moon: return 6.68
        case .system: return 0
        }
    }

    /// Seconds per idle revolution (relative feel, not to scale —
    /// the gas giants really are the fastest spinners).
    var dayLength: TimeInterval {
        switch self {
        case .sun: return 45
        case .mercury: return 40
        case .venus: return 50
        case .earth: return 24
        case .mars: return 25
        case .jupiter: return 10
        case .saturn: return 11
        case .uranus: return 17
        case .neptune: return 16
        case .moon: return 55
        case .system: return 400
        }
    }

    /// Per-body light trim for the bright-textured giants. (Earth goes the
    /// other way — its dark texture is brightened at load instead, so the
    /// trees and clouds riding on it aren't blasted by boosted lights.)
    var lightBoost: CGFloat {
        switch self {
        case .jupiter: return 0.58
        case .saturn: return 0.55
        default: return 1.0
        }
    }

    /// Exposure lift applied to the model's own texture at load.
    /// NASA's Blue Marble ships several stops darker than their web
    /// viewer shows it.
    var textureEV: CGFloat {
        self == .earth ? 2.3 : 0
    }

    /// Orientation of each planet's orbital plane in system mode:
    /// (inclination, facing azimuth), in degrees. Deliberately varied —
    /// some horizontal, some steep, Mars fully vertical — so the system
    /// reads as a 3D mobile instead of one flat horizon.
    var orbitPlane: (inclination: CGFloat, azimuth: CGFloat) {
        switch self {
        case .mercury: return (8, 0)
        case .venus:   return (62, 45)
        case .earth:   return (22, 90)
        case .mars:    return (88, 135)
        case .jupiter: return (12, 180)
        case .saturn:  return (48, 225)
        case .uranus:  return (75, 270)
        case .neptune: return (30, 315)
        default:       return (0, 0)
        }
    }

    /// Solar-system-mode layout: orbit radius (compressed log of the real
    /// distances in AU), display radius (compressed real size ratios), and
    /// revolution period following Kepler's pacing — inner planets race,
    /// outer ones crawl.
    var orbit: (radius: CGFloat, size: CGFloat, period: TimeInterval) {
        switch self {
        case .mercury: return (0.40, 0.025, 6)
        case .venus:   return (0.50, 0.038, 9)
        case .earth:   return (0.58, 0.040, 12)
        case .mars:    return (0.68, 0.030, 17)
        case .jupiter: return (1.02, 0.135, 34)
        case .saturn:  return (1.24, 0.115, 50)
        case .uranus:  return (1.50, 0.075, 76)
        case .neptune: return (1.68, 0.073, 100)
        default:       return (0, 0, 1)
        }
    }
}

/// Transparent SceneKit view hosting the celestial body, its mood animations,
/// and click-vs-drag handling for the borderless window.
final class AvatarView: SCNView {
    var clickHandler: (() -> Void)?
    var dropHandler: ((URL) -> Void)?

    /// group (bob/jump/shake) > trackball (user's free rotation) > tilt (axial tilt)
    /// > spin (rotates on axis) > body geometry
    private let groupNode = SCNNode()
    private let trackballNode = SCNNode()
    private let tiltNode = SCNNode()
    private let spinNode = SCNNode()

    private let sunMaterial = SCNMaterial()
    private lazy var sunNode: SCNNode = makeSunNode()
    private var loadedBodies: [Body: SCNNode] = [:]
    private weak var sunlightNode: SCNNode?
    private weak var ambientNode: SCNNode?

    /// System-mode bookkeeping for antics and the rocket.
    private var systemClones: [Body: SCNNode] = [:]
    private weak var systemRoot: SCNNode?

    private var anticsTimer: Timer?
    private var rocketTimers: [Timer] = []
    private var lowPower = false
    private(set) var livePositions = false

    /// Transparent-mode ambience: Earth runs a tiny space program.
    /// The flight itself happens on a desktop-wide overlay, owned by
    /// the app delegate — this view just decides when to launch.
    var ambientRocketHandler: (() -> Void)?
    private var surfaceRocketTimer: Timer?
    private var ambientRockets = false
    private var isSceneSuspended = false

    /// The real ISS, orbiting the Earth avatar at its live position.
    private lazy var issNode: SCNNode = makeISSNode()
    private var issHasFix = false

    /// Earth climate styling.
    private(set) var climate: Climate = .sunny
    private weak var cloudMaterial: SCNMaterial?
    private weak var earthWrapper: SCNNode?
    private weak var rainHost: SCNNode?
    private var lightningTimer: Timer?

    private(set) var body: Body = .earth
    private(set) var mood: Mood = .idle
    /// Speed multipliers for axis spin and orbital motion.
    private(set) var rotationRate: Double = 1
    private(set) var revolutionRate: Double = 1
    private var moodResetTimer: Timer?

    private var mouseDownPoint: NSPoint = .zero
    private var didDrag = false
    private var lastDragPoint: NSPoint = .zero
    private var lastDragTime: TimeInterval = 0
    private var flickAxis = simd_float3(0, 1, 0)
    private var flickSpeed: Float = 0        // radians/second
    private var inertiaTimer: Timer?

    /// Radians of rotation per pixel of drag.
    private static let spinPerPixel: Float = 0.012

    /// Ambient motion coasts at 24fps; direct manipulation (drag, pinch,
    /// flick inertia) gets the full 60 so it feels glued to the finger.
    private static let idleFPS = 24
    private static let interactiveFPS = 60

    init() {
        super.init(frame: .zero, options: nil)
        backgroundColor = .clear
        allowsCameraControl = false
        // Always-running app: cap the frame rate and keep AA cheap.
        preferredFramesPerSecond = Self.idleFPS
        antialiasingMode = .multisampling2X
        rendersContinuously = false
        setupScene()
        registerForDraggedTypes([.fileURL])
        scheduleNextAntic()
    }

    /// Fully suspend animation and rendering (window occluded, screen asleep).
    func setSuspended(_ suspended: Bool) {
        isSceneSuspended = suspended
        scene?.isPaused = suspended
        isPlaying = !suspended
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("not supported") }

    private func setupScene() {
        let scene = SCNScene()
        scene.background.contents = NSColor.clear
        self.scene = scene

        scene.rootNode.addChildNode(groupNode)
        groupNode.addChildNode(trackballNode)
        trackballNode.addChildNode(tiltNode)
        tiltNode.addChildNode(spinNode)

        let cameraNode = SCNNode()
        cameraNode.camera = SCNCamera()
        cameraNode.position = SCNVector3(0, 0, 3.1)
        scene.rootNode.addChildNode(cameraNode)

        // Headlight rig, like NASA's own model viewer: the key light points
        // with the camera so the hemisphere you see is always lit, rolling
        // off naturally at the limb — 3D depth without a day/night split.
        let sunlight = SCNNode()
        sunlight.light = SCNLight()
        sunlight.light?.type = .directional
        sunlight.light?.intensity = 1700
        sunlight.eulerAngles = SCNVector3(-0.15, 0.2, 0)
        scene.rootNode.addChildNode(sunlight)
        sunlightNode = sunlight

        let ambient = SCNNode()
        ambient.light = SCNLight()
        ambient.light?.type = .ambient
        ambient.light?.intensity = 260
        scene.rootNode.addChildNode(ambient)
        ambientNode = ambient
    }

    private func makeSunNode() -> SCNNode {
        let sphere = SCNSphere(radius: 0.82)
        sphere.segmentCount = 48
        sunMaterial.lightingModel = .constant
        sunMaterial.emission.intensity = 1.0
        sphere.materials = [sunMaterial]
        return SCNNode(geometry: sphere)
    }

    /// Loads a bundled NASA model (.glb via GLTFSceneKit, .usdz natively)
    /// and normalizes it to radius 0.82 centered at the origin.
    private func loadModelNode(resource: String, textureEV: CGFloat = 0) -> SCNNode? {
        let holder = SCNNode()
        if let url = Bundle.module.url(forResource: resource, withExtension: "glb") {
            do {
                let scene = try GLTFSceneSource(url: url).scene()
                for child in scene.rootNode.childNodes {
                    holder.addChildNode(child)
                }
            } catch {
                NSLog("Failed to load \(resource).glb: \(error)")
                return nil
            }
        } else if let url = Bundle.module.url(forResource: resource, withExtension: "usdz"),
                  let scene = try? SCNScene(url: url, options: nil) {
            for child in scene.rootNode.childNodes {
                holder.addChildNode(child)
            }
        } else {
            NSLog("Missing bundled resource for \(resource)")
            return nil
        }

        // Lambert, not PBR: SceneKit's ambient light does nothing for
        // physically based materials, which left the dark-textured planets
        // murky no matter the rig. Lambert matches NASA's own viewer look
        // and is cheaper to shade every frame.
        holder.enumerateHierarchy { node, _ in
            for material in node.geometry?.materials ?? [] {
                // Some NASA exports arrive effectively unlit — the surface
                // photo sits in the emission slot, so no light rig has any
                // effect. Move it to diffuse so lighting actually shapes
                // the ball, and kill leftover glow.
                let emissionIsTexture = material.emission.contents != nil
                    && !(material.emission.contents is NSColor)
                let diffuseIsTexture = material.diffuse.contents != nil
                    && !(material.diffuse.contents is NSColor)
                if emissionIsTexture {
                    if !diffuseIsTexture {
                        material.diffuse.contents = material.emission.contents
                    }
                    material.emission.contents = NSColor.black
                }
                // GLTFSceneKit injects its own surface shader modifier that
                // overrides every property set here — strip it or none of
                // this (nor any light rig) has any effect.
                material.shaderModifiers = nil
                material.lightingModel = .lambert
                material.metalness.contents = 0.0
                material.roughness.contents = 0.9
                if textureEV != 0, let image = material.diffuse.contents as? NSImage {
                    material.diffuse.contents = SunArt.brightened(image, ev: textureEV)
                }
            }
        }

        // NASA models come in arbitrary units — normalize to our radius.
        // Saturn is centered and scaled by its globe instead of its bounds,
        // because the replacement rings stretch far beyond the ball.
        var anchorCenter: SCNVector3
        var anchorScale: CGFloat
        if resource == "saturn", let globe = replaceSaturnRings(in: holder) {
            anchorCenter = globe.center
            anchorScale = 0.55 / globe.radius
        } else {
            let (center, radius) = holder.boundingSphere
            guard radius > 0 else {
                NSLog("\(resource) loaded but has no visible geometry")
                return nil
            }
            anchorCenter = center
            anchorScale = 0.82 / CGFloat(radius)
        }
        holder.scale = SCNVector3(anchorScale, anchorScale, anchorScale)
        holder.position = SCNVector3(
            -CGFloat(anchorCenter.x) * anchorScale,
            -CGFloat(anchorCenter.y) * anchorScale,
            -CGFloat(anchorCenter.z) * anchorScale
        )
        let wrapper = SCNNode()
        wrapper.addChildNode(holder)
        return wrapper
    }

    /// NASA's Saturn USDZ ring sheet imports with broken UVs in SceneKit
    /// and draws as a circle of chevron dashes. Hide it and lay a smooth
    /// hand-drawn annulus in the equatorial plane instead.
    /// Returns the globe's center and radius in holder space.
    private func replaceSaturnRings(in holder: SCNNode) -> (center: SCNVector3, radius: CGFloat)? {
        var globeCenter = SCNVector3Zero
        var globeRadius: CGFloat = 0
        holder.enumerateHierarchy { node, _ in
            guard node.geometry != nil else { return }
            let (minBox, maxBox) = node.boundingBox
            let extents = [maxBox.x - minBox.x, maxBox.y - minBox.y, maxBox.z - minBox.z]
            guard let thin = extents.min(), let wide = extents.max(), wide > 0 else { return }
            if thin / wide < 0.05 {
                node.isHidden = true
                return
            }
            let sphere = node.boundingSphere
            let centerInHolder = holder.convertPosition(sphere.center, from: node)
            let edgeInHolder = holder.convertPosition(
                SCNVector3(sphere.center.x + CGFloat(sphere.radius), sphere.center.y, sphere.center.z),
                from: node
            )
            let radiusInHolder = CGFloat(hypot(
                Double(edgeInHolder.x - centerInHolder.x),
                hypot(Double(edgeInHolder.y - centerInHolder.y), Double(edgeInHolder.z - centerInHolder.z))
            ))
            if radiusInHolder > globeRadius {
                globeRadius = radiusInHolder
                globeCenter = centerInHolder
            }
        }
        guard globeRadius > 0 else { return nil }

        let outer = globeRadius * 2.1
        let plane = SCNPlane(width: outer * 2, height: outer * 2)
        let material = SCNMaterial()
        material.diffuse.contents = SunArt.saturnRingImage()
        // Self-lit: the flat ring catches the key light at a grazing angle
        // and would render as a pale ghost under lambert.
        material.lightingModel = .constant
        material.isDoubleSided = true
        material.writesToDepthBuffer = false
        plane.materials = [material]
        let rings = SCNNode(geometry: plane)
        rings.position = globeCenter
        rings.eulerAngles.x = -.pi / 2
        rings.renderingOrder = 1
        holder.addChildNode(rings)
        return (globeCenter, globeRadius)
    }

    private func loadedBody(_ body: Body) -> SCNNode? {
        guard let resource = body.glbResource else { return nil }
        if loadedBodies[body] == nil {
            let node = loadModelNode(resource: resource, textureEV: body.textureEV)
            // Earth gets the whimsy treatment: clouds and cartoon trees
            // ride along on the model so they spin with the surface.
            if body == .earth, let node {
                if let clouds = EarthDecor.cloudLayer(surfaceRadius: 0.82) {
                    node.addChildNode(clouds.node)
                    cloudMaterial = clouds.material
                }
                // Individual nodes on purpose: flattenedClone drops the
                // nested normalization scale on cloned subtrees and renders
                // raw-size trunks.
                for tree in EarthDecor.trees(surfaceRadius: 0.82) {
                    node.addChildNode(tree)
                }
                earthWrapper = node
            }
            loadedBodies[body] = node
        }
        return loadedBodies[body]
    }

    /// The whole solar system: glowing live-textured sun with a corona,
    /// eight planets revolving on inclined orbits while spinning on their
    /// axes, an asteroid belt, and a twinkling starfield.
    private func makeSystemNode() -> SCNNode {
        let system = SCNNode()
        systemClones.removeAll()
        // Keep the outermost orbit safely inside the camera frustum so
        // Uranus/Neptune never get sliced off at the window edge.
        system.scale = SCNVector3(0.8, 0.8, 0.8)


        // Sun with a gentle breathing pulse.
        let sun = sunNode.clone()
        let sunScale: CGFloat = 0.30
        sun.scale = SCNVector3(sunScale, sunScale, sunScale)
        let grow = SCNAction.scale(to: sunScale * 1.06, duration: 2.2)
        grow.timingMode = .easeInEaseOut
        let shrink = SCNAction.scale(to: sunScale, duration: 2.2)
        shrink.timingMode = .easeInEaseOut
        sun.runAction(.repeatForever(.sequence([grow, shrink])))
        system.addChildNode(sun)

        // Corona: additive billboard glow behind the sun.
        let coronaPlane = SCNPlane(width: 0.85, height: 0.85)
        let coronaMaterial = SCNMaterial()
        coronaMaterial.diffuse.contents = SunArt.glowImage(
            color: NSColor(calibratedRed: 1.0, green: 0.72, blue: 0.28, alpha: 0.7)
        )
        coronaMaterial.lightingModel = .constant
        coronaMaterial.blendMode = .add
        coronaMaterial.writesToDepthBuffer = false
        coronaPlane.materials = [coronaMaterial]
        let corona = SCNNode(geometry: coronaPlane)
        corona.constraints = [SCNBillboardConstraint()]
        corona.renderingOrder = -1
        system.addChildNode(corona)

        // Faint guide rings tracing the orbits — this is what turns
        // "floating marbles" into a readable orrery. All eight circles
        // share one line geometry: a single draw call.
        system.addChildNode(orbitRingsNode())

        for planet in Body.planets {
            let (orbitRadius, size, period) = planet.orbit

            guard let template = loadedBody(planet) else { continue }

            // Each planet gets its own orbital plane orientation — except in
            // live mode, where real positions demand the real (flat) ecliptic.
            let orbitPlane = SCNNode()
            if !livePositions {
                let (inclination, azimuth) = planet.orbitPlane
                orbitPlane.simdOrientation =
                    simd_quatf(angle: Float(azimuth * .pi / 180), axis: simd_float3(0, 1, 0)) *
                    simd_quatf(angle: Float(inclination * .pi / 180), axis: simd_float3(1, 0, 0))
            }
            system.addChildNode(orbitPlane)

            let orbitNode = SCNNode()
            if livePositions, let longitude = Ephemeris.currentLongitude(planet) {
                orbitNode.eulerAngles.y = longitude
            } else {
                orbitNode.eulerAngles.y = CGFloat.random(in: 0...(2 * .pi))
            }
            orbitPlane.addChildNode(orbitNode)

            let holder = SCNNode()
            holder.position = SCNVector3(orbitRadius, 0, 0)
            orbitNode.addChildNode(holder)

            let tilt = SCNNode()
            tilt.eulerAngles = SCNVector3(0, 0, -planet.tilt * CGFloat.pi / 180)
            holder.addChildNode(tilt)

            let spin = SCNNode()
            tilt.addChildNode(spin)

            let clone = template.clone()
            // Saturn's template is normalized by its globe (0.55), the rest
            // by their bounds (0.82).
            let s = size / (planet == .saturn ? 0.55 : 0.82)
            clone.scale = SCNVector3(s, s, s)
            spin.addChildNode(clone)
            systemClones[planet] = holder

            // Rotation on its own axis + revolution around the sun.
            // Live mode revolves at the true rate (imperceptible at 1×,
            // crank Revolution Speed to fast-forward the actual sky).
            let orbitDuration: TimeInterval
            if livePositions, let days = Ephemeris.periodDays(planet) {
                orbitDuration = days * 86_400 / revolutionRate
            } else {
                orbitDuration = period / revolutionRate
            }
            spin.runAction(.repeatForever(.rotateBy(
                x: 0, y: CGFloat.pi * 2, z: 0, duration: planet.dayLength / 4 / rotationRate
            )))
            orbitNode.runAction(.repeatForever(.rotateBy(
                x: 0, y: CGFloat.pi * 2, z: 0, duration: orbitDuration
            )))
        }

        // Asteroid belt between Mars and Jupiter.
        var beltPoints: [SCNVector3] = []
        for _ in 0..<600 {
            let angle = CGFloat.random(in: 0...(2 * .pi))
            let r = CGFloat.random(in: 0.78...0.90)
            beltPoints.append(SCNVector3(
                r * cos(angle),
                CGFloat.random(in: -0.008...0.008),
                r * sin(angle)
            ))
        }
        let belt = pointCloudNode(
            points: beltPoints,
            color: NSColor(calibratedWhite: 0.65, alpha: 0.55),
            pointSize: 1.5
        )
        belt.runAction(.repeatForever(.rotateBy(x: 0, y: CGFloat.pi * 2, z: 0, duration: 90 / revolutionRate)))
        system.addChildNode(belt)

        // Twinkling starfield shell around everything.
        var starPoints: [SCNVector3] = []
        for _ in 0..<420 {
            let theta = CGFloat.random(in: 0...(2 * .pi))
            let z = CGFloat.random(in: -1.0...1.0)
            let r: CGFloat = 2.3
            let s = sqrt(max(0, 1 - z * z))
            starPoints.append(SCNVector3(r * s * cos(theta), r * z, r * s * sin(theta)))
        }
        let stars = pointCloudNode(
            points: starPoints,
            color: NSColor(calibratedWhite: 1.0, alpha: 0.9),
            pointSize: 2.0
        )
        let dim = SCNAction.fadeOpacity(to: 0.45, duration: 1.8)
        dim.timingMode = .easeInEaseOut
        let brighten = SCNAction.fadeOpacity(to: 1.0, duration: 1.8)
        brighten.timingMode = .easeInEaseOut
        stars.runAction(.repeatForever(.sequence([dim, brighten])))
        stars.runAction(.repeatForever(.rotateBy(x: 0, y: -CGFloat.pi * 2, z: 0, duration: 600)))
        system.addChildNode(stars)

        systemRoot = system
        return system
    }

    // MARK: - ISS

    /// A stylized-but-recognizable station: central truss, twin modules,
    /// four blue solar wings. Slightly emissive so it reads at small size.
    private func makeISSNode() -> SCNNode {
        let iss = SCNNode()

        let trussGeometry = SCNCylinder(radius: 0.004, height: 0.09)
        trussGeometry.firstMaterial?.diffuse.contents = NSColor(calibratedWhite: 0.85, alpha: 1)
        trussGeometry.firstMaterial?.emission.contents = NSColor(calibratedWhite: 0.3, alpha: 1)
        let truss = SCNNode(geometry: trussGeometry)
        truss.eulerAngles.z = .pi / 2
        iss.addChildNode(truss)

        for x in [-0.012, 0.012] {
            let moduleGeometry = SCNCylinder(radius: 0.007, height: 0.035)
            moduleGeometry.firstMaterial?.diffuse.contents = NSColor(calibratedWhite: 0.9, alpha: 1)
            moduleGeometry.firstMaterial?.emission.contents = NSColor(calibratedWhite: 0.35, alpha: 1)
            let module = SCNNode(geometry: moduleGeometry)
            module.position = SCNVector3(x, 0, 0)
            module.eulerAngles.x = .pi / 2
            iss.addChildNode(module)
        }

        let panelColor = NSColor(calibratedRed: 0.2, green: 0.3, blue: 0.6, alpha: 1)
        for x in [-0.038, -0.028, 0.028, 0.038] {
            let panelGeometry = SCNBox(width: 0.008, height: 0.001, length: 0.045, chamferRadius: 0)
            panelGeometry.firstMaterial?.diffuse.contents = panelColor
            panelGeometry.firstMaterial?.emission.contents = panelColor.withAlphaComponent(0.5)
            let panel = SCNNode(geometry: panelGeometry)
            panel.position = SCNVector3(x, 0, 0)
            iss.addChildNode(panel)
        }
        // Cartoon scale — the real proportion would be an invisible speck.
        iss.scale = SCNVector3(3.2, 3.2, 3.2)
        return iss
    }

    /// Live position update. The station rides above the (non-spinning)
    /// tilt frame, gliding to each new fix over the poll interval.
    func updateISS(latitude: Double, longitude: Double) {
        guard body == .earth else { return }
        if issNode.parent == nil {
            tiltNode.addChildNode(issNode)
        }
        let lat = CGFloat(latitude) * .pi / 180
        let lon = CGFloat(longitude) * .pi / 180
        let up = simd_float3(
            Float(cos(lat) * cos(lon)),
            Float(sin(lat)),
            Float(cos(lat) * sin(lon))
        )
        let target = up * Float(0.82 * 1.32)
        issNode.simdOrientation = simd_quatf(from: simd_float3(0, 1, 0), to: up)
        if issHasFix {
            let glide = SCNAction.move(to: SCNVector3(target), duration: 10)
            issNode.runAction(glide, forKey: "issGlide")
        } else {
            issNode.simdPosition = target
            issHasFix = true
        }
    }

    // MARK: - Climate

    func setClimate(_ newClimate: Climate) {
        climate = newClimate
        if body == .earth {
            setBody(.earth)   // re-applies lighting + effects
        } else {
            applyClimateEffects()
        }
    }

    private func applyClimateEffects() {
        cloudMaterial?.transparency = climate.cloudTransparency
        cloudMaterial?.multiply.contents = climate.cloudTint

        // Rain lives on the earth wrapper so it follows the planet.
        rainHost?.removeFromParentNode()
        lightningTimer?.invalidate()
        lightningTimer = nil
        guard body == .earth, let earthWrapper else { return }

        if climate.rainBirthRate > 0 {
            let host = SCNNode()
            host.addParticleSystem(EarthDecor.rainSystem(birthRate: climate.rainBirthRate))
            earthWrapper.addChildNode(host)
            rainHost = host
        }
        if climate.hasLightning {
            scheduleLightning()
        }
    }

    private func scheduleLightning() {
        lightningTimer = Timer.scheduledTimer(withTimeInterval: .random(in: 2.5...8), repeats: false) { [weak self] _ in
            self?.lightningFlash()
            self?.scheduleLightning()
        }
        lightningTimer?.tolerance = 1
    }

    private func lightningFlash() {
        guard let light = ambientNode?.light else { return }
        let original = light.intensity
        let flash = { (delay: TimeInterval, value: CGFloat) in
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { light.intensity = value }
        }
        flash(0, 1600)
        flash(0.08, original)
        flash(0.16, 1300)
        flash(0.26, original)

        // A visible bolt strikes from the cloud deck to the surface,
        // somewhere on the facing hemisphere.
        guard let earthWrapper else { return }
        let boltPlane = SCNPlane(width: 0.16, height: 0.32)
        let material = SCNMaterial()
        material.diffuse.contents = EarthDecor.boltImage()
        material.lightingModel = .constant
        material.blendMode = .add
        material.isDoubleSided = true
        material.writesToDepthBuffer = false
        boltPlane.materials = [material]
        let bolt = SCNNode(geometry: boltPlane)

        // Random spot facing the camera-ish: longitude biased to front.
        let lat = CGFloat.random(in: -0.9...0.9)
        let lon = CGFloat.random(in: -0.8...0.8)
        let up = simd_float3(
            Float(cos(lat) * sin(lon)),
            Float(sin(lat)),
            Float(cos(lat) * cos(lon))
        )
        bolt.simdPosition = up * 0.97
        bolt.simdOrientation = simd_quatf(from: simd_float3(0, 1, 0), to: up)
        bolt.opacity = 0
        earthWrapper.addChildNode(bolt)
        bolt.runAction(.sequence([
            .fadeIn(duration: 0.03),
            .wait(duration: 0.09),
            .fadeOut(duration: 0.05),
            .wait(duration: 0.05),
            .fadeIn(duration: 0.02),
            .wait(duration: 0.06),
            .fadeOut(duration: 0.12),
            .removeFromParentNode()
        ]))
    }

    func setLivePositions(_ on: Bool) {
        livePositions = on
        if body == .system {
            setBody(.system)
        }
    }

    /// Every orbit's guide circle, pre-rotated into its plane and merged
    /// into a single line geometry.
    private func orbitRingsNode() -> SCNNode {
        let segments = 96
        var points: [SCNVector3] = []
        var indices: [Int32] = []
        for planet in Body.planets {
            let radius = Float(planet.orbit.radius)
            var orientation = simd_quatf(angle: 0, axis: simd_float3(0, 1, 0))
            if !livePositions {
                let (inclination, azimuth) = planet.orbitPlane
                orientation =
                    simd_quatf(angle: Float(azimuth * .pi / 180), axis: simd_float3(0, 1, 0)) *
                    simd_quatf(angle: Float(inclination * .pi / 180), axis: simd_float3(1, 0, 0))
            }
            let base = Int32(points.count)
            for i in 0...segments {
                let angle = Float(i) / Float(segments) * 2 * .pi
                let point = orientation.act(simd_float3(cos(angle) * radius, 0, sin(angle) * radius))
                points.append(SCNVector3(point))
                if i < segments {
                    indices.append(base + Int32(i))
                    indices.append(base + Int32(i) + 1)
                }
            }
        }
        let source = SCNGeometrySource(vertices: points)
        let data = Data(bytes: &indices, count: indices.count * MemoryLayout<Int32>.size)
        let element = SCNGeometryElement(
            data: data,
            primitiveType: .line,
            primitiveCount: indices.count / 2,
            bytesPerIndex: MemoryLayout<Int32>.size
        )
        let geometry = SCNGeometry(sources: [source], elements: [element])
        let material = SCNMaterial()
        material.diffuse.contents = NSColor(calibratedWhite: 1.0, alpha: 0.16)
        material.lightingModel = .constant
        material.writesToDepthBuffer = false
        geometry.materials = [material]
        return SCNNode(geometry: geometry)
    }

    /// Tiny dots rendered as screen-space points (asteroids, stars).
    private func pointCloudNode(points: [SCNVector3], color: NSColor, pointSize: CGFloat) -> SCNNode {
        let source = SCNGeometrySource(vertices: points)
        var indices = Array(0..<Int32(points.count))
        let data = Data(bytes: &indices, count: indices.count * MemoryLayout<Int32>.size)
        let element = SCNGeometryElement(
            data: data,
            primitiveType: .point,
            primitiveCount: points.count,
            bytesPerIndex: MemoryLayout<Int32>.size
        )
        element.pointSize = pointSize
        element.minimumPointScreenSpaceRadius = 0.5
        element.maximumPointScreenSpaceRadius = pointSize
        let geometry = SCNGeometry(sources: [source], elements: [element])
        let material = SCNMaterial()
        material.diffuse.contents = color
        material.lightingModel = .constant
        geometry.materials = [material]
        return SCNNode(geometry: geometry)
    }

    // MARK: - Body switching

    func setBody(_ newBody: Body) {
        spinNode.childNodes.forEach { $0.removeFromParentNode() }

        switch newBody {
        case .system:
            spinNode.addChildNode(makeSystemNode())
            body = .system
        case .sun:
            spinNode.addChildNode(sunNode)
            body = .sun
        default:
            if let node = loadedBody(newBody) {
                spinNode.addChildNode(node)
                body = newBody
            } else {
                // Model failed to load — fall back to the sun.
                spinNode.addChildNode(sunNode)
                body = .sun
            }
        }

        if body == .system {
            // Shallow viewing angle: planets visibly pass in front of and
            // behind the sun instead of circling a flat diagram.
            tiltNode.eulerAngles = SCNVector3(-0.45, 0, 0)
        } else {
            // A pure screen-plane roll keeps Saturn's rings edge-on to the
            // camera forever — pitch it toward the viewer so they open up.
            let pitch: CGFloat = body == .saturn ? 0.42 : 0
            tiltNode.eulerAngles = SCNVector3(pitch, 0, -body.tilt * CGFloat.pi / 180)
        }

        // Lighting per mode: the system is lit by its own sun; the moon is
        // lit from the direction matching tonight's real phase.
        switch body {
        case .system:
            sunlightNode?.eulerAngles = SCNVector3(-0.15, 0.2, 0)
            sunlightNode?.light?.intensity = 1700
            ambientNode?.light?.intensity = 300
        case .moon:
            let phase = Ephemeris.moonPhase()
            // 0 = light from behind (new), 0.5 = light from the viewer (full).
            sunlightNode?.eulerAngles = SCNVector3(0, CGFloat((0.5 - phase) * 2 * .pi), 0)
            sunlightNode?.light?.intensity = 1400
            // Earthshine, exaggerated: near new moon the disk should read
            // as a dim grey moon, not a black hole in the desktop.
            ambientNode?.light?.intensity = 290
        default:
            sunlightNode?.eulerAngles = SCNVector3(-0.15, 0.2, 0)
            var key: CGFloat = 1700 * body.lightBoost
            var fill: CGFloat = 260 * body.lightBoost
            if body == .earth {
                key *= climate.lightFactor.key
                fill *= climate.lightFactor.ambient
            }
            sunlightNode?.light?.intensity = key
            ambientNode?.light?.intensity = fill
        }
        applyClimateEffects()

        // Evict cached models we're no longer showing — planet GLBs carry
        // multi-megabyte textures and this app runs forever.
        if body != .system {
            loadedBodies = loadedBodies.filter { $0.key == body }
        }

        // The ISS only orbits the full-size Earth.
        if body != .earth {
            issNode.removeFromParentNode()
            issHasFix = false
        }

        updateSurfaceRocketTimer()

        // Hourly rocket launches only make sense with a system to fly in.
        rocketTimers.forEach { $0.invalidate() }
        rocketTimers.removeAll()
        if body == .system {
            rocketTimers.append(Timer.scheduledTimer(withTimeInterval: 120, repeats: false) { [weak self] _ in
                self?.launchRocket()
            })
            rocketTimers.append(Timer.scheduledTimer(withTimeInterval: 3600, repeats: true) { [weak self] _ in
                self?.launchRocket()
            })
            rocketTimers.forEach { $0.tolerance = 60 }
        }

        setMood(.idle)
    }

    // MARK: - Live NASA sun texture

    func setSunImage(_ diskImage: NSImage) {
        let texture = SunArt.surfaceTexture(fromDisk: diskImage)
        sunMaterial.diffuse.contents = texture
        sunMaterial.emission.contents = texture
    }

    // MARK: - Moods

    func setMood(_ newMood: Mood) {
        moodResetTimer?.invalidate()
        mood = newMood

        sunMaterial.emission.intensity = newMood.emissionIntensity * (lowPower ? 0.7 : 1)

        groupNode.removeAllActions()
        stopInertia()
        spinNode.removeAllActions()
        groupNode.position = SCNVector3Zero
        groupNode.orientation = SCNQuaternion(0, 0, 0, 1)

        // The body always keeps turning on its axis; moods change the pace.
        runAxisSpin()
        if let motion = groupMotion(for: newMood) {
            groupNode.runAction(motion)
        }

        // Happy and error are transient — settle back to idle.
        if newMood == .happy || newMood == .error {
            moodResetTimer = Timer.scheduledTimer(withTimeInterval: 2.5, repeats: false) { [weak self] _ in
                self?.setMood(.idle)
            }
        }
    }

    private func runAxisSpin() {
        spinNode.runAction(
            .repeatForever(.rotateBy(x: 0, y: CGFloat.pi * 2, z: 0, duration: spinDuration(for: mood))),
            forKey: "axisSpin"
        )
    }

    func setRates(rotation: Double, revolution: Double) {
        rotationRate = max(rotation, 0.01)
        revolutionRate = max(revolution, 0.01)
        setBody(body)
    }

    private func spinDuration(for mood: Mood) -> TimeInterval {
        // The system's idle turn is orbital drift, not axis spin.
        let rate = body == .system ? revolutionRate : rotationRate
        let tired: Double = lowPower ? 2.5 : 1
        switch mood {
        case .idle:     return body.dayLength * tired / rate
        case .thinking: return 1.4
        case .happy:    return 5
        case .error:    return body.dayLength * 2 / rate
        }
    }

    /// Low battery: droop a little, spin slower, glow dimmer.
    func setLowPower(_ low: Bool) {
        guard low != lowPower else { return }
        lowPower = low
        setMood(mood)
    }

    private func groupMotion(for mood: Mood) -> SCNAction? {
        switch mood {
        case .idle:
            if lowPower {
                let droop = SCNAction.moveBy(x: 0, y: -0.09, z: 0, duration: 1.2)
                droop.timingMode = .easeOut
                return droop
            }
            let bobUp = SCNAction.moveBy(x: 0, y: 0.06, z: 0, duration: 1.8)
            bobUp.timingMode = .easeInEaseOut
            return .repeatForever(.sequence([bobUp, bobUp.reversed()]))
        case .thinking:
            return nil
        case .happy:
            let jump = SCNAction.moveBy(x: 0, y: 0.25, z: 0, duration: 0.18)
            jump.timingMode = .easeOut
            let land = jump.reversed()
            land.timingMode = .easeIn
            return .sequence([jump, land, jump, land])
        case .error:
            let right = SCNAction.moveBy(x: 0.12, y: 0, z: 0, duration: 0.05)
            let left = SCNAction.moveBy(x: -0.24, y: 0, z: 0, duration: 0.1)
            let center = SCNAction.moveBy(x: 0.12, y: 0, z: 0, duration: 0.05)
            return .repeat(.sequence([right, left, center]), count: 5)
        }
    }

    // MARK: - Idle antics

    private func scheduleNextAntic() {
        anticsTimer?.invalidate()
        anticsTimer = Timer.scheduledTimer(withTimeInterval: .random(in: 150...360), repeats: false) { [weak self] _ in
            self?.performRandomAntic()
            self?.scheduleNextAntic()
        }
        anticsTimer?.tolerance = 30
    }

    private func performRandomAntic() {
        guard mood == .idle, window?.isVisible == true else { return }
        var antics: [() -> Void] = [anticWobble, anticComet]
        if body == .sun || body == .system { antics.append(anticSolarFlare) }
        if body == .mars || (body == .system && systemClones[.mars] != nil) { antics.append(anticBarrelRoll) }
        antics.randomElement()?()
    }

    private func anticWobble() {
        let rock = SCNAction.sequence([
            .rotateBy(x: 0, y: 0, z: 0.18, duration: 0.14),
            .rotateBy(x: 0, y: 0, z: -0.36, duration: 0.28),
            .rotateBy(x: 0, y: 0, z: 0.18, duration: 0.14)
        ])
        groupNode.runAction(.repeat(rock, count: 2))
    }

    private func anticSolarFlare() {
        let spike = CABasicAnimation(keyPath: "emission.intensity")
        spike.fromValue = sunMaterial.emission.intensity
        spike.toValue = sunMaterial.emission.intensity * 2.0
        spike.duration = 0.35
        spike.autoreverses = true
        sunMaterial.addAnimation(spike, forKey: "flare")
    }

    private func anticBarrelRoll() {
        let target = body == .system ? systemClones[.mars] : spinNode
        target?.runAction(.rotateBy(x: 0, y: 0, z: CGFloat.pi * 2, duration: 1.1))
    }

    private func anticComet() {
        guard let scene else { return }
        let comet = SCNNode()
        let head = SCNSphere(radius: 0.016)
        head.firstMaterial?.diffuse.contents = NSColor.white
        head.firstMaterial?.lightingModel = .constant
        comet.addChildNode(SCNNode(geometry: head))

        let trailPlane = SCNPlane(width: 0.55, height: 0.04)
        let trailMaterial = SCNMaterial()
        trailMaterial.diffuse.contents = SunArt.trailImage()
        trailMaterial.lightingModel = .constant
        trailMaterial.blendMode = .add
        trailMaterial.isDoubleSided = true
        trailMaterial.writesToDepthBuffer = false
        trailPlane.materials = [trailMaterial]
        let trail = SCNNode(geometry: trailPlane)
        trail.position = SCNVector3(0.29, 0.02, 0)
        comet.addChildNode(trail)

        let fromRight = Bool.random()
        let y0 = CGFloat.random(in: -0.7...1.0)
        let y1 = y0 - CGFloat.random(in: 0.1...0.45)
        comet.position = SCNVector3(fromRight ? 2.2 : -2.2, y0, 0.6)
        if !fromRight {
            comet.eulerAngles.y = .pi
        }
        scene.rootNode.addChildNode(comet)

        let fly = SCNAction.move(to: SCNVector3(fromRight ? -2.2 : 2.2, y1, 0.6), duration: 2.3)
        comet.runAction(.sequence([.group([fly, .sequence([.wait(duration: 1.8), .fadeOut(duration: 0.5)])]), .removeFromParentNode()]))
    }

    // MARK: - Toys & reactions

    /// Dodge away from a fast-approaching cursor.
    func dodge(fromDX dx: CGFloat) {
        guard mood == .idle else { return }
        let away: CGFloat = dx > 0 ? -0.28 : 0.28
        let jump = SCNAction.moveBy(x: away, y: 0.06, z: 0, duration: 0.15)
        jump.timingMode = .easeOut
        let back = SCNAction.moveBy(x: -away, y: -0.06, z: 0, duration: 0.7)
        back.timingMode = .easeInEaseOut
        groupNode.runAction(.sequence([jump, back]))
    }

    /// Startled hop for drag-and-drop.
    private func startle() {
        let hop = SCNAction.moveBy(x: 0, y: 0.2, z: 0, duration: 0.12)
        hop.timingMode = .easeOut
        let land = hop.reversed()
        land.timingMode = .easeIn
        groupNode.runAction(.sequence([hop, land]))
    }

    /// Friday 6pm — party time.
    func confettiBurst() {
        guard let scene else { return }
        let colors: [NSColor] = [.systemRed, .systemYellow, .systemGreen, .systemBlue, .systemPink]
        for color in colors {
            let points = (0..<55).map { _ -> SCNVector3 in
                let theta = CGFloat.random(in: 0...(2 * .pi))
                let phi = CGFloat.random(in: 0...(.pi))
                let r = CGFloat.random(in: 0.05...0.22)
                return SCNVector3(r * sin(phi) * cos(theta), r * sin(phi) * sin(theta), r * cos(phi))
            }
            let cloud = pointCloudNode(points: points, color: color, pointSize: 3.5)
            cloud.position = SCNVector3(0, 0.1, 0.5)
            scene.rootNode.addChildNode(cloud)
            let burst = SCNAction.group([
                .scale(to: CGFloat.random(in: 5...8), duration: 2.4),
                .moveBy(x: 0, y: -0.5, z: 0, duration: 2.4),
                .sequence([.wait(duration: 1.2), .fadeOut(duration: 1.2)])
            ])
            cloud.runAction(.sequence([burst, .removeFromParentNode()]))
        }
    }

    /// Easter egg: poor Pluto, out in the cold.
    func showPluto() {
        guard let scene, scene.rootNode.childNode(withName: "pluto", recursively: false) == nil else { return }
        let sphere = SCNSphere(radius: 0.035)
        sphere.firstMaterial?.diffuse.contents = NSColor(calibratedWhite: 0.55, alpha: 1)
        let pluto = SCNNode(geometry: sphere)
        pluto.name = "pluto"
        pluto.position = SCNVector3(1.45, -1.15, 0.2)
        pluto.eulerAngles.z = 0.35   // hanging its head
        pluto.opacity = 0
        scene.rootNode.addChildNode(pluto)

        let sadBob = SCNAction.sequence([
            .moveBy(x: 0, y: 0.02, z: 0, duration: 2.4),
            .moveBy(x: 0, y: -0.02, z: 0, duration: 2.4)
        ])
        pluto.runAction(.sequence([
            .fadeIn(duration: 1.5),
            .repeat(sadBob, count: 12),
            .fadeOut(duration: 2),
            .removeFromParentNode()
        ]))
    }

    /// A little probe sets off from Earth toward a random planet.
    private func launchRocket() {
        guard body == .system,
              let earth = systemClones[.earth],
              let targetBody = Body.planets.filter({ $0 != .earth }).randomElement(),
              let target = systemClones[targetBody],
              let scene else { return }

        let rocket = makeRocketNode(hullHeight: 0.035)
        scene.rootNode.addChildNode(rocket)
        rocket.worldPosition = earth.presentation.worldPosition

        // Cruise to where the target is right now (close enough for a toy).
        let destination = target.presentation.worldPosition
        let cruise = SCNAction.move(to: destination, duration: 40)
        let arrive = SCNAction.group([.scale(to: 2.2, duration: 0.4), .fadeOut(duration: 0.4)])
        rocket.runAction(.sequence([cruise, arrive, .removeFromParentNode()]))
    }

    /// A tiny capsule rocket with an orange flame at its tail.
    private func makeRocketNode(hullHeight: CGFloat) -> SCNNode {
        let rocket = SCNNode()
        let hull = SCNCapsule(capRadius: hullHeight * 0.23, height: hullHeight)
        hull.firstMaterial?.diffuse.contents = NSColor.white
        hull.firstMaterial?.lightingModel = .constant
        rocket.addChildNode(SCNNode(geometry: hull))
        let flame = SCNSphere(radius: hullHeight * 0.17)
        flame.firstMaterial?.diffuse.contents = NSColor.orange
        flame.firstMaterial?.lightingModel = .constant
        let flameNode = SCNNode(geometry: flame)
        flameNode.name = "flame"
        flameNode.position = SCNVector3(0, -hullHeight * 0.71, 0)
        rocket.addChildNode(flameNode)
        return rocket
    }

    // MARK: - Ambient rockets (transparent mode)

    /// While the app is pure decoration (click-through mode), a rocket
    /// lifts off from Earth every 30 seconds and flies off screen.
    func setAmbientRockets(_ on: Bool) {
        ambientRockets = on
        updateSurfaceRocketTimer()
        if on {
            // Inaugural launch soon after flipping the switch,
            // so the new mode announces itself.
            DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in
                self?.fireAmbientRocket()
            }
        }
    }

    private func updateSurfaceRocketTimer() {
        surfaceRocketTimer?.invalidate()
        surfaceRocketTimer = nil
        guard ambientRockets, body == .earth else { return }
        let timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            self?.fireAmbientRocket()
        }
        timer.tolerance = 5
        surfaceRocketTimer = timer
    }

    private func fireAmbientRocket() {
        guard ambientRockets, !isSceneSuspended, body == .earth,
              window?.isVisible == true else { return }
        ambientRocketHandler?()
    }

    /// The flight: rise vertically off the pad, pitch over into a gravity
    /// turn, skim around the globe the long way across the window, and
    /// accelerate away until it escapes off screen. The nose always points
    /// along the flight path.
    ///
    /// `freezeAt` places the rocket at that phase (0…1) of the trajectory
    /// with no animation — for snapshot verification.
    func launchSurfaceRocket(force: Bool = false, freezeAt: Float? = nil) {
        guard let scene, body == .earth else { return }
        if !force {
            guard ambientRockets, !isSceneSuspended, window?.isVisible == true else { return }
        }

        // Launch site on the visible hemisphere, away from dead center.
        let lat = CGFloat.random(in: 0.25...1.0) * (Bool.random() ? 1 : -1)
        let lon = CGFloat.random(in: 0.35...1.2) * (Bool.random() ? 1 : -1)
        let up = simd_float3(
            Float(cos(lat) * sin(lon)),
            Float(sin(lat)),
            Float(cos(lat) * cos(lon))
        )
        // Sweep tangentially in the screen plane, toward the far side of
        // the window — the arc crosses the whole view before exiting.
        var side = simd_normalize(simd_cross(simd_float3(0, 0, 1), up))
        if up.x * side.x > 0 || (abs(up.x) < 0.05 && Bool.random()) {
            side = -side
        }

        // A grand tour: two-and-some full loops around the planet on an
        // ever-widening spiral that sweeps the whole window (and bobs
        // toward and away from the camera each lap) before escaping.
        let sweep = Float.random(in: 2.0...2.75) * 2 * .pi
        let path: (Float) -> simd_float3 = { e in
            // Gravity turn: the angle builds gently (pure vertical rise
            // at first), the radius widens lap by lap to cover the view,
            // and the late power term flings it off screen.
            let theta = sweep * pow(e, 1.5)
            let radius = 0.86 + 0.95 * e + 2.0 * pow(e, 8)
            return (cos(theta) * up + sin(theta) * side) * radius
        }
        let pose: (SCNNode, Float) -> Void = { node, e in
            let here = path(e)
            let ahead = path(min(e + 0.004, 1))
            node.simdPosition = here
            let velocity = ahead - here
            node.simdOrientation = simd_quatf(
                from: simd_float3(0, 1, 0),
                to: simd_length(velocity) > 1e-7 ? simd_normalize(velocity) : up
            )
        }

        let rocket = makeRocketNode(hullHeight: 0.07)
        rocket.name = "surfaceRocket"
        pose(rocket, 0)
        scene.rootNode.addChildNode(rocket)

        if let freezeAt {
            pose(rocket, freezeAt)
            return
        }

        // Thrust: the flame pulses the whole way up.
        if let flame = rocket.childNode(withName: "flame", recursively: true) {
            flame.runAction(.repeatForever(.sequence([
                .scale(to: 1.35, duration: 0.1),
                .scale(to: 0.9, duration: 0.12)
            ])))
        }

        let duration: TimeInterval = 12
        rocket.opacity = 0
        let fly = SCNAction.customAction(duration: duration) { node, elapsed in
            let s = min(Float(elapsed) / Float(duration), 1)
            // Accelerating from rest for the entire flight.
            let e = 0.35 * s * s + 0.65 * s * s * s
            pose(node, e)
        }
        rocket.runAction(.sequence([
            .group([
                .fadeIn(duration: 0.3),
                fly,
                .sequence([.wait(duration: duration - 1.0), .fadeOut(duration: 1.0)])
            ]),
            .removeFromParentNode()
        ]))
    }

    // MARK: - Drag & drop

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        startle()
        return .copy
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        guard let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self]) as? [URL],
              let url = urls.first else { return false }
        setMood(.happy)
        dropHandler?(url)
        return true
    }

    // MARK: - Mouse controls
    // Left drag: trackball-rotate the body freely, flick inertia on release.
    // Left double-click: open the chat.
    // Right drag: move the window.
    // The axis spin keeps running underneath — the body never stops turning.

    override func mouseDown(with event: NSEvent) {
        // Control+drag moves the window, same as a right-drag.
        if event.modifierFlags.contains(.control) {
            window?.performDrag(with: event)
            return
        }
        mouseDownPoint = event.locationInWindow
        lastDragPoint = mouseDownPoint
        lastDragTime = event.timestamp
        flickSpeed = 0
        didDrag = false
        stopInertia()
        preferredFramesPerSecond = Self.interactiveFPS
    }

    override func mouseDragged(with event: NSEvent) {
        let p = event.locationInWindow
        if !didDrag {
            guard hypot(p.x - mouseDownPoint.x, p.y - mouseDownPoint.y) > 3 else { return }
            didDrag = true
        }

        let dx = Float(p.x - lastDragPoint.x)
        let dy = Float(p.y - lastDragPoint.y)
        let dt = max(event.timestamp - lastDragTime, 1.0 / 240.0)

        // Horizontal drag rotates around the screen's vertical axis,
        // vertical drag around the horizontal one (arcball style).
        let angle = simd_length(simd_float2(dx, dy)) * Self.spinPerPixel
        if angle > 0 {
            let axis = simd_normalize(simd_float3(-dy, dx, 0))
            let q = simd_quatf(angle: angle, axis: axis)
            trackballNode.simdOrientation = q * trackballNode.simdOrientation

            // Smoothed release velocity so the flick reflects the last motion.
            flickAxis = axis
            flickSpeed = 0.7 * (angle / Float(dt)) + 0.3 * flickSpeed
        }

        lastDragPoint = p
        lastDragTime = event.timestamp
    }

    override func mouseUp(with event: NSEvent) {
        if didDrag {
            startInertia()
        } else if event.clickCount >= 2 {
            clickHandler?()
        }
        didDrag = false
        // Inertia keeps the fast clock; otherwise settle back down.
        if inertiaTimer == nil {
            preferredFramesPerSecond = Self.idleFPS
        }
    }

    override func rightMouseDown(with event: NSEvent) {
        window?.performDrag(with: event)
    }

    override func magnify(with event: NSEvent) {
        preferredFramesPerSecond =
            event.phase == .ended || event.phase == .cancelled
                ? Self.idleFPS : Self.interactiveFPS
        (window as? FloatingPanel)?.scaleBy(1 + event.magnification)
    }

    // MARK: - Flick inertia

    private func startInertia() {
        stopInertia()
        var speed = min(flickSpeed, 40)
        let axis = flickAxis
        guard speed > 0.3 else { return }
        let frame: TimeInterval = 1.0 / 60.0
        inertiaTimer = Timer.scheduledTimer(withTimeInterval: frame, repeats: true) { [weak self] _ in
            guard let self else { return }
            let q = simd_quatf(angle: speed * Float(frame), axis: axis)
            self.trackballNode.simdOrientation = q * self.trackballNode.simdOrientation
            speed *= 0.985
            if speed <= 0.3 {
                self.stopInertia()
            }
        }
    }

    private func stopInertia() {
        inertiaTimer?.invalidate()
        inertiaTimer = nil
        preferredFramesPerSecond = Self.idleFPS
    }
}
