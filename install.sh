#!/usr/bin/env bash
#
# Install OmniScript as a command and as a desktop app.
#
#   ./install.sh              the newest release: one file, no dependencies
#   ./install.sh -s beta      build the repository instead (needs cc, no make)
#   ./install.sh --version 1.0.0
#   ./install.sh --dry-run    show what would happen and change nothing
#
# What it does:
#   - release channel: downloads omni-<os>-<arch> + .sha256 from GitHub,
#     verifies, installs one `omni` binary into PREFIX/bin
#   - beta channel: builds from source (cc, no make required) and links
#   - app channel: creates a desktop entry (Linux), .app bundle (macOS),
#     Start Menu shortcut is handled by install.ps1 on Windows. This script
#     also creates .desktop + icon on Linux/macOS so OmniScript appears as
#     an app in launchers.
#   - writes ~/.local/share/omniscript/install.txt manifest for uninstall.sh
#
# With no release to be had -- no network, nothing published yet -- it says so
# and installs from source instead: the tree beside this script, or a clone of
# main. That needs a C compiler and nothing else (no make required).

set -euo pipefail

REPO_SLUG="OmniNodeCo/OmniScript"
API_URL="https://api.github.com"

CHANNEL=""
PINNED=""
PREFIX=""
FORCE=0
DRY_RUN=0

usage() {
    cat <<'USAGE'
Usage: install.sh [options]

  -s, --channel release|beta
                     release (the default): the newest published release, one
                     file, no dependencies.
                     beta: the repository -- the source tree beside this script,
                     or a clone of main. Needs a C compiler (no make required).
  --version VERSION  a particular release, for example 1.0.0 or v1.0.0
  --prefix DIR       where to install                        [~/.local]
  --api-url URL      the GitHub API to ask              [https://api.github.com]
  --force            replace an existing omni, keeping a .bak copy
  --dry-run, -n      print what would happen and change nothing
  -h, --help         this text

Commands go into PREFIX/bin. A desktop app entry is also created:
  Linux   ~/.local/share/applications/omniscript.desktop + icon
  macOS   ~/Applications/OmniScript.app (plus binary in PREFIX/bin)
Everything is recorded in ~/.local/share/omniscript/install.txt, which
uninstall.sh reads.
USAGE
}

die()  { printf 'install.sh: error: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '    %s\n' "$*" >&2; }

run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

while [ $# -gt 0 ]; do
    case "$1" in
        --channel|-s)      [ $# -ge 2 ] || die "--channel needs release or beta"
                           CHANNEL="$2"; shift 2 ;;
        --channel=*)       CHANNEL="${1#*=}"; shift ;;
        --version)         [ $# -ge 2 ] || die "--version needs a version"
                           PINNED="$2"; shift 2 ;;
        --version=*)       PINNED="${1#*=}"; shift ;;
        --prefix)          [ $# -ge 2 ] || die "--prefix needs a directory"
                           PREFIX="$2"; shift 2 ;;
        --prefix=*)        PREFIX="${1#*=}"; shift ;;
        --api-url)         [ $# -ge 2 ] || die "--api-url needs a URL"
                           API_URL="$2"; shift 2 ;;
        --api-url=*)       API_URL="${1#*=}"; shift ;;
        --force|-f)        FORCE=1; shift ;;
        --dry-run|-n)      DRY_RUN=1; shift ;;
        -h|--help)         usage; exit 0 ;;
        *)                 usage >&2; die "unknown option: $1" ;;
    esac
done

case "$CHANNEL" in
    ""|release|beta) ;;
    *) usage >&2; die "--channel must be release or beta (got '$CHANNEL')" ;;
esac

[ -n "$PREFIX" ] || PREFIX="$HOME/.local"
BIN_DIR="$PREFIX/bin"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omniscript"
MANIFEST="$DATA_DIR/install.txt"
REPO_URL="https://github.com/$REPO_SLUG.git"
HISTORY_FILE="$HOME/.omniscript_history"

SOURCE_DIR="" CLONED=0
MODE="" COMMAND_KIND="" BINARY_PATH="" OMNI_VERSION="unknown"
RELEASE_TAG="" INSTALLED_COMMANDS=""
# App installation paths (filled by install_app)
DESKTOP_FILE="" ICON_FILE="" ICON_PNG="" APP_BUNDLE="" APP_ICON="" START_MENU_LNK=""

# --------------------------------------------------------------- this machine
platform_tag() {
    os="$(uname -s 2>/dev/null | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz' || echo unknown)"
    arch="$(uname -m 2>/dev/null | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz' || echo unknown)"
    case "$os" in
        linux*)               os=linux ;;
        darwin*|mac*)         os=macos ;;
        mingw*|msys*|cygwin*) os=windows ;;
    esac
    case "$arch" in
        x86_64|amd64)   arch=x86_64 ;;
        aarch64|arm64)  arch=arm64 ;;
        i386|i686)      arch=x86 ;;
    esac
    printf '%s-%s\n' "$os" "$arch"
}

is_windows_host() {
    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
        *) return 1 ;;
    esac
}

is_macos_host() {
    case "$(uname -s 2>/dev/null)" in
        Darwin*) return 0 ;;
        *) return 1 ;;
    esac
}

if is_windows_host; then COMMANDS="omni.exe"; else COMMANDS="omni"; fi
MAIN_COMMAND="${COMMANDS%% *}"

# ------------------------------------------------------------------ downloading
have_fetch() {
    command -v curl >/dev/null 2>&1 && return 0
    command -v wget >/dev/null 2>&1 && return 0
    return 1
}

fetch_text() {
    url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 --max-time 60 "$url"
    else
        wget -q -O - --timeout=60 --tries=2 "$url"
    fi
}

fetch_file() {
    url="$1"
    dest="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 --max-time 900 -o "$dest" "$url"
    else
        wget -q -O "$dest" --timeout=900 --tries=2 "$url"
    fi
}

json_value() {
    printf '%s' "$1" | tr ',{' '\n\n' | grep -m1 "\"$2\"[ \t]*:" 2>/dev/null |
        sed -e 's/.*:[ \t]*"//' -e 's/".*$//' || true
}

asset_url() {
    printf '%s' "$1" | tr ',{' '\n\n' | grep 'browser_download_url' 2>/dev/null |
        sed -e 's/.*:[ \t]*"//' -e 's/".*$//' |
        while IFS= read -r url; do
            case "${url##*/}" in
                "$2") printf '%s\n' "$url"; exit 0 ;;
            esac
        done | head -1 || true
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 -r "$1" 2>/dev/null | cut -d' ' -f1
    else
        die "no sha256sum, shasum or openssl to verify the download with"
    fi
}

# ------------------------------------------------------------ the bin directory
ensure_bin_dir() {
    if [ "$DRY_RUN" != 1 ]; then
        mkdir -p "$BIN_DIR"
    elif [ ! -d "$BIN_DIR" ]; then
        printf '    [dry-run] mkdir -p %s\n' "$BIN_DIR"
    fi
    { [ -w "$BIN_DIR" ] || [ "$DRY_RUN" = 1 ]; } ||
        die "$BIN_DIR is not writable; try --prefix ~/.local, or run with sudo --prefix /usr/local"
}

recorded_by_us() {
    [ -f "$MANIFEST" ] || return 1
    grep -qxF -e "command=$1" -e "binary=$1" "$MANIFEST" 2>/dev/null
}

place_command() {
    name="$1"; target="$2"; kind="${3:-symlink}"
    path="$BIN_DIR/$name"
    if [ -L "$path" ] || [ -e "$path" ]; then
        existing=""
        [ -L "$path" ] && existing="$(readlink "$path" 2>/dev/null || true)"
        if [ "$existing" = "$target" ] && [ -f "$path" ]; then
            note "$name already points at $target"
            INSTALLED_COMMANDS="$INSTALLED_COMMANDS $path"
            return 0
        fi
        if [ "$FORCE" != 1 ] && ! recorded_by_us "$path"; then
            die "$path already exists and was not created by this script
       (it is $( [ -n "$existing" ] && printf 'a symlink to %s' "$existing" || printf 'a real file' ))
       Re-run with --force to replace it; a backup is kept next to it."
        fi
        run mv "$path" "$path.bak"
        note "moved the old $name to $path.bak"
    fi
    case "$kind" in
        copy) run cp "$target" "$path" ;;
        *)    run ln -s "$target" "$path" ;;
    esac
    note "$name -> $target"
    INSTALLED_COMMANDS="$INSTALLED_COMMANDS $path"
}

check_no_foreign_commands() {
    foreign=""
    for name in $COMMANDS; do
        path="$BIN_DIR/$name"
        if { [ -e "$path" ] || [ -L "$path" ]; } && ! recorded_by_us "$path"; then
            foreign="$foreign
       $path"
        fi
    done
    if [ -n "$foreign" ] && [ "$FORCE" != 1 ]; then
        die "these already exist and were not created by this script:$foreign
       Re-run with --force to move them aside (a .bak copy is kept next to each)."
    fi
}

# ============================================================ release channel
REL_JSON="" REL_VERSION="" REL_ASSET_NAME="" REL_ASSET_URL=""
REL_DOWNLOAD=""
REL_FATAL=""

discover_release() {
    have_fetch || { warn "no curl or wget to download with"; return 1; }
    api="${API_URL%/}"
    if [ -n "$PINNED" ]; then
        case "$PINNED" in
            v*) RELEASE_TAG="$PINNED" ;;
            *)  RELEASE_TAG="v$PINNED" ;;
        esac
        url="$api/repos/$REPO_SLUG/releases/tags/$RELEASE_TAG"
    else
        url="$api/repos/$REPO_SLUG/releases/latest"
    fi
    info "Asking $REPO_SLUG what it has published"
    if ! REL_JSON="$(fetch_text "$url" 2>/dev/null)"; then
        warn "no answer from $url"
        [ -n "$PINNED" ] && REL_FATAL="$REPO_SLUG has no release tagged $RELEASE_TAG"
        return 1
    fi
    [ -n "$REL_JSON" ] || { warn "$url came back empty"; return 1; }
    RELEASE_TAG="$(json_value "$REL_JSON" tag_name)"
    case "$RELEASE_TAG" in
        ""|null) warn "that release has no tag on it"
                 [ -n "$PINNED" ] && REL_FATAL="$REPO_SLUG has no release tagged $PINNED"
                 return 1 ;;
    esac
    REL_VERSION="${RELEASE_TAG#v}"
    note "the newest release is $RELEASE_TAG"
}

pick_release_asset() {
    tag="$(platform_tag)"
    suffix=""
    is_windows_host && suffix=".exe"
    name="omni-$tag$suffix"
    url="$(asset_url "$REL_JSON" "$name")"
    if [ -n "$url" ]; then
        REL_ASSET_NAME="$name"
        REL_ASSET_URL="$url"
        note "this machine takes $name"
        return 0
    fi
    warn "nothing in $RELEASE_TAG is built for $tag"
    return 1
}

download_release_asset() {
    REL_DOWNLOAD="${TMPDIR:-/tmp}/omniscript-download-$$"
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] download %s\n' "$REL_ASSET_URL"
        return 0
    fi
    info "Downloading $REL_ASSET_NAME"
    if ! fetch_file "$REL_ASSET_URL" "$REL_DOWNLOAD"; then
        rm -f "$REL_DOWNLOAD"
        warn "the download failed"
        return 1
    fi
    note "$(wc -c < "$REL_DOWNLOAD" | tr -d ' ') bytes"
    sums_url="$(asset_url "$REL_JSON" "$REL_ASSET_NAME.sha256")"
    if [ -z "$sums_url" ]; then
        rm -f "$REL_DOWNLOAD"
        warn "the release publishes no checksum for $REL_ASSET_NAME -- refusing it"
        REL_FATAL="$RELEASE_TAG publishes no checksum for $REL_ASSET_NAME"
        return 1
    fi
    sums="$(fetch_text "$sums_url" 2>/dev/null || true)"
    want="$(printf '%s\n' "$sums" | head -1 | cut -d' ' -f1 | tr 'A-Z' 'a-z' || true)"
    got="$(sha256_of "$REL_DOWNLOAD" 2>/dev/null || true)"
    if [ -z "$want" ] || [ -z "$got" ]; then
        rm -f "$REL_DOWNLOAD"
        warn "the checksum could not be compared -- refusing the download"
        REL_FATAL="could not verify $REL_ASSET_NAME"
        return 1
    fi
    if [ "$got" != "$want" ]; then
        rm -f "$REL_DOWNLOAD"
        warn "checksum mismatch for $REL_ASSET_NAME"
        warn "  the release says $want"
        warn "  the download is  $got"
        REL_FATAL="$REL_ASSET_NAME does not match the checksum the release published"
        return 1
    fi
    note "sha256 verified"
}

install_release_binary() {
    check_no_foreign_commands
    ensure_bin_dir
    target="$BIN_DIR/$MAIN_COMMAND"
    MODE="binary"
    COMMAND_KIND="binary"
    BINARY_PATH="$target"
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] install %s as %s\n' "$REL_ASSET_NAME" "$target"
        INSTALLED_COMMANDS="$target"
        return 0
    fi
    mv "$REL_DOWNLOAD" "$target"
    chmod 755 "$target"
    INSTALLED_COMMANDS="$target"
    note "installed $target"
}

install_release() {
    discover_release || return 1
    pick_release_asset || return 1
    download_release_asset || return 1
    install_release_binary || return 1
    OMNI_VERSION="$REL_VERSION"
}

# ============================================================== beta channel
is_source_tree() {
    [ -f "$1/src/main.c" ]
}

find_source() {
    script_dir="$(dirname "$0")"
    here="$(cd "$script_dir" 2>/dev/null && pwd -P || true)"
    if [ -n "$here" ] && is_source_tree "$here"; then
        SOURCE_DIR="$here"
    elif [ -n "${OMNI_HOME:-}" ] && is_source_tree "$OMNI_HOME"; then
        SOURCE_DIR="$OMNI_HOME"
    elif is_source_tree "$DATA_DIR/src"; then
        SOURCE_DIR="$DATA_DIR/src"
    else
        command -v git >/dev/null 2>&1 ||
            die "no release to download, no source tree here, and no git to fetch one"
        SOURCE_DIR="$DATA_DIR/src"
        info "Fetching OmniScript into $SOURCE_DIR"
        run mkdir -p "$DATA_DIR"
        run git clone --quiet --branch main --depth 1 "$REPO_URL" "$SOURCE_DIR"
        CLONED=1
    fi
    [ -d "$SOURCE_DIR" ] || die "$SOURCE_DIR does not exist"
    if [ "$DRY_RUN" != 1 ]; then
        SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd -P)"
        is_source_tree "$SOURCE_DIR" || die "$SOURCE_DIR is not an OmniScript source tree"
    fi
}

find_tools() {
    if command -v cc >/dev/null 2>&1; then return 0; fi
    if command -v gcc >/dev/null 2>&1; then return 0; fi
    if command -v clang >/dev/null 2>&1; then return 0; fi
    if command -v cl >/dev/null 2>&1; then return 0; fi
    die "no C compiler on PATH; the beta channel needs a C compiler (cc, gcc, clang, or cl)"
}

build_source() {
    info "Building in $SOURCE_DIR"
    CC="${CC:-}"
    if [ -z "$CC" ]; then
        for c in cc gcc clang; do
            if command -v "$c" >/dev/null 2>&1; then CC="$c"; break; fi
        done
    fi
    if [ -n "$CC" ]; then
        VER="$(cat "$SOURCE_DIR/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 0.0.0)"
        SRC="$SOURCE_DIR/src/util.c $SOURCE_DIR/src/lex.c $SOURCE_DIR/src/parse.c $SOURCE_DIR/src/eval.c $SOURCE_DIR/src/draw.c $SOURCE_DIR/src/sha256.c $SOURCE_DIR/src/update.c $SOURCE_DIR/src/main.c"
        if [ -f /usr/include/X11/Xlib.h ] || [ -f /usr/local/include/X11/Xlib.h ] || [ -f /opt/X11/include/X11/Xlib.h ] || [ -f /opt/homebrew/include/X11/Xlib.h ]; then
            SRC="$SRC $SOURCE_DIR/src/gui_x11.c"
            CFLAGS_EXTRA="-DHAVE_X11"
            LDFLAGS_EXTRA="-lX11"
        else
            case "$(uname -s 2>/dev/null)" in
                MINGW*|MSYS*|CYGWIN*)
                    if [ -f "$SOURCE_DIR/src/gui_win32.c" ]; then
                        SRC="$SRC $SOURCE_DIR/src/gui_win32.c"
                        LDFLAGS_EXTRA="-lgdi32 -luser32"
                        CFLAGS_EXTRA=""
                    else
                        SRC="$SRC $SOURCE_DIR/src/gui_stub.c"
                        CFLAGS_EXTRA=""
                        LDFLAGS_EXTRA=""
                    fi
                    ;;
                *)
                    SRC="$SRC $SOURCE_DIR/src/gui_stub.c"
                    CFLAGS_EXTRA=""
                    LDFLAGS_EXTRA=""
                    ;;
            esac
        fi
        : "${CFLAGS_EXTRA:=}"
        : "${LDFLAGS_EXTRA:=}"
        info "Compiling directly with $CC (no make)"
        if [ "$DRY_RUN" = 1 ]; then
            printf '    [dry-run] %s -O2 -std=c11 -Wall -Wextra -DOMNI_VERSION=\"%s\" -D_POSIX_C_SOURCE=200809L %s -o %s/omni %s %s\n' "$CC" "$VER" "$CFLAGS_EXTRA" "$SOURCE_DIR" "$SRC" "$LDFLAGS_EXTRA"
            return 0
        fi
        if $CC -O2 -std=c11 -Wall -Wextra -DOMNI_VERSION=\""$VER"\" -D_POSIX_C_SOURCE=200809L $CFLAGS_EXTRA -o "$SOURCE_DIR/omni" $SRC $LDFLAGS_EXTRA 2>&1; then
            return 0
        fi
        warn "direct $CC compile failed, trying make"
    fi
    if command -v make >/dev/null 2>&1; then
        run make -C "$SOURCE_DIR"
        return 0
    fi
    if command -v mingw32-make >/dev/null 2>&1; then
        run mingw32-make -C "$SOURCE_DIR"
        return 0
    fi
    if command -v gmake >/dev/null 2>&1; then
        run gmake -C "$SOURCE_DIR"
        return 0
    fi
    die "build failed and no make found to fall back to"
}

install_from_source() {
    check_no_foreign_commands
    binary="$SOURCE_DIR/omni"
    is_windows_host && binary="$SOURCE_DIR/omni.exe"
    [ -x "$binary" ] || die "the build did not produce $binary"
    MODE="symlink"
    COMMAND_KIND="symlink"
    for name in $COMMANDS; do
        if is_windows_host; then
            place_command "$name" "$binary" copy
        else
            place_command "$name" "$binary" symlink
        fi
    done
}

# ============================================================== app installation
# Install OmniScript as a desktop app: .desktop + icon on Linux, .app on macOS
install_app() {
    info "Installing OmniScript as an app"
    # Determine binary to use for icon generation and Exec
    app_bin="$BIN_DIR/$MAIN_COMMAND"
    [ -x "$app_bin" ] || app_bin="$(printf '%s\n' $INSTALLED_COMMANDS | head -1)"
    [ -x "$app_bin" ] || app_bin="$SOURCE_DIR/omni"
    is_windows_host && {
        # Windows app shortcuts are handled by install.ps1; this script only does Linux/macOS
        return 0
    }

    # --- icon generation ---
    # Try to generate a 64x64 icon using omni itself
    ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/64x64/apps"
    ICON_DIR2="$DATA_DIR/icons"
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] mkdir -p %s\n' "$ICON_DIR"
        printf '    [dry-run] generate icon via %s\n' "$app_bin"
    else
        mkdir -p "$ICON_DIR" "$ICON_DIR2" "$DATA_DIR" 2>/dev/null || true
        # Generate BMP icon if possible — no window to avoid GUI blocking in CI
        if [ -x "$app_bin" ]; then
            "$app_bin" -e 'draw(rect(0, 0, 64, 64, "#0d1117"), circle(32, 32, 20, "#1f6feb"), text(8, 20, "Om", white, 14), save("'"$DATA_DIR"'/icon.bmp"))' >/dev/null 2>&1 || true
            if [ -f "$DATA_DIR/icon.bmp" ]; then
                ICON_FILE="$DATA_DIR/icon.bmp"
                # Try to convert to PNG if convert/magick available, else keep BMP
                if command -v convert >/dev/null 2>&1; then
                    convert "$DATA_DIR/icon.bmp" "$ICON_DIR/omniscript.png" 2>/dev/null && ICON_PNG="$ICON_DIR/omniscript.png" || true
                    convert "$DATA_DIR/icon.bmp" "$ICON_DIR2/icon.png" 2>/dev/null && true
                fi
                if [ -z "$ICON_PNG" ] && command -v magick >/dev/null 2>&1; then
                    magick "$DATA_DIR/icon.bmp" "$ICON_DIR/omniscript.png" 2>/dev/null && ICON_PNG="$ICON_DIR/omniscript.png" || true
                fi
                # Fallback: copy BMP as PNG name (some launchers accept BMP)
                if [ -z "$ICON_PNG" ]; then
                    cp "$DATA_DIR/icon.bmp" "$ICON_DIR/omniscript.bmp" 2>/dev/null && ICON_PNG="$ICON_DIR/omniscript.bmp" || true
                fi
                # Also copy to DATA_DIR/icons for manifest
                cp "$DATA_DIR/icon.bmp" "$ICON_DIR2/icon.bmp" 2>/dev/null || true
                if [ -f "$ICON_DIR2/icon.bmp" ]; then
                    ICON_FILE="$ICON_DIR2/icon.bmp"
                fi
            fi
        fi
        # If icon generation failed, create a minimal placeholder
        if [ -z "$ICON_FILE" ]; then
            # Create a tiny placeholder file so manifest has something
            printf 'OmniScript icon placeholder' > "$DATA_DIR/icon.txt" 2>/dev/null || true
            ICON_FILE="$DATA_DIR/icon.txt"
        fi
    fi

    # --- Linux .desktop file ---
    APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] mkdir -p %s\n' "$APPS_DIR"
        printf '    [dry-run] write %s/omniscript.desktop\n' "$APPS_DIR"
    else
        mkdir -p "$APPS_DIR" 2>/dev/null || true
        DESKTOP_FILE="$APPS_DIR/omniscript.desktop"
        # Prefer PNG icon if we have it, else use generic name or BMP path
        if [ -n "$ICON_PNG" ]; then
            ICON_NAME="$ICON_PNG"
        elif [ -n "$ICON_FILE" ]; then
            ICON_NAME="$ICON_FILE"
        else
            ICON_NAME="omniscript"
        fi
        cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Name=OmniScript
GenericName=OmniScript Language
Comment=Native tiny language for drawing and automating — one binary, libc only
Exec=$BIN_DIR/omni
Icon=$ICON_NAME
Terminal=true
Type=Application
Categories=Development;Education;Science;
Keywords=omni;script;drawing;automation;programming;
StartupWMClass=OmniScript
MimeType=text/x-omniscript;
Actions=REPL;Examples;

[Desktop Action REPL]
Name=Open REPL
Exec=$BIN_DIR/omni
Terminal=true

[Desktop Action Examples]
Name=Run Examples
Exec=$BIN_DIR/omni $SOURCE_DIR/examples/03_drawing.omni
Terminal=true
DESKTOP
        chmod 644 "$DESKTOP_FILE" 2>/dev/null || true
        note "created app launcher $DESKTOP_FILE"
        # Update desktop database if possible
        if command -v update-desktop-database >/dev/null 2>&1; then
            update-desktop-database "$APPS_DIR" 2>/dev/null || true
        fi
        if command -v gtk-update-icon-cache >/dev/null 2>&1; then
            gtk-update-icon-cache -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
        fi
    fi

    # --- macOS .app bundle ---
    if is_macos_host; then
        MAC_APP_DIR="$HOME/Applications"
        [ -d "$MAC_APP_DIR" ] || MAC_APP_DIR="/Applications"
        # Prefer user Applications
        if [ ! -w "$HOME/Applications" ] && [ -w "/Applications" ]; then
            MAC_APP_DIR="/Applications"
        else
            MAC_APP_DIR="$HOME/Applications"
            mkdir -p "$MAC_APP_DIR" 2>/dev/null || true
        fi
        APP_BUNDLE="$MAC_APP_DIR/OmniScript.app"
        if [ "$DRY_RUN" = 1 ]; then
            printf '    [dry-run] mkdir -p %s/Contents/MacOS %s/Contents/Resources\n' "$APP_BUNDLE" "$APP_BUNDLE"
            printf '    [dry-run] create %s as macOS app bundle\n' "$APP_BUNDLE"
        else
            mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources" 2>/dev/null || true
            # Copy binary
            if [ -f "$BIN_DIR/omni" ]; then
                cp "$BIN_DIR/omni" "$APP_BUNDLE/Contents/MacOS/OmniScript" 2>/dev/null || cp "$BIN_DIR/omni" "$APP_BUNDLE/Contents/MacOS/omni" 2>/dev/null || true
                chmod 755 "$APP_BUNDLE/Contents/MacOS/OmniScript" 2>/dev/null || true
                chmod 755 "$APP_BUNDLE/Contents/MacOS/omni" 2>/dev/null || true
            elif [ -f "$SOURCE_DIR/omni" ]; then
                cp "$SOURCE_DIR/omni" "$APP_BUNDLE/Contents/MacOS/OmniScript" 2>/dev/null || true
                chmod 755 "$APP_BUNDLE/Contents/MacOS/OmniScript" 2>/dev/null || true
            fi
            # Icon
            if [ -f "$DATA_DIR/icon.bmp" ]; then
                cp "$DATA_DIR/icon.bmp" "$APP_BUNDLE/Contents/Resources/icon.bmp" 2>/dev/null || true
                APP_ICON="$APP_BUNDLE/Contents/Resources/icon.bmp"
            fi
            # Info.plist
            cat > "$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>OmniScript</string>
    <key>CFBundleDisplayName</key><string>OmniScript</string>
    <key>CFBundleIdentifier</key><string>com.omninode.omniscript</string>
    <key>CFBundleVersion</key><string>$OMNI_VERSION</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>OmniScript</string>
    <key>LSMinimumSystemVersion</key><string>10.12</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
            note "created macOS app $APP_BUNDLE"
        fi
    fi
}

# ------------------------------------------------------------------ manifest
write_manifest() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] write %s\n' "$MANIFEST"
        return 0
    fi
    mkdir -p "$DATA_DIR"
    {
        printf 'api_url=%s\n' "$API_URL"
        printf 'bin_dir=%s\n' "$BIN_DIR"
        printf 'binary=%s\n' "$BINARY_PATH"
        printf 'channel=%s\n' "$CHANNEL"
        printf 'cloned_by_installer=%s\n' "$( [ "$CLONED" = 1 ] && echo 1 || echo 0)"
        printf 'command_kind=%s\n' "$COMMAND_KIND"
        for path in $INSTALLED_COMMANDS; do printf 'command=%s\n' "$path"; done
        printf 'data_dir=%s\n' "$DATA_DIR"
        printf 'history_file=%s\n' "$HISTORY_FILE"
        printf 'installed_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo unknown)"
        printf 'mode=%s\n' "$MODE"
        printf 'package=omniscript-lang\n'
        printf 'release_tag=%s\n' "$RELEASE_TAG"
        printf 'repo=%s\n' "$REPO_SLUG"
        printf 'repo_url=%s\n' "$REPO_URL"
        printf 'source=%s\n' "$SOURCE_DIR"
        printf 'version=%s\n' "$OMNI_VERSION"
        # App entries
        [ -n "$DESKTOP_FILE" ] && printf 'desktop_file=%s\n' "$DESKTOP_FILE"
        [ -n "$ICON_FILE" ] && printf 'icon_file=%s\n' "$ICON_FILE"
        [ -n "$ICON_PNG" ] && printf 'icon_png=%s\n' "$ICON_PNG"
        [ -n "$APP_BUNDLE" ] && printf 'app_bundle=%s\n' "$APP_BUNDLE"
        [ -n "$APP_ICON" ] && printf 'app_icon=%s\n' "$APP_ICON"
    } > "$MANIFEST"
    note "wrote $MANIFEST"
}

# -------------------------------------------------------------------- verify
VERIFY_ERROR=""

verify_install() {
    [ "$DRY_RUN" = 1 ] && return 0
    info "Checking the install"
    for path in $INSTALLED_COMMANDS; do
        if [ ! -x "$path" ] && [ ! -L "$path" ]; then
            VERIFY_ERROR="$path is not usable"
            return 1
        fi
    done
    probe="$BIN_DIR/$MAIN_COMMAND"
    [ -e "$probe" ] || probe="$(printf '%s\n' $INSTALLED_COMMANDS | head -1)"
    if ! reported="$("$probe" --version 2>&1)"; then
        VERIFY_ERROR="$probe --version failed: $reported"
        return 1
    fi
    note "$reported"
    smoke="$("$probe" -e 'cmd("echo smoke ok: 42")' 2>&1)" || {
        VERIFY_ERROR="the interpreter did not run: $smoke"
        return 1
    }
    note "$smoke"
    if [ -n "$RELEASE_TAG" ] && [ "$OMNI_VERSION" != unknown ]; then
        case "$reported" in
            *"$OMNI_VERSION"*) ;;
            *) VERIFY_ERROR="the release says $OMNI_VERSION but $probe reports: $reported"
               return 1 ;;
        esac
    fi
    # App verification (non-fatal)
    if [ -n "$DESKTOP_FILE" ] && [ -f "$DESKTOP_FILE" ]; then
        note "app launcher $DESKTOP_FILE"
    fi
    if [ -n "$APP_BUNDLE" ] && [ -d "$APP_BUNDLE" ]; then
        note "macOS app $APP_BUNDLE"
    fi
}

undo_release_install() {
    warn "rolling the release install back"
    for path in $INSTALLED_COMMANDS; do
        [ -n "$path" ] || continue
        if [ -L "$path" ] || [ -f "$path" ]; then
            rm -f "$path"
            note "removed $path"
        fi
    done
    [ -n "$DESKTOP_FILE" ] && [ -f "$DESKTOP_FILE" ] && rm -f "$DESKTOP_FILE" && note "removed $DESKTOP_FILE"
    [ -n "$ICON_PNG" ] && [ -f "$ICON_PNG" ] && rm -f "$ICON_PNG" && note "removed $ICON_PNG"
    [ -n "$APP_BUNDLE" ] && [ -d "$APP_BUNDLE" ] && rm -rf "$APP_BUNDLE" && note "removed $APP_BUNDLE"
    [ -f "$MANIFEST" ] && rm -f "$MANIFEST" && note "removed $MANIFEST"
    return 0
}

# ------------------------------------------------------------------------ main
source_beside_us() {
    script_dir="$(dirname "$0")"
    here="$(cd "$script_dir" 2>/dev/null && pwd -P || true)"
    [ -n "$here" ] && is_source_tree "$here" && return 0
    [ -n "${OMNI_HOME:-}" ] && is_source_tree "$OMNI_HOME" && return 0
    return 1
}

if [ -z "$CHANNEL" ]; then
    if source_beside_us; then
        CHANNEL="beta"
        [ "$DRY_RUN" = 1 ] || note "installing from the source tree here (beta channel);"
        [ "$DRY_RUN" = 1 ] || note "pass --channel release to take the published release instead"
    else
        CHANNEL="release"
    fi
fi

INSTALLED=0
if [ "$CHANNEL" = release ]; then
    if install_release; then
        INSTALLED=1
        info "OmniScript $OMNI_VERSION from $RELEASE_TAG ($REL_ASSET_NAME)"
        note "commands into $BIN_DIR, no dependencies"
        ensure_bin_dir
        install_app || warn "app install failed (non-fatal)"
    else
        [ -n "$REL_FATAL" ] && die "$REL_FATAL"
        warn "the release channel did not deliver; installing from $REPO_URL instead"
        CHANNEL="beta"
    fi
fi

if [ "$INSTALLED" != 1 ]; then
    find_source
    find_tools
    if [ -n "$PINNED" ]; then
        OMNI_VERSION="${PINNED#v}"
    elif [ -f "$SOURCE_DIR/VERSION" ]; then
        OMNI_VERSION="$(tr -d ' \t\n' < "$SOURCE_DIR/VERSION")"
    else
        OMNI_VERSION="unknown"
    fi
    info "OmniScript $OMNI_VERSION from $SOURCE_DIR"
    note "built with cc (no make required), commands into $BIN_DIR"
    ensure_bin_dir
    build_source
    install_from_source
    install_app || warn "app install failed (non-fatal)"
fi

write_manifest
if ! verify_install; then
    if [ "$INSTALLED" = 1 ]; then
        warn "$VERIFY_ERROR"
        undo_release_install
    fi
    die "$VERIFY_ERROR"
fi

case ":$PATH:" in
    *":$BIN_DIR:"*) on_path=1 ;;
    *) on_path=0 ;;
esac

if [ "$DRY_RUN" = 1 ]; then
    info "Dry run: nothing was changed"
    exit 0
fi

printf '\n'
info "OmniScript $OMNI_VERSION is installed ($CHANNEL channel) as an app"
if [ "$on_path" = 1 ]; then
    note "run it with: omni -e 'cmd(\"echo hello\")'   or just: omni"
else
    note "$BIN_DIR is not on your PATH yet. Add this to your shell profile:"
    printf '\n        export PATH="%s:$PATH"\n\n' "$BIN_DIR"
    note "then open a new terminal, or run that line now."
fi
if [ -n "$DESKTOP_FILE" ]; then
    note "app launcher: $DESKTOP_FILE (shows in your app menu)"
fi
if [ -n "$APP_BUNDLE" ]; then
    note "macOS app: $APP_BUNDLE"
fi
note "update with: omni update            ($CHANNEL channel)"
if [ -n "$SOURCE_DIR" ]; then
    note "uninstall with: $SOURCE_DIR/uninstall.sh"
else
    note "uninstall with: curl -fsSL https://raw.githubusercontent.com/$REPO_SLUG/main/uninstall.sh | bash"
fi
