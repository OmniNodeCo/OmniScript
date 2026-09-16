# OmniScript

A language with four commands. That is the whole idea: the things you actually
reach for, spelled the short way, and Python one `import` away when you need more.

```
import python                     # the escape hatch, and the only import

draw(window(640, 400, "Demo"),    # a picture: a window, or a real one on screen
     rect(0, 0, 640, 60, "#161b22"),
     text(20, 20, "Hello, OmniScript", white, 18),
     circle(320, 240, 80, blue),
     button(20, 340, 150, 36, "List files", cmd("ls -la")),
     save("hello.png"))

cmd("tree /f")                    # a shell command, and its output
cmd(background, "python3 -m http.server 8000")   # ...without waiting for it

file(create, "notes.txt", "first line\nsecond line\n")
file(edit, "notes.txt", "first", "FIRST")
file(delete, "notes.txt")

python("print(6 * 7)")            # anything Python can do, in one line
```

A program is a list of commands. Each one says what it did. There are no
variables, no loops and nothing to define — a bare word is worth its own name,
which is how `create`, `background` and `blue` reach a command without quotes.

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

## The four commands

**`draw(...)`** takes a list of elements — `window(w, h, title, background)`,
`rect(x, y, w, h, color)`, `circle(x, y, r, color)`, `line(x1, y1, x2, y2, color,
width)`, `text(x, y, "s", color, size)`, `button(x, y, w, h, "label", action)` —
and `save("file.png")`. With a screen, it opens a real window and the buttons
run their action when clicked. Without one — a server, CI — the same picture is
written as a PNG, drawn here in pure Python: no libraries, nothing to install.

**`cmd(...)`** runs a shell command in the program's directory and prints what
it said. `cmd(background, ...)` starts it detached and carries on.

**`file(create | edit | delete, path, ...)`** writes a new file, replaces text
in an existing one (`file(edit, path, old, new)`), or removes it. It refuses to
clobber, and it says how many bytes or places it touched.

**`python(...)`** runs Python, once `import python` is at the top. An
expression prints its value; anything else just runs.

Colours take `#rrggbb`, `#rgb`, or a name: `red`, `green`, `blue`, `white`,
`black`, `yellow`, `orange`, `purple`, `pink`, `cyan`, `grey` and a few more.

## Update

```bash
omni update --check     # what is published, what you have
omni update             # fetch it, check the sha256, swap it in, prove it runs
omni update -c beta     # follow the repository instead
```

## How it is put together

`omniscript/language.py` is the lexer, the parser and the interpreter — the
grammar fits in three lines. `omniscript/draw.py` is the pixels, the shapes,
the 3x5 font and the PNG writer, plus the tkinter window. `omniscript/cli.py`
is the command line and the REPL. `omniscript/update.py` is `omni update`.

Tests: `python -m unittest discover -s tests`.
