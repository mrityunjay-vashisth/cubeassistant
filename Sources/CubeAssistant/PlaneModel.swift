import AppKit
import SceneKit
import GLTFSceneKit

/// The Blender-built cartoon plane used for desktop flights.
/// Loads nose along +X with wingspan normalized to 1, and exposes the
/// "Prop" node so the propeller can spin.
enum PlaneModel {
    static func load() -> (root: SCNNode, prop: SCNNode?)? {
        guard let url = Bundle.module.url(forResource: "plane_aero", withExtension: "glb") else { return nil }
        let holder = SCNNode()
        do {
            // Explicit `try` so Swift picks GLTFSceneKit's throwing scene()
            // override — the inherited SCNSceneSource.scene() crashes on GLB.
            let scene = try GLTFSceneSource(url: url).scene()
            for child in scene.rootNode.childNodes {
                holder.addChildNode(child)
            }
        } catch {
            NSLog("Failed to load plane_aero.glb: \(error)")
            return nil
        }
        holder.enumerateHierarchy { node, _ in
            for material in node.geometry?.materials ?? [] {
                material.shaderModifiers = nil
                material.lightingModel = .lambert
            }
        }
        let (minBox, maxBox) = holder.boundingBox
        let span = CGFloat(maxBox.z - minBox.z)   // wings lie along ±Z
        guard span > 0 else { return nil }
        let scale = 1.0 / span
        holder.scale = SCNVector3(scale, scale, scale)
        holder.position = SCNVector3(
            -CGFloat(minBox.x + maxBox.x) / 2 * scale,
            -CGFloat(minBox.y + maxBox.y) / 2 * scale,
            -CGFloat(minBox.z + maxBox.z) / 2 * scale
        )
        let wrapper = SCNNode()
        wrapper.addChildNode(holder)
        let prop = wrapper.childNode(withName: "Prop", recursively: true)
        return (wrapper, prop)
    }
}
