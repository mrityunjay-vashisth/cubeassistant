// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "CubeAssistant",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(url: "https://github.com/magicien/GLTFSceneKit.git", exact: "0.4.1")
    ],
    targets: [
        .executableTarget(
            name: "CubeAssistant",
            dependencies: ["GLTFSceneKit"],
            path: "Sources/CubeAssistant",
            resources: [
                .copy("Resources/sun171.jpg"),
                .copy("Resources/mercury.glb"),
                .copy("Resources/venus.glb"),
                .copy("Resources/earth.glb"),
                .copy("Resources/mars.glb"),
                .copy("Resources/jupiter.glb"),
                .copy("Resources/saturn.usdz"),
                .copy("Resources/uranus.glb"),
                .copy("Resources/neptune.glb"),
                .copy("Resources/moon.glb"),
                .copy("Resources/clouds.jpg"),
                .copy("Resources/plane_aero.glb"),
                .copy("Resources/tree_leafy.glb"),
                .copy("Resources/tree_pine.glb"),
                .copy("Resources/tree_palm.glb")
            ]
        )
    ]
)
