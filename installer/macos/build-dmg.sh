#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 1.0.0)"
echo "==> OmniScript $VERSION macOS DMG"

# Build omni binary if not exists
if [ ! -f "$ROOT/omni" ]; then
  echo "    Building omni"
  make -C "$ROOT"
fi

BUILD_DIR="$ROOT/dist/dmg-build"
APP_DIR="$BUILD_DIR/OmniScript.app"
DMG_NAME="OmniScript-${VERSION}-macOS.dmg"
DIST_DIR="$ROOT/dist"
mkdir -p "$DIST_DIR" "$BUILD_DIR"

echo "    Creating app bundle at $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
mkdir -p "$APP_DIR/Contents/Resources/examples"

# Copy binary
cp "$ROOT/omni" "$APP_DIR/Contents/MacOS/omni"
chmod 755 "$APP_DIR/Contents/MacOS/omni"

# Copy Info.plist with version substitution
sed "s/1.0.0/$VERSION/g" "$ROOT/installer/macos/Info.plist" > "$APP_DIR/Contents/Info.plist"

# Copy docs
cp "$ROOT/README.md" "$APP_DIR/Contents/Resources/" 2>/dev/null || true
cp "$ROOT/LICENSE" "$APP_DIR/Contents/Resources/" 2>/dev/null || true
cp -R "$ROOT/examples" "$APP_DIR/Contents/Resources/" 2>/dev/null || true

# Try to create icon from BMP if possible
# Generate icon BMP using omni itself
if [ -x "$ROOT/omni" ]; then
  "$ROOT/omni" -e "import draw; draw.window(512,512); draw.rect(0,0,512,512,\"#0d1117\"); draw.circle(256,256,180,\"#1f6feb\"); draw.text(80,180,\"Omni\", \"white\", 80); draw.save(\"$BUILD_DIR/icon.bmp\")" >/dev/null 2>&1 || true
  # Convert to icns if tools available (sips + iconutil on macOS)
  if command -v sips >/dev/null 2>&1 && [ -f "$BUILD_DIR/icon.bmp" ]; then
    mkdir -p "$BUILD_DIR/icon.iconset"
    sips -z 16 16 "$BUILD_DIR/icon.bmp" --out "$BUILD_DIR/icon.iconset/icon_16x16.png" >/dev/null 2>&1 || true
    sips -z 32 32 "$BUILD_DIR/icon.bmp" --out "$BUILD_DIR/icon.iconset/icon_16x16@2x.png" >/dev/null 2>&1 || true
    sips -z 32 32 "$BUILD_DIR/icon.bmp" --out "$BUILD_DIR/icon.iconset/icon_32x32.png" >/dev/null 2>&1 || true
    sips -z 64 64 "$BUILD_DIR/icon.bmp" --out "$BUILD_DIR/icon.iconset/icon_32x32@2x.png" >/dev/null 2>&1 || true
    sips -z 128 128 "$BUILD_DIR/icon.bmp" --out "$BUILD_DIR/icon.iconset/icon_128x128.png" >/dev/null 2>&1 || true
    sips -z 256 256 "$BUILD_DIR/icon.bmp" --out "$BUILD_DIR/icon.iconset/icon_128x128@2x.png" >/dev/null 2>&1 || true
    sips -z 256 256 "$BUILD_DIR/icon.bmp" --out "$BUILD_DIR/icon.iconset/icon_256x256.png" >/dev/null 2>&1 || true
    sips -z 512 512 "$BUILD_DIR/icon.bmp" --out "$BUILD_DIR/icon.iconset/icon_256x256@2x.png" >/dev/null 2>&1 || true
    if command -v iconutil >/dev/null 2>&1; then
      iconutil -c icns "$BUILD_DIR/icon.iconset" -o "$APP_DIR/Contents/Resources/AppIcon.icns" 2>/dev/null || true
    fi
  fi
fi

# Create DMG staging
STAGE="$BUILD_DIR/dmg-staging"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP_DIR" "$STAGE/"
ln -s /Applications "$STAGE/Applications" 2>/dev/null || true
cp "$ROOT/README.md" "$STAGE/" 2>/dev/null || true

echo "    Building DMG $DIST_DIR/$DMG_NAME"

if command -v hdiutil >/dev/null 2>&1; then
  # macOS native
  rm -f "$DIST_DIR/$DMG_NAME"
  hdiutil create -volname "OmniScript $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DIST_DIR/$DMG_NAME"
  echo "    DMG created: $DIST_DIR/$DMG_NAME"
  ls -lh "$DIST_DIR/$DMG_NAME"
else
  # Linux fallback: create tar.gz that looks like dmg contents, or use genisoimage if available
  echo "    hdiutil not found (not on macOS), creating tar.gz fallback"
  tar -czf "$DIST_DIR/OmniScript-${VERSION}-macOS.tar.gz" -C "$STAGE" .
  echo "    Tarball created: $DIST_DIR/OmniScript-${VERSION}-macOS.tar.gz"
  ls -lh "$DIST_DIR/OmniScript-${VERSION}-macOS.tar.gz"
  # If genisoimage available, try to make iso
  if command -v genisoimage >/dev/null 2>&1; then
    genisoimage -o "$DIST_DIR/$DMG_NAME" -V "OmniScript $VERSION" -r "$STAGE" 2>/dev/null || true
    echo "    ISO fallback created"
  fi
fi

# Cleanup
rm -rf "$BUILD_DIR"

echo "==> Done"
