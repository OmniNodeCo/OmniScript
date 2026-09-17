# draw_gui

The GUI side of OmniScript in three steps: size the window, add buttons, show
it. ([examples/06_gui.omni](../examples/06_gui.omni) runs end to end.)

```python
draw_gui.window_size(420, 260, "GUI demo")

draw_gui.button(pos=(16, 60), size=(180, 40), text="List this folder",
                action=cmd("ls"))
draw_gui.button(pos=(16, 112), size=(180, 40), text="Write a note",
                action=file(create, "clicked.txt", "clicked\n"))

draw_gui(text(16, 16, "Click one:", white, 14),
         save("gui.png"))
```

## window_size

```python
draw_gui.window_size(800, 600)                        # width, height
draw_gui.window_size(800, 600, "Demo")                # ...title
draw_gui.window_size(800, 600, "Demo", "#0d1117")     # ...background
draw_gui.window_size("800x600")                       # a string
draw_gui.window_size((800, 600))                      # a pair
draw_gui.window_size(size=(800, 600), title="Demo")   # keywords
```

Keywords: `width=` (`w=`), `height=` (`h=`), `title=` (`name=`),
`background=` (`bg=`, `color=`), `size=(w, h)`. Default is `640x400
"OmniScript"`. `window_size(...)` also works as an element inside `draw(...)`.

## button

```python
draw_gui.button(pos=(20, 30), text="List files", action=cmd("ls -la"))
draw_gui.button(20, 30, 150, 36, "List files", cmd("ls -la"))  # positional
```

| Keyword | Meaning | Default |
|---|---|---|
| `pos=(x, y)` / `x=`, `y=` | where the button goes | `(0, 0)` |
| `size=(w, h)` / `width=`, `height=` | how big it is | `120x32` |
| `text=` (`label=`, `title=`, `caption=`) | what it says | `"button"` |
| `action=` (`command=`, `on_click=`) | the command on click | none |

The action is any command — `cmd(...)`, `file(...)`, `python(...)`,
`draw(...)` — and it runs when clicked, never before. In a PNG the button is
drawn so you can see what the window holds.

## draw_gui()

```python
draw_gui()                                     # queued buttons, at window_size
draw_gui(text(16, 16, "Hi", white, 14))        # ...plus elements
draw_gui(save("gui.png"))                      # ...as a PNG, no window needed
```

`draw_gui()` shows the queued buttons plus whatever elements it is given. An
explicit `window(...)` in the list wins over the `window_size`. After a
successful show the queue is empty again, ready for the next window.

With a screen you get a real window with clickable buttons; without one (a
server, CI) the same picture is written to `drawing.png` — unless `save(...)`
names the file.
