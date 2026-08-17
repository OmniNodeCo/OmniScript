# OmniScript

**OmniScript is an original, standalone programming language with its own syntax, semantics, `.omni` file format, interpreter, checker, formatter, test runner, REPL, module system, standard library, installers, and editor extension.**

It is designed to read clearly without turning into pseudocode:

```omni
use "math"

shape Orbit(radius) {
    craft circumference() {
        return 2 * math.pi * self.radius
    }
}

bind paths := [Orbit(2), Orbit(4), Orbit(8)]
each path, index in paths {
    emit "orbit", index, "length", path.circumference()
}
```

OmniScript is not a transpiled dialect of another language. `.omni` source is tokenized, parsed into an OmniScript AST, semantically checked, and executed by the reference runtime in this repository. The toolchain itself is implemented in dependency-free Python so it is portable and easy to embed.

## Included

- Original grammar with `bind`, `seal`, `craft`, `shape`, `when`, `whilst`, `each`, `<-`, `:=`, `..`, `??`, and `|>`
- Numbers, truth values, text, lists, maps, `void`, first-class crafts, closures, and shape instances
- Functions with defaults and recursion; mutable object/list/map data
- Branches, loops, ranges, assertions, early return, break, and continue
- Source modules and built-in `math`, `text`, `json`, `path`, and `random` modules
- Friendly source diagnostics with locations and call frames
- `omni run`, `repl`, `check`, `fmt`, `test`, `init`, `tokens`, `ast`, and `doctor`
- Binary-first Shell, Batch, and PowerShell installers with SHA-256 verification
- Native Linux/Windows x86-64 and ARM64 executables plus an Apple Silicon macOS binary, built by `build.yml`
- A custom VS Code extension with highlighting, snippets, Run, and Check commands
- Public Python embedding API and a tested reference implementation

## Quick start

Release installers download a self-contained executable, so Python is not required.

Linux or macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/install.sh | sh
```

Windows Command Prompt from a checkout:

```bat
install.bat
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/OmniNodeCo/OmniScript/arena/01a00f9c-omniscript/scripts/install.ps1 | iex
```

To develop from source, use Python 3.10 or newer:

```bash
python3 -m pip install -e .
omni init hello-omni
cd hello-omni
omni run
omni test
```

Create `hello.omni`:

```omni
craft greet(name := "world") {
    return "Hello, " + name + "!"
}

emit greet()
emit greet("OmniScript")
```

Then run it:

```bash
omni hello.omni
```

## A taste of the language

```omni
// Mutable and sealed bindings
bind score := 7
seal multiplier := 6
score <- score * multiplier

// Inclusive ranges and index-aware iteration
each value, index in 1..4 {
    emit index, value
}

// Lists, maps, properties, and pipelines
bind profile := {name: "Ada", languages: ["math", "logic"]}
profile.active <- true
emit profile.languages |> len |> text

// Conditional expressions and null coalescing
bind title := profile.title ?? "Engineer"
bind status := score >= 40 ? "ready" : "learning"

// Runtime assertions are also the test format
assert status == "ready", "score should be ready"
```

Statements can end with a newline or `;`. Both `//` and `#` start line comments; block comments use `/* ... */` and may nest.

## Project layout

`omni init my-app` creates:

```text
my-app/
├── omni.toml
├── src/main.omni
└── tests/main_test.omni
```

`omni run` reads the entry path from `omni.toml`. `omni test` recursively executes every `*_test.omni` file and treats a failed `assert` as a failed test.

## Documentation

- [Getting started](docs/getting-started.md)
- [Installers and native executables](docs/installers-and-binaries.md)
- [Language guide](docs/language-guide.md)
- [Grammar reference](docs/grammar.ebnf)
- [Standard library](docs/standard-library.md)
- [Modules and projects](docs/modules-and-projects.md)
- [CLI reference](docs/cli.md)
- [VS Code extension](docs/vscode.md)
- [Embedding API](docs/embedding.md)
- [Language design](docs/design.md)

Examples live in [`examples/`](examples). Try the full tour with `omni examples/tour.omni`.

## Development

No third-party runtime or test dependency is required:

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
omni check examples/*.omni examples/lib/*.omni
omni test examples/tests

# Build a self-contained binary for this host
./scripts/build_all_local.sh
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the language-change workflow. OmniScript is currently **0.1.0 alpha**: the language and tooling are functional, but the grammar may evolve before 1.0.

## License

MIT — see [LICENSE](LICENSE).
