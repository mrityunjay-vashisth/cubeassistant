# CubeAssistant

A little planet that floats on your Mac desktop. Drag Earth around, switch to the Sun or other worlds, and now and then a rocket launches from it and flies a lap around your screen.

- SwiftUI + SceneKit, 3D models loaded with GLTFSceneKit
- Live ISS position and solar imagery
- Optional chat through the Claude Code CLI on your machine (`claude -p`); there is no bundled model

Download the signed app and watch the 30 second demo: https://nibblcorp.com/cubeassistant

Requires macOS 14 or later, Apple Silicon or Intel.

## Build

```sh
swift build -c release
.build/release/CubeAssistant
```

`scripts/release.sh` builds, signs and notarizes a DMG (needs your own Developer ID and notary profile).

Render a still for checking visuals:

```sh
.build/release/CubeAssistant --snapshot out.png --body earth
```

Third-party code, imagery and models are listed in `Packaging/THIRD_PARTY.md`.
