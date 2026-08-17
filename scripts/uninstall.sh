#!/usr/bin/env sh
set -eu

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="${OMNISCRIPT_INSTALL_DIR:-$DATA_HOME/omniscript}"
BIN_DIR="${OMNISCRIPT_BIN_DIR:-$HOME/.local/bin}"

rm -rf "$INSTALL_DIR"
rm -f "$BIN_DIR/omni" "$BIN_DIR/omniscript"
echo "OmniScript was removed from $INSTALL_DIR"
