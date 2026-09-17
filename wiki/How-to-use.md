# How to Use

## 1. Check the install

```bash
omni --version
```

You should see `OmniScript 1.1.1` (or newer). If the command is not found, see
[[Install]] — usually `~/.local/bin` is not on your PATH yet.

## 2. Write a script

Save this as `hello.omni`:

```python
cmd("echo hello from OmniScript")

draw(window(320, 120, "Hi"),
     text(20, 20, "Hello, OmniScript", white, 18),
     save("hello.png"))
```

## 3. Run it

```bash
omni hello.omni
```

That is the whole workflow: `omni` plus the file. It prints what each command
did, and writes `hello.png` next to it. Other ways to run:

| How | Example |
|---|---|
| A file | `omni hello.omni` |
| One line | `omni -e 'cmd("echo hi")'` |
| Interactive | `omni` (a REPL; Ctrl-D to leave) |
| Directly | `chmod +x hello.omni` with `#!/usr/bin/env omni` on the first line |

Paths in a script are relative to **where you run `omni`**, so run it from the
script's folder. With no screen (a server, CI) drawings are written as PNGs
instead of opening windows — see [[Draw-GUI]].

## 4. If it does not work

| Symptom | Fix |
|---|---|
| `omni: command not found` | Add the install dir to PATH ([[Install]]), open a new terminal |
| `there is no command called draw_gui` | You have 1.0.0: run `omni update` |
| `cannot read` on line 1 of a Windows-saved file | Fixed in 1.1.1: run `omni update` |
| Quotes vanish in `-e` on Windows | The `.cmd` shim eats them — put the code in a file instead |
| An error with a `^` under a line | Read it: it names the file, line and what was expected |

Still stuck? [[Uninstall]] takes everything back out for a clean reinstall.
