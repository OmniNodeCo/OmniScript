#!/usr/bin/env sh
# Install a self-contained OmniScript release binary on Linux or macOS.
set -eu

REPOSITORY="${OMNISCRIPT_REPOSITORY:-OmniNodeCo/OmniScript}"
VERSION="${OMNISCRIPT_VERSION:-latest}"
NIGHTLY_RUN="${OMNISCRIPT_NIGHTLY_RUN:-32034373761}"
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
if [ "$OS" = "macos" ] && [ "$ARCH" != "arm64" ]; then
    echo "error: prebuilt macOS releases support Apple Silicon ARM64 only" >&2
    exit 1
fi

ASSET="omni-$OS-$ARCH"
if [ "$VERSION" = "latest" ]; then
    RELEASE_BASE="https://github.com/$REPOSITORY/releases/latest/download"
else
    VERSION=${VERSION#v}
    RELEASE_BASE="https://github.com/$REPOSITORY/releases/download/v$VERSION"
fi

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omniscript.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

echo "Looking for $ASSET in $REPOSITORY releases ($VERSION)"
RELEASE_AVAILABLE=1
curl -fsSL --retry 3 --connect-timeout 15 "$RELEASE_BASE/$ASSET" -o "$TMP_DIR/$ASSET" || RELEASE_AVAILABLE=0
if [ "$RELEASE_AVAILABLE" -eq 1 ]; then
    curl -fsSL --retry 3 --connect-timeout 15 "$RELEASE_BASE/SHA256SUMS" -o "$TMP_DIR/SHA256SUMS" || RELEASE_AVAILABLE=0
fi

if [ "$RELEASE_AVAILABLE" -eq 1 ]; then
    EXPECTED=$(awk -v asset="$ASSET" '$2 == asset || $2 == "*" asset { print $1; exit }' "$TMP_DIR/SHA256SUMS")
    if [ -z "$EXPECTED" ]; then
        echo "error: $ASSET is missing from SHA256SUMS" >&2
        exit 1
    fi
    VERIFY_FILE="$TMP_DIR/$ASSET"
else
    rm -f "$TMP_DIR/$ASSET" "$TMP_DIR/SHA256SUMS"
    if [ "$VERSION" != "latest" ]; then
        echo "error: OmniScript release v$VERSION was not found" >&2
        exit 1
    fi
    if ! command -v unzip >/dev/null 2>&1; then
        echo "error: unzip is required to install the nightly build" >&2
        exit 1
    fi
    echo "warning: no GitHub release exists yet; installing verified nightly run $NIGHTLY_RUN" >&2
    case "$ASSET" in
        omni-linux-arm64) EXPECTED=ab131448bf0cf12e1c9599c7371496d882e57b3ae1a125c57d85f05c1163c89f ;;
        omni-linux-x86_64) EXPECTED=65629e6c4ac4e376b87916e9e109e1ecbe9c130dbec7d65ac6414d5157353099 ;;
        omni-macos-arm64) EXPECTED=685432cb3356febc718584306700a5696bcc02b012384fdd92381002f0e5421b ;;
        *) echo "error: no trusted nightly digest is registered for $ASSET" >&2; exit 1 ;;
    esac
    VERIFY_FILE="$TMP_DIR/$ASSET.zip"
    NIGHTLY_URL="https://nightly.link/$REPOSITORY/actions/runs/$NIGHTLY_RUN/$ASSET.zip"
    curl -fsSL --retry 3 --connect-timeout 15 "$NIGHTLY_URL" -o "$VERIFY_FILE"
fi

if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL=$(sha256sum "$VERIFY_FILE" | awk '{print $1}')
else
    ACTUAL=$(shasum -a 256 "$VERIFY_FILE" | awk '{print $1}')
fi
if [ "$EXPECTED" != "$ACTUAL" ]; then
    echo "error: checksum verification failed for $ASSET" >&2
    exit 1
fi
if [ "$RELEASE_AVAILABLE" -eq 0 ]; then
    unzip -p "$VERIFY_FILE" "$ASSET" > "$TMP_DIR/$ASSET"
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
