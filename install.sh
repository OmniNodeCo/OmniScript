#!/usr/bin/env bash
set -euo pipefail
PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(cat "$SRC_DIR/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 2.0.0)"

echo "==> OmniScript $VERSION — super simple"
echo "    Building from $SRC_DIR"

CC=""
for c in cc gcc clang; do
  if command -v "$c" >/dev/null 2>&1; then CC="$c"; break; fi
done
[ -n "$CC" ] || { echo "no C compiler found"; exit 1; }

mkdir -p "$BIN_DIR"
SRC="$SRC_DIR/src/util.c $SRC_DIR/src/lex.c $SRC_DIR/src/parse.c $SRC_DIR/src/eval.c $SRC_DIR/src/draw.c $SRC_DIR/src/main.c"
CFLAGS="-O2 -std=c11 -Wall -Wextra -DOMNI_VERSION=\"$VERSION\" -D_POSIX_C_SOURCE=200809L"
LDLIBS=""

if [ -f /usr/include/X11/Xlib.h ] || [ -f /usr/local/include/X11/Xlib.h ]; then
  SRC="$SRC $SRC_DIR/src/gui_x11.c"
  CFLAGS="$CFLAGS -DHAVE_X11"
  LDLIBS="$LDLIBS -lX11"
  echo "    X11 found — with GUI"
else
  SRC="$SRC $SRC_DIR/src/gui_stub.c"
  echo "    No X11 — drawings become BMP files"
fi

echo "==> Compiling with $CC"
$CC $CFLAGS -o "$SRC_DIR/omni" $SRC $LDLIBS

echo "==> Installing to $BIN_DIR/omni"
cp "$SRC_DIR/omni" "$BIN_DIR/omni"
chmod 755 "$BIN_DIR/omni"

echo "==> Checking"
"$BIN_DIR/omni" --version
"$BIN_DIR/omni" -e 'import draw; draw.window(100,100); draw.rect(0,0,50,50,"red"); draw.save("test.bmp"); print("ok")'
rm -f test.bmp

echo ""
echo "OmniScript $VERSION installed to $BIN_DIR/omni"
case ":$PATH:" in
  *":$BIN_DIR:"*) echo "Run: omni --help" ;;
  *) echo "Add to PATH: export PATH=\"$BIN_DIR:\$PATH\""; echo "Then: omni --help" ;;
esac
