# OmniScript — very very very simple

A tiny programming language. One C binary, no dependencies.

```
import draw
import cmd
import pathlib
```

Three modules, Python-like imports.

## Install

No more `curl | bash`. Proper native installers in `installer/`:

### Windows — Inno Setup EXE

```bat
installer\windows\build.bat
```
Or PowerShell:
```powershell
installer\windows\build.ps1
```
Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php).  
Output: `dist/OmniScript-1.0.0-Windows-x86_64-Setup.exe` — installs to Program Files, adds to PATH, Start Menu + uninstaller.

### macOS — DMG

```bash
./installer/macos/build-dmg.sh
```
Creates `dist/OmniScript-1.0.0-macOS.dmg` with `OmniScript.app`. Drag to Applications.

### Linux — DEB + tarball

```bash
./installer/linux/build-deb.sh
sudo dpkg -i dist/omniscript_1.0.0_amd64.deb
# or
sudo apt install ./dist/omniscript_1.0.0_amd64.deb
```

Also builds `dist/omniscript-1.0.0-linux-amd64.tar.gz`.

### All installers

```bash
./installer/build-all.sh
# or
make dist
```

Creates `dist/` with tarball, DEB, DMG (or tar.gz fallback) and `SHA256SUMS.txt`.

### Quick build (dev)

```bash
make
./omni --version   # 1.0.0
./omni --help
sudo make install  # to /usr/local/bin
```

## Hello World

`hello.omni`:

```omni
import draw
import cmd
import pathlib

draw.window(640, 400, "Demo")
draw.rect(0, 0, 640, 60, "#161b22")
draw.text(20, 20, "Hello, OmniScript", "white", 18)
draw.circle(320, 220, 80, "blue")
draw.button(20, 300, 140, 36, "List files", action="ls -la")
draw.show()

cmd.run("echo hi")

pathlib.write("hi.txt", "hello")
print(pathlib.read("hi.txt"))
```

```bash
./omni hello.omni
```

No GUI? Writes `drawing.bmp`.

## Language

```omni
# comment
import draw
import draw as d
import draw, cmd, pathlib
from draw import window, rect
from draw import window as win
from draw import *

x = 123
y = "hello"
z = (10, 20)

print("hi", x, y)
input("Name: ")
```

- newline or `;` separates statements
- `=` assignment, `a.b` attribute, `f(1, 2, key=val)` call, `(1,2)` tuple
- No loops, no if, no defs — straight lines only

## Modules

### draw

```omni
import draw
draw.window(800, 600, "My App", "#0d1117")
draw.rect(10, 10, 100, 50, "red")
draw.circle(100, 100, 30, "blue")
draw.line(0, 0, 100, 100, "green", 2)
draw.text(20, 20, "Hello", "white", 18)
draw.button(20, 80, 120, 30, "Click", action="ls -la")
draw.save("out.bmp")
draw.show()
draw.clear()
```

Kwargs: `pos=(x,y)`, `size=(w,h)`, `color=`, `radius=`, `thickness=`, `message=`, `label=`, `action=` / `command=` / `on_click=`.

Colors: `#rrggbb`, `#rgb`, or names: black white red green blue yellow orange purple pink cyan teal navy grey gray silver gold brown lime maroon olive.

Buttons run shell command on click. `q` / `Esc` to close.

### cmd

```omni
import cmd
cmd.run("ls -la")   # foreground, returns code
cmd.bg("sleep 10")  # background, returns pid
cmd("pwd")          # shortcut
```

### pathlib

```omni
import pathlib
pathlib.write("a.txt", "hi")
pathlib.read("a.txt")
pathlib.exists("a.txt")
pathlib.mkdir("dir")
pathlib.list(".")
pathlib.delete("a.txt")

p = pathlib.Path("a.txt")
p.write("hello")
p.read()
p.name()
p.parent()
```

## Examples

- `01_hello.omni` — draw + cmd + pathlib
- `02_buttons.omni` — buttons
- `03_files.omni` — pathlib
- `04_cmd.omni` — background
- `05_imports.omni` — import styles
- `06_gui.omni` — full GUI

## REPL

```bash
./omni
omni> import draw
omni> draw.window(200,100)
omni> draw.rect(0,0,50,50,"red")
omni> draw.show()
```

## Structure

```
src/omni.h, lex.c, parse.c, eval.c, draw.c, gui_*.c, util.c, main.c
installer/windows/OmniScript.iss   # Inno Setup
installer/macos/build-dmg.sh       # DMG
installer/linux/build-deb.sh       # DEB
installer/build-all.sh             # all
```

MIT
