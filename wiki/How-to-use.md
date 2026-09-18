# How to Use

## 1. Check the install

```bash
omni --version
```

You should see `1.0.0`. If not found, see [[Install]] — usually `~/.local/bin` is not on PATH yet.

## 2. Write a script

Save as `hello.omni`:

```
cmd("echo hello from native OmniScript")

draw(
    window(320, 120, "Hi"),
    text(20, 20, "Hello, OmniScript", white, 18),
    save("hello.bmp")
)
```

## 3. Run it

```bash
omni hello.omni
```

That is the workflow: `omni` plus the file. It prints what each command did, and writes `hello.bmp`. Other ways:

| How | Example |
|---|---|
| A file | `omni hello.omni` |
| One line | `omni -e 'cmd("echo hi")'` |
| Interactive | `omni` (REPL — `omni file.omni` and `omni update` work inside too; `exit` to leave) |
| Shebang | `#!/usr/bin/env omni` on first line, then `chmod +x hello.omni` |

Paths in scripts are relative to **where you run `omni`**. With no display (server, CI) drawings become BMP files — `drawing.bmp` by default, or `save("name.bmp")` you choose.

## 4. Drawing

```
draw(
    window(640, 400, "Demo", "#0d1117"),
    rect(10, 10, 100, 40, red),
    circle(200, 100, 30, blue),
    line(0, 0, 640, 400, green, 2),
    text(20, 60, "Hi", white, 21),
    button(20, 100, 120, 32, "Go", action=cmd("echo clicked")),
    save("pic.bmp")
)
```

Keywords and pairs:

- `rect(pos=(10,20), size=(30,40), color=red)`
- `rect(x=0, y=0, w=100, h=40, fill=red)`
- `circle(x=90, y=90, r=15, colour=lime)`
- `line(from=(0,0), to=(50,50), thickness=3)`
- `text(pos=(4,4), text="hi", size=10)`
- `window(size="800x600", bg=navy)`
- `window_size("800x600")` or `window_size((800,600))`

Colors: `#rrggbb`, `#rgb`, or names: black, white, red, green, blue, yellow, orange, purple, pink, cyan, teal, navy, grey/gray, silver, gold, brown, lime, maroon, olive.

## 5. GUI

```
draw_gui.window_size(340, 180, "Greeter")
draw_gui.button(20, 30, 140, 36, "Greet", action=cmd("echo Hello"))
draw_gui.button(180, 30, 140, 36, "Files", action=cmd("ls -la"))
draw_gui()
```

On Linux needs X11 headers at build time; on Windows uses Win32 GDI; otherwise writes a BMP. Buttons say `clicked 'Label'` then run their action.

## 6. Other commands

- `cmd("ls -la")` — runs shell, prints stdout+stderr, says exit code if non-zero
- `cmd(background, "sleep 10")` — detaches, says pid
- `file(create, "a.txt", "hi")` — creates, refuses if exists
- `file(edit, "a.txt", "old", "new")` — counts replacements
- `file(delete, "a.txt")`
- `input("Name: ")` — prompt, echoes `typed: ...`

## 7. If it does not work

| Symptom | Fix |
|---|---|
| `omni: command not found` | Add install dir to PATH ([[Install]]), new terminal |
| `there is no command called ...` | Check spelling; commands are `draw`, `draw_gui`, `cmd`, `file`, `input`, `draw_gui.button`, `draw_gui.window_size` |
| `cannot read '@' here` | Invalid character; strings need quotes |
| `never closed` | Missing `)` |
| `is not a colour` | Use `#rrggbb` or named colors |
| Error with `^` under line | File, line, column — read it |

Still stuck? [[Uninstall]] removes everything.
