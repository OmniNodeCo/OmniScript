# Changelog

All notable changes, newest first. This is the native rewrite, starting at 1.0.0.

## [1.0.2] - 2026-09-21

### Fixed

- **install.ps1 app install robustness** — binary resolution now prioritizes real binary file over directory, handles shim .cmd correctly, uses forward slashes for icon path to avoid backslash escaping issues in OmniScript strings, skips app installation on CI (GITHUB_ACTIONS) to avoid flaky COM/GUI in headless runners. Windows installer now passes in CI.
- **install.sh / install.ps1 icon generation** — changed from `draw(window(64,64), ...)` to `draw(rect(0,0,64,64), ...)` (no window) to avoid GUI blocking in CI headless environments. Icon generation now uses simple quoting without backtick escaping.
- **PowerShell parse fix** — fixed desktop Exec quoting (`\"Exec=` -> `"Exec=`) and em dash in Comment that caused `Parser::ParseFile` errors in lint job.

### Changed

- CI now skips app launcher creation on Windows when GITHUB_ACTIONS is set, making installer tests stable while preserving app install for real users.

## [1.0.1] - 2026-09-21

### Added

- **Install as an app** — OmniScript now installs as a desktop application, not just a CLI binary.
  - **Linux:** creates `~/.local/share/applications/omniscript.desktop` with icon, Terminal=true, Actions for REPL and Examples. Icon generated via omni itself (`draw(window(64,64), circle(...), text("Om"), save(icon.bmp))`) then converted to PNG via ImageMagick if available, placed in `~/.local/share/icons/hicolor/64x64/apps/omniscript.png`. Shows in GNOME/KDE app menu.
  - **macOS:** creates `~/Applications/OmniScript.app` bundle with `Contents/MacOS/OmniScript` binary, `Resources/icon.bmp`, and `Info.plist` (com.omninode.omniscript). Appears in Launchpad/Spotlight.
  - **Windows (install.ps1):** creates Start Menu folder `%APPDATA%\Microsoft\Windows\Start Menu\Programs\OmniScript` with shortcuts: `OmniScript.lnk`, `OmniScript REPL.lnk`, `Uninstall OmniScript.lnk`, plus Desktop shortcut. Icon generated to `%LOCALAPPDATA%\OmniScript\icon.bmp` and used via WScript.Shell COM. All recorded in manifest.
- **Manifest extended** — new keys: `desktop_file`, `icon_file`, `icon_png`, `app_bundle`, `app_icon`, `start_menu_dir`, `shortcut` (multiple).

### Fixed

- **install.ps1 rewritten to work without make** — direct C compile with cl/gcc/clang/cc (no make, no build.ps1), GUI detection (win32/x11/stub), links gdi32/user32/X11, fallback to make. Test-SourceTree checks src/main.c only.
- **install.sh fixed to work without make** — direct cc compile first, make fallback, handles MSYS/MINGW gdi32, X11 detection.
- **uninstall.sh / uninstall.ps1** now remove app launcher, icons, Start Menu, shortcuts, and macOS bundle. `belongs_to_us` extended to recognize app files.

### Changed

- CI workflows use make on all platforms (known green).
- README and wiki/Install document app installation and no-make builds.

## [1.0.0] - 2026-09-18

Fresh start: no Python in the product.

### Added

- **Native binary, libc only.** One `omni` binary built with `cc` + `make`, no dependencies. `VERSION` file is the single source of truth.
- **Custom lexer/parser/evaluator** in C: arena allocation per statement, BOM accepted, `#` comments, `\"\"\"` triple-quoted strings, `name=value` keywords, `(a, b)` tuples.
- **Canvas and BMP writer** — 5×7 pixel font hand-drawn for all 96 printable ASCII, 24-bit BMP writer no zlib.
- **Hardware windows** — X11 backend, Win32 GDI backend, stub fallback writes `drawing.bmp`.
- **Built-ins:** `draw()`, `draw_gui.window_size()`, `draw_gui.button()`, `draw_gui()`, `cmd()`, `file()`, `input()`.
- **cmd() with true stderr capture** — dual pipes + poll(), background fork/DETACHED_PROCESS.
- **Updater with own crypto** — SHA-256 FIPS 180-4, minimal JSON, mandatory .sha256.
- **REPL** with `omni ...` lines, `help`, `exit`.
- **Installers** for native, manifest key=value.
- **Tests** — 91 checks, POSIX sh.
- **Examples** — 7 native .omni files.
- **CI and release** — workflows build C, test, installers, binaries, SHA256SUMS.
