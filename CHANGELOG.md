# Changelog

## [1.0.4] - 2026-09-22

Windows installer redesigned like the **Python installer** (python.org) — the proven way for the terminal to react to a new CLI after install.

### Changed (Windows)

- **Like Python: per-user install, NO admin required** — default install dir `%LOCALAPPDATA%\Programs\OmniScript` (exactly where Python puts itself: `%LOCALAPPDATA%\Programs\Python\PythonXY`). No UAC prompt, no failed admin copies, install can never break.
- **Like Python: adds to USER PATH always** — `C:\Users\You\AppData\Local\Programs\OmniScript` added to the user PATH (machine PATH only when you choose "install for all users", like Python does).
- **Like Python: `omni.exe` copied to `%LOCALAPPDATA%\Microsoft\WindowsApps`** — a dir always in the user PATH on Win10/11, no admin needed. `omni` resolves even if the PATH edit is slow to apply.
- **Like Python: App Paths in HKCU** (no admin) — Start-menu search and Win+Run find `omni`.
- **Like Python: per-user `.omni` file association** via `HKCU\Software\Classes` (no admin) — double-click runs file.
- **All-users option** (Python "Install for all users"): installs to `C:\Program Files\OmniScript`, adds machine PATH, fallback `C:\Windows\omni.exe` — done safely in code, only when elevated.
- Removed `setx /M` (truncates PATH) and hard `[Files]` copies to `C:\Windows`/`System32` (broke per-user installs — root cause of "omni not recognized").

### Fixed

- Per-user (non-admin) installs previously failed on `C:\Windows` copies → PATH entry could be lost → `omni` not recognized. Now everything user-writable, like Python.

### Usage after install (new terminal)

```bat
omni --version
omni
omni examples\01_hello.omni
omni myfile.omni
```

## [1.0.3] - 2026-09-22

git-like CLI fix attempt: admin + SYSTEM/USER PATH + C:\Windows fallbacks. Superseded by 1.0.4 (Python style).

## [1.0.2] - 2026-09-22

Make `omni` runnable in any terminal and able to run files — OS integrated, file association.

## [1.0.1] - 2026-09-22

Fix Windows `omni` not recognized — OS integrated.

## [1.0.0] - 2026-09-21

Super simple — native installers: EXE, DMG, DEB, RPM.
