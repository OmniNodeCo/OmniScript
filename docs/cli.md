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

## Inspection commands

- `omni tokens file.omni` prints source positions, token kinds, lexemes, and decoded literals.
- `omni ast file.omni` prints the parsed AST as JSON.
- `omni doctor` displays environment information and runs a toolchain self-test.
- `omni --version` prints the toolchain version.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Command succeeded |
| 1 | Source, check, runtime, test, formatting, or filesystem error |
| 2 | Invalid CLI arguments (from `argparse`) |
