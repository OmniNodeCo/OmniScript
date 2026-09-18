# Changelog

All notable changes, newest first. This is the native rewrite, starting at 1.0.0.

## [1.0.0] - 2026-09-18

Fresh start: no Python in the product.

### Added

- **Native binary, libc only.** One `omni` binary built with `cc` + `make`, no dependencies. `VERSION` file is the single source of truth.
- **Custom lexer/parser/evaluator** in C: arena allocation per statement, BOM accepted, `#` comments, `"""` triple-quoted strings, `name=value` keywords, `(a, b)` tuples, duplicate-keyword and positional-after-keyword errors.
- **Canvas and BMP writer** — `canvas_new`, `canvas_rect`, `canvas_circle`, `canvas_line`, `canvas_text`, `img_write_bmp` (24-bit BMP, no zlib). 5×7 pixel font hand-drawn for all 96 printable ASCII.
- **Hardware windows** — X11 backend (`-DHAVE_X11`, `-lX11`) with color allocation and button hit-testing, Win32 GDI backend (`-lgdi32`) with `CreateSolidBrush`/`Ellipse`/`LineTo`, and stub fallback that writes `drawing.bmp` when no display is present.
- **Built-ins:** `draw()`, `draw_gui.window_size()`, `draw_gui.button()`, `draw_gui()`, `cmd()`, `file(create|edit|delete)`, `input()`. Keyword aliases (`w`/`h`/`bg`/`colour`/`fill`/`r`/`pos`/`size`/`from`/`to`/`msg`/`text`/`label`/`action`/`command`/`on_click`/`do=`), pair parsing (`pos=(10,20)`, `size="800x600"`), window-size unpacking.
- **cmd() with true stderr capture** — POSIX dual pipes + `poll()` to avoid deadlock, background mode via `fork`+`setsid` or Win32 `DETACHED_PROCESS`, stdout and stderr both said.
- **file()** creates parents, refuses existing on create, counts occurrences on edit.
- **input()** with `prompt=` / `text=` / `msg=` keywords, `typed: ...` echo, EOF handling.
- **Updater with own crypto** — `src/sha256.c` FIPS 180-4, `src/update.c` minimal JSON (string unescape, `\uXXXX` → UTF-8), repo validation to block shell injection, asset `omni-<os>-<arch>[.exe]` + `omni-...sha256`, mandatory checksum verification, `exe_path` via `/proc/self/exe` / `_NSGetExecutablePath` / `GetModuleFileNameA`.
- **REPL** runs `omni ...` lines in-session (files, `-e`, `--version`, `update`) and bare `update`, `help`, `exit`, with paren/triple-string continuation and shell-like quoting. `help` lists language.
- **Installers** rewritten for native: release channel downloads `omni-<os>-<arch>` + `.sha256`, verifies, installs one `omni` binary; beta channel builds with `cc`+`make`. Both PowerShell and bash versions parse cleanly, manifest is key=value, `--force` keeps `.bak`.
- **Tests** — `tests/run.sh` 91 checks, POSIX sh, validates CLI, cmd capture (stdout+stderr, large interleaved), file lifecycle, input, lexer errors, removals (`import`/`python` removed in 1.0.0), draw with keyword aliases and BMP header validation (`BM` + dimensions + size field), draw_gui queue, REPL, update argument validation, and all examples.
- **Examples** — 7 native `.omni` files covering cmd, input, drawing, buttons, background, gui, files.
- **CI and release** — workflows build C on Linux/macOS/Windows, run test suite, exercise installers, build per-platform binaries, create `SHA256SUMS.txt` + per-binary `.sha256`, publish GitHub release.

### Removed

- Python package `omniscript/`, `pyproject.toml`, `tools/build_executable.py`, PyInstaller, zipapp, wheel, sdist, `python()` built-in, `import`/`from ... import` statements.
- Old wiki pages that described Python behavior.

### Fixed

- Font glyphs `g` and `q` previously indistinguishable from `9`; now have distinct descenders.
- `longjmp` clobber warnings in `run_source` fixed by using `ip->source` directly.
- `full_path` truncation warning fixed with bounded copy.
- `RGB` macro missing paren in Win32 stub fixed.
