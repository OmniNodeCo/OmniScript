# Changelog

## [2.0.0] - 2026-09-21

Super simple rewrite — cleared everything.

### Added

- **Imports like Python**: `import draw`, `import draw as d`, `from draw import window`, `from draw import *`
- **draw module**: `window`, `rect`, `circle`, `line`, `text`, `button`, `save`, `show`, `clear`, callable `draw()` — GUI buttons with shell actions, BMP fallback
- **cmd module**: `run`, `bg`/`background`, callable `cmd()` — foreground and background shell commands
- **pathlib module**: `read`, `write`, `append`, `exists`, `is_file`, `is_dir`, `mkdir`, `delete`, `list`, `join`, `name`, `parent`, `suffix`, `Path` object with bound methods
- **Builtins**: `print`, `input`
- **Simple language**: only imports, assignments, expressions, calls, attributes, tuples — newline or `;` separated

### Removed

- Old `draw()` element syntax, `draw_gui`, `file()`, complex eval, updater, sha256

## [1.0.1] - 2026-09-21

Old native rewrite — see git history.

## [1.0.0] - 2026-09-18

Initial native rewrite.
