# Changelog

Mirrors [`CHANGELOG.md`](../CHANGELOG.md) — repository file is source of truth.

## [1.0.0] - 2026-09-18

Fresh start: no Python in the product.

**Native binary, libc only.** One `omni` binary, `cc` + `make`, `VERSION` file is single source of truth.

**Custom lexer/parser/evaluator** in C, arena per statement, BOM accepted, `#` comments, `"""` triple strings, keywords, tuples, duplicate checks.

**Canvas and BMP writer** — rect, circle, line, text, 5×7 hand-drawn font, 24-bit BMP, no zlib.

**Hardware windows** — X11 on Linux, Win32 GDI on Windows, stub fallback writes BMP.

**Built-ins:** `draw()`, `draw_gui.window_size()`, `draw_gui.button()`, `draw_gui()`, `cmd()`, `file()`, `input()` with aliases and pair parsing.

**cmd()** captures stdout+stderr separately via dual pipes + poll(), background via fork/setsid or DETACHED_PROCESS.

**Updater** with own SHA-256 (FIPS 180-4) and minimal JSON, asset `omni-<os>-<arch>[.exe]` + `.sha256`, mandatory checksum.

**REPL** runs `omni ...` lines in-session, `help`, `exit`, continuation tracking.

**Installers** for native: release downloads verified binary; beta builds with `make`. Manifest key=value, `--force` keeps `.bak`.

**Tests** — 91 checks, POSIX sh, BMP header validation, examples.

**Examples** — 7 native `.omni` files.

**CI and release** — C builds on Linux/macOS/Windows, per-platform binaries, `SHA256SUMS.txt` + `.sha256`.
