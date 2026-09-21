# OmniScript 2.0.0 — super simple

A tiny language, C only, no dependencies. Three modules, Python-like imports.

```omni
import draw
import cmd
import pathlib

draw.window(640, 400, "Demo")
draw.rect(0, 0, 640, 60, "#161b22")
draw.text(20, 20, "Hello, simple OmniScript", "white", 18)
draw.circle(320, 220, 80, "blue")
draw.button(20, 300, 140, 36, "List files", action="ls -la")
draw.show()  # opens window if possible, else writes drawing.bmp

cmd.run("ls -la")
cmd.bg("sleep 10")

pathlib.write("hello.txt", "hi")
print(pathlib.read("hello.txt"))
print(pathlib.exists("hello.txt"))

p = pathlib.Path("hello.txt")
print(p.read())
print(p.name())
```

## Install / Build

```bash
git clone https://github.com/OmniNodeCo/OmniScript
cd OmniScript
make
./omni --help
./omni examples/01_hello.omni
```

No X11? Drawings become BMP files.

## Language

Super simple:

- `#` comment
- newline or `;` separates statements
- `import draw` , `import draw as d` , `import draw, cmd`
- `from draw import window, rect` , `from draw import *` , `from draw import window as win`
- `x = 123` , `y = "hi"` , `z = (1, 2)`
- `print(...)` , `input("prompt: ")`
- calls: `func(1, 2, key=val)` , attributes: `draw.rect(...)` , `pathlib.Path("a").read()`

No loops, no ifs, no defs — just straight lines. Very very very simple.

## Modules

### `import draw`

Simple GUI and BMP:

- `draw.window(w, h, title?, bg?)` — also `draw.window_size` — supports `window("800x600")` or `window(size=(800,600))`
- `draw.rect(x, y, w, h, color?)` — kwargs: `pos=(x,y)`, `size=(w,h)`, `color=`
- `draw.circle(x, y, r, color?)` — `pos=`
- `draw.line(x1,y1,x2,y2, color?, width?)` — `from=(x1,y1)`, `to=(x2,y2)`, `thickness=`
- `draw.text(x, y, msg, color?, size?)` — `pos=`, `message=`
- `draw.button(x, y, w, h, label, action?)` — `pos=`, `size=`, `label=`, `action=` / `command=` / `on_click=` — action is shell command string run on click
- `draw.save(path)` — save BMP now
- `draw.show()` — show window or save to `drawing.bmp`
- `draw.clear()` — clear canvas
- `draw()` — callable, same as `show()`, also accepts elements: `draw(window(640,400), rect(...))`

Colors: `#rrggbb`, `#rgb`, or names: black, white, red, green, blue, yellow, orange, purple, pink, cyan, teal, navy, grey/gray, silver, gold, brown, lime, maroon, olive.

Buttons: when GUI available (X11 on Linux, Win32 on Windows), window shows. Clicking a button runs its `action` string as shell command and prints output. Press `q` or `Esc` to close.

### `import cmd`

Run shell commands:

- `cmd.run("ls -la")` — runs foreground, prints stdout+stderr, returns exit code
- `cmd.bg("sleep 10")` — runs in background (detached), returns pid
- `cmd("ls")` — shortcut for `run`

Background uses `fork`+`setsid` on Unix, `CreateProcess` detached on Windows.

### `import pathlib`

Python-like file paths:

- `pathlib.read(path)` — returns file content string
- `pathlib.write(path, content)` — writes, creates parents, returns full path
- `pathlib.append(path, content)`
- `pathlib.exists(path)` — bool
- `pathlib.is_file(path)` , `pathlib.is_dir(path)`
- `pathlib.mkdir(path)` — mkdir -p
- `pathlib.delete(path)` — also `unlink`, `remove`
- `pathlib.list(dir=".")` — returns tuple of names
- `pathlib.join(a, b, ...)` — join paths
- `pathlib.name(path)` / `basename`
- `pathlib.parent(path)` / `dirname`
- `pathlib.suffix(path)` / `ext`
- `pathlib.Path("file")` — returns Path object

Path object:

```omni
p = pathlib.Path("a.txt")
p.read()
p.write("hi")
p.exists()
p.is_file()
p.mkdir()
p.delete()
p.list()
p.name()
p.parent()
```

All paths resolved relative to cwd.

## Examples

- `01_hello.omni` — draw + cmd + pathlib
- `02_buttons.omni` — window with buttons
- `03_files.omni` — pathlib basics
- `04_cmd.omni` — background commands
- `05_imports.omni` — import styles

## How it is built

- `src/lex.c` — tokenizer
- `src/parse.c` — recursive descent, handles imports, assignments, calls, attributes, tuples
- `src/eval.c` — interpreter, env, modules: draw, cmd, pathlib
- `src/draw.c` — canvas, 5x7 font, BMP writer
- `src/gui_x11.c`, `src/gui_win32.c`, `src/gui_stub.c` — windowing
- `src/util.c` — arena, values, colors
- `src/main.c` — CLI + REPL

One binary, libc only.

## License

MIT
