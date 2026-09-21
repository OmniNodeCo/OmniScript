# Changelog

## [1.0.0] - 2026-09-21

Super simple — cleared everything. Native installers: Inno Setup EXE (Windows), DMG (macOS), DEB + tarball (Linux).

### Added

- **Imports like Python**: `import draw`, `import draw as d`, `from draw import window`, `from draw import *`
- **draw module**: `window`, `rect`, `circle`, `line`, `text`, `button`, `save`, `show`, `clear`, callable `draw()` — GUI buttons with shell actions, BMP fallback
- **cmd module**: `run`, `bg`/`background`, callable `cmd()` — foreground and background shell commands
- **pathlib module**: `read`, `write`, `append`, `exists`, `is_file`, `is_dir`, `mkdir`, `delete`, `list`, `join`, `name`, `parent`, `suffix`, `Path` object with bound methods
- **Builtins**: `print`, `input`
- **Simple language**: only imports, assignments, expressions, calls, attributes, tuples — newline or `;` separated
- **Installers**: `installer/windows/OmniScript.iss` Inno Setup 6 EXE, `installer/macos/build-dmg.sh` DMG + app bundle, `installer/linux/build-deb.sh` DEB + tarball, `installer/build-all.sh` + `make dist/dmg/deb`

### Removed

- Old `draw()` element syntax, `draw_gui`, `file()`, complex eval, updater, sha256, install.sh/install.ps1 curl-pipe (now native installers)
