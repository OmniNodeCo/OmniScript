# Changelog

## [1.0.1] - 2026-09-22

Fix Windows `omni` not recognized after install — OS integrated, type `omni` and it reacts.

### Fixed

- **Windows EXE**: Now adds to both SYSTEM and USER PATH, broadcasts WM_SETTINGCHANGE, creates fallback copy in `{win}\omni.exe`, always adds PATH even if task unchecked, adds App Paths registry for `omni` and `omni.exe`. After install, **reopen terminal** then `omni --version` works.
- **Inno Setup**: Added `desktopicon` task, fixed `OMNI_VERSION` quoting in `build.bat`/`build.ps1` (`-DOMNI_VERSION=\"1.0.1\"`), added `omni-wrapper.bat`.

### Added

- **RPM**: `installer/linux/build-rpm.sh` — `omniscript-1.0.1-1.x86_64.rpm`
- **macOS**: DMG now includes `Install CLI.command` + `install-cli.sh` + `README.txt`, builds PKG via `pkgbuild` for OS integration

## [1.0.0] - 2026-09-21

Super simple — cleared everything. Native installers: Inno Setup EXE (Windows), DMG (macOS), DEB + RPM + tarball (Linux).

### Added

- **Imports like Python**: `import draw`, `import draw as d`, `from draw import window`, `from draw import *`
- **draw module**: `window`, `rect`, `circle`, `line`, `text`, `button`, `save`, `show`, `clear`, callable `draw()` — GUI buttons with shell actions, BMP fallback
- **cmd module**: `run`, `bg`/`background`, callable `cmd()` — foreground and background shell commands
- **pathlib module**: `read`, `write`, `append`, `exists`, `is_file`, `is_dir`, `mkdir`, `delete`, `list`, `join`, `name`, `parent`, `suffix`, `Path` object with bound methods
- **Builtins**: `print`, `input`
- **Simple language**: only imports, assignments, expressions, calls, attributes, tuples — newline or `;` separated
- **Installers**: `installer/windows/OmniScript.iss` Inno Setup 6 EXE, `installer/macos/build-dmg.sh` DMG + app bundle + PKG, `installer/linux/build-deb.sh` DEB, `installer/linux/build-rpm.sh` RPM, `installer/build-all.sh` + `make dist/dmg/deb/rpm/exe`

### Removed

- Old `draw()` element syntax, `draw_gui`, `file()`, complex eval, updater, sha256, install.sh/install.ps1 curl-pipe (now native installers)
