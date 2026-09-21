# OmniScript 1.0.0 — native, no Python

[![build](https://github.com/OmniNodeCo/OmniScript/actions/workflows/build.yml/badge.svg)](https://github.com/OmniNodeCo/OmniScript/actions/workflows/build.yml)

OmniScript is a tiny language for drawing and automating things. **This is the native rewrite: one C binary, libc only, no Python, no libraries.** Everything is custom:

- lexer, parser, evaluator in C with arena allocation
- pixel canvas, shapes (rect, circle, line), 5×7 font drawn by hand, BMP writer with no zlib
- hardware windows: X11 on Linux, Win32 GDI on Windows, headless fallback writes `drawing.bmp`
- updater with its own SHA-256 and minimal JSON parser, `curl` for transport, checksum enforced
- `cmd()` captures stdout and stderr separately via `poll()` + dual pipes, `file()` and `input()` native

```omni
draw(
    window(640, 400, "Demo"),
    rect(0, 0, 640, 60, "#161b22"),
    text(20, 20, "Hello, native OmniScript", white, 18),
    circle(320, 220, 80, blue),
    save("hello.bmp")
)

draw_gui.window_size(640, 400, "Demo")
draw_gui.button(20, 300, 140, 36, "List files", action=cmd("ls -la"))
draw_gui()
```

A program is a list of commands. Each says what it did. There are no variables or loops — a bare word is its own name, which is how `create`, `background`, `red`, `blue` reach a command without quotes.

## Commands

- `draw(...)` — elements: `window(w, h, title, bg)`, `window_size(...)`, `rect(x, y, w, h, color)`, `circle(x, y, r, color)`, `line(x1, y1, x2, y2, color, width)`, `text(x, y, msg, color, size)`, `button(x, y, w, h, label, action=...)`, `save(path)`. With a display it opens a real window; without one it writes a BMP.
- `draw_gui.window_size(...)` — `window_size(800, 600)`, `window_size("800x600")`, `window_size((800, 600))`, or keywords `width=`, `height=`, `title=`, `background=` / `bg=` / `color=`.
- `draw_gui.button(...)` — `button(pos=(20, 30), text="Go", action=cmd("echo hi"))`. `pos=(x,y)`, `size=(w,h)`, `action=` / `command=` / `on_click=` / `do=` is the command kept for click. Also positional: `button(20, 30, 120, 32, "Go", cmd("..."))`.
- `draw_gui(...)` — shows the queued buttons plus its own elements. `save("gui.bmp")` writes a BMP instead.
- `cmd(...)` — shell command. `cmd(background, "sleep 10")` detaches. Prints combined output, says exit code if non-zero, returns pid/code.
- `file(...)` — `file(create, "a.txt", "hi")`, `file(edit, "a.txt", "old", "new")`, `file(delete, "a.txt")`. Creates parents, refuses overwrite on create.
- `input(...)` — `input("Name: ")` or `input(prompt="Name: ")`. Prints `typed: ...` and returns the line.

Keywords work everywhere: `rect(x=0, y=0, color=blue)`, `rect(pos=(0,0), size=(64,40))`, `line(from=(0,0), to=(9,9), thickness=3)`. Colors: `#rrggbb`, `#rgb`, or names: black, white, red, green, blue, yellow, orange, purple, pink, cyan, teal, navy, grey/gray, silver, gold, brown, lime, maroon, olive.

Errors point at the line with a caret.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash
```

```powershell
iwr -use1 https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.ps1 | iex
```

That takes the binary built for your machine from the newest release, verifies its `.sha256`, and puts `omni` on PATH. Channels: **release** (default) and **beta** (`-s beta`, builds from source with `cc` — no make required). `--version` pins a release, `--dry-run` shows the plan.

From a clone:

```bash
git clone https://github.com/OmniNodeCo/OmniScript
cd OmniScript
cc -O2 -std=c11 -Wall -Wextra -DOMNI_VERSION="1.0.2" -o omni src/*.c -lX11   # no make needed
# or
make                      # classic make still works
./omni --version
./omni examples/03_drawing.omni
./omni -e 'cmd("echo hi")'
./omni   # REPL
```

To remove:

```bash
./uninstall.sh --purge
```

```powershell
.\uninstall.ps1 -Purge
```

## Update

```bash
omni update --check
omni update
omni update 1.0.0 stable /tmp
```

Update needs `curl` and refuses to install without a checksum.

## How it is put together

- `src/lex.c`, `src/parse.c` — tokenizer and parser, BOM accepted, `#` comments, `"""` triple strings
- `src/eval.c` — evaluator, built-ins, color parser, GUI queue, error `longjmp`
- `src/draw.c` — canvas, 5×7 font (96 glyphs hand-drawn), BMP writer (24-bit, bottom-up, padded)
- `src/gui_x11.c`, `src/gui_win32.c`, `src/gui_stub.c` — native windows
- `src/sha256.c` — FIPS 180-4 SHA-256
- `src/update.c` — release discovery via GitHub API, asset `omni-<os>-<arch>[.exe]` + `.sha256`, verified install
- `src/main.c` — CLI, REPL with paren/triple-string tracking, `omni ...` inside REPL via shell-like split
- `src/util.c` — arena, output, numbers

Tests: `make test` or `sh tests/run.sh ./omni` — 91 checks, no Python.

## Examples

- `01_first_steps.omni` — cmd + file
- `02_asking.omni` — input
- `03_drawing.omni` — shapes to BMP
- `04_buttons.omni` — buttons to BMP
- `05_background.omni` — background cmd
- `06_gui.omni` — interactive window built line by line
- `07_files.omni` — file lifecycle
