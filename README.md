# OmniScript

[![build](https://github.com/OmniNodeCo/OmniScript/actions/workflows/build.yml/badge.svg)](https://github.com/OmniNodeCo/OmniScript/actions/workflows/build.yml)

A language with four commands for drawing things. Imports work like Python,
`draw()` draws anything, and `draw_gui` puts buttons in a window:

```
import math                   # imports work like Python
from math import sqrt

draw(window(640, 400, "Demo"),  # a picture: a window, or a real one on screen
     rect(0, 0, 640, 60, "#161b22"),
     text(20, 20, "Hello, OmniScript", white, 18),
     circle(320, 240, 80, blue),
     save("hello.png"))

draw_gui.window_size(640, 400, "Demo")
draw_gui.button(pos=(20, 300), text="List files", action=cmd("ls -la"))
draw_gui()                    # show the window
```

A program is a list of commands. Each one says what it did. There are no
variables, no loops and nothing to define — a bare word is worth its own name,
which is how `create`, `background` and `blue` reach a command without quotes.

`cmd()`, `file()` and `python()` are still there for everything else: shell
commands, files, and anything Python can do. See [the changelog](CHANGELOG.md)
for what is new, and [the wiki](../../wiki) for the full guides.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash
```

```powershell
iwr -use1 https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.ps1 | iex
```

That takes the file built for your machine from the newest release, checks its
sha256 and puts `omni` and `omniscript` on your PATH. No Python needed. Two
channels: **release** (the default, this page's releases) and **beta**
(`-s beta`, the repository — `git pull` is then the upgrade, and it wants
Python 3.10+). `--version` pins one release, `--dry-run` shows the plan and
touches nothing, `uninstall.sh` takes the whole thing back out.

From a clone, there is nothing to build:

```bash
git clone https://github.com/OmniNodeCo/OmniScript
cd OmniScript
./omni                          # a REPL
./omni hello.omni               # a file
./omni -e 'cmd("echo hi")'      # one line
```

A virtual environment or a system-wide install is plain `pip install .`.

To remove it again:

```bash
./uninstall.sh --purge
```

```powershell
.\uninstall.ps1 -Purge
```

## The four commands

**`import ...`** works like Python: `import math`, `import os as o`,
`from math import sqrt`. Whatever you import is waiting for you inside
`python()`, and any import enables `python()`. (`import python` still works
exactly as before.)

**`draw(...)`** takes a list of elements — `window(w, h, title, background)`,
`rect(x, y, w, h, color)`, `circle(x, y, r, color)`, `line(x1, y1, x2, y2, color,
width)`, `text(x, y, "s", color, size)`, `button(x, y, w, h, "label", action)` —
and `save("file.png")`. With a screen, it opens a real window and the buttons
run their action when clicked. Without one — a server, CI — the same picture is
written as a PNG, drawn here in pure Python: no libraries, nothing to install.

Elements also take keywords: `rect(pos=(0, 0), size=(64, 40), color=blue)`,
`text(pos=(4, 4), text="hi", size=10)`, `line(from=(0, 0), to=(9, 9))`.

**`draw_gui.window_size(...)`** sets the GUI window's size: `window_size(800,
600)`, `window_size("800x600")`, `window_size(width=800, height=600,
title="Demo")`. It says the size back.

**`draw_gui.button(...)`** adds a button: `button(pos=(20, 30), text="List
files", action=cmd("ls"))`. `pos=` is `(x, y)`, `size=` is `(width, height)`,
and `action=` is the command that runs when the button is clicked — kept for
later, never run now. Positional arguments work too:
`button(20, 30, 150, 36, "List files", cmd("ls"))`.

**`draw_gui(...)`** shows the window: the queued buttons plus whatever elements
it is given, at the `window_size`. Give it `save("gui.png")` and it writes a
PNG instead — the headless-friendly way, and how the examples keep CI moving.

Colours take `#rrggbb`, `#rgb`, or a name: `red`, `green`, `blue`, `white`,
`black`, `yellow`, `orange`, `purple`, `pink`, `cyan`, `grey` and a few more.

Beyond the four: **`cmd(...)`** runs a shell command (`cmd(background, ...)`
without waiting), **`file(create | edit | delete, path, ...)`** writes, edits
and removes files, and **`python(...)`** runs Python once anything is imported.

## Update

```bash
omni update --check     # what is published, what you have
omni update             # fetch it, check the sha256, swap it in, prove it runs
omni update -c beta     # follow the repository instead
```

## How it is put together

`omniscript/language.py` is the lexer, the parser and the interpreter.
`omniscript/draw.py` is the pixels, the shapes, the 3x5 font and the PNG
writer, plus the tkinter window. `omniscript/cli.py` is the command line and
the REPL. `omniscript/update.py` is `omni update`.

Tests: `python -m unittest discover -s tests`.
