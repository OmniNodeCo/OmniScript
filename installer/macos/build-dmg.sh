#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 1.0.4)"
echo "==> OmniScript $VERSION macOS DMG + PKG (OS integrated)"

# Build omni binary if not exists
if [ ! -f "$ROOT/omni" ]; then
  echo "    Building omni"
  make -C "$ROOT"
fi

BUILD_DIR="$ROOT/dist/dmg-build"
APP_DIR="$BUILD_DIR/OmniScript.app"
DMG_NAME="OmniScript-${VERSION}-macOS.dmg"
PKG_NAME="OmniScript-${VERSION}-macOS.pkg"
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

# Create a wrapper script that opens terminal with omni REPL if double-clicked?
# Actually Contents/MacOS/omni is already the binary, but macOS .app needs to be executable
# Make it so .app launches terminal: create a small launcher script
cat > "$APP_DIR/Contents/MacOS/OmniScript" <<'LAUNCH'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
# If launched from Finder, open Terminal with omni REPL
if [ -t 0 ]; then
  "$DIR/omni" "$@"
else
  osascript -e "tell application \"Terminal\" to do script \"\\\"$DIR/omni\\\"; exit\"" 2>/dev/null || "$DIR/omni"
fi
LAUNCH
chmod 755 "$APP_DIR/Contents/MacOS/OmniScript"

# Copy Info.plist with version substitution
sed "s/1.0.4/$VERSION/g" "$ROOT/installer/macos/Info.plist" > "$APP_DIR/Contents/Info.plist"

# Copy docs
cp "$ROOT/README.md" "$APP_DIR/Contents/Resources/" 2>/dev/null || true
cp "$ROOT/LICENSE" "$APP_DIR/Contents/Resources/" 2>/dev/null || true
cp -R "$ROOT/examples" "$APP_DIR/Contents/Resources/" 2>/dev/null || true

# Try to create icon from BMP if possible
if [ -x "$ROOT/omni" ]; then
  "$ROOT/omni" -e "import draw; draw.window(512,512); draw.rect(0,0,512,512,\"#0d1117\"); draw.circle(256,256,180,\"#1f6feb\"); draw.text(80,180,\"Omni\", \"white\", 80); draw.save(\"$BUILD_DIR/icon.bmp\")" >/dev/null 2>&1 || true
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

# Create CLI installer script for OS integration
cat > "$BUILD_DIR/install-cli.sh" <<EOS
#!/bin/bash
set -e
echo "==> OmniScript $VERSION — installing CLI into OS"
echo "    This will copy omni to /usr/local/bin so you can type 'omni' in terminal"
SRC="\$(cd "\$(dirname "\$0")" && pwd)/OmniScript.app/Contents/MacOS/omni"
if [ ! -f "\$SRC" ]; then
  SRC="\$(cd "\$(dirname "\$0")" && pwd)/omni"
fi
if [ ! -f "\$SRC" ]; then
  echo "omni binary not found"
  exit 1
fi
echo "    Found \$SRC"
echo "    Installing to /usr/local/bin/omni (needs sudo)"
sudo mkdir -p /usr/local/bin
sudo cp "\$SRC" /usr/local/bin/omni
sudo chmod 755 /usr/local/bin/omni
echo "    Installed! Try:"
echo "      omni --version"
echo "      omni"
echo "      omni examples/01_hello.omni"
# Also add to PATH hint for Apple Silicon homebrew shell
if ! echo "\$PATH" | grep -q "/usr/local/bin"; then
  echo "    NOTE: /usr/local/bin not in PATH, add to your shell profile:"
  echo "      echo 'export PATH=\"/usr/local/bin:\$PATH\"' >> ~/.zshrc"
fi
EOS
chmod +x "$BUILD_DIR/install-cli.sh"

# Also create a double-clickable .command file
cat > "$BUILD_DIR/Install CLI.command" <<EOS
#!/bin/bash
cd "\$(dirname "\$0")"
./install-cli.sh
echo "Press Enter to close"
read
EOS
chmod +x "$BUILD_DIR/Install CLI.command"

# Create DMG staging with OS integration
STAGE="$BUILD_DIR/dmg-staging"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP_DIR" "$STAGE/"
ln -s /Applications "$STAGE/Applications" 2>/dev/null || true
cp "$ROOT/README.md" "$STAGE/" 2>/dev/null || true
cp "$BUILD_DIR/install-cli.sh" "$STAGE/"
cp "$BUILD_DIR/Install CLI.command" "$STAGE/"
cat > "$STAGE/README.txt" <<READ
OmniScript $VERSION — very very very simple

1. Drag OmniScript.app to Applications (macOS app)
2. Double-click "Install CLI.command" to install 'omni' command into terminal
   Or run: ./install-cli.sh
   Then you can type in terminal:
     omni --version
     omni
     omni examples/01_hello.omni

The app and CLI are the same binary. After install, typing 'omni' in terminal reacts immediately.

Uninstall:
  sudo rm /usr/local/bin/omni
  rm -rf /Applications/OmniScript.app
READ

echo "    Building DMG $DIST_DIR/$DMG_NAME"

if command -v hdiutil >/dev/null 2>&1; then
  # macOS native DMG
  rm -f "$DIST_DIR/$DMG_NAME"
  hdiutil create -volname "OmniScript $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DIST_DIR/$DMG_NAME"
  echo "    DMG created: $DIST_DIR/$DMG_NAME"
  ls -lh "$DIST_DIR/$DMG_NAME"

  # Also build PKG installer for CLI (OS integrated)
  if command -v pkgbuild >/dev/null 2>&1; then
    echo "    Building PKG $DIST_DIR/$PKG_NAME"
    PKG_ROOT="$BUILD_DIR/pkgroot"
    rm -rf "$PKG_ROOT"
    mkdir -p "$PKG_ROOT/usr/local/bin"
    mkdir -p "$PKG_ROOT/Applications"
    cp -R "$APP_DIR" "$PKG_ROOT/Applications/"
    cp "$ROOT/omni" "$PKG_ROOT/usr/local/bin/omni"
    chmod 755 "$PKG_ROOT/usr/local/bin/omni"
    rm -f "$DIST_DIR/$PKG_NAME"
    pkgbuild --root "$PKG_ROOT" --identifier com.omninode.omniscript --version "$VERSION" --install-location / "$DIST_DIR/$PKG_NAME" 2>&1 | tail -n 20
    echo "    PKG created: $DIST_DIR/$PKG_NAME"
    ls -lh "$DIST_DIR/$PKG_NAME" 2>&1 || true
    rm -rf "$PKG_ROOT"
  else
    echo "    pkgbuild not found, skipping PKG (only on macOS)"
  fi

else
  # Linux fallback: create tar.gz that looks like dmg contents
  echo "    hdiutil not found (not on macOS), creating tar.gz fallback"
  tar -czf "$DIST_DIR/OmniScript-${VERSION}-macOS.tar.gz" -C "$STAGE" .
  echo "    Tarball created: $DIST_DIR/OmniScript-${VERSION}-macOS.tar.gz"
  ls -lh "$DIST_DIR/OmniScript-${VERSION}-macOS.tar.gz"
  # Also create a generic macOS tarball with app
  tar -czf "$DIST_DIR/OmniScript-${VERSION}-macOS-app.tar.gz" -C "$BUILD_DIR" OmniScript.app 2>/dev/null || true
  if command -v genisoimage >/dev/null 2>&1; then
    genisoimage -o "$DIST_DIR/$DMG_NAME" -V "OmniScript $VERSION" -r "$STAGE" 2>/dev/null || true
    echo "    ISO fallback created"
  fi
fi

# Cleanup
rm -rf "$BUILD_DIR"

echo "==> Done — after install, type 'omni' in terminal and it reacts"
