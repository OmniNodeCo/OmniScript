#!/usr/bin/env sh
set -eu

BIN_DIR="${OMNISCRIPT_BIN_DIR:-$HOME/.local/bin}"
LEGACY_DIR="${OMNISCRIPT_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/omniscript}"
CACHE_DIR="${OMNISCRIPT_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/omniscript}"

rm -f "$BIN_DIR/omni" "$BIN_DIR/omniscript"
rm -rf "$CACHE_DIR"
# Clean installations made by OmniScript 0.1's original Python installer.
rm -rf "$LEGACY_DIR"
echo "OmniScript was removed from $BIN_DIR"
echo "OmniScript cache was removed from $CACHE_DIR"
