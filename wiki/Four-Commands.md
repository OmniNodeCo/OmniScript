# The four commands

OmniScript's initial set: imports, `draw()`, `draw_gui.button()` and
`draw_gui.window_size()`. A program is a list of commands; each one says what
it did. There are no variables, no loops and nothing to define — a bare word
is worth its own name (`create`, `background`, `blue`).

## 1. Imports — normal, like Python

```python
import math
import os as operating_system
from math import sqrt
```

Whatever you import is already bound inside `python()`, and any import enables
`python()`. See [[Imports]] for the whole story.

## 2. draw() — draws anything

```python
draw(window(640, 400, "Demo"),
     rect(0, 0, 640, 60, "#161b22"),
     text(20, 20, "Hello, OmniScript", white, 18),
     circle(320, 240, 80, blue),
     line(0, 399, 640, 399, red, 2),
     button(20, 340, 150, 36, "List files", cmd("ls -la")),
     save("hello.png"))
```

Elements: `window(w, h, title, background)`, `rect(x, y, w, h, color)`,
`circle(x, y, r, color)`, `line(x1, y1, x2, y2, color, width)`,
`text(x, y, "s", color, size)`, `button(x, y, w, h, "label", action)`,
`window_size(...)` (a window by another name) and `save("file.png")`.

- With a screen it opens a real window; clicking a button runs its action.
- With `save(...)`, or with no screen at all, it writes a PNG instead — pure
  Python, no libraries.
- Elements take keywords too: `rect(pos=(0, 0), size=(64, 40), color=blue)`,
  `text(pos=(4, 4), text="hi", size=10)`, `line(from=(0, 0), to=(9, 9))`.
- Colours: `#rrggbb`, `#rgb`, or a name (`red`, `green`, `blue`, `white`,
  `black`, `yellow`, `orange`, `purple`, `pink`, `cyan`, `grey`, …).

## 3. draw_gui.window_size() — the window size

```python
draw_gui.window_size(800, 600)
draw_gui.window_size("800x600")
draw_gui.window_size(width=800, height=600, title="Demo", background="#0d1117")
```

Sets the GUI window's size (and title, and background) and says it back:
`window size 800x600 "Demo"`.

## 4. draw_gui.button() — draw a button

```python
draw_gui.button(pos=(20, 30), text="List files", action=cmd("ls -la"))
```

- `pos=(x, y)` where it goes; `size=(w, h)` how big (default `120x32`).
- `text=` (also `label=`, `title=`, `caption=`) what it says.
- `action=` (also `command=`, `on_click=`) what runs on click — a command like
  `cmd("ls")` or `file(create, "a.txt", "hi")`. It is kept for the click and
  never runs early.
- Positional form works too: `button(20, 30, 150, 36, "List files", cmd("ls"))`.

Each call answers `added button 'List files' at (20, 30)`.

## Showing it: draw_gui()

```python
draw_gui()                    # the queued buttons, at the window_size
draw_gui(text(16, 16, "Hi"), save("gui.png"))   # plus elements; a PNG instead
```

`draw_gui()` opens the window with everything queued so far. Give it
`save(...)` and it writes a PNG — the headless-friendly way. See [[Draw-GUI]].

## Beyond the four

- `cmd("tree /f")` runs a shell command; `cmd(background, ...)` does not wait.
- `file(create, "a.txt", "hi")`, `file(edit, "a.txt", "a", "b")`,
  `file(delete, "a.txt")` write, edit and remove files.
- `python("print(6 * 7)")` runs Python once anything is imported.
