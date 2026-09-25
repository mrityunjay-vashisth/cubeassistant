import AppKit

/// Borderless transparent always-on-top window hosting the celestial body.
final class FloatingPanel: NSWindow {
    private static let originKey = "CubeAssistant.origin"
    private static let sizeKey = "CubeAssistant.size"
    private static let sizeRange: ClosedRange<CGFloat> = 100...600

    let avatarView = AvatarView()

    init() {
        let saved = CGFloat(UserDefaults.standard.double(forKey: Self.sizeKey))
        let side = Self.sizeRange.contains(saved) ? saved : 200
        let size = NSSize(width: side, height: side)
        super.init(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        isReleasedWhenClosed = false

        contentView = avatarView

        setFrameOrigin(Self.restoredOrigin(for: size))
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(saveOrigin),
            name: NSWindow.didMoveNotification,
            object: self
        )
    }

    override var canBecomeKey: Bool { true }

    /// Pinch-to-resize: scale the window around its center, staying square.
    func scaleBy(_ factor: CGFloat) {
        let side = min(max(frame.width * factor, Self.sizeRange.lowerBound), Self.sizeRange.upperBound)
        let newFrame = NSRect(
            x: frame.midX - side / 2,
            y: frame.midY - side / 2,
            width: side,
            height: side
        )
        setFrame(newFrame, display: true)
        UserDefaults.standard.set(Double(side), forKey: Self.sizeKey)
        saveOrigin()
    }

    @objc private func saveOrigin() {
        UserDefaults.standard.set(
            NSStringFromPoint(frame.origin),
            forKey: Self.originKey
        )
    }

    private static func restoredOrigin(for size: NSSize) -> NSPoint {
        if let saved = UserDefaults.standard.string(forKey: originKey) {
            let origin = NSPointFromString(saved)
            // Only restore if still on some screen.
            let frame = NSRect(origin: origin, size: size)
            if NSScreen.screens.contains(where: { $0.visibleFrame.intersects(frame) }) {
                return origin
            }
        }
        let visible = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        return NSPoint(x: visible.maxX - size.width - 30, y: visible.minY + 40)
    }
}
