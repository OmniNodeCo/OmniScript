#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 1.0.0)"
ARCH="amd64"
if [ "$(uname -m)" = "aarch64" ] || [ "$(uname -m)" = "arm64" ]; then ARCH="arm64"; fi

echo "==> OmniScript $VERSION Linux DEB ($ARCH) — OS integrated"

# Build omni if needed
if [ ! -f "$ROOT/omni" ]; then
  echo "    Building omni"
  make -C "$ROOT"
fi

DIST_DIR="$ROOT/dist"
BUILD_DIR="$DIST_DIR/deb-build/omniscript_${VERSION}_${ARCH}"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/share/doc/omniscript"
mkdir -p "$BUILD_DIR/usr/share/omniscript/examples"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/64x64/apps"

# Control file
cat > "$BUILD_DIR/DEBIAN/control" <<CONTROL
Package: omniscript
Version: $VERSION
Section: devel
Priority: optional
Architecture: $ARCH
Maintainer: OmniNodeCo <hello@omninode.co>
Description: OmniScript — very very very simple language
 Tiny language with draw, cmd, pathlib modules.
 Imports like Python: import draw, cmd, pathlib.
 One binary, libc only.
 After install, type 'omni' in terminal and it reacts.
Homepage: https://github.com/OmniNodeCo/OmniScript
CONTROL

# Binary — OS integrated into /usr/bin
cp "$ROOT/omni" "$BUILD_DIR/usr/bin/omni"
chmod 755 "$BUILD_DIR/usr/bin/omni"

# Docs
cp "$ROOT/README.md" "$BUILD_DIR/usr/share/doc/omniscript/" 2>/dev/null || true
cp "$ROOT/LICENSE" "$BUILD_DIR/usr/share/doc/omniscript/" 2>/dev/null || true
cp "$ROOT/VERSION" "$BUILD_DIR/usr/share/doc/omniscript/" 2>/dev/null || true
cp -r "$ROOT/examples"/* "$BUILD_DIR/usr/share/omniscript/examples/" 2>/dev/null || true

# Desktop file — OS integrated launcher
cat > "$BUILD_DIR/usr/share/applications/omniscript.desktop" <<DESKTOP
[Desktop Entry]
Name=OmniScript
GenericName=OmniScript Language
Comment=Tiny language — draw, cmd, pathlib — type 'omni' in terminal
Exec=omni
Icon=omniscript
Terminal=true
Type=Application
Categories=Development;
Keywords=omni;script;
StartupNotify=false
DESKTOP

# Postinst — tell user OS integration works
cat > "$BUILD_DIR/DEBIAN/postinst" <<POSTINST
#!/bin/sh
set -e
echo "==> OmniScript $VERSION installed into OS"
echo "    Binary: /usr/bin/omni"
echo "    Now type in terminal and it reacts:"
echo "      omni --version"
echo "      omni"
echo "      omni /usr/share/omniscript/examples/01_hello.omni"
# Update desktop database if available
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications 2>/dev/null || true
fi
# Test that omni reacts
if [ -x /usr/bin/omni ]; then
  /usr/bin/omni --version 2>&1 || true
fi
exit 0
POSTINST
chmod 755 "$BUILD_DIR/DEBIAN/postinst"

cat > "$BUILD_DIR/DEBIAN/postrm" <<POSTRM
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications 2>/dev/null || true
fi
echo "OmniScript removed. 'omni' command no longer available."
exit 0
POSTRM
chmod 755 "$BUILD_DIR/DEBIAN/postrm"

# Icon — generate via omni if possible
if [ -x "$ROOT/omni" ]; then
  "$ROOT/omni" -e "import draw; draw.window(64,64); draw.rect(0,0,64,64,\"#0d1117\"); draw.circle(32,32,20,\"#1f6feb\"); draw.text(8,20,\"Om\", \"white\", 14); draw.save(\"$BUILD_DIR/usr/share/icons/hicolor/64x64/apps/omniscript.bmp\")" >/dev/null 2>&1 || true
  if [ -f "$BUILD_DIR/usr/share/icons/hicolor/64x64/apps/omniscript.bmp" ]; then
    if command -v convert >/dev/null 2>&1; then
      convert "$BUILD_DIR/usr/share/icons/hicolor/64x64/apps/omniscript.bmp" "$BUILD_DIR/usr/share/icons/hicolor/64x64/apps/omniscript.png" 2>/dev/null || true
      rm "$BUILD_DIR/usr/share/icons/hicolor/64x64/apps/omniscript.bmp"
    fi
  fi
fi

# Build deb
mkdir -p "$DIST_DIR"
DEB_FILE="$DIST_DIR/omniscript_${VERSION}_${ARCH}.deb"

if command -v dpkg-deb >/dev/null 2>&1; then
  dpkg-deb --build "$BUILD_DIR" "$DEB_FILE"
  echo "    DEB created: $DEB_FILE — install then type 'omni' and it reacts"
  ls -lh "$DEB_FILE"
else
  echo "    dpkg-deb not found, creating tar.gz fallback"
  tar -czf "$DIST_DIR/omniscript-${VERSION}-linux-${ARCH}.tar.gz" -C "$BUILD_DIR" usr/
  echo "    Tarball: $DIST_DIR/omniscript-${VERSION}-linux-${ARCH}.tar.gz"
  ls -lh "$DIST_DIR/omniscript-${VERSION}-linux-${ARCH}.tar.gz"
fi

# Also always create tar.gz
TAR_FILE="$DIST_DIR/omniscript-${VERSION}-linux-${ARCH}.tar.gz"
if [ ! -f "$TAR_FILE" ]; then
  tar -czf "$TAR_FILE" -C "$ROOT" omni README.md LICENSE VERSION examples/ 2>/dev/null || tar -czf "$TAR_FILE" -C "$BUILD_DIR" usr/
  echo "    Tarball created: $TAR_FILE"
  ls -lh "$TAR_FILE"
fi

# Cleanup
rm -rf "$DIST_DIR/deb-build"

echo "==> Done — after 'sudo dpkg -i $DEB_FILE', type 'omni' in terminal and it reacts"
