#!/usr/bin/env bash
# Build, bundle, sign, notarize and staple CubeAssistant for direct distribution.
#
#   scripts/release.sh [--version 1.0.0] [--build 1] [--skip-notarize]
#
# Environment:
#   SIGN_IDENTITY   Developer ID Application identity (default: first one in keychain)
#   NOTARY_PROFILE  notarytool keychain profile name (default: cubeassistant-notary)
#
# One-time setup for notarization (interactive, do this once):
#   xcrun notarytool store-credentials cubeassistant-notary \
#       --apple-id you@example.com --team-id 45NAN33T97
#   (use an app-specific password from appleid.apple.com, or pass
#    --key AuthKey.p8 --key-id XXXX --issuer YYYY for an App Store Connect API key)
#
# Output: dist/CubeAssistant-<version>.dmg (notarized + stapled) and dist/CubeAssistant.app
#
# Entitlements: Packaging/CubeAssistant.entitlements is intentionally empty
# (comments are not allowed in it; AMFI rejects them). Hardened Runtime comes
# from `codesign --options runtime`. The app is NOT sandboxed on purpose: it
# launches the `claude` CLI, `/bin/zsh -lc "which claude"` and `/usr/bin/pmset`
# and reads the user's shell PATH, none of which work in the App Sandbox. No
# hardened-runtime exceptions are needed (no JIT, no third-party dylibs;
# GLTFSceneKit is statically linked).
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$PWD
VERSION=1.0.0
BUILD=$(date +%Y%m%d%H%M)
NOTARIZE=1
while [[ $# -gt 0 ]]; do
  case $1 in
    --version) VERSION=$2; shift 2 ;;
    --build) BUILD=$2; shift 2 ;;
    --skip-notarize) NOTARIZE=0; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

APP_NAME=CubeAssistant
DIST=$ROOT/dist
DD=$ROOT/.build/xcode
PRODUCTS=$DD/Build/Products/Release
APP=$DIST/$APP_NAME.app
DMG=$DIST/$APP_NAME-$VERSION.dmg
SIGN_IDENTITY=${SIGN_IDENTITY:-$(security find-identity -v -p codesigning | grep -o '"Developer ID Application: [^"]*"' | head -1 | tr -d '"')}
NOTARY_PROFILE=${NOTARY_PROFILE:-cubeassistant-notary}

[[ -n $SIGN_IDENTITY ]] || { echo "no Developer ID Application identity found" >&2; exit 1; }
echo "==> version $VERSION ($BUILD), signing as: $SIGN_IDENTITY"

# 1. Universal release build via xcodebuild. (Not `swift build`: the SwiftPM
#    resource accessor it generates only looks next to the executable, which
#    codesign rejects as unsealed contents. Xcode's accessor checks
#    Contents/Resources first, for our bundle and GLTFSceneKit's.)
echo "==> building"
xcodebuild -scheme $APP_NAME -configuration Release -derivedDataPath "$DD" \
  -destination 'generic/platform=macOS' ARCHS='arm64 x86_64' ONLY_ACTIVE_ARCH=NO \
  -quiet build

# 2. Assemble the .app.
echo "==> assembling bundle"
rm -rf "$DIST"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$PRODUCTS/$APP_NAME" "$APP/Contents/MacOS/"
cp -R "$PRODUCTS/${APP_NAME}_${APP_NAME}.bundle" "$APP/Contents/Resources/"
cp -R "$PRODUCTS/GLTFSceneKit_GLTFSceneKit.bundle" "$APP/Contents/Resources/"
cp -R "$PRODUCTS/$APP_NAME.dSYM" "$DIST/"
sed -e "s/__VERSION__/$VERSION/" -e "s/__BUILD__/$BUILD/" \
  Packaging/Info.plist > "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"
cp Packaging/THIRD_PARTY.md "$APP/Contents/Resources/"

# Icon: render Earth with the app itself, then compose the icns.
if [[ ! -f Packaging/AppIcon.icns ]]; then
  echo "==> rendering app icon"
  "$PRODUCTS/$APP_NAME" --snapshot "$DIST/icon-earth.png" --body earth --size 1024 >/dev/null
  python3 scripts/make-icon.py "$DIST/icon-earth.png" Packaging/AppIcon.icns
  rm -f "$DIST/icon-earth.png"
fi
cp Packaging/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

# Strip any stray metadata that breaks sealing.
xattr -cr "$APP"
find "$APP" -name .DS_Store -delete

# 3. Sign inside-out with Hardened Runtime and a secure timestamp.
echo "==> signing"
for b in "$APP/Contents/Resources/"*.bundle; do
  codesign --force --sign "$SIGN_IDENTITY" --timestamp --options runtime "$b"
done
codesign --force --sign "$SIGN_IDENTITY" --timestamp --options runtime \
  --entitlements Packaging/CubeAssistant.entitlements "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

# 4. Notarize + staple the app itself, so the copy users drag out of the DMG
#    carries its own ticket and passes Gatekeeper on an offline first launch.
if [[ $NOTARIZE -eq 1 ]]; then
  echo "==> notarizing app (profile: $NOTARY_PROFILE)"
  ZIP=$DIST/$APP_NAME-notarize.zip
  ditto -c -k --keepParent "$APP" "$ZIP"
  xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
  rm -f "$ZIP"
  xcrun stapler staple "$APP"
  xcrun stapler validate "$APP"
fi

# 5. DMG around the stapled app, then notarize + staple the DMG too.
echo "==> building dmg"
STAGE=$DIST/dmg-root; rm -rf "$STAGE"; mkdir -p "$STAGE"
ditto "$APP" "$STAGE/$APP_NAME.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO -quiet "$DMG"
rm -rf "$STAGE"
codesign --force --sign "$SIGN_IDENTITY" --timestamp "$DMG"

if [[ $NOTARIZE -eq 1 ]]; then
  echo "==> notarizing dmg (profile: $NOTARY_PROFILE)"
  xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
else
  echo "==> skipping notarization"
fi

# 6. Gatekeeper assessment.
echo "==> verifying"
spctl --assess --type execute --verbose=2 "$APP" || true
[[ $NOTARIZE -eq 1 ]] && spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG" || true
if [[ $NOTARIZE -eq 1 ]]; then
  MNT=$(hdiutil attach -nobrowse -readonly "$DMG" | awk -F'\t' '/\/Volumes\//{print $NF}')
  xcrun stapler validate "$MNT/$APP_NAME.app" || { hdiutil detach -quiet "$MNT"; echo "app inside dmg is not stapled" >&2; exit 1; }
  hdiutil detach -quiet "$MNT"
fi
shasum -a 256 "$DMG"
echo "==> done: $DMG"
