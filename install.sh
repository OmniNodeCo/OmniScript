#!/usr/bin/env sh
# Install a self-contained OmniScript release binary on Linux or macOS.
set -eu

REPOSITORY="${OMNISCRIPT_REPOSITORY:-OmniNodeCo/OmniScript}"
BUNDLED_VERSION=0.2.1
VERSION="${OMNISCRIPT_VERSION:-$BUNDLED_VERSION}"
CHANNEL="${OMNISCRIPT_CHANNEL:-auto}"
NIGHTLY_RUN="${OMNISCRIPT_NIGHTLY_RUN:-32053497470}"
BIN_DIR="${OMNISCRIPT_BIN_DIR:-$HOME/.local/bin}"
CACHE_DIR="${OMNISCRIPT_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/omniscript}"

case "$CHANNEL" in
    auto|release|nightly) ;;
    *) echo "error: OMNISCRIPT_CHANNEL must be auto, release, or nightly" >&2; exit 1 ;;
esac

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

RELEASE_AVAILABLE=0
if [ "$CHANNEL" != "nightly" ]; then
    echo "Looking for $ASSET in $REPOSITORY releases ($VERSION)"
    RELEASE_AVAILABLE=1
    curl -fsSL --retry 3 --connect-timeout 15 "$RELEASE_BASE/$ASSET" -o "$TMP_DIR/$ASSET" || RELEASE_AVAILABLE=0
    if [ "$RELEASE_AVAILABLE" -eq 1 ]; then
        curl -fsSL --retry 3 --connect-timeout 15 "$RELEASE_BASE/SHA256SUMS" -o "$TMP_DIR/SHA256SUMS" || RELEASE_AVAILABLE=0
    fi
else
    echo "Installing $ASSET from the nightly channel"
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
    if [ "$CHANNEL" = "release" ]; then
        echo "error: no matching OmniScript release was found" >&2
        exit 1
    fi
    if [ "$CHANNEL" = "auto" ] && [ "$VERSION" != "latest" ] && [ "$VERSION" != "$BUNDLED_VERSION" ]; then
        echo "error: OmniScript release v$VERSION was not found" >&2
        exit 1
    fi
    if ! command -v unzip >/dev/null 2>&1; then
        echo "error: unzip is required to install the nightly build" >&2
        exit 1
    fi
    if [ "$CHANNEL" = "nightly" ]; then
        echo "installing verified nightly run $NIGHTLY_RUN" >&2
    else
        echo "warning: release v$BUNDLED_VERSION is not published yet; installing verified run $NIGHTLY_RUN" >&2
    fi
    case "$ASSET" in
        omni-linux-arm64) EXPECTED=163a25b2eaf0504867729a83c6886402794cc020878057ae558b0c21ccabbca6 ;;
        omni-linux-x86_64) EXPECTED=d3bba9878144032fb4f9475c543ad2c3e2e47278479704ca65fb7bb1575f7824 ;;
        omni-macos-arm64) EXPECTED=8e3ba7fedbcd4a8ce46564f78fc25b2bd3af343182e7db34f52ada95adc30536 ;;
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
# A newly published release must not be hidden by an older cached 404.
rm -rf "$CACHE_DIR"
if [ "$OS" = "macos" ] && command -v xattr >/dev/null 2>&1; then
    xattr -d com.apple.quarantine "$BIN_DIR/omni" 2>/dev/null || true
fi

echo "OmniScript installed to $BIN_DIR/omni"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "note: add $BIN_DIR to your PATH" ;;
esac
"$BIN_DIR/omni" --version
