#!/bin/sh
# Simple tests for OmniScript 1.0.0 simple
OMNI="${1:-./omni}"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
case "$OMNI" in /*) ;; *) OMNI="$(pwd)/$OMNI" ;; esac
pass=0
fail=0
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
cd "$T" || exit 1

out=""
err=""
rc=0

run() {
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

VER_EXPECTED="$(cat "$ROOT/VERSION" 2>/dev/null | tr -d ' \t\n\r' || echo 1.0.0)"
run "" --version
check "version" 0 "$VER_EXPECTED" -

# imports
run "" -e 'import draw; print("ok")'
check "import draw" 0 "imported draw" -

run "" -e 'import cmd; print("ok")'
check "import cmd" 0 "imported cmd" -

run "" -e 'import pathlib; print("ok")'
check "import pathlib" 0 "imported pathlib" -

run "" -e 'from draw import rect, circle; print("ok")'
check "from import" 0 "imported draw.rect" -

run "" -e 'import draw as d; d.window(100,100); d.rect(0,0,10,10,"red"); d.save("a.bmp")'
check "draw save" 0 "wrote a.bmp" -
if [ -f a.bmp ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL bmp not created"; fi

# cmd
run "" -e 'import cmd; cmd.run("echo hello")'
check "cmd run" 0 "hello" -

run "" -e 'import cmd; cmd.bg("sleep 0.1")'
check "cmd bg" 0 "running in background" -

# pathlib
run "" -e 'import pathlib; pathlib.write("t.txt","hi"); print(pathlib.read("t.txt"))'
check "pathlib write/read" 0 "hi" -

run "" -e 'import pathlib; pathlib.write("t.txt","hi"); print(pathlib.exists("t.txt"))'
check "pathlib exists" 0 "True" -

run "" -e 'import pathlib; pathlib.write("t.txt","hi"); pathlib.delete("t.txt"); print(pathlib.exists("t.txt"))'
check "pathlib delete" 0 "False" -

run "" -e 'import pathlib; p=pathlib.Path("a.txt"); p.write("hello"); print(p.read())'
check "pathlib Path object" 0 "hello" -

# draw features
run "" -e 'import draw; draw.window(200,100); draw.circle(50,50,20,"red"); draw.save("c.bmp")'
check "draw circle" 0 "wrote c.bmp" -

run "" -e 'import draw; draw.window(200,100); draw.line(0,0,100,100,"blue",2); draw.save("l.bmp")'
check "draw line" 0 "wrote l.bmp" -

run "" -e 'import draw; draw.window(200,100); draw.text(10,10,"hi","white",14); draw.save("t.bmp")'
check "draw text" 0 "wrote t.bmp" -

run "" -e 'import draw; draw.window(200,100); draw.button(10,10,80,30,"btn", action="echo clicked"); draw.save("b.bmp")'
check "draw button" 0 "added button" -

# print
run "" -e 'print("hello world")'
check "print" 0 "hello world" -

# assignment
run "" -e 'x = "test"; print(x)'
check "assign" 0 "test" -

echo "--- $pass passed, $fail failed ---"
if [ "$fail" -ne 0 ]; then exit 1; fi
