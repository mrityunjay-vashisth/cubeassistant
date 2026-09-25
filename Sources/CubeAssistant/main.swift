import AppKit
import SceneKit

// Debug: `CubeAssistant --plane out.png` renders the 3D flight plane in a
// banked 3/4 pose, to verify orientation, materials, and the prop node.
if let flagIndex = CommandLine.arguments.firstIndex(of: "--plane"),
   CommandLine.arguments.count > flagIndex + 1 {
    let path = CommandLine.arguments[flagIndex + 1]
    // The view must exist before GLTFSceneKit loads anything — texture
    // upload needs a live Metal context.
    let view = SCNView(frame: NSRect(x: 0, y: 0, width: 500, height: 400))
    guard let model = PlaneModel.load() else {
        print("plane failed to load")
        exit(1)
    }
    print("prop node: \(model.prop == nil ? "MISSING" : "found")")
    let scene = SCNScene()
    scene.background.contents = NSColor(calibratedWhite: 0.35, alpha: 1)
    view.scene = scene
    let cameraNode = SCNNode()
    cameraNode.camera = SCNCamera()
    cameraNode.camera?.zFar = 2000
    cameraNode.position = SCNVector3(0, 0, 300)
    scene.rootNode.addChildNode(cameraNode)
    let sun = SCNNode()
    sun.light = SCNLight(); sun.light?.type = .directional; sun.light?.intensity = 1300
    sun.eulerAngles = SCNVector3(-0.3, 0.35, 0)
    scene.rootNode.addChildNode(sun)
    let amb = SCNNode()
    amb.light = SCNLight(); amb.light?.type = .ambient; amb.light?.intensity = 420
    scene.rootNode.addChildNode(amb)
    let flight = SCNNode()
    model.root.scale = SCNVector3(150, 150, 150)
    flight.addChildNode(model.root)
    flight.simdOrientation =
        simd_quatf(angle: 0.5, axis: simd_float3(0, 0, 1)) *
        simd_quatf(angle: -0.4, axis: simd_float3(0, 1, 0)) *
        simd_quatf(angle: 0.45, axis: simd_float3(1, 0, 0))
    scene.rootNode.addChildNode(flight)
    RunLoop.main.run(until: Date().addingTimeInterval(0.5))
    let shot = view.snapshot()
    if let tiff = shot.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
       let png = rep.representation(using: .png, properties: [:]) {
        try? png.write(to: URL(fileURLWithPath: path))
        print("plane snapshot written to \(path)")
        exit(0)
    }
    exit(1)
}

// Debug: `CubeAssistant --sprite out.png` renders the desktop-rocket sprite.
if let flagIndex = CommandLine.arguments.firstIndex(of: "--sprite"),
   CommandLine.arguments.count > flagIndex + 1 {
    let path = CommandLine.arguments[flagIndex + 1]
    if let sprite = AppDelegate.rocketSprite(size: 224) {
        let rep = NSBitmapImageRep(cgImage: sprite)
        try? rep.representation(using: .png, properties: [:])?
            .write(to: URL(fileURLWithPath: path))
        print("sprite written to \(path)")
        exit(0)
    }
    print("sprite failed")
    exit(1)
}

// Debug: `CubeAssistant --snapshot out.png [--body earth]` renders the avatar
// offscreen and exits, for checking visuals without a screen.
if let flagIndex = CommandLine.arguments.firstIndex(of: "--snapshot"),
   CommandLine.arguments.count > flagIndex + 1 {
    let path = CommandLine.arguments[flagIndex + 1]
    let view = AvatarView()
    // --size N: square render size in points (default 400); the release
    // script uses 1024 to build the app icon.
    var size: CGFloat = 400
    if let sizeIndex = CommandLine.arguments.firstIndex(of: "--size"),
       CommandLine.arguments.count > sizeIndex + 1,
       let value = Double(CommandLine.arguments[sizeIndex + 1]), value > 0 {
        size = CGFloat(value)
    }
    view.frame = NSRect(x: 0, y: 0, width: size, height: size)
    var body = Body.earth
    if let bodyIndex = CommandLine.arguments.firstIndex(of: "--body"),
       CommandLine.arguments.count > bodyIndex + 1,
       let chosen = Body(rawValue: CommandLine.arguments[bodyIndex + 1]) {
        body = chosen
    }
    if body == .sun || body == .system, let image = SunFetcher().bestAvailableImage() {
        view.setSunImage(image)
    }
    view.setBody(body)
    if let climateIndex = CommandLine.arguments.firstIndex(of: "--climate"),
       CommandLine.arguments.count > climateIndex + 1,
       let climate = Climate(rawValue: CommandLine.arguments[climateIndex + 1]) {
        view.setClimate(climate)
    }
    // --dark: render on a dark slate instead of transparency, so faint
    // white elements (orbit rings, stars) are visible in the PNG.
    if CommandLine.arguments.contains("--dark") {
        view.scene?.background.contents = NSColor(calibratedWhite: 0.09, alpha: 1)
    }
    // --rocket <phase 0..1>: place an ambient rocket frozen at that point
    // of its flight path, for verifying the trajectory frame by frame.
    if let flagIndex = CommandLine.arguments.firstIndex(of: "--rocket") {
        var phase: Float = 0.02
        if CommandLine.arguments.count > flagIndex + 1,
           let value = Float(CommandLine.arguments[flagIndex + 1]) {
            phase = value
        }
        view.launchSurfaceRocket(force: true, freezeAt: phase)
    }
    // --materials: list every material in the composed scene, including
    // library-injected shader modifiers that can override our settings.
    if CommandLine.arguments.contains("--materials") {
        view.scene?.rootNode.enumerateHierarchy { node, _ in
            guard let geometry = node.geometry else { return }
            for material in geometry.materials {
                var line = "node=\(node.name ?? "?") model=\(material.lightingModel.rawValue)"
                if let modifiers = material.shaderModifiers, !modifiers.isEmpty {
                    line += " modifiers=\(modifiers.keys.map(\.rawValue).sorted())"
                }
                if material.program != nil { line += " CUSTOM-PROGRAM" }
                let diffuse = material.diffuse.contents
                line += " diffuse=\(diffuse == nil ? "nil" : String(describing: type(of: diffuse!)))"
                let emission = material.emission.contents
                line += " emission=\(emission == nil ? "nil" : String(describing: type(of: emission!)))"
                print(line)
            }
        }
    }
    RunLoop.main.run(until: Date().addingTimeInterval(1.0))
    let snapshot = view.snapshot()
    if let tiff = snapshot.tiffRepresentation,
       let rep = NSBitmapImageRep(data: tiff),
       let png = rep.representation(using: .png, properties: [:]) {
        try? png.write(to: URL(fileURLWithPath: path))
        print("snapshot written to \(path), body: \(view.body)")
        exit(0)
    }
    print("snapshot failed")
    exit(1)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
