#!/usr/bin/env sh
# Install a self-contained OmniScript release binary on Linux or macOS.
set -eu

REPOSITORY="${OMNISCRIPT_REPOSITORY:-OmniNodeCo/OmniScript}"
VERSION="${OMNISCRIPT_VERSION:-latest}"
BIN_DIR="${OMNISCRIPT_BIN_DIR:-$HOME/.local/bin}"

if ! command -v curl >/dev/null 2>&1; then
    echo "error: curl is required" >&2
    exit 1
fi

case "$(uname -s)" in
    Linux) OS=linux ;;
    Darwin) OS=macos ;;
    *) echo "error: OmniScript binaries support Linux and macOS; use install.bat on Windows" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64|amd64) ARCH=x86_64 ;;
    arm64|aarch64) ARCH=arm64 ;;
    *) echo "error: unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac

ASSET="omni-$OS-$ARCH"
if [ "$VERSION" = "latest" ]; then
    RELEASE_BASE="https://github.com/$REPOSITORY/releases/latest/download"
else
    VERSION=${VERSION#v}
    RELEASE_BASE="https://github.com/$REPOSITORY/releases/download/v$VERSION"
fi

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omniscript.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

echo "Downloading $ASSET from $REPOSITORY ($VERSION)"
curl -fL --retry 3 --connect-timeout 15 "$RELEASE_BASE/$ASSET" -o "$TMP_DIR/$ASSET"
curl -fL --retry 3 --connect-timeout 15 "$RELEASE_BASE/SHA256SUMS" -o "$TMP_DIR/SHA256SUMS"

EXPECTED=$(awk -v asset="$ASSET" '$2 == asset || $2 == "*" asset { print $1; exit }' "$TMP_DIR/SHA256SUMS")
if [ -z "$EXPECTED" ]; then
    echo "error: $ASSET is missing from SHA256SUMS" >&2
    exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL=$(sha256sum "$TMP_DIR/$ASSET" | awk '{print $1}')
else
    ACTUAL=$(shasum -a 256 "$TMP_DIR/$ASSET" | awk '{print $1}')
fi
if [ "$EXPECTED" != "$ACTUAL" ]; then
    echo "error: checksum verification failed for $ASSET" >&2
    exit 1
fi

mkdir -p "$BIN_DIR"
chmod 755 "$TMP_DIR/$ASSET"
mv "$TMP_DIR/$ASSET" "$BIN_DIR/omni"
ln -sf "$BIN_DIR/omni" "$BIN_DIR/omniscript"
if [ "$OS" = "macos" ] && command -v xattr >/dev/null 2>&1; then
    xattr -d com.apple.quarantine "$BIN_DIR/omni" 2>/dev/null || true
fi

echo "OmniScript installed to $BIN_DIR/omni"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "note: add $BIN_DIR to your PATH" ;;
esac
"$BIN_DIR/omni" --version
