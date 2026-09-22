# OmniScript — very very very simple

A tiny programming language. One C binary, no dependencies.

```
import draw
import cmd
import pathlib
```

Three modules, Python-like imports.

## Install — OS integrated, type `omni` and it reacts, runs files

### Windows — EXE (Inno Setup) — works like git CLI

```bat
installer\windows\build.bat
```

**How git CLI works (researched):** Git installer requires admin, adds `C:\Program Files\Git\cmd` to BOTH SYSTEM and USER PATH via registry + setx, broadcasts WM_SETTINGCHANGE, copies wrapper to location always in PATH. After install, **reopen terminal**, then `git --version` works in CMD/PowerShell/Terminal/Git Bash.

**Omni 1.0.3 does same:**
- `PrivilegesRequired=admin`, adds `C:\Program Files\OmniScript` to SYSTEM+USER PATH always, setx /M + PowerShell SetEnvironmentVariable, broadcast WM_SETTINGCHANGE
- Fallback copies to `C:\Windows\omni.exe`, `C:\Windows\System32\omni.exe`, `%LOCALAPPDATA%\Microsoft\WindowsApps\omni.exe` (always in PATH like python), plus `omni.bat` wrappers
- App Paths registry + `.omni` file association double-click runs file
- Includes `fix-path.ps1` like git troubleshooting

Output: `dist/OmniScript-1.0.3-Windows-x86_64-Setup.exe`

**After install, REOPEN terminal (CMD, PowerShell, Windows Terminal, Git Bash, VS Code terminal all work), then it reacts:**

```bat
omni --version
omni
omni examples\01_hello.omni
omni myfile.omni
omni -e "import draw; draw.window(200,100); draw.rect(0,0,50,50,\"red\"); draw.show()"
```

If `'omni' is not recognized` (old 1.0.0/1.0.1):
```bat
"C:\Program Files\OmniScript\omni.exe" --version
powershell -ExecutionPolicy Bypass -File "C:\Program Files\OmniScript\fix-path.ps1"
:: reopen terminal
omni --version
```
Or install **1.0.3** — works like git.

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
sudo dpkg -i dist/omniscript_1.0.3_amd64.deb
sudo rpm -i dist/omniscript-1.0.3-1.x86_64.rpm
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
