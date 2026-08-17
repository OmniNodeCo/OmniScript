# CLI reference

The installed executable is `omni`; `omniscript` is an alias.

## `omni run [file] [-- arguments...]`

Parse, check, and execute a program. If `file` is omitted, the CLI reads `[project].entry` from `omni.toml`. Program arguments are exposed as a sealed `args` list.

```bash
omni run src/main.omni -- one two
omni src/main.omni
omni run --no-check generated.omni
```

## `omni repl`

Start an interactive environment. A non-void expression is displayed with `=>`. Declarations remain available until exit.

## `omni check files...`

Run lexical, syntactic, and semantic checks without executing source. It catches unknown names, duplicate declarations, writes to sealed bindings, and misplaced `return`, `break`, or `continue`.

```bash
omni check src/main.omni tests/main_test.omni
```

Exit status is nonzero if any file has a problem.

## `omni fmt files...`

Apply four-space block indentation, remove trailing whitespace, preserve comments/token spelling, and ensure a final newline. Invalid source is never rewritten.

```bash
omni fmt src/main.omni
omni fmt --check src/main.omni tests/main_test.omni
```

`--check` is intended for CI and does not alter files.

## `omni test [path]`

Recursively discover `*_test.omni` files, run each in a fresh isolated environment, and print a pass/fail summary. A failed `assert`, check error, parse error, or runtime error fails that file.

```bash
omni test
omni test tests/parser_test.omni
omni test examples/tests
```

## `omni init name`

Scaffold `omni.toml`, `src/main.omni`, `tests/main_test.omni`, and `.gitignore`. Use `.` for the current directory. The command refuses to write into a nonempty directory unless `--force` is supplied.

## `omni update`

Open a small interactive menu that asks which channel to install:

```text
Checking GitHub Releases...
OmniScript 0.3.0 updater
Latest GitHub release: 0.1.0
Release page: https://github.com/OmniNodeCo/OmniScript/releases/tag/v0.1.0
  1) Release — latest published, stable build
  2) Nightly — newest verified development build
  3) Check only — do not install anything
Choose 1, 2, or 3 [1]:
```

For scripts or advanced use, skip the menu explicitly:

```bash
omni update --channel release
omni update --channel nightly
omni update --channel release --yes  # permit an intentional downgrade
omni update --check
omni update --force --check   # bypass cached release information
omni update --json            # machine-readable release check
omni update --clear-cache
```

Before showing the menu, OmniScript queries GitHub's latest-release API and displays the version and release page it found. Release information is cached for 24 hours. If GitHub's release API is temporarily unavailable, the menu reports the failure but still permits a Nightly installation.

Windows starts the updater as a separate PowerShell process so the running executable can exit before replacement. The updater also removes private PyInstaller parent-process state before starting the new executable, preventing cross-archive security validation failures. Linux and macOS update synchronously. Every channel still uses the platform installer's SHA-256 verification.

Set `OMNISCRIPT_CACHE_DIR` to move the cache, `OMNISCRIPT_REPOSITORY=owner/repository` to use a fork, or `OMNISCRIPT_INSTALLER_REF` to select another installer branch. Network and installer failures return a readable diagnostic.

## Inspection commands

- `omni tokens file.omni` prints source positions, token kinds, lexemes, and decoded literals.
- `omni ast file.omni` prints the parsed AST as JSON.
- `omni doctor` displays environment and update-cache information, then runs a toolchain self-test.
- `omni --version` prints the toolchain version.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Command succeeded |
| 1 | Source, check, runtime, test, formatting, or filesystem error |
| 2 | Invalid CLI arguments (from `argparse`) |
