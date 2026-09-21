#!/bin/sh
# OmniScript native test suite. Usage: sh tests/run.sh [./omni]
# POSIX sh only: it must run on dash, bash, zsh and the macOS shell.
OMNI="${1:-./omni}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "$OMNI" in
/*) ;;
*) OMNI="$(pwd)/$OMNI" ;;
esac
pass=0
fail=0
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
cd "$T" || exit 1

out=""
err=""
rc=0

run() {
    # run <stdin-file-or-empty> <omni args...>; sets out/err/rc
    in="$1"
    shift
    if [ -n "$in" ]; then
        out="$("$OMNI" "$@" <"$in" 2>"$T/stderr.txt")"
        rc=$?
    else
        out="$("$OMNI" "$@" 2>"$T/stderr.txt")"
        rc=$?
    fi
    err="$(cat "$T/stderr.txt")"
}

check() {
    # check <name> <want-rc> <want-out-substr> <want-err-substr> ("-" skips)
    name="$1"
    if [ "$rc" != "$2" ]; then
        fail=$((fail + 1))
        printf 'FAIL %s: exit %s, want %s\n  out: %s\n  err: %s\n' "$name" "$rc" "$2" "$out" "$err"
        return
    fi
    if [ "$3" != "-" ]; then
        case "$out" in
        *"$3"*) ;;
        *)
            fail=$((fail + 1))
            printf 'FAIL %s: stdout lacks %s\n  out: %s\n' "$name" "$3" "$out"
            return
            ;;
        esac
    fi
    if [ "$4" != "-" ]; then
        case "$err" in
        *"$4"*) ;;
        *)
            fail=$((fail + 1))
            printf 'FAIL %s: stderr lacks %s\n  err: %s\n' "$name" "$4" "$err"
            return
            ;;
        esac
    fi
    pass=$((pass + 1))
}

bmp_ok() {
    # bmp_ok <name> <file> <want-w> <want-h>: checks BM + dims + size field
    w="$(od -A n -t u1 -j 18 -N 4 "$2" | tr -d ' \n')"
    h="$(od -A n -t u1 -j 22 -N 4 "$2" | tr -d ' \n')"
    sig="$(od -A n -c -N 2 "$2" | tr -d ' \n')"
    # od prints decimal bytes LSB first; reassemble width/height/size
    dims="$(od -A d -t u4 -j 18 -N 8 "$2" | head -1)"
    sizef="$(od -A d -t u4 -j 2 -N 4 "$2" | head -1 | awk '{print $2}')"
    actual="$(wc -c <"$2" | tr -d ' ')"
    if [ "$sig" != "BM" ]; then
        fail=$((fail + 1))
        printf 'FAIL %s: %s is not a BMP\n' "$1" "$2"
        return
    fi
    case "$dims" in
    *"$3"*"$4"*) ;;
    *)
        fail=$((fail + 1))
        printf 'FAIL %s: dims %s, want %sx%s\n' "$1" "$dims" "$3" "$4"
        return
        ;;
    esac
    if [ "$sizef" != "$actual" ]; then
        fail=$((fail + 1))
        printf 'FAIL %s: size field %s != %s bytes\n' "$1" "$sizef" "$actual"
        return
    fi
    pass=$((pass + 1))
}

# ------------------------------------------------------------- CLI basics
# Version comes from VERSION file, not hardcoded
VER_EXPECTED="$(cat "$ROOT/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 1.0.0)"
[ -n "$VER_EXPECTED" ] || VER_EXPECTED="1.0.0"
run "" --version
check "version" 0 "$VER_EXPECTED" -
run "" -V
check "version-short" 0 "$VER_EXPECTED" -
run "" --help
check "help" 0 "omni FILE" -
run "" -h
check "help-short" 0 "omni FILE" -
run "" no-such-file.omni
check "missing-file" 1 - "cannot read"
run "" --bogus
check "bad-flag" 2 - "unknown option"
run "" -e
check "bare-e" 2 - "-e needs code"
run "" -e 'cmd("echo x")' extra
check "extra-arg" 2 - "unexpected argument"
run "" a.omni b.omni
check "two-files" 2 - "unexpected argument"

# -------------------------------------------------------------------- cmd
run "" -e 'cmd("echo hello")'
check "cmd-echo" 0 hello -
run "" -e 'cmd("exit 3")'
check "cmd-exit-code" 0 "the command exited 3" -
run "" -e 'cmd("echo oops >&2")'
check "cmd-stderr" 0 oops -
run "" -e 'cmd(background, "sleep 0.2")'
check "cmd-background" 0 "running in the background" -
run "" -e 'cmd("")'
check "cmd-empty" 1 - "empty command"
run "" -e 'cmd("echo x", out="f")'
check "cmd-kwarg" 1 - "takes no 'name=' arguments"
printf 'cmd("echo a")\ncmd("echo b")\n' > multi.omni
run "" multi.omni
check "cmd-multi" 0 b -
printf 'cmd("""echo one\necho two""")\n' > triple.omni
run "" triple.omni
check "cmd-triple" 0 two -

# ------------------------------------------------------------------- file
run "" -e 'file(create, "a.txt", "hi")'
check "file-create" 0 "created a.txt (2 bytes)" -
run "" -e 'file(create, "a.txt", "again")'
check "file-create-existing" 1 - "already there"
run "" -e 'file(create, "sub/dir/b.txt", "deep")'
check "file-create-nested" 0 "created sub/dir/b.txt" -
[ -f sub/dir/b.txt ] && pass=$((pass + 1)) || { fail=$((fail + 1)); printf 'FAIL file-nested-missing\n'; }
run "" -e 'file(edit, "a.txt", "hi", "hello")'
check "file-edit" 0 "edited a.txt (1 place)" -
[ "$(cat a.txt)" = "hello" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); printf 'FAIL file-edit-content: %s\n' "$(cat a.txt)"; }
run "" -e 'file(edit, "a.txt", "zzz", "q")'
check "file-edit-missing" 1 - "has no 'zzz' in it"
run "" -e 'file(edit, "a.txt", "hi")'
check "file-edit-args" 1 - "old, new"
run "" -e 'file(delete, "a.txt")'
check "file-delete" 0 "deleted a.txt (5 bytes)" -
run "" -e 'file(delete, "a.txt")'
check "file-delete-missing" 1 - "is not there"
run "" -e 'file(rename, "a.txt")'
check "file-bad-action" 1 - "create, edit, delete"
run "" -e 'file(create, "x.txt", "y", extra=1)'
check "file-kwarg" 1 - "takes no 'name=' arguments"

# ------------------------------------------------------------------ input
printf 'Bob\n' > name.txt
run name.txt -e 'input("Name: ")'
check "input-prompt" 0 "typed: Bob" -
case "$out" in
"Name: typed: Bob") pass=$((pass + 1)) ;;
*) fail=$((fail + 1)); printf 'FAIL input-echo-order: %s\n' "$out" ;;
esac
printf 'x\n' > x.txt
run x.txt -e 'input()'
check "input-bare" 0 "typed: x" -
: > empty.txt
run empty.txt -e 'input()'
check "input-eof" 1 - "nothing typed"
run x.txt -e 'input("a", "b")'
check "input-two-args" 1 - "takes a prompt"
run x.txt -e 'input(bogus="a")'
check "input-bad-kwarg" 1 - "has no 'bogus='"

# ------------------------------------------------------- lexer/parser errors
run "" -e 'cmd("oops)'
check "unclosed-string" 1 - "no closing quote"
run "" -e 'cmd(@)'
check "bad-char" 1 - "cannot read '@'"
run "" -e 'cmd("x"'
check "unclosed-paren" 1 - "never closed"
run "" -e 'draw(rectangle(1))'
check "bad-element" 1 - "no element called rectangle"
run "" -e 'draw(cmd("ls"))'
check "command-as-element" 1 - "not something draw() can place"
run "" -e 'draw()'
check "draw-empty" 1 - "needs something to draw"
run "" -e 'draw(draw_gui.button(1,2))'
check "dotted-inside-draw" 1 - "without the prefix"
run "" -e 'nosuch("x")'
check "bad-command" 1 - "no command called nosuch"
run "" -e 'rect(1,2,3)'
check "element-outside" 1 - "only belongs inside"
run "" -e 'draw_gui.zoom(1)'
check "gui-typo" 1 - "it has .button and .window_size"

# ---------------------------------------------------------------- removals
run "" -e 'import os'
check "import-removed" 1 - "imports were removed in 1.0.0"
run "" -e 'from os import path'
check "from-removed" 1 - "imports were removed in 1.0.0"
run "" -e 'python("1+1")'
check "python-removed" 1 - "python() was removed in 1.0.0"

# -------------------------------------------------------------------- draw
run "" -e 'draw(window(200, 100, "Hi"), save("pic.bmp"))'
check "draw-save" 0 "wrote pic.bmp (200x100)" -
bmp_ok "draw-bmp-valid" pic.bmp 200 100
run "" -e 'draw(window(50, 40), rect(1, 2, 3, 4, red), circle(9, 9, 3, blue), line(0, 0, 9, 9, green, 2), text(2, 20, "ok", white, 14), save("all.bmp"))'
check "draw-shapes" 0 "wrote all.bmp (50x40)" -
bmp_ok "shapes-bmp-valid" all.bmp 50 40
run "" -e 'draw(window(size="800x600", bg=navy), rect(pos=(10, 20), size=(30, 40), fill=red), circle(x=90, y=90, r=15, colour=lime), line(from=(0,0), to=(50,50), thickness=3), text(5, 120, msg="pairs", size=20), save(to="pairs.bmp"))'
check "draw-pairs" 0 "wrote pairs.bmp (800x600)" -
run "" -e 'draw(window_size("320x200"), save("wsz.bmp"))'
check "draw-wsz-string" 0 "wrote wsz.bmp (320x200)" -
run "" -e 'draw(window_size((100, 80)), save("wsz2.bmp"))'
check "draw-wsz-tuple" 0 "wrote wsz2.bmp (100x80)" -
run "" -e 'draw(window(64, 64), save("deep/nested/img.bmp"))'
check "draw-save-nested" 0 "wrote deep/nested/img.bmp (64x64)" -
run "" -e 'draw(window(100, 100, w=50))'
check "draw-dup-alias" 1 - "got 'width' twice"
run "" -e 'draw(rect(x=1, x=2))'
check "draw-dup-kwarg" 1 - "got 'x=' twice"
run "" -e 'draw(rect(0, 0, 10, 10, colour=nope))'
check "draw-bad-color" 1 - "is not a colour"
run "" -e 'draw(rect(0, 0, nope, 10))'
check "draw-bad-number" 1 - "has to be a number"
run "" -e 'draw(rect(0, 0, 99999, 10))'
check "draw-too-big" 1 - "between -8000 and 8000"
run "" -e 'draw(window(0, 10))'
check "draw-zero-window" 1 - "cannot be 0x10"
run "" -e 'draw(save())'
check "draw-save-nopath" 1 - "needs a file name"
run "" -e 'draw(window(40, 30))'
check "draw-fallback" 0 "there is no window here, so wrote drawing.bmp (40x30)" -
bmp_ok "fallback-bmp-valid" drawing.bmp 40 30

# ---------------------------------------------------------------- draw_gui
run "" -e 'draw_gui.window_size(300, 200, "T")'
check "gui-window-size" 0 'window size 300x200 "T"' -
run "" -e 'draw_gui.window_size(0, 10)'
check "gui-window-zero" 1 - "cannot be 0x10"
run "" -e 'draw_gui.button(10, 20, 100, 30, "Go", action=cmd("echo hi"))'
check "gui-button" 0 "added button 'Go' at (10, 20)" -
run "" -e 'draw_gui.button(1, 2, 3, 4, action="nope")'
check "gui-button-action" 1 - "has to be a command"
printf 'draw_gui.window_size(300, 200)\ndraw_gui.button(10, 20, 100, 30, "Go", action=cmd("echo hi"))\ndraw_gui()\n' > gui.omni
run "" gui.omni
check "gui-render" 0 "there is no window here, so wrote drawing.bmp (300x200)" -
bmp_ok "gui-bmp-valid" drawing.bmp 300 200

# -------------------------------------------------------------------- REPL
printf 'cmd("echo via-repl")\nexit\n' > repl1.txt
run repl1.txt
check "repl-cmd" 0 via-repl -
printf 'badline(\n"still")\ncmd("echo after")\nexit\n' > repl2.txt
run repl2.txt
check "repl-multiline-survives" 0 after -
case "$err" in
*"no command called badline"*) pass=$((pass + 1)) ;;
*) fail=$((fail + 1)); printf 'FAIL repl-multiline-error: %s\n' "$err" ;;
esac
printf 'omni --version\nexit\n' > repl3.txt
run repl3.txt
check "repl-omni-version" 0 "$VER_EXPECTED" -
printf "omni -e 'cmd(\"echo nested\")'\nexit\n" > repl4.txt
run repl4.txt
check "repl-omni-e" 0 nested -
printf 'update --bogus\nexit\n' > repl5.txt
run repl5.txt
check "repl-update-survives" 0 "omni> " -
printf 'help\nexit\n' > repl6.txt
run repl6.txt
check "repl-help" 0 "The language:" -

# ------------------------------------------------------- update validation
run "" update --bogus
check "update-bad-flag" 2 - "unknown option"
run "" update 1.x
check "update-bad-version" 2 - "not a version like 1.2.0"
run "" update 1.0.0 weekly
check "update-bad-channel" 2 - "stable or beta"
run "" update 1.0.0 stable /tmp a b
check "update-too-many" 2 - "too many arguments"
run "" update 1.0.0 stable /tmp 'x";id"'
check "update-bad-repo" 2 - "not a repo like owner/name"
run "" update --check latest stable nobody-has/this-repo-zzz
check "update-unknown-repo" 1 - "omni update:"

# ------------------------------------------------------- shipped examples
for ex in "$ROOT"/examples/*.omni; do
    name="$(basename "$ex")"
    run "$ROOT/tests/example_input.txt" "$ex"
    if [ "$rc" = 0 ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        printf 'FAIL example %s (exit %s): %s\n' "$name" "$rc" "$err"
    fi
done

# ------------------------------------------------------------------ summary
printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
