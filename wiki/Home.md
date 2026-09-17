# OmniScript wiki

OmniScript is a language with four commands for drawing things. This wiki is
the manual; the [README](../README.md) is the one-page version.

## Start here

- [[Install]] — `omni` on your PATH in one line
- [[Four-Commands]] — the four initial commands, with examples
- [[Draw-GUI]] — windows, buttons and `pos=`
- [[Imports]] — imports work like Python
- [[Uninstall]] — taking it all back out
- [[Changelog]] — what changed in each version

## The four commands, in ten lines

```python
import math                   # imports work like Python
from math import sqrt

draw(window(640, 400, "Demo"),  # draw(): draws anything
     rect(0, 0, 640, 60, "#161b22"),
     text(20, 20, "Hello, OmniScript", white, 18),
     save("hello.png"))

draw_gui.window_size(640, 400, "Demo")
draw_gui.button(pos=(20, 300), text="List files", action=cmd("ls -la"))
draw_gui()                    # show the window
```

Beyond the four, `cmd()` runs shell commands, `file()` writes/edits/deletes
files, and `python()` runs Python once anything is imported.
