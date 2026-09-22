#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(cat "$ROOT/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 1.0.1)"

echo "==> OmniScript $VERSION — building all installers"
echo "    Root: $ROOT"

# Clean and build binary
make -C "$ROOT" clean
make -C "$ROOT" -j4
"$ROOT/omni" --version

DIST="$ROOT/dist"
mkdir -p "$DIST"

# 1. Tarball (generic)
echo ""
echo "==> Generic tarball"
tar -czf "$DIST/omniscript-${VERSION}.tar.gz" -C "$ROOT" --exclude='.git' --exclude='dist' --exclude='*.o' --exclude='omni' --exclude='omni.exe' .
ls -lh "$DIST/omniscript-${VERSION}.tar.gz"

# 2. Linux DEB + tar.gz
echo ""
if [ -f "$ROOT/installer/linux/build-deb.sh" ]; then
  bash "$ROOT/installer/linux/build-deb.sh"
else
  echo "    Skipping Linux DEB — script not found"
fi

# 2b. Linux RPM
echo ""
if [ -f "$ROOT/installer/linux/build-rpm.sh" ]; then
  bash "$ROOT/installer/linux/build-rpm.sh" || echo "    RPM build skipped/failed"
else
  echo "    Skipping Linux RPM"
fi

# 3. macOS DMG (will create tar.gz fallback on Linux)
echo ""
if [ -f "$ROOT/installer/macos/build-dmg.sh" ]; then
  bash "$ROOT/installer/macos/build-dmg.sh"
else
  echo "    Skipping macOS DMG"
fi

# 4. Windows — note about Inno Setup
echo ""
echo "==> Windows installer"
echo "    To build Windows EXE installer, on Windows run:"
echo "      installer\\windows\\build.bat"
echo "    Or with PowerShell:"
echo "      powershell -ExecutionPolicy Bypass -File installer\\windows\\build.ps1"
echo "    Requires Inno Setup 6: https://jrsoftware.org/isinfo.php"
echo "    Output will be in dist/OmniScript-${VERSION}-Windows-x86_64-Setup.exe"

# If we are on Linux and have iscc via wine or native, try?
if command -v iscc >/dev/null 2>&1; then
  echo "    ISCC found, building Windows installer..."
  (cd "$ROOT/installer/windows" && iscc /DMyAppVersion="$VERSION" OmniScript.iss) || echo "    ISCC build failed"
fi

echo ""
echo "==> All done. Files in $DIST:"
ls -lh "$DIST"

# SHA256 sums
echo ""
echo "==> SHA256SUMS"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$DIST" && sha256sum * > SHA256SUMS.txt && cat SHA256SUMS.txt)
elif command -v shasum >/dev/null 2>&1; then
  (cd "$DIST" && shasum -a 256 * > SHA256SUMS.txt && cat SHA256SUMS.txt)
fi
