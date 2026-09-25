import AppKit
import SceneKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private static let bodyKey = "CubeAssistant.body"
    private static let clickThroughKey = "CubeAssistant.clickThrough"
    private static let rotationRateKey = "CubeAssistant.rotationRate"
    private static let revolutionRateKey = "CubeAssistant.revolutionRate"
    private static let livePositionsKey = "CubeAssistant.livePositions"
    private static let climateKey = "CubeAssistant.climate"
    private static let ratePresets: [Double] = [0.25, 0.5, 1, 2, 5, 10]

    private var panel: FloatingPanel!
    private var statusItem: NSStatusItem!
    private let popover = NSPopover()
    private let chatController = ChatViewController()
    private let backend = ClaudeBackend()
    private let sunFetcher = SunFetcher()
    private let issFetcher = ISSFetcher()

    private var bodyMenuItems: [Body: NSMenuItem] = [:]
    private var interactiveMenuItem: NSMenuItem!
    private var transparentMenuItem: NSMenuItem!
    private var rotationRateItems: [NSMenuItem] = []
    private var revolutionRateItems: [NSMenuItem] = []
    private var livePositionsItem: NSMenuItem!
    private var climateItems: [Climate: NSMenuItem] = [:]

    private var batteryTimer: Timer?
    private var fridayTimer: Timer?
    private var lastConfettiDay = ""
    private var lastMouse: (point: NSPoint, time: TimeInterval)?
    private var lastDodge: TimeInterval = 0
    private var mouseMonitor: Any?
    private var screenAsleep = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        panel = FloatingPanel()
        panel.orderFrontRegardless()

        // Keep the sun texture live from NASA SDO (used whenever the sun body is shown).
        if let image = sunFetcher.bestAvailableImage() {
            panel.avatarView.setSunImage(image)
        }
        sunFetcher.onUpdate = { [weak self] image in
            self?.panel.avatarView.setSunImage(image)
        }
        sunFetcher.start()

        issFetcher.onUpdate = { [weak self] lat, lon in
            self?.panel.avatarView.updateISS(latitude: lat, longitude: lon)
        }
        issFetcher.start()

        popover.contentViewController = chatController
        popover.behavior = .transient

        panel.avatarView.clickHandler = { [weak self] in
            self?.toggleChat()
        }
        panel.avatarView.ambientRocketHandler = { [weak self] in
            guard let self else { return }
            // Half the flights are the 3D plane, half the rocket.
            if Bool.random() {
                self.launchDesktopPlane()
            } else {
                self.launchDesktopRocket()
            }
        }
        chatController.onSend = { [weak self] prompt in
            self?.send(prompt)
        }

        setupStatusItem()

        applyRates(
            rotation: UserDefaults.standard.object(forKey: Self.rotationRateKey) as? Double ?? 1,
            revolution: UserDefaults.standard.object(forKey: Self.revolutionRateKey) as? Double ?? 1
        )
        applyLivePositions(UserDefaults.standard.bool(forKey: Self.livePositionsKey))
        applyClimate(Climate(rawValue: UserDefaults.standard.string(forKey: Self.climateKey) ?? "") ?? .sunny)
        let saved = UserDefaults.standard.string(forKey: Self.bodyKey)
        applyBody(Body(rawValue: saved ?? "") ?? .earth)
        applyClickThrough(UserDefaults.standard.bool(forKey: Self.clickThroughKey))

        panel.avatarView.dropHandler = { [weak self] url in
            guard let self else { return }
            if !self.popover.isShown {
                self.toggleChat()
            }
            self.chatController.prefill("What should I do with \(url.path)?")
            self.chatController.focusInput()
        }

        startWorldSensors()
    }

    private func toggleChat() {
        if popover.isShown {
            popover.close()
        } else {
            NSApp.activate(ignoringOtherApps: true)
            popover.show(relativeTo: panel.avatarView.bounds, of: panel.avatarView, preferredEdge: .maxY)
            chatController.focusInput()
        }
    }

    private func send(_ prompt: String) {
        if prompt.lowercased().contains("pluto") {
            panel.avatarView.showPluto()
        }
        chatController.setBusy(true)
        chatController.showPrompt(prompt)
        panel.avatarView.setMood(.thinking)

        backend.send(prompt) { [weak self] result in
            guard let self else { return }
            self.chatController.setBusy(false)
            switch result {
            case .success(let reply):
                self.chatController.showReply(reply, for: prompt)
                self.panel.avatarView.setMood(.happy)
            case .failure(let error):
                self.chatController.showError(error.localizedDescription)
                self.panel.avatarView.setMood(.error)
            }
        }
    }

    // MARK: - Body selection

    private func applyBody(_ body: Body) {
        panel.avatarView.setBody(body)
        let actual = panel.avatarView.body
        UserDefaults.standard.set(actual.rawValue, forKey: Self.bodyKey)
        statusItem.button?.title = actual.statusEmoji
        issFetcher.isActive = actual == .earth
        for (body, item) in bodyMenuItems {
            item.state = body == actual ? .on : .off
        }
    }

    @objc private func chooseBody(_ sender: NSMenuItem) {
        guard let body = sender.representedObject as? Body else { return }
        applyBody(body)
    }

    // MARK: - Interaction mode

    private func applyClickThrough(_ clickThrough: Bool) {
        panel.ignoresMouseEvents = clickThrough
        if clickThrough, popover.isShown {
            popover.close()
        }
        UserDefaults.standard.set(clickThrough, forKey: Self.clickThroughKey)
        interactiveMenuItem.state = clickThrough ? .off : .on
        transparentMenuItem.state = clickThrough ? .on : .off
        updateMouseMonitor()
        // Decoration mode gets ambience: Earth launches a rocket every 30s.
        panel.avatarView.setAmbientRockets(clickThrough)
    }

    @objc private func chooseInteractive() { applyClickThrough(false) }
    @objc private func chooseTransparent() { applyClickThrough(true) }

    // MARK: - Desktop rocket

    private var rocketOverlay: NSWindow?

    /// A rocket lifts off from the Earth window and tours the whole
    /// display — big swooping curves through every corner — before
    /// exiting off a screen edge. Lives on a temporary click-through
    /// overlay that is torn down the moment the flight ends.
    private func launchDesktopRocket() {
        guard rocketOverlay == nil,
              let screen = panel.screen ?? NSScreen.main else { return }

        let overlay = NSWindow(
            contentRect: screen.frame,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )
        overlay.isOpaque = false
        overlay.backgroundColor = .clear
        overlay.hasShadow = false
        overlay.ignoresMouseEvents = true
        overlay.level = panel.level
        overlay.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        let host = NSView(frame: NSRect(origin: .zero, size: screen.frame.size))
        host.wantsLayer = true
        overlay.contentView = host
        overlay.orderFrontRegardless()
        rocketOverlay = overlay

        let spriteSize: CGFloat = 56
        let rocketLayer = CALayer()
        rocketLayer.contents = Self.rocketSprite(size: spriteSize)
        rocketLayer.bounds = CGRect(x: 0, y: 0, width: spriteSize, height: spriteSize)

        // Exhaust: an emitter follows the same path, leaving smoke puffs
        // and quick orange sparks hanging in the air behind the rocket.
        let emitter = CAEmitterLayer()
        emitter.frame = host.bounds
        emitter.emitterShape = .point
        emitter.emitterPosition = .zero
        emitter.renderMode = .oldestLast
        let puff = SunArt.glowImage(color: .white, size: 32)
            .cgImage(forProposedRect: nil, context: nil, hints: nil)
        let smoke = CAEmitterCell()
        smoke.contents = puff
        smoke.birthRate = 55
        smoke.lifetime = 1.5
        smoke.velocity = 12
        smoke.velocityRange = 10
        smoke.emissionRange = .pi * 2
        smoke.scale = 0.4
        smoke.scaleRange = 0.15
        smoke.scaleSpeed = 0.3
        smoke.alphaSpeed = -0.75
        smoke.color = NSColor(calibratedWhite: 0.85, alpha: 0.55).cgColor
        let spark = CAEmitterCell()
        spark.contents = puff
        spark.birthRate = 45
        spark.lifetime = 0.3
        spark.velocity = 8
        spark.emissionRange = .pi * 2
        spark.scale = 0.25
        spark.scaleSpeed = -0.4
        spark.alphaSpeed = -2.8
        spark.color = NSColor(calibratedRed: 1.0, green: 0.6, blue: 0.15, alpha: 0.9).cgColor
        emitter.emitterCells = [smoke, spark]
        host.layer?.addSublayer(emitter)
        host.layer?.addSublayer(rocketLayer)

        // Flight plan: climb off the pad, tour a waypoint in each quadrant
        // of the screen (shuffled), then leave past an edge. The exit
        // point sits far beyond the screen so the rocket never overshoots
        // it and tries to double back.
        let width = screen.frame.width
        let height = screen.frame.height
        let start = CGPoint(
            x: panel.frame.midX - screen.frame.minX,
            y: panel.frame.midY - screen.frame.minY
        )
        var targets = [
            CGPoint(x: .random(in: 0.08...0.4) * width, y: .random(in: 0.55...0.92) * height),
            CGPoint(x: .random(in: 0.6...0.92) * width, y: .random(in: 0.55...0.92) * height),
            CGPoint(x: .random(in: 0.6...0.92) * width, y: .random(in: 0.08...0.4) * height),
            CGPoint(x: .random(in: 0.08...0.4) * width, y: .random(in: 0.08...0.4) * height)
        ].shuffled()
        targets.insert(CGPoint(
            x: start.x + .random(in: -60...60),
            y: min(start.y + height * 0.3, height * 0.95)
        ), at: 0)
        targets.append([
            CGPoint(x: -1400, y: .random(in: 0...height)),
            CGPoint(x: width + 1400, y: .random(in: 0...height)),
            CGPoint(x: .random(in: 0...width), y: height + 1400),
            CGPoint(x: .random(in: 0...width), y: -1400)
        ].randomElement()!)

        // Not an animation — a flight simulation. The rocket has thrust
        // and a capped turn rate, and steers toward each waypoint 60
        // times a second. A bounded turn rate means the heading can
        // never snap: only wide banking arcs, like a real vehicle.
        rocketLayer.actions = ["position": NSNull(), "transform": NSNull()]
        emitter.actions = ["emitterPosition": NSNull()]
        var position = start
        var heading: CGFloat = .pi / 2      // straight up off the pad
        var speed: CGFloat = 30
        var elapsed: CGFloat = 0
        var targetIndex = 0
        rocketLayer.position = position
        emitter.emitterPosition = position

        let tick: CGFloat = 1.0 / 60.0
        let maxTurnRate: CGFloat = 1.25     // rad/s — the no-kink guarantee
        Timer.scheduledTimer(withTimeInterval: TimeInterval(tick), repeats: true) { [weak self] timer in
            elapsed += tick
            // Cruise gently during the tour — a modest speed keeps the
            // turning circle tight enough to actually visit waypoints —
            // then open the throttle on the exit leg.
            let cruise: CGFloat = targetIndex == targets.count - 1 ? 900 : 330
            speed = min(speed + 130 * tick, cruise)

            let target = targets[targetIndex]
            let desired = atan2(target.y - position.y, target.x - position.x)
            let wrapped = atan2(sin(desired - heading), cos(desired - heading))
            let maxTurn = maxTurnRate * tick
            heading += max(-maxTurn, min(maxTurn, wrapped))
            position.x += cos(heading) * speed * tick
            position.y += sin(heading) * speed * tick

            CATransaction.begin()
            CATransaction.setDisableActions(true)
            rocketLayer.position = position
            rocketLayer.setAffineTransform(CGAffineTransform(rotationAngle: heading))
            emitter.emitterPosition = position
            CATransaction.commit()

            // Advance once the waypoint is inside our turning reach —
            // chasing a point tighter than the turn circle means orbiting
            // it forever.
            let reach = max(80, speed / maxTurnRate * 0.85)
            if targetIndex < targets.count - 1,
               hypot(target.x - position.x, target.y - position.y) < reach {
                targetIndex += 1
            }

            let out = position.x < -120 || position.x > width + 120
                || position.y < -120 || position.y > height + 120
            if (targetIndex == targets.count - 1 && out) || elapsed > 30 {
                timer.invalidate()
                emitter.birthRate = 0
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.8) {
                    overlay.orderOut(nil)
                    self?.rocketOverlay = nil
                }
            }
        }
    }

    /// The real 3D plane touring the desktop: SceneKit overlay, model
    /// banking into turns, propeller spinning, contrail streaming behind.
    /// Same steering simulation as the rocket — bounded turn rate, so the
    /// flight is all smooth arcs.
    private func launchDesktopPlane() {
        guard rocketOverlay == nil,
              let screen = panel.screen ?? NSScreen.main,
              let model = PlaneModel.load() else {
            launchDesktopRocket()
            return
        }

        let width = screen.frame.width
        let height = screen.frame.height
        let overlay = NSWindow(
            contentRect: screen.frame,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )
        overlay.isOpaque = false
        overlay.backgroundColor = .clear
        overlay.hasShadow = false
        overlay.ignoresMouseEvents = true
        overlay.level = panel.level
        overlay.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        let scnView = SCNView(frame: NSRect(origin: .zero, size: screen.frame.size))
        scnView.backgroundColor = .clear
        scnView.preferredFramesPerSecond = 60
        scnView.antialiasingMode = .multisampling2X
        let scene = SCNScene()
        scene.background.contents = NSColor.clear
        scnView.scene = scene
        overlay.contentView = scnView
        overlay.orderFrontRegardless()
        rocketOverlay = overlay

        // Camera: perspective, positioned so one world unit = one screen
        // point on the flight plane (z = 0).
        let cameraNode = SCNNode()
        let camera = SCNCamera()
        camera.zNear = 10
        camera.zFar = 10_000
        cameraNode.camera = camera
        let distance = (height / 2) / tan(camera.fieldOfView * .pi / 360)
        cameraNode.position = SCNVector3(0, 0, distance)
        scene.rootNode.addChildNode(cameraNode)

        let sunlight = SCNNode()
        sunlight.light = SCNLight()
        sunlight.light?.type = .directional
        sunlight.light?.intensity = 1300
        sunlight.eulerAngles = SCNVector3(-0.3, 0.35, 0)
        scene.rootNode.addChildNode(sunlight)
        let ambient = SCNNode()
        ambient.light = SCNLight()
        ambient.light?.type = .ambient
        ambient.light?.intensity = 420
        scene.rootNode.addChildNode(ambient)

        // The plane, wingspan ~85 points — in scale with the rocket.
        let flightNode = SCNNode()
        let plane = model.root
        plane.scale = SCNVector3(85, 85, 85)
        flightNode.addChildNode(plane)
        scene.rootNode.addChildNode(flightNode)
        model.prop?.runAction(.repeatForever(.rotateBy(x: -.pi * 2, y: 0, z: 0, duration: 0.09)))

        // Contrail from the tail.
        let trail = SCNParticleSystem()
        trail.birthRate = 70
        trail.particleLifeSpan = 1.4
        trail.particleSize = 7
        trail.particleSizeVariation = 3
        trail.particleVelocity = 14
        trail.particleVelocityVariation = 10
        trail.emissionDuration = .greatestFiniteMagnitude
        trail.birthDirection = .random
        trail.particleColor = NSColor(calibratedWhite: 0.95, alpha: 0.4)
        trail.blendMode = .additive
        trail.isAffectedByGravity = false
        trail.particleImage = SunArt.glowImage(color: .white, size: 32)
        let tail = SCNNode()
        tail.position = SCNVector3(-40, 0, 0)
        tail.addParticleSystem(trail)
        flightNode.addChildNode(tail)

        let start = CGPoint(
            x: panel.frame.midX - screen.frame.minX,
            y: panel.frame.midY - screen.frame.minY
        )
        var targets = [
            CGPoint(x: .random(in: 0.08...0.4) * width, y: .random(in: 0.55...0.92) * height),
            CGPoint(x: .random(in: 0.6...0.92) * width, y: .random(in: 0.55...0.92) * height),
            CGPoint(x: .random(in: 0.6...0.92) * width, y: .random(in: 0.08...0.4) * height),
            CGPoint(x: .random(in: 0.08...0.4) * width, y: .random(in: 0.08...0.4) * height)
        ].shuffled()
        targets.insert(CGPoint(
            x: start.x + .random(in: -60...60),
            y: min(start.y + height * 0.3, height * 0.95)
        ), at: 0)
        targets.append([
            CGPoint(x: -1400, y: .random(in: 0...height)),
            CGPoint(x: width + 1400, y: .random(in: 0...height)),
            CGPoint(x: .random(in: 0...width), y: height + 1400),
            CGPoint(x: .random(in: 0...width), y: -1400)
        ].randomElement()!)

        var position = start
        var heading: CGFloat = .pi / 2
        var speed: CGFloat = 40
        var bank: CGFloat = 0
        var elapsed: CGFloat = 0
        var targetIndex = 0
        var flipped = false
        var flipBlend: Float = 0   // 0 = facing right, 1 = facing left

        let tick: CGFloat = 1.0 / 60.0
        let maxTurnRate: CGFloat = 1.1
        Timer.scheduledTimer(withTimeInterval: TimeInterval(tick), repeats: true) { [weak self] timer in
            elapsed += tick
            let cruise: CGFloat = targetIndex == targets.count - 1 ? 850 : 320
            speed = min(speed + 120 * tick, cruise)

            let target = targets[targetIndex]
            let desired = atan2(target.y - position.y, target.x - position.x)
            let wrapped = atan2(sin(desired - heading), cos(desired - heading))
            let maxTurn = maxTurnRate * tick
            let turn = max(-maxTurn, min(maxTurn, wrapped))
            heading += turn
            position.x += cos(heading) * speed * tick
            position.y += sin(heading) * speed * tick

            // Keep the plane right side up past vertical. Instead of
            // snapping 180°, blend between the two facings with a slerp —
            // the flip becomes a smooth half-second roll maneuver.
            if cos(heading) < -0.25 { flipped = true }
            else if cos(heading) > 0.25 { flipped = false }
            flipBlend += ((flipped ? 1 : 0) - flipBlend) * 0.08
            let targetBank = 0.6 * (turn / maxTurn)
            bank += (targetBank - bank) * 0.07

            let facingRight =
                simd_quatf(angle: Float(heading), axis: simd_float3(0, 0, 1)) *
                simd_quatf(angle: -0.4, axis: simd_float3(0, 1, 0)) *
                simd_quatf(angle: Float(bank), axis: simd_float3(1, 0, 0))
            let facingLeft =
                simd_quatf(angle: Float(heading - .pi), axis: simd_float3(0, 0, 1)) *
                simd_quatf(angle: .pi + 0.4, axis: simd_float3(0, 1, 0)) *
                simd_quatf(angle: Float(-bank), axis: simd_float3(1, 0, 0))
            flightNode.simdOrientation = simd_slerp(facingRight, facingLeft, flipBlend)
            flightNode.simdPosition = simd_float3(
                Float(position.x - width / 2),
                Float(position.y - height / 2),
                0
            )

            let reach = max(80, speed / maxTurnRate * 0.85)
            if targetIndex < targets.count - 1,
               hypot(target.x - position.x, target.y - position.y) < reach {
                targetIndex += 1
            }

            let out = position.x < -160 || position.x > width + 160
                || position.y < -160 || position.y > height + 160
            if (targetIndex == targets.count - 1 && out) || elapsed > 35 {
                timer.invalidate()
                trail.birthRate = 0
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
                    overlay.orderOut(nil)
                    self?.rocketOverlay = nil
                }
            }
        }
    }

    /// Hand-drawn cartoon rocket: white fuselage, red nose cone and fins,
    /// blue porthole, twin-tone flame. Drawn nose-up, then rotated so the
    /// nose points along +x — the direction rotationMode(.rotateAuto)
    /// aligns with the path tangent.
    static func rocketSprite(size: CGFloat) -> CGImage? {
        let image = NSImage(size: NSSize(width: size, height: size))
        image.lockFocus()
        NSGraphicsContext.current?.imageInterpolation = .high
        let transform = NSAffineTransform()
        transform.translateX(by: size / 2, yBy: size / 2)
        transform.rotate(byDegrees: -90)
        transform.translateX(by: -size / 2, yBy: -size / 2)
        transform.concat()

        let w = size, h = size
        let cx = w / 2
        let red = NSColor(calibratedRed: 0.86, green: 0.22, blue: 0.2, alpha: 1)

        // Flame: orange teardrop with a yellow core, below the tail.
        let flame = NSBezierPath()
        flame.move(to: NSPoint(x: cx - 0.075 * w, y: 0.2 * h))
        flame.curve(
            to: NSPoint(x: cx, y: 0.02 * h),
            controlPoint1: NSPoint(x: cx - 0.06 * w, y: 0.1 * h),
            controlPoint2: NSPoint(x: cx - 0.02 * w, y: 0.05 * h)
        )
        flame.curve(
            to: NSPoint(x: cx + 0.075 * w, y: 0.2 * h),
            controlPoint1: NSPoint(x: cx + 0.02 * w, y: 0.05 * h),
            controlPoint2: NSPoint(x: cx + 0.06 * w, y: 0.1 * h)
        )
        flame.close()
        NSColor(calibratedRed: 1.0, green: 0.55, blue: 0.1, alpha: 1).setFill()
        flame.fill()
        let core = NSBezierPath(ovalIn: NSRect(
            x: cx - 0.04 * w, y: 0.11 * h, width: 0.08 * w, height: 0.11 * h
        ))
        NSColor(calibratedRed: 1.0, green: 0.85, blue: 0.3, alpha: 1).setFill()
        core.fill()

        // Fins, flaring out on both sides of the tail.
        for sign in [CGFloat(-1), 1] {
            let fin = NSBezierPath()
            fin.move(to: NSPoint(x: cx + sign * 0.13 * w, y: 0.4 * h))
            fin.line(to: NSPoint(x: cx + sign * 0.3 * w, y: 0.16 * h))
            fin.line(to: NSPoint(x: cx + sign * 0.13 * w, y: 0.22 * h))
            fin.close()
            red.setFill()
            fin.fill()
        }

        // Fuselage: capsule with a soft left-to-right shading gradient.
        let body = NSBezierPath(
            roundedRect: NSRect(x: cx - 0.14 * w, y: 0.18 * h, width: 0.28 * w, height: 0.6 * h),
            xRadius: 0.14 * w,
            yRadius: 0.2 * w
        )
        NSGradient(
            starting: NSColor.white,
            ending: NSColor(calibratedWhite: 0.72, alpha: 1)
        )?.draw(in: body, angle: 0)

        // Nose cone.
        let nose = NSBezierPath()
        nose.move(to: NSPoint(x: cx - 0.14 * w, y: 0.68 * h))
        nose.curve(
            to: NSPoint(x: cx, y: 0.99 * h),
            controlPoint1: NSPoint(x: cx - 0.12 * w, y: 0.85 * h),
            controlPoint2: NSPoint(x: cx - 0.05 * w, y: 0.96 * h)
        )
        nose.curve(
            to: NSPoint(x: cx + 0.14 * w, y: 0.68 * h),
            controlPoint1: NSPoint(x: cx + 0.05 * w, y: 0.96 * h),
            controlPoint2: NSPoint(x: cx + 0.12 * w, y: 0.85 * h)
        )
        nose.close()
        red.setFill()
        nose.fill()

        // Porthole: steel ring around blue glass.
        NSColor(calibratedWhite: 0.62, alpha: 1).setFill()
        NSBezierPath(ovalIn: NSRect(
            x: cx - 0.085 * w, y: 0.465 * h, width: 0.17 * w, height: 0.17 * w
        )).fill()
        NSColor(calibratedRed: 0.45, green: 0.72, blue: 0.95, alpha: 1).setFill()
        NSBezierPath(ovalIn: NSRect(
            x: cx - 0.06 * w, y: 0.465 * h + 0.025 * w, width: 0.12 * w, height: 0.12 * w
        )).fill()

        image.unlockFocus()
        return image.cgImage(forProposedRect: nil, context: nil, hints: nil)
    }

    // MARK: - Climate

    private func applyClimate(_ climate: Climate) {
        panel.avatarView.setClimate(climate)
        UserDefaults.standard.set(climate.rawValue, forKey: Self.climateKey)
        for (value, item) in climateItems {
            item.state = value == climate ? .on : .off
        }
    }

    @objc private func chooseClimate(_ sender: NSMenuItem) {
        guard let climate = sender.representedObject as? Climate else { return }
        applyClimate(climate)
    }

    // MARK: - Live positions

    private func applyLivePositions(_ on: Bool) {
        panel.avatarView.setLivePositions(on)
        UserDefaults.standard.set(on, forKey: Self.livePositionsKey)
        livePositionsItem.state = on ? .on : .off
    }

    @objc private func toggleLivePositions() {
        applyLivePositions(!panel.avatarView.livePositions)
    }

    // MARK: - World sensors

    private func startWorldSensors() {
        // Happy spin when the Mac wakes up with you.
        DistributedNotificationCenter.default().addObserver(
            forName: NSNotification.Name("com.apple.screenIsUnlocked"),
            object: nil, queue: .main
        ) { [weak self] _ in
            self?.panel.avatarView.setMood(.happy)
        }

        // Battery droop.
        checkBattery()
        batteryTimer = Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { [weak self] _ in
            self?.checkBattery()
        }
        batteryTimer?.tolerance = 60

        // Friday 6pm confetti.
        fridayTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            self?.checkFriday()
        }
        fridayTimer?.tolerance = 10

        updateMouseMonitor()

        // Suspend all rendering when the window is covered or off-screen.
        NotificationCenter.default.addObserver(
            forName: NSWindow.didChangeOcclusionStateNotification,
            object: panel, queue: .main
        ) { [weak self] _ in
            self?.updatePowerState()
        }
        // ...and when the screens sleep.
        let workspace = NSWorkspace.shared.notificationCenter
        workspace.addObserver(forName: NSWorkspace.screensDidSleepNotification, object: nil, queue: .main) { [weak self] _ in
            self?.screenAsleep = true
            self?.updatePowerState()
        }
        workspace.addObserver(forName: NSWorkspace.screensDidWakeNotification, object: nil, queue: .main) { [weak self] _ in
            self?.screenAsleep = false
            self?.updatePowerState()
        }
    }

    /// One place decides what may run: rendering, ISS polling, mouse watching.
    private func updatePowerState() {
        let visible = panel.occlusionState.contains(.visible) && !screenAsleep
        panel.avatarView.setSuspended(!visible)
        issFetcher.isActive = visible && panel.avatarView.body == .earth
        updateMouseMonitor()
    }

    /// The global mouse monitor wakes this process on every cursor move
    /// system-wide — only keep it installed while it can matter.
    private func updateMouseMonitor() {
        let wanted = panel.occlusionState.contains(.visible)
            && !screenAsleep
            && !panel.ignoresMouseEvents
        if wanted, mouseMonitor == nil {
            mouseMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.mouseMoved]) { [weak self] _ in
                self?.handleMouseMoved(NSEvent.mouseLocation)
            }
        } else if !wanted, let monitor = mouseMonitor {
            NSEvent.removeMonitor(monitor)
            mouseMonitor = nil
        }
    }

    private func checkBattery() {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/pmset")
        process.arguments = ["-g", "batt"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        guard (try? process.run()) != nil else { return }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard let output = String(data: data, encoding: .utf8) else { return }
        let discharging = output.contains("discharging")
        let percent = output.split(separator: ";").first
            .flatMap { $0.split(separator: "\t").last }
            .flatMap { Int($0.trimmingCharacters(in: CharacterSet(charactersIn: "% "))) }
        panel.avatarView.setLowPower(discharging && (percent ?? 100) <= 20)
    }

    private func checkFriday() {
        let now = Date()
        let calendar = Calendar.current
        let components = calendar.dateComponents([.weekday, .hour, .yearForWeekOfYear, .weekOfYear], from: now)
        guard components.weekday == 6, components.hour == 18 else { return }
        let dayStamp = "\(components.yearForWeekOfYear ?? 0)-\(components.weekOfYear ?? 0)"
        guard dayStamp != lastConfettiDay else { return }
        lastConfettiDay = dayStamp
        panel.avatarView.confettiBurst()
    }

    private func handleMouseMoved(_ point: NSPoint) {
        let now = ProcessInfo.processInfo.systemUptime
        defer { lastMouse = (point, now) }
        guard let last = lastMouse else { return }
        let dt = now - last.time
        guard dt > 0.001, dt < 0.2, now - lastDodge > 5 else { return }

        let velocity = CGVector(dx: (point.x - last.point.x) / dt, dy: (point.y - last.point.y) / dt)
        let speed = hypot(velocity.dx, velocity.dy)
        guard speed > 1300 else { return }

        let center = CGPoint(x: panel.frame.midX, y: panel.frame.midY)
        let toCenter = CGVector(dx: center.x - point.x, dy: center.y - point.y)
        let distance = hypot(toCenter.dx, toCenter.dy)
        guard distance > 60, distance < 420 else { return }

        // Only dodge if the cursor is actually headed at us.
        let alignment = (velocity.dx * toCenter.dx + velocity.dy * toCenter.dy) / (speed * distance)
        guard alignment > 0.8 else { return }

        lastDodge = now
        panel.avatarView.dodge(fromDX: velocity.dx)
    }

    // MARK: - Speed

    private func applyRates(rotation: Double, revolution: Double) {
        panel.avatarView.setRates(rotation: rotation, revolution: revolution)
        UserDefaults.standard.set(rotation, forKey: Self.rotationRateKey)
        UserDefaults.standard.set(revolution, forKey: Self.revolutionRateKey)
        for item in rotationRateItems {
            item.state = (item.representedObject as? Double) == rotation ? .on : .off
        }
        for item in revolutionRateItems {
            item.state = (item.representedObject as? Double) == revolution ? .on : .off
        }
    }

    @objc private func chooseRotationRate(_ sender: NSMenuItem) {
        guard let rate = sender.representedObject as? Double else { return }
        applyRates(rotation: rate, revolution: panel.avatarView.revolutionRate)
    }

    @objc private func chooseRevolutionRate(_ sender: NSMenuItem) {
        guard let rate = sender.representedObject as? Double else { return }
        applyRates(rotation: panel.avatarView.rotationRate, revolution: rate)
    }

    private func rateSubmenu(title: String, action: Selector, items: inout [NSMenuItem]) -> NSMenuItem {
        let submenu = NSMenu()
        for rate in Self.ratePresets {
            let label = rate == 1 ? "1× (Normal)" : String(format: rate < 1 ? "%.2g×" : "%.0f×", rate)
            let item = NSMenuItem(title: label, action: action, keyEquivalent: "")
            item.representedObject = rate
            submenu.addItem(item)
            items.append(item)
        }
        let parent = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        parent.submenu = submenu
        return parent
    }

    // MARK: - Status item

    private func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)

        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Show", action: #selector(show), keyEquivalent: ""))
        menu.addItem(.separator())
        for body in Body.allCases {
            let item = NSMenuItem(title: body.menuTitle, action: #selector(chooseBody(_:)), keyEquivalent: "")
            item.representedObject = body
            bodyMenuItems[body] = item
            menu.addItem(item)
        }
        menu.addItem(.separator())
        livePositionsItem = NSMenuItem(title: "Live Positions (Today)", action: #selector(toggleLivePositions), keyEquivalent: "")
        menu.addItem(livePositionsItem)

        let climateMenu = NSMenu()
        for climate in Climate.allCases {
            let item = NSMenuItem(title: climate.menuTitle, action: #selector(chooseClimate(_:)), keyEquivalent: "")
            item.representedObject = climate
            climateItems[climate] = item
            climateMenu.addItem(item)
        }
        let climateParent = NSMenuItem(title: "Climate (Earth)", action: nil, keyEquivalent: "")
        climateParent.submenu = climateMenu
        menu.addItem(climateParent)
        menu.addItem(.separator())
        menu.addItem(rateSubmenu(title: "Rotation Speed", action: #selector(chooseRotationRate(_:)), items: &rotationRateItems))
        menu.addItem(rateSubmenu(title: "Revolution Speed", action: #selector(chooseRevolutionRate(_:)), items: &revolutionRateItems))
        menu.addItem(.separator())
        interactiveMenuItem = NSMenuItem(title: "Interactive", action: #selector(chooseInteractive), keyEquivalent: "")
        transparentMenuItem = NSMenuItem(title: "Transparent (Click-Through)", action: #selector(chooseTransparent), keyEquivalent: "")
        menu.addItem(interactiveMenuItem)
        menu.addItem(transparentMenuItem)
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit CubeAssistant", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        statusItem.menu = menu
    }

    @objc private func show() {
        panel.orderFrontRegardless()
    }
}
