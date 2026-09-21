# How to Use

## Install

```bash
make
./omni --version  # should be 1.0.0
```

## Write a script

`hello.omni`:

```
import draw
import cmd
import pathlib

draw.window(640, 400, "Hello")
draw.rect(0, 0, 640, 60, "#161b22")
draw.text(20, 20, "Hello, simple OmniScript", "white", 18)
draw.button(20, 100, 140, 36, "List", action="ls -la")
draw.save("hello.bmp")

cmd.run("echo hi")

pathlib.write("hi.txt", "hello")
print(pathlib.read("hi.txt"))
```

## Run

```bash
omni hello.omni
omni -e 'import draw; draw.window(100,100); draw.rect(0,0,50,50,"red"); draw.save("a.bmp")'
omni   # REPL
```

Paths are relative to where you run `omni`. No window? Writes BMP.

## Imports (like Python)

```
import draw
import cmd, pathlib
import draw as d

from draw import window, rect, button, show
from draw import window as win
from draw import *
from pathlib import read, write
```

## draw

```
import draw

draw.window(640, 400, "Demo", "#0d1117")
draw.rect(0, 0, 100, 40, "red")           # x,y,w,h,color
draw.circle(100, 100, 30, "blue")
draw.line(0,0, 100,100, "green", 2)
draw.text(20,20, "Hi", "white", 18)
draw.button(20,80, 120,30, "Click", action="echo clicked")
draw.save("out.bmp")
draw.show()   # or draw()
draw.clear()
```

Kwargs:

- `rect(pos=(10,20), size=(100,40), color="red")`
- `circle(pos=(50,50), radius=20, color="blue")`
- `line(from=(0,0), to=(100,100), thickness=2)`
- `text(pos=(10,10), message="hi", size=14)`
- `button(pos=(20,30), size=(100,30), label="Go", action="ls")`
- `window(size=(800,600), title="Hi", background="#000")`
- `window("800x600")`

Colors: `#rrggbb`, `#rgb`, or names: black, white, red, green, blue, yellow, orange, purple, pink, cyan, teal, navy, grey, silver, gold, brown, lime, maroon, olive.

Buttons run shell command on click.

## cmd

```
import cmd

cmd.run("ls -la")          # foreground, prints output, returns code
cmd.bg("sleep 10")         # background, returns pid
cmd("echo hi")             # shortcut for run
```

## pathlib

```
import pathlib

pathlib.write("a.txt", "hi")
pathlib.read("a.txt")
pathlib.exists("a.txt")
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
p.write("hi")
p.read()
p.exists()
p.delete()
```

## Other

- `print("hello", 123)`
- `input("Name: ")`
- `x = 123` , `y = "hi"` , `z = (1, 2)`

That's it — very simple.
