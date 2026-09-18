# OmniScript — native 1.0.0

OmniScript is a tiny language for drawing and automating things. This is the native rewrite: **one C binary, libc only, no Python**.

- [[Install]] — one line, verified binary
- [[How-to-use]] — write and run scripts
- [[Changelog]] — what changed
- [[Uninstall]] — remove it

```
draw(
    window(640, 400, "Demo"),
    rect(0, 0, 640, 60, "#161b22"),
    text(20, 20, "Hello, native", white, 18),
    circle(320, 220, 80, blue),
    save("hello.bmp")
)

draw_gui.window_size(640, 400, "Demo")
draw_gui.button(20, 300, 140, 36, "List files", action=cmd("ls -la"))
draw_gui()
```

Commands: `draw`, `draw_gui.window_size`, `draw_gui.button`, `draw_gui`, `cmd`, `file`, `input`. No variables, no loops — a bare word is its own name.
