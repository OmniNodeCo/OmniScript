# Changelog

All notable changes to OmniScript, newest first. Versions are `MAJOR.MINOR.PATCH`;
to install one in particular: `./install.sh --version 1.1.0`.

## [1.1.2] - 2026-09-17

Typing shell commands at the REPL prompt (`omni update`, `omni test.omni`)
failed with a parse error. The REPL now runs `omni ...` lines in the session --
files, `-e`, `--version` and `update` -- and understands bare `update`, `help`
and `exit`. The banner points at `help`.

## [1.1.1] - 2026-09-17

Scripts that Windows editors saved with a byte-order mark failed with a
cryptic `cannot read` error instead of running. Script files are now decoded
so the mark is silently accepted, with a backstop in the interpreter for pasted
or piped programs. CRLF endings, empty files and `#!` first lines are covered
by tests.

## [1.1.0] - 2026-09-17

The four initial drawing commands: imports, `draw()`, `draw_gui.button()` and
`draw_gui.window_size()`.

### Added

- **Imports work like Python.** `import math`, `import os as o`,
  `import os, sys`, `from math import sqrt`, `from math import floor as f` and
  `from math import *` all work. Whatever is imported is already bound inside
  `python()`, so `python("print(sqrt(16))")` just runs.
- **`draw_gui.window_size(...)`** sets the GUI window's size. It takes
  `window_size(800, 600)`, `window_size("800x600")`, `window_size((800, 600))`
  or keywords (`width=`, `height=`, `title=`, `background=`), and says the size
  back. `window_size(...)` also works as an element inside `draw(...)`.
- **`draw_gui.button(...)`** adds a button to the GUI: `button(pos=(20, 30),
  text="List files", action=cmd("ls"))`. `pos=` is `(x, y)`, `size=` is
  `(width, height)`, `action=` (also `command=`, `on_click=`) is the command
  that runs on click. Positional arguments work as before. The action is kept
  for the click and never runs early.
- **`draw_gui(...)`** shows the window: the queued buttons plus any elements it
  is given, at the `window_size`. With `save("gui.png")` it writes a PNG
  instead, so GUI scripts run headless too.
- **Keyword arguments and pairs everywhere.** Elements take `name=` keywords
  (`rect(x=0, y=0, color=blue)`), and `(20, 30)` in value position is a pair:
  `pos=(x, y)`, `size=(w, h)`, `from=(x1, y1)`, `to=(x2, y2)`.

### Changed

- Any import now enables `python()`; the error when there is none still points
  at `import python`.
- Drawing errors (a bad colour, a bad number) now point at the line with a
  caret instead of a bare traceback.
- The installer hint runs `omni -e 'cmd("echo hello")'`, which works, instead
  of a `print()` OmniScript never had.

### Examples and docs

- New examples: `examples/06_gui.omni` (window size, three buttons, a PNG) and
  `examples/07_imports.omni` (every import form).
- New `wiki/` pages: Home, Install, Uninstall, the four commands, draw_gui,
  imports and this changelog, synced to the GitHub wiki on every release.

## [1.0.0] - 2026-09-16

The first release: `draw()`, `cmd()`, `file()` and `python()` (after
`import python`), a PNG-or-window renderer with clickable buttons, `omni
update` on release and beta channels, `install.sh`/`install.ps1` and
`uninstall.sh`/`uninstall.ps1`, and the release pipeline that builds the
executables, the zipapp, the wheel and the sdist.
