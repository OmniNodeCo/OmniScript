#!/usr/bin/env bash
#
# Install OmniScript.
#
#   ./install.sh                      # from this checkout: `omni` symlinked into ~/.local/bin
#   ./install.sh --channel release    # the published release: one file, no Python needed
#   ./install.sh --channel beta       # follow the repository (the default inside a checkout)
#   ./install.sh --mode venv          # self-contained venv, symlinked the same way
#   ./install.sh --prefix /usr/local --force
#   ./install.sh --vscode             # also drop in the editor extension
#
#   curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash
#
# Two channels, the same two `omni update` follows:
#
#   release   what the project published. A standalone executable for this
#             machine if it built one, otherwise the wheel into a venv or pip.
#             The default when this script arrives with no source tree beside
#             it, and the only channel that needs no Python at all.
#   beta      the repository itself: this checkout, or a clone of a branch, with
#             the commands pointing straight at it so `git pull` is an upgrade.
#             The default when the script is run from a source tree.
#
# If the release channel cannot deliver -- nothing published yet, no file built
# for this machine, no network -- the script says so plainly and installs from
# the repository instead. Either way everything it creates goes into a manifest,
# so uninstall.sh can take it all back out again, and only what it put there.
#
# Bash 3.2 compatible, because that is still what macOS ships.

set -euo pipefail

REPO_SLUG="${OMNISCRIPT_REPO:-OmniNodeCo/OmniScript}"
API_URL="${OMNISCRIPT_API_URL:-https://api.github.com}"
REPO_URL="${OMNISCRIPT_REPO_URL:-https://github.com/$REPO_SLUG.git}"
MIN_PYTHON="3.10"

MODE="symlink"
CHANNEL=""
PREFIX="${HOME}/.local"
BIN_DIR=""
PYTHON=""
SOURCE_DIR=""
REF="main"
PINNED=""
WITH_VSCODE=0
BREAK_SYSTEM=0
PIP_USER=0
DRY_RUN=0
FORCE=0
NO_VERIFY=0

usage() {
    cat <<'USAGE'
Usage: install.sh [options]

  --channel CHANNEL  release: the published release (default with no source tree
                     here); beta: the repository (default inside a checkout)
  --mode MODE        symlink (default), venv, or pip; a release install of a
                     standalone executable records itself as mode binary
  --prefix DIR       install root; commands land in DIR/bin   [~/.local]
  --bin DIR          where to put the commands                [PREFIX/bin]
  --source DIR       source tree to install from              [this script's directory]
  --python PATH      interpreter to use                       [first python3 >= 3.10 on PATH]
  --ref REF          branch or tag to fetch when cloning      [main]
  --version VERSION  release channel: a particular release    [the newest]
  --repo OWNER/NAME  repository to ask and clone from         [OmniNodeCo/OmniScript]
  --api-url URL      API root to ask for releases             [https://api.github.com]
  --no-verify        skip the SHA256 check on what is downloaded
  --vscode           also install the editor extension (VS Code, Cursor, vscode-server)
  --user             pip mode: install for this user only
  --break-system-packages
                     pip mode: pass through to pip on PEP 668 systems
  --force            replace commands this script did not create
  --dry-run          print what would happen and change nothing
  -h, --help         this text

Channels:
  release   download what the project published: a standalone executable for
            this machine when there is one, otherwise the wheel. With an
            executable there is nothing to compile and no Python to find.
  beta      install from a source tree -- this checkout, or a clone of --ref --
            and keep tracking it. `omni update --channel beta` then moves it.

Modes:
  symlink   point DIR/bin/omni at the launcher in the source tree. Instant, no
            copies, no network. The source tree has to stay where it is.
  venv      build a virtual environment under ~/.local/share/omniscript/venv,
            install the package into it, then symlink its commands. Survives
            deleting the source tree.
  pip       install into the interpreter you already use, then make sure the
            commands are reachable from DIR/bin.

The default mode needs no network and no root. Everything installed is recorded
in ~/.local/share/omniscript/install.txt for uninstall.sh.
USAGE
}

die() {
    printf 'install.sh: error: %s\n' "$*" >&2
    exit 1
}

info() { printf '==> %s\n' "$*"; }

note() { printf '    %s\n' "$*"; }

warn() { printf '    %s\n' "$*" >&2; }

# Run a command, or in --dry-run just show it.
run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

# Portable absolute path: macOS readlink has no -f.
abspath() {
    case "$1" in
        /*) printf '%s\n' "$1" ;;
        *)  printf '%s\n' "$PWD/$1" ;;
    esac
}

while [ $# -gt 0 ]; do
    case "$1" in
        --channel) CHANNEL="${2:-}"; shift 2 ;;
        --channel=*) CHANNEL="${1#*=}"; shift ;;
        --mode) MODE="${2:-}"; shift 2 ;;
        --mode=*) MODE="${1#*=}"; shift ;;
        --prefix) PREFIX="${2:-}"; shift 2 ;;
        --prefix=*) PREFIX="${1#*=}"; shift ;;
        --bin) BIN_DIR="${2:-}"; shift 2 ;;
        --bin=*) BIN_DIR="${1#*=}"; shift ;;
        --source) SOURCE_DIR="${2:-}"; shift 2 ;;
        --source=*) SOURCE_DIR="${1#*=}"; shift ;;
        --python) PYTHON="${2:-}"; shift 2 ;;
        --python=*) PYTHON="${1#*=}"; shift ;;
        --ref) REF="${2:-}"; shift 2 ;;
        --ref=*) REF="${1#*=}"; shift ;;
        --version) [ $# -ge 2 ] || die "--version needs a version, for example 1.2.0"
                   PINNED="$2"; shift 2 ;;
        --version=*) PINNED="${1#*=}"; shift ;;
        --tag) [ $# -ge 2 ] || die "--tag needs a tag, for example v1.2.0"
               PINNED="$2"; shift 2 ;;
        --tag=*) PINNED="${1#*=}"; shift ;;
        --repo) REPO_SLUG="${2:-}"; shift 2 ;;
        --repo=*) REPO_SLUG="${1#*=}"; shift ;;
        --api-url) API_URL="${2:-}"; shift 2 ;;
        --api-url=*) API_URL="${1#*=}"; shift ;;
        --no-verify) NO_VERIFY=1; shift ;;
        --vscode) WITH_VSCODE=1; shift ;;
        --user) PIP_USER=1; shift ;;
        --break-system-packages) BREAK_SYSTEM=1; shift ;;
        --force) FORCE=1; shift ;;
        --dry-run|-n) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown option: $1" ;;
    esac
done

case "$MODE" in
    symlink|venv|pip) ;;
    *) usage >&2; die "--mode must be symlink, venv or pip (got '$MODE')" ;;
esac
[ -n "$PREFIX" ] || die "--prefix needs a directory"
[ -n "$BIN_DIR" ] || BIN_DIR="$PREFIX/bin"
[ -n "$REPO_SLUG" ] || die "--repo needs an OWNER/NAME"
REPO_URL="${OMNISCRIPT_REPO_URL:-https://github.com/$REPO_SLUG.git}"

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/omniscript"
MANIFEST="$DATA_DIR/install.txt"
VENV_DIR="$DATA_DIR/venv"

# State the two channels fill in as they go.
INSTALLED_COMMANDS=""
INSTALLED_VENV=""
PIP_TARGET=""
BINARY_PATH=""
COMMAND_KIND="symlink"
RELEASE_TAG=""
INSTALL_SPEC=""
CLONED=0
OMNI_VERSION="unknown"
PY_VERSION=""

# --------------------------------------------------------------- this machine
platform_tag() {
    os="$(uname -s 2>/dev/null | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz' || echo unknown)"
    arch="$(uname -m 2>/dev/null | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz' || echo unknown)"
    case "$os" in
        linux*)           os=linux ;;
        darwin*|mac*)     os=macos ;;
        mingw*|msys*|cygwin*) os=windows ;;
        freebsd*)         os=freebsd ;;
        openbsd*)         os=openbsd ;;
    esac
    case "$arch" in
        x86_64|amd64)     arch=x86_64 ;;
        aarch64|arm64)    arch=arm64 ;;
        armv7l|armv7)     arch=armv7 ;;
        i386|i686)        arch=i686 ;;
    esac
    printf '%s-%s\n' "$os" "$arch"
}

is_windows_host() {
    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
        *) return 1 ;;
    esac
}

# On a Windows host the commands need their extension to be runnable from cmd,
# and pip writes them that way too, so the names carry it everywhere.
if is_windows_host; then
    COMMANDS="omni.exe omniscript.exe"
else
    COMMANDS="omni omniscript"
fi
MAIN_COMMAND="${COMMANDS%% *}"
SECOND_COMMAND="${COMMANDS##* }"

# ------------------------------------------------------------------ downloading
have_fetch() {
    command -v curl >/dev/null 2>&1 && return 0
    command -v wget >/dev/null 2>&1 && return 0
    [ -n "$PYTHON" ] && return 0
    command -v python3 >/dev/null 2>&1 && return 0
    return 1
}

fetch_text() {
    url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 --max-time 60 "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O - --timeout=60 --tries=2 "$url"
    else
        python_for_fetch - "$url" <<'PY'
import sys, urllib.request
request = urllib.request.Request(sys.argv[1], headers={"User-Agent": "omniscript-install"})
sys.stdout.write(urllib.request.urlopen(request, timeout=60).read().decode("utf-8", "replace"))
PY
    fi
}

fetch_file() {
    url="$1"
    dest="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 --max-time 900 -o "$dest" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$dest" --timeout=900 --tries=2 "$url"
    else
        python_for_fetch - "$url" "$dest" <<'PY'
import shutil, sys, urllib.request
request = urllib.request.Request(sys.argv[1], headers={"User-Agent": "omniscript-install"})
with urllib.request.urlopen(request, timeout=900) as response, open(sys.argv[2], "wb") as fh:
    shutil.copyfileobj(response, fh)
PY
    fi
}

python_for_fetch() {
    if [ -n "$PYTHON" ]; then "$PYTHON" "$@"; else python3 "$@"; fi
}

# One scalar out of a JSON document, without needing a JSON parser: split on the
# punctuation that separates members, then take the first "key": "value".
json_value() {
    printf '%s' "$1" | tr ',{' '\n\n' | grep -m1 "\"$2\"[ 	]*:" 2>/dev/null |
        sed -e 's/.*:[ 	]*"//' -e 's/".*$//' || true
}

# The download URL of the asset whose file name is exactly the one asked for.
asset_url() {
    json="$1"
    wanted="$2"
    printf '%s' "$json" | tr ',{' '\n\n' | grep 'browser_download_url' 2>/dev/null |
        sed -e 's/.*:[ 	]*"//' -e 's/".*$//' |
        while IFS= read -r url; do
            case "${url##*/}" in
                "$wanted") printf '%s\n' "$url"; exit 0 ;;
            esac
        done | head -1 || true
}

sha256_of() {
    file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$file" | cut -d' ' -f1
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 -r "$file" 2>/dev/null | cut -d' ' -f1
    else
        python_for_fetch -c 'import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$file"
    fi
}

# ------------------------------------------------------------- the bin dir
ensure_bin_dir() {
    if [ "$DRY_RUN" != 1 ]; then
        mkdir -p "$BIN_DIR"
    elif [ ! -d "$BIN_DIR" ]; then
        printf '    [dry-run] mkdir -p %s\n' "$BIN_DIR"
    fi
    [ -w "$BIN_DIR" ] || [ "$DRY_RUN" = 1 ] ||
        die "$BIN_DIR is not writable; try --prefix ~/.local, or run with sudo --prefix /usr/local"
}

# A command we already put there is ours to replace: the manifest says so.
recorded_by_us() {
    path="$1"
    [ -f "$MANIFEST" ] || return 1
    grep -qF "\"$path\"" "$MANIFEST" 2>/dev/null
}

place_command() {
    # place_command <name> <target> <kind>
    # kind: symlink (POSIX), copy (Windows hosts), shim (install.ps1's business)
    name="$1"
    target="$2"
    kind="${3:-symlink}"
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

# Both linking modes create symlinks, so an existing regular file at that path
# belongs to somebody else. Say so before touching anything, rather than halfway
# through with one command linked and the next refused.
check_no_foreign_commands() {
    foreign=""
    for name in $COMMANDS; do
        path="$BIN_DIR/$name"
        if [ ! -L "$path" ] && { [ -e "$path" ] || [ -L "$path" ]; } &&
                ! recorded_by_us "$path"; then
            foreign="$foreign
       $path"
        fi
    done
    if [ -n "$foreign" ] && [ "$FORCE" != 1 ]; then
        die "these already exist and were not created by this script:$foreign
       Re-run with --force to move them aside (a .bak copy is kept next to each),
       or point --bin somewhere else."
    fi
}

# ============================================================ release channel
# Discovers what was published, downloads the right file for this machine and
# installs it. Returns 0 when OmniScript is installed as a single file, 10 when
# a wheel was fetched for venv or pip mode to install, and 1 when the release
# channel cannot deliver and the repository should be used instead.
REL_JSON=""
REL_VERSION=""
REL_ASSET_NAME=""
REL_ASSET_URL=""
REL_ASSET_KIND=""
REL_DOWNLOAD=""
# Set when the release channel was asked for something specific and did not get
# it: a pinned version that is not there, or a download that does not match its
# checksum. Those are errors, not a reason to quietly install something else.
REL_FATAL=""

discover_release() {
    have_fetch || { warn "no curl, wget or python to download with"; return 1; }
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
    return 0
}

pick_release_asset() {
    tag="$(platform_tag)"
    suffix=""
    is_windows_host && suffix=".exe"
    case "$MODE" in
        venv|pip)
            candidates="omniscript_lang-$REL_VERSION-py3-none-any.whl"
            kinds="wheel"
            ;;
        *)
            candidates="omni-$REL_VERSION-$tag$suffix omni-$REL_VERSION-any.pyz"
            kinds="binary pyz"
            ;;
    esac
    set -- $candidates
    kinds_list="$kinds"
    for name in "$@"; do
        kind="${kinds_list%% *}"
        kinds_list="${kinds_list#* }"
        url="$(asset_url "$REL_JSON" "$name")"
        if [ -n "$url" ]; then
            REL_ASSET_NAME="$name"
            REL_ASSET_URL="$url"
            REL_ASSET_KIND="$kind"
            note "this machine takes $name ($kind)"
            return 0
        fi
    done
    missing_note=""
    case "$MODE" in
        venv|pip) missing_note=" and no wheel is attached" ;;
    esac
    warn "nothing in $RELEASE_TAG is built for $tag$missing_note"
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
    if [ "$NO_VERIFY" = 1 ]; then
        note "not checking the checksum (--no-verify)"
        return 0
    fi
    sums_url="$(asset_url "$REL_JSON" SHA256SUMS.txt)"
    if [ -z "$sums_url" ]; then
        warn "the release has no SHA256SUMS.txt, so this download is unchecked"
        return 0
    fi
    sums="$(fetch_text "$sums_url" 2>/dev/null || true)"
    want="$(printf '%s\n' "$sums" | grep -F "$REL_ASSET_NAME" | head -1 | cut -d' ' -f1 || true)"
    if [ -z "$want" ]; then
        warn "SHA256SUMS.txt does not mention $REL_ASSET_NAME"
        return 0
    fi
    got="$(sha256_of "$REL_DOWNLOAD" 2>/dev/null || true)"
    if [ -z "$got" ]; then
        warn "nothing here can compute a sha256, so this download is unchecked"
        return 0
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
    return 0
}

install_release_binary() {
    check_no_foreign_commands
    ensure_bin_dir
    case "$REL_ASSET_KIND" in
        pyz)
            # A zipapp runs through its shebang, so it needs a Python on PATH.
            if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
                warn "$REL_ASSET_NAME needs a Python to run, and there is none on PATH"
                return 1
            fi
            ;;
    esac
    target="$BIN_DIR/$MAIN_COMMAND"
    second="$BIN_DIR/$SECOND_COMMAND"
    if [ "$DRY_RUN" = 1 ]; then
        printf '    [dry-run] install %s as %s\n' "$REL_ASSET_NAME" "$target"
        printf '    [dry-run] %s -> %s\n' "$second" "$target"
        BINARY_PATH="$target"
        MODE="binary"
        COMMAND_KIND="binary"
        INSTALLED_COMMANDS="$target $second"
        return 0
    fi
    mv "$REL_DOWNLOAD" "$target"
    chmod 755 "$target"
    BINARY_PATH="$target"
    MODE="binary"
    COMMAND_KIND="binary"
    INSTALLED_COMMANDS="$target"
    note "installed $target"
    if [ "$second" != "$target" ]; then
        rm -f "$second"
        if is_windows_host; then
            cp "$target" "$second"
        else
            ln -s "$target" "$second"
            note "$SECOND_COMMAND -> $MAIN_COMMAND"
        fi
        INSTALLED_COMMANDS="$INSTALLED_COMMANDS $second"
    fi
    return 0
}

install_release() {
    discover_release || return 1
    pick_release_asset || return 1
    download_release_asset || return 1
    if [ "$REL_ASSET_KIND" = wheel ]; then
        INSTALL_SPEC="$REL_DOWNLOAD"
        OMNI_VERSION="$REL_VERSION"
        return 10
    fi
    install_release_binary || return 1
    OMNI_VERSION="$REL_VERSION"
    return 0
}

# ============================================================== beta channel
find_source() {
    # Split in two on purpose: bash's parser trips over a redirection inside a
    # nested command substitution when it is in a function body.
    script_dir="$(dirname "$0")"
    here="$(cd "$script_dir" 2>/dev/null && pwd -P || true)"
    if [ -z "$SOURCE_DIR" ] && [ -n "$here" ] && [ -f "$here/omniscript/cli.py" ]; then
        SOURCE_DIR="$here"
    fi
    if [ -z "$SOURCE_DIR" ] && [ -n "${OMNI_HOME:-}" ] && [ -f "$OMNI_HOME/omniscript/cli.py" ]; then
        SOURCE_DIR="$OMNI_HOME"
    fi
    if [ -z "$SOURCE_DIR" ] && [ -f "$DATA_DIR/src/omniscript/cli.py" ]; then
        SOURCE_DIR="$DATA_DIR/src"
    fi

    if [ -z "$SOURCE_DIR" ] || [ ! -f "$SOURCE_DIR/omniscript/cli.py" ]; then
        if [ -n "$SOURCE_DIR" ]; then
            die "--source $SOURCE_DIR is not an OmniScript source tree (no omniscript/cli.py)"
        fi
        SOURCE_DIR="$DATA_DIR/src"
        if [ -f "$SOURCE_DIR/omniscript/cli.py" ]; then
            info "Using the source already in $SOURCE_DIR"
            if [ "$REF" != main ]; then
                run git -C "$SOURCE_DIR" fetch --quiet origin "$REF"
                run git -C "$SOURCE_DIR" checkout --quiet "$REF"
            fi
        else
            command -v git >/dev/null 2>&1 ||
                die "no source tree here and no git to fetch one; run this from a clone, or pass --source DIR"
            info "Fetching OmniScript ($REF) into $SOURCE_DIR"
            run mkdir -p "$DATA_DIR"
            run git clone --quiet --branch "$REF" --depth 1 "$REPO_URL" "$SOURCE_DIR"
            CLONED=1
        fi
    fi
    [ -d "$SOURCE_DIR" ] || die "$SOURCE_DIR does not exist"
    SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd -P)"
    [ -f "$SOURCE_DIR/omniscript/cli.py" ] || die "$SOURCE_DIR is not an OmniScript source tree"
}

find_python() {
    if [ -z "$PYTHON" ]; then
        for candidate in python3 python; do
            if command -v "$candidate" >/dev/null 2>&1; then
                PYTHON="$(command -v "$candidate")"
                break
            fi
        done
    fi
    [ -n "$PYTHON" ] || die "no python on PATH; install Python $MIN_PYTHON or newer, or pass --python PATH"
    [ -x "$PYTHON" ] || die "$PYTHON is not executable"

    if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        found="$("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo unknown)"
        die "$PYTHON is Python $found; OmniScript needs $MIN_PYTHON or newer (try --python PATH)"
    fi
    PY_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
}

install_symlink_mode() {
    check_no_foreign_commands
    [ -x "$SOURCE_DIR/omni" ] || run chmod +x "$SOURCE_DIR/omni"
    COMMAND_KIND="symlink"
    for name in $COMMANDS; do
        if is_windows_host; then
            place_command "$name" "$SOURCE_DIR/omni" copy
        else
            place_command "$name" "$SOURCE_DIR/omni" symlink
        fi
    done
}

install_venv_mode() {
    check_no_foreign_commands
    info "Creating a virtual environment in $VENV_DIR"
    if [ -d "$VENV_DIR" ] && [ "$FORCE" = 1 ]; then
        run rm -rf "$VENV_DIR"
    fi
    run mkdir -p "$DATA_DIR"
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        run "$PYTHON" -m venv "$VENV_DIR"
    fi
    info "Installing ${INSTALL_SPEC:-$SOURCE_DIR} into it"
    run "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
    run "$VENV_DIR/bin/python" -m pip install --quiet "${INSTALL_SPEC:-$SOURCE_DIR}"
    INSTALLED_VENV="$VENV_DIR"
    COMMAND_KIND="symlink"
    for name in $COMMANDS; do
        [ -x "$VENV_DIR/bin/$name" ] || die "the venv has no $name command; the install did not take"
        if is_windows_host; then
            place_command "$name" "$VENV_DIR/bin/$name" copy
        else
            place_command "$name" "$VENV_DIR/bin/$name" symlink
        fi
    done
}

install_pip_mode() {
    info "Installing ${INSTALL_SPEC:-$SOURCE_DIR} into $PYTHON with pip"
    pip_args="install"
    [ "$PIP_USER" = 1 ] && pip_args="$pip_args --user"
    [ "$BREAK_SYSTEM" = 1 ] && pip_args="$pip_args --break-system-packages"
    # shellcheck disable=SC2086
    if ! pip_log="$(run "$PYTHON" -m pip $pip_args "${INSTALL_SPEC:-$SOURCE_DIR}" 2>&1)"; then
        printf '%s\n' "$pip_log" >&2
        case "$pip_log" in
            *externally-managed-environment*)
                die "this Python is managed by your OS. Either use --mode venv (recommended),
       or re-run with --break-system-packages if you know what that does."
                ;;
        esac
        die "pip install failed"
    fi
    printf '%s\n' "$pip_log" | tail -3 | while IFS= read -r line; do note "$line"; done

    PIP_TARGET="$("$PYTHON" - "$PIP_USER" <<'PY'
import os, sys, sysconfig
scheme = "%s_user" % os.name if sys.argv[1] == "1" else None
print(sysconfig.get_path("scripts", scheme))
PY
)"
    COMMAND_KIND="symlink"
    for name in $COMMANDS; do
        if [ -x "$PIP_TARGET/$name" ]; then
            if [ "$PIP_TARGET" != "$BIN_DIR" ]; then
                place_command "$name" "$PIP_TARGET/$name" symlink
            else
                note "$name is already in $BIN_DIR"
                INSTALLED_COMMANDS="$INSTALLED_COMMANDS $BIN_DIR/$name"
            fi
        else
            note "pip did not create $PIP_TARGET/$name"
        fi
    done
}

# ------------------------------------------------------------------ manifest
# One key=value per line, and one repeated line per command or extension. Plain
# text, so writing it needs no Python and reading it needs no JSON parser:
# uninstall.sh works with sed on a machine that has nothing else.
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
        for dir in $VSCODE_DIRS; do printf 'extension=%s\n' "$dir"; done
        printf 'history_file=%s\n' "$HOME/.omniscript_history"
        printf 'installed_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo unknown)"
        printf 'mode=%s\n' "$MODE"
        printf 'package=omniscript-lang\n'
        printf 'pip_break_system_packages=%s\n' "$( [ "$BREAK_SYSTEM" = 1 ] && echo 1 || echo 0)"
        printf 'pip_scripts_dir=%s\n' "$PIP_TARGET"
        printf 'pip_user=%s\n' "$( [ "$PIP_USER" = 1 ] && echo 1 || echo 0)"
        printf 'python=%s\n' "$PYTHON"
        printf 'python_version=%s\n' "$PY_VERSION"
        printf 'ref=%s\n' "$REF"
        printf 'release_tag=%s\n' "$RELEASE_TAG"
        printf 'repo=%s\n' "$REPO_SLUG"
        printf 'repo_url=%s\n' "$REPO_URL"
        printf 'source=%s\n' "$SOURCE_DIR"
        printf 'venv=%s\n' "$INSTALLED_VENV"
        printf 'version=%s\n' "$OMNI_VERSION"
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
    smoke="$("$probe" -e 'let c = draw(8, 8)
c.rect(0, 0, 8, 8, "#2ea043")
print("smoke ok:", 6 * 7, [1, 2, 3].map((x) -> x * x).join(","))' 2>&1)"
    if [ $? -ne 0 ]; then
        VERIFY_ERROR="the interpreter did not run: $smoke"
        return 1
    fi
    note "$smoke"
    if [ -n "$RELEASE_TAG" ] && [ "$OMNI_VERSION" != unknown ]; then
        case "$reported" in
            *"$OMNI_VERSION"*) ;;
            *) VERIFY_ERROR="the release says $OMNI_VERSION but $probe reports: $reported"
               return 1 ;;
        esac
    fi
    return 0
}

# A release install that does not work is worse than no install: take back
# exactly the files it just wrote.
undo_release_install() {
    warn "rolling the release install back"
    for path in $INSTALLED_COMMANDS; do
        [ -n "$path" ] || continue
        if [ -L "$path" ] || [ -f "$path" ]; then
            rm -f "$path"
            note "removed $path"
        fi
    done
    if [ -f "$MANIFEST" ]; then
        rm -f "$MANIFEST"
        note "removed $MANIFEST"
    fi
}

# ------------------------------------------------------- editor extension
VSCODE_DIRS=""
install_vscode() {
    [ "$WITH_VSCODE" = 1 ] || return 0
    [ -n "$SOURCE_DIR" ] || die "--vscode needs a source tree with extras/vscode in it"
    [ -n "$PYTHON" ] || find_python
    EXT_VERSION="$("$PYTHON" - "$SOURCE_DIR" <<'PY'
import json, sys, pathlib
pkg = json.loads((pathlib.Path(sys.argv[1]) / "extras/vscode/package.json").read_text())
print("%s.%s-%s" % (pkg.get("publisher", "omninode"), pkg["name"], pkg["version"]))
PY
)" || die "could not read extras/vscode/package.json"
    found_editor=0
    for base in "$HOME/.vscode/extensions" "$HOME/.cursor/extensions" "$HOME/.vscode-server/extensions"; do
        editor_root="$(dirname "$base")"
        if [ -d "$editor_root" ] || [ "$base" = "$HOME/.vscode/extensions" ]; then
            ext_dir="$base/$EXT_VERSION"
            info "Installing the editor extension into $ext_dir"
            run mkdir -p "$ext_dir"
            run cp -R "$SOURCE_DIR/extras/vscode/." "$ext_dir/"
            VSCODE_DIRS="$VSCODE_DIRS $ext_dir"
            found_editor=1
        fi
    done
    [ "$found_editor" = 1 ] || note "no editor found; installed into ~/.vscode/extensions anyway"
    note "restart the editor to pick up OmniScript syntax highlighting"
}

# ======================================================================= main
# Which channel? An explicit one wins. Otherwise a source tree beside the script
# means "install what is here", and no source tree means "get me the release".
source_beside_us() {
    # Split in two on purpose: bash's parser trips over a redirection inside a
    # nested command substitution when it is in a function body.
    script_dir="$(dirname "$0")"
    here="$(cd "$script_dir" 2>/dev/null && pwd -P || true)"
    [ -n "$SOURCE_DIR" ] && return 0
    [ -n "$here" ] && [ -f "$here/omniscript/cli.py" ] && return 0
    [ -n "${OMNI_HOME:-}" ] && [ -f "$OMNI_HOME/omniscript/cli.py" ] && return 0
    return 1
}

if [ -z "$CHANNEL" ]; then
    if source_beside_us; then
        CHANNEL="beta"
        if [ "$DRY_RUN" != 1 ]; then
            note "installing from the source tree here (beta channel);"
            note "pass --channel release to take the published release instead"
        fi
    else
        CHANNEL="release"
    fi
fi
case "$CHANNEL" in
    release|beta) ;;
    *) usage >&2; die "--channel must be release or beta (got '$CHANNEL')" ;;
esac

RELEASE_RESULT=1
if [ "$CHANNEL" = release ]; then
    set +e
    install_release
    RELEASE_RESULT=$?
    set -e
    case "$RELEASE_RESULT" in
        0)  info "OmniScript $OMNI_VERSION from $RELEASE_TAG ($REL_ASSET_NAME)" ;;
        10) info "OmniScript $OMNI_VERSION from $RELEASE_TAG ($REL_ASSET_NAME)" ;;
        *)  [ -n "$REL_FATAL" ] && die "$REL_FATAL"
            warn "the release channel did not deliver; installing from $REPO_URL instead"
            CHANNEL="beta"
            ;;
    esac
fi

if [ "$RELEASE_RESULT" = 0 ]; then
    note "commands into $BIN_DIR, no Python needed"
elif [ "$RELEASE_RESULT" = 10 ]; then
    find_python
    note "python $PY_VERSION ($PYTHON), commands into $BIN_DIR, mode $MODE"
    ensure_bin_dir
    case "$MODE" in
        venv) install_venv_mode ;;
        pip) install_pip_mode ;;
        *) die "internal: a wheel was fetched for mode $MODE" ;;
    esac
    rm -f "$REL_DOWNLOAD"
else
    find_source
    find_python
    if [ -z "$PINNED" ]; then
        OMNI_VERSION="$("$PYTHON" -c "import sys; sys.path.insert(0, '$SOURCE_DIR'); import omniscript; print(omniscript.__version__)" 2>/dev/null || echo unknown)"
    else
        OMNI_VERSION="${PINNED#v}"
    fi
    info "OmniScript $OMNI_VERSION from $SOURCE_DIR"
    note "python $PY_VERSION ($PYTHON), commands into $BIN_DIR, mode $MODE"
    ensure_bin_dir
    case "$MODE" in
        symlink) install_symlink_mode ;;
        venv) install_venv_mode ;;
        pip) install_pip_mode ;;
    esac
fi

install_vscode
write_manifest
if ! verify_install; then
    if [ "$RELEASE_RESULT" = 0 ]; then
        warn "$VERIFY_ERROR"
        undo_release_install
    fi
    die "$VERIFY_ERROR"
fi

# ------------------------------------------------------------- PATH advice
case ":$PATH:" in
    *":$BIN_DIR:"*) on_path=1 ;;
    *) on_path=0 ;;
esac

if [ "$DRY_RUN" = 1 ]; then
    info "Dry run: nothing was changed"
    exit 0
fi

printf '\n'
info "OmniScript $OMNI_VERSION is installed ($CHANNEL channel)"
if [ "$on_path" = 1 ]; then
    note "run it with: omni -e 'print(\"hello\")'   or just: omni"
else
    note "$BIN_DIR is not on your PATH yet. Add this to your shell profile:"
    printf '\n        export PATH="%s:$PATH"\n\n' "$BIN_DIR"
    note "then open a new terminal, or run that line now."
fi
note "update with: omni update            ($CHANNEL channel)"
if [ -n "$SOURCE_DIR" ]; then
    note "uninstall with: $SOURCE_DIR/uninstall.sh"
else
    note "uninstall with: curl -fsSL https://raw.githubusercontent.com/$REPO_SLUG/main/uninstall.sh | bash"
fi
