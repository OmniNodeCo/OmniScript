# Changelog

All notable changes to OmniScript are documented here. The format follows Keep a Changelog and versioning follows Semantic Versioning.

## [0.3.0] - 2026-08-17

### Added

- Dependency-free `http`, `csv`, `crypto`, `date`, `system`, and `data` utility packages.
- Advanced easy-layout GUI controls: headings, status text, dropdowns, listboxes, sliders, progress bars, themes, timers, and native file/color dialogs.
- Package guide, advanced GUI dashboard, utility package example, and complete mocked tests.

## [0.2.1] - 2026-08-17

### Fixed

- Update checks now query GitHub's releases API directly and ignore stale cached 404 responses.
- Installers clear update metadata after replacing OmniScript, so newly published releases appear immediately.
- Self-updates now reset private PyInstaller bootloader state before validating the replacement executable.

## [0.2.0] - 2026-08-17

### Added

- Beginner-friendly built-in `gui` package with automatic layout, common controls, dialogs, and ordinary craft callbacks.
- GUI tutorial, complete example application, mocked desktop tests, and GUI modules in native executable builds.
- Interactive `omni update` menu that checks GitHub Releases, shows the latest published version, and offers verified release or nightly channels.

## [0.1.0] - 2026-08-17

### Added

- Original `.omni` lexical grammar, parser, AST, semantic checker, and tree-walking runtime.
- Bindings, crafts, closures, shapes, control flow, collections, ranges, pipelines, modules, assertions, and diagnostics.
- Built-in collection/file crafts and `math`, `text`, `json`, `path`, and `random` modules.
- CLI with run, REPL, check, format, test, init, token, AST, and doctor commands.
- Binary-first POSIX shell, Windows Batch, and PowerShell installers and uninstallers.
- PyInstaller build tooling and separate build/release workflows for Linux/Windows x86-64 and ARM64 plus Apple Silicon macOS.
- Cached `omni update` release checks and cache-aware uninstallers.
- Custom VS Code language extension with commands and snippets.
- Language, CLI, standard-library, module, design, and embedding documentation.
- Examples, unit tests, project metadata, Dockerfile, and cross-platform CI.
