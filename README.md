# OmniScript — very very very simple

A tiny programming language. One C binary, no dependencies.

```
import draw
import cmd
import pathlib
```

Three modules, Python-like imports.

## Install — OS integrated, type `omni` and it reacts, runs files

### Windows — EXE (Inno Setup) — works like the Python installer

```bat
installer\windows\build.bat
```

**How the Python installer makes `python` work in the terminal (researched, python.org):**
1. Default is **per-user, NO admin required** — installs to `%LOCALAPPDATA%\Programs\Python\PythonXY`
2. Optional "install for all users" (admin) → `C:\Program Files\PythonXY` + machine PATH
3. Adds install dir to **USER PATH** (always) / machine PATH (all-users)
4. Registers **App Paths** so Start-menu search / Win+Run find `python`
5. Per-user file association (`.py`) via HKCU — no admin
6. Open a **new terminal** → `python` works in CMD, PowerShell, Windows Terminal, Git Bash

**Omni 1.0.4 does exactly the same:**
- Per-user default: `%LOCALAPPDATA%\Programs\OmniScript` — no UAC prompt, install never fails
- Always adds `{app}` to **USER PATH** (machine PATH + `C:\Windows\omni.exe` fallback only for "all users"/admin, done safely in code)
- Copies `omni.exe` to `%LOCALAPPDATA%\Microsoft\WindowsApps` — always in user PATH on Win10/11, no admin
- App Paths in HKCU — Start search + Win+Run find `omni`
- Per-user `.omni` file association (double-click runs file)
- Includes `fix-path.ps1` troubleshooting

Output: `dist/OmniScript-1.0.4-Windows-x86_64-Setup.exe`

**After install, OPEN A NEW TERMINAL (CMD, PowerShell, Windows Terminal, Git Bash, VS Code terminal all work), then it reacts:**

```bat
omni --version
omni
omni examples\01_hello.omni
omni myfile.omni
omni -e "import draw; draw.window(200,100); draw.rect(0,0,50,50,\"red\"); draw.show()"
```

If `'omni' is not recognized` (old 1.0.0–1.0.3 installs):
```bat
"%LOCALAPPDATA%\Programs\OmniScript\omni.exe" --version
powershell -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\Programs\OmniScript\fix-path.ps1"
:: open a new terminal
omni --version
```
Or install **1.0.4** — works like Python.

### macOS — DMG + PKG

```bash
./installer/macos/build-dmg.sh
# Drag OmniScript.app to Applications
# Double-click Install CLI.command inside DMG
omni --version
omni examples/01_hello.omni
```

### Linux — DEB + RPM

```bash
sudo dpkg -i dist/omniscript_1.0.4_amd64.deb
sudo rpm -i dist/omniscript-1.0.4-1.x86_64.rpm
omni --version
omni examples/01_hello.omni
```

### All

```bash
./installer/build-all.sh
make dist
```

## How to run files — researched and tested

OmniScript binary (`src/main.c`) supports:

```bash
omni FILE              # run script file
omni -e "CODE"         # run one-liner
omni --version
omni --help
omni                   # REPL, type help, exit
```

**Windows tested:**
- `omni examples\01_hello.omni` — runs file, shows GUI or writes BMP
- `omni myfile.omni` — any .omni file, path with spaces needs quotes: `omni "C:\My Files\test.omni"`
- Double-click `.omni` file → runs via file association (`HKCR\.omni` → `OmniScriptFile` → `"{app}\omni.exe" "%1"`)
- `omni -e "import cmd; cmd.run(\"dir\")"` — runs command

**All terminals work:** CMD, PowerShell, Windows Terminal, Git Bash, VS Code terminal — after reopen.

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
omni hello.omni
omni -e "import pathlib; print(pathlib.read(\"hi.txt\"))"
```

## Language

```omni
import draw, cmd, pathlib
from draw import window, rect
x = 123
print("hi", x)
```

- newline or `;` separates statements, `=` assign, `a.b` attr, `f(1,2,key=val)` call, `(1,2)` tuple

## Modules

- `draw`: window, rect, circle, line, text, button, save, show, clear
- `cmd`: run, bg
- `pathlib`: read/write/exists/mkdir/list/delete + Path object

## Structure

```
src/omni.h, lex.c, parse.c, eval.c, draw.c, gui_*.c, util.c, main.c
installer/windows/OmniScript.iss   # EXE — OS integrated, git-like, file assoc
installer/macos/build-dmg.sh       # DMG + PKG + Install CLI.command
installer/linux/build-deb.sh       # DEB
installer/linux/build-rpm.sh       # RPM
installer/windows/fix-path.ps1     # fix PATH like git
```

MIT
