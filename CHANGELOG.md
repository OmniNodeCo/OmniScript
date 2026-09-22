# Changelog

## [1.0.2] - 2026-09-22

Make `omni` runnable in any terminal and able to run files — OS integrated, file association.

### Fixed

- **Windows PATH**: `omni` not recognized after install — now adds to BOTH SYSTEM and USER PATH, always (even if task unchecked), broadcasts WM_SETTINGCHANGE, creates fallback copies in `{win}\omni.exe` and `{sys}\omni.exe` so `omni` works immediately even before PATH reload. Works in CMD, PowerShell, Windows Terminal, Git Bash.
- **Windows file association**: Added `.omni` file association — double-click `.omni` file runs with OmniScript, registry `HKCR\.omni` -> `OmniScriptFile`, `shell\open\command` = `"{app}\omni.exe" "%1"`.
- **Windows EXE**: Now runs `omni --version` and shows message "REOPEN terminal, then type: omni --version and omni examples\01_hello.omni"

### Added

- `omni file.omni` — runs files (already in main.c, now OS integrated via file association)
- `omni -e "code"` — runs one-liner
- `omni` — REPL

## [1.0.1] - 2026-09-22

Fix Windows `omni` not recognized after install — OS integrated, type `omni` and it reacts.

### Fixed

- **Windows EXE**: Adds to both SYSTEM and USER PATH, broadcasts WM_SETTINGCHANGE, fallback copy in `{win}\omni.exe`, always adds PATH, App Paths registry.
- **Inno Setup**: Added `desktopicon` task, fixed `OMNI_VERSION` quoting.

### Added

- **RPM**: `installer/linux/build-rpm.sh`
- **macOS**: DMG includes `Install CLI.command` + `install-cli.sh` + PKG

## [1.0.0] - 2026-09-21

Super simple — native installers: Inno Setup EXE, DMG, DEB, RPM.

### Added

- Imports like Python, draw module with GUI buttons, cmd background, pathlib like Python
- Installers: EXE, DMG, DEB, RPM, build-all.sh
