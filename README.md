# OmniScript — very very very simple

A tiny programming language. One C file binary, no dependencies.

```
import draw
import cmd
import pathlib
```

That's it. Three modules.

## Build

```bash
make
./omni --version   # 2.0.0
./omni --help
```

No make? `cc -O2 -std=c11 -o omni src/*.c -lX11` (Linux) or `src/gui_stub.c` if no X11.

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

No GUI? It writes `drawing.bmp` automatically.

## Language

Super simple, no tricks:

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

- statements separated by newline or `;`
- `=` assignment
- `a.b` attribute
- `f(1, 2, key=val)` call with positional + keyword args
- `(1, 2)` tuple

No loops, no if, no functions — just straight lines.

## Modules

### draw — GUI + BMP

```omni
import draw

draw.window(800, 600, "My App", "#0d1117")   # or window("800x600") or window(size=(800,600))
draw.rect(10, 10, 100, 50, "red")            # x,y,w,h,color
draw.circle(100, 100, 30, "blue")            # x,y,r,color
draw.line(0, 0, 100, 100, "green", 2)        # x1,y1,x2,y2,color,width
draw.text(20, 20, "Hello", "white", 18)      # x,y,msg,color,size
draw.button(20, 80, 120, 30, "Click", action="ls -la")
draw.save("out.bmp")
draw.show()   # or draw()
draw.clear()
```

Kwargs work: `rect(pos=(10,20), size=(100,40), color="red")`, `circle(pos=(50,50), radius=20)`, `line(from=(0,0), to=(10,10), thickness=2)`, `text(pos=(0,0), message="hi")`, `button(pos=(0,0), size=(100,30), label="Go", action="echo hi")`.

Colors: `#rrggbb`, `#rgb`, or `black white red green blue yellow orange purple pink cyan teal navy grey gray silver gold brown lime maroon olive`.

Buttons: when window is shown (X11 / Win32), clicking runs the `action` shell command. Press `q` or `Esc` to close.

### cmd — shell commands

```omni
import cmd

cmd.run("ls -la")   # foreground, prints output, returns exit code
cmd.bg("sleep 10")  # background, returns pid
cmd("pwd")          # same as run
```

### pathlib — like Python

```omni
import pathlib

pathlib.write("a.txt", "hi")
pathlib.read("a.txt")
pathlib.append("a.txt", " more")
pathlib.exists("a.txt")   # True/False
pathlib.is_file("a.txt")
pathlib.is_dir("mydir")
pathlib.mkdir("mydir/sub")
pathlib.list(".")
pathlib.delete("a.txt")
pathlib.join("a", "b", "c.txt")
pathlib.name("a/b/c.txt")
pathlib.parent("a/b/c.txt")
pathlib.suffix("a.txt")

p = pathlib.Path("a.txt")
p.write("hello")
p.read()
p.exists()
p.delete()
p.name()
p.parent()
```

## Examples

```
examples/
  01_hello.omni    draw + cmd + pathlib
  02_buttons.omni  buttons
  03_files.omni    pathlib
  04_cmd.omni      background jobs
  05_imports.omni  import styles
  06_gui.omni      full gui demo
```

## REPL

```bash
./omni
omni> import draw
omni> draw.window(200,100)
omni> draw.rect(0,0,50,50,"red")
omni> draw.show()
omni> exit
```

## Structure

```
src/
  omni.h    types
  lex.c     tokenizer
  parse.c   parser (imports, assign, call, attr, tuple)
  eval.c    interpreter + draw/cmd/pathlib modules
  draw.c    canvas + 5x7 font + BMP
  gui_x11.c / gui_win32.c / gui_stub.c
  util.c    values + colors + arena
  main.c    cli + repl
```

One binary, libc only.

## License

MIT
