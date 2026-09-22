# Changelog

## [1.0.3] - 2026-09-22

Make it work like `git` CLI does — `omni` runnable in any terminal immediately, runs files.

### Fixed

- **Windows like git**: Now works like `git` CLI — installer adds to BOTH SYSTEM and USER PATH, always, broadcasts WM_SETTINGCHANGE, creates fallback copies in `{win}\omni.exe`, `{sys}\omni.exe`, and `{localappdata}\Microsoft\WindowsApps\omni.exe` (which is always in user PATH). Also creates `omni.bat` wrappers in Windows dirs. After install, **reopen terminal** and `omni` works in CMD, PowerShell, Windows Terminal, Git Bash like `git`.
- **File association**: `.omni` double-click runs file via `"{app}\omni.exe" "%1"`, plus `omni file.omni` and `omni -e "code"` work.
- Added `fix-path.ps1` — PowerShell script to fix PATH immediately if `omni` not recognized (like `git` troubleshooting).

### Added

- `installer/windows/fix-path.ps1` — fixes PATH like git
- `PrivilegesRequired=admin` with override dialog — ensures PATH and Windows dir copy works like git installer

## [1.0.2] - 2026-09-22

Make `omni` runnable in any terminal and able to run files — OS integrated, file association.

### Fixed

- Windows PATH adds to SYSTEM+USER, fallback copies, file association .omni

## [1.0.1] - 2026-09-22

Fix Windows `omni` not recognized — OS integrated.

## [1.0.0] - 2026-09-21

Super simple — native installers: EXE, DMG, DEB, RPM.
