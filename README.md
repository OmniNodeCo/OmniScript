# OmniScript — very very very simple

A tiny programming language. One C binary, no dependencies.

```
import draw
import cmd
import pathlib
```

Three modules, Python-like imports.

## Install — native installers (EXE, DMG, DEB, RPM) — OS integrated, type `omni` and it reacts

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
Output: `dist/OmniScript-1.0.1-Windows-x86_64-Setup.exe` — installs to Program Files, adds to **both SYSTEM and USER PATH**, creates fallback copy in `C:\Windows\omni.exe`, Start Menu + uninstaller.

**After install, REOPEN terminal, then:**
```bat
omni --version
omni
```

If you still see `'omni' is not recognized`:
1. **Reopen** CMD/PowerShell (old window doesn't get new PATH)
2. Try full path: `"C:\Program Files\OmniScript\omni.exe" --version`
3. Or: `C:\Windows\omni.exe --version` (fallback copy)
4. Manual PATH: `setx PATH "%PATH%;C:\Program Files\OmniScript"` then reopen terminal
5. PowerShell: `$env:Path += ";C:\Program Files\OmniScript"; omni --version`

### macOS — DMG + PKG

```bash
./installer/macos/build-dmg.sh
```
Creates `dist/OmniScript-1.0.1-macOS.dmg` with `OmniScript.app` + `Install CLI.command`. Drag to Applications, then double-click `Install CLI.command` to install `omni` to `/usr/local/bin`.

```bash
omni --version
omni
```

### Linux — DEB + RPM + tarball

```bash
./installer/linux/build-deb.sh
sudo dpkg -i dist/omniscript_1.0.1_amd64.deb

./installer/linux/build-rpm.sh
sudo rpm -i dist/omniscript-1.0.1-1.x86_64.rpm

# After install, type and it reacts:
omni --version
omni
```

### All installers

```bash
./installer/build-all.sh
# or
make dist
```

Creates `dist/` with tarball, DEB, RPM, DMG, PKG, EXE + `SHA256SUMS.txt`.

### Quick build (dev)

```bash
make
./omni --version   # 1.0.1
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

### cmd

```omni
import cmd
cmd.run("ls -la")
cmd.bg("sleep 10")
```

### pathlib

```omni
import pathlib
pathlib.write("a.txt", "hi")
pathlib.read("a.txt")
p = pathlib.Path("a.txt")
p.write("hello")
```

## Structure

```
src/omni.h, lex.c, parse.c, eval.c, draw.c, gui_*.c, util.c, main.c
installer/windows/OmniScript.iss   # Inno Setup EXE — OS integrated
installer/macos/build-dmg.sh       # DMG + PKG
installer/linux/build-deb.sh       # DEB
installer/linux/build-rpm.sh       # RPM
installer/build-all.sh             # all
```

MIT
