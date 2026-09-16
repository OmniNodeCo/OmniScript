# OmniScript

[![build](https://github.com/OmniNodeCo/OmniScript/actions/workflows/build.yml/badge.svg)](https://github.com/OmniNodeCo/OmniScript/actions/workflows/build.yml)

**A small language for doing big things in few lines.**

OmniScript is a from-scratch programming language with its own syntax, its own
interpreter and its own standard library. There is nothing to import: reading a
CSV, calling a web service, drawing a PNG chart and shelling out to the
operating system are each **one built-in call**.

```omni
# hello.omni -- this whole file is the program
print("Hello, OmniScript!")

let scores = [91, 87, 95, 78]
print("average ${scores.avg()}, best ${scores.max()}")

let c = draw(window_size(320, 200))          # open a drawing surface
c.circle(160, 100, 70, "steelblue")
c.text(120, 95, "omni", "white", 2)
c.save("hello.png")                          # ...or it saves itself on exit
```

```
$ ./omni hello.omni
Hello, OmniScript!
average 87.75, best 95
picture saved to /you/hello.png (320x200)
```

---

## Why it feels simpler than the alternatives

| the thing you want            | OmniScript                            |
| ----------------------------- | ------------------------------------- |
| read a CSV into records       | `read_csv("data.csv")`                |
| call a JSON API               | `http_get(url).json()`                |
| run a program, keep its text  | `cmd("git status").out`               |
| draw a bar chart to PNG       | `chart(values, kind: "bar").save("c.png")` |
| do 8 slow things at once      | `parallel_map(items, fn, workers: 8)` |
| work with dates               | `date("2026-09-15") + days(3)`        |
| group rows by a column        | `rows.group_by("region")`             |
| safe navigation through nulls | `config?.db?.host ?? "localhost"`     |
| match and unpack data         | `match row { {name, age} when age > 18 => ... }` |

No `import`, no `with open(...)`, no `if __name__ == "__main__":`, no
boilerplate. Long chains are laid out one step per line, because a line may end
after an operator:

```omni
let words = text.lower() |>
  regex_all(r"[a-z]+") |>
  filter((w) -> w.len() > 2)

chart(words.counts().sort_by("value", desc: true), kind: "bar")
  .save("words.png")
``` Values are immutable by default (`let`) and mutable when you say
so (`mut`). Errors point at the exact line, with a caret and a hint.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.sh | bash
```

```powershell
iwr -use1 https://raw.githubusercontent.com/OmniNodeCo/OmniScript/main/install.ps1 | iex
```

That downloads one file from the newest release, checks its SHA-256, and puts
`omni` and `omniscript` on your PATH. No Python needed.

There are two channels:

* **release** (the default) — the newest GitHub Release.
* **beta** (`-s beta`) — the repository itself, so `git pull` is the upgrade.
  Needs Python 3.10+.

```bash
./install.sh -s beta --ref my-branch   # follow the repository instead
./install.sh --version 1.0.0           # pin one release
./install.sh --dry-run                 # show the plan, touch nothing
./uninstall.sh                         # take it all back out
./uninstall.sh --purge                 # ...and the history, the clone, the manifest
```

If no release can be reached, the installer says so and uses the repository
instead. A `--version` that does not exist, or a download whose checksum does not
match, stops it and installs nothing.

### From a clone

```bash
git clone https://github.com/OmniNodeCo/OmniScript
cd OmniScript
./omni --version          # that is the whole install: nothing to build
./install.sh              # a source tree implies the beta channel
```

`--mode` says how a source install is wired up: **symlink** (the default — the
commands point into the tree, so `git pull` upgrades them), **venv** (a private
environment under `~/.local/share/omniscript/venv`) or **pip** (into the
interpreter you already use; on a PEP 668 system it stops rather than override
your package manager).

### What is written down

Every install leaves `~/.local/share/omniscript/install.txt` — one `key=value`
per line, plain text, so nothing needs Python or a JSON parser to read it:

```
mode=binary
channel=release
release_tag=v1.0.0
command=/home/you/.local/bin/omni
command=/home/you/.local/bin/omniscript
```

The uninstaller reads that file and removes exactly what is listed, a downloaded
executable as readily as a symlink. It never deletes a source tree you cloned
yourself, and it will not remove a command it cannot prove it created — `--force`
moves a stranger's `omni` to `omni.bak` instead of overwriting it, and
`--dry-run` shows the whole plan and changes nothing.

## Update

Whatever the installer put there, `omni` can replace itself:

```bash
omni update --check       # what is published, what you have, and the difference
omni update               # download it, check the sha256, swap it in, prove it runs
omni update --version 1.0.0
omni update -c beta --ref main    # switch to following the repository
```

`omni update` reads the manifest to find out which channel this install came from
and stays on it; `-c` switches. A binary install downloads the new executable,
checks it against `SHA256SUMS.txt`, swaps it in place (keeping the old one until
the new one has been seen to run) and leaves the commands pointing at it. A source
install fetches the branch or tag it tracks and re-runs the install over the top.
Nothing is written unless the new one works: `--check` and `--no-verify` do what
they say, and a failed update puts back what was there before.

## Use it

```bash
./omni run examples/01_hello.omni     # run a file
./omni examples/01_hello.omni         # ...same thing, shorter
./omni -e 'print(2 ** 10)'            # run a one-liner
./omni repl                           # interactive prompt
./omni check file.omni                # syntax check without running
./omni ast -e 'let x = 1 + 2 * 3'     # print the syntax tree
./omni tokens -e '1..3'               # print the token stream
./omni test                           # run every @test in the project
./omni docs                           # list every built-in
./omni docs chart                     # explain one of them
./omni update --check                 # what has been published since this copy
```

Inside the REPL: `:help`, `:vars`, `:type expr`, `:tokens expr`, `:ast expr`,
`:quit`.

---

## A two-minute tour

```omni
# ---- values: numbers, text, lists, maps, ranges ----
let n = 42
let name = "ada"
let tags = ["fast", "small"]
let config = {host: "localhost", port: 8080}
let one_to_ten = [1..=10]               # ranges are values

# ---- text builds itself ----
print("hi ${name}, you have ${tags.len()} tags, 2+2 = \{2 + 2}")

# ---- functions: named or inline, defaults and keywords ----
fn area(w, h = w) { w * h }
print(area(3), area(3, 4), area(h: 9, w: 2))
let double = (x) -> x * 2

# ---- control flow without ceremony ----
mut total = 0
for i in 1..=100 { total += i }
while total > 5000 { total /= 2 }

let grade = match 87 {
  x when x >= 90 => "A"
  x when x >= 80 => "B"
  _ => "C"
}

# ---- lists and maps read like sentences ----
let rows = [
  {region: "north", units: 12},
  {region: "south", units: 30},
  {region: "north", units: 8},
]
print(rows.filter((r) -> r.units > 10).map((r) -> r.region))
print(rows.group_by("region").map((rs) -> rs.sum((r) -> r.units)))
print(rows.sort("units", desc: true).first())

# ---- pipelines ----
let report = rows |> group_by("region") |> to_json(indent: 2)

# ---- classes ----
class Counter {
  n = 0
  fn bump(by = 1) { self.n += by; self.n }
  fn str() { "<Counter ${self.n}>" }
}
let c = new Counter()
c.bump()
c.bump(4)
print(str(c))

# ---- errors ----
try {
  error("something went wrong")
} catch e {
  print("caught:", e.message)
}
```

### Working with the outside world

```omni
# files
write("notes.txt", "one\ntwo\n")
print(read_lines("notes.txt"))
write_json("config.json", {debug: true})

# CSV / JSON in one call
let people = read_csv("people.csv")
print(people.filter((p) -> p.age > 30).map((p) -> p.name))

# the shell
let branch = cmd("git branch --show-current").trim()
let listing = cmd("ls", "-1").lines()

# the web
let user = http_get("https://api.example.com/user").json()

# concurrency
let pages = parallel_map(urls, (u) -> http_get(u).text, workers: 8)
```

### Drawing

```omni
let c = draw(window_size(480, 320), bg: "#0f172a")
c.gradient(0, 0, c.w, c.h, "#0f172a", "#1e293b")
c.circle(240, 160, 90, "steelblue")
c.rounded_rect(40, 40, 120, 60, 12, "#f59e0b")
c.text(60, 65, "hello", "white", 2)
c.poly([[380, 60], [440, 120], [380, 120]], "#22c55e")
c.save("art.png")

chart([4, 8, 15, 16, 23, 42], kind: "bar", title: "the numbers").save("bars.png")
chart([1, 3, 2, 5, 4], kind: "line", title: "trend").save("trend.png")
```

Canvases are rendered by a dependency-free software rasteriser built into the
language (rectangles, circles, ellipses, lines, polygons, flood fill,
gradients, blur, and a 5x7 bitmap font), then written as PNG. Any canvas you
forget to save is written for you when the program ends.

---

## What the language gives you

* **Values** – numbers (floats under the hood, printed cleanly), text with
  `${...}` and `\{...}` interpolation, lists, maps, ranges (`1..10`,
  `1..=10`, `1..10..2`), booleans, `null`.
* **Bindings** – `let` (immutable) and `mut` (mutable), destructuring
  (`let [a, *rest] = ...`, `let {name, age} = ...`, `a, b = b, a`).
* **Functions** – defaults, keyword arguments, `*rest` / `**extra`,
  **destructuring parameters** (`fn dist([x1, y1], [x2, y2])`,
  `pairs.map(([a, b]) -> a * b)`), closures, lambdas (`(x) -> x * 2`,
  `(x) -> { ... }`, `fn (x) { ... }`), implicit last-expression return,
  `@memo`, `@test`, `@main`, `@deprecated`.
* **Control flow** – `if`/`else if`/`else` (also an expression), `for` over
  anything iterable (with `for k, v in map`), `while`, `do while`, `break`,
  `continue`, `match` with guards and patterns, `try`/`catch`/`finally`.
* **Classes** – fields with defaults, `new` constructors, methods with
  `self`, single inheritance with `: Parent`, `is` / `isnt` type tests, and
  operator overloading through `__add__`, `__eq__`, `__lt__` and friends.
* **Dates** – `date("2026-09-15") + days(3)`, `d.format("%A, %d %B")`,
  `d.diff(other, "days")`, `date_range(...)`, all with no imports.
* **Operators** – arithmetic (`/` exact, `//` whole-number), comparison that
  **chains** (`1 < x < 10`), `and`/`or`/`not`, bitwise, `**`, `++`/`--`, `+=`
  and friends, ternary `? :`, elvis `??`, optional chaining `?.`, pipelines
  `|>` and `||>`, slices `xs[1..3]` and `xs[::-1]`, multi-target assignment
  (`a, b = b, a`).
* **Safety** – immutable by default, null-safe navigation, and error messages
  that quote your source line and suggest fixes
  (`` `nma` is not defined … did you mean `name`? ``).

Read **[LANGUAGE.md](LANGUAGE.md)** for the complete reference, including the
operator precedence table and every syntax form.

---

## Project layout

```
omni                  launcher (./omni run file.omni, ./omni repl, ...)
omniscript/           the language itself
  lexer.py            text  -> tokens
  parser.py           tokens -> syntax tree
  ast.py              the tree node types
  interp.py           the evaluator
  values.py           runtime values (functions, classes, ranges, ...)
  errors.py           error types + the pretty printer
  cli.py              the command line
  stdlib/             every built-in
    core.py           print, math, lists, maps, strings, time, random
    methods.py        dot-methods: "abc".upper(), [1,2].sort(), 5.times(...)
    system.py         cmd(), files, paths, csv, json, base64
    net.py            http_*, download, regex_*
    graphics.py       canvas rasteriser, PNG writer, chart()
    concurrent.py     parallel(), parallel_map(), spawn()
    dates.py          date(), date ranges, and the Date type
  update.py           the release channels: ask GitHub, pick an asset, verify,
                      swap it in -- shared by `omni update` and the installers
  std/                importable .omni modules: math, text, list, stats
examples/             10 runnable programs (outputs land in .preview/)
tests/                215 interpreter cases + 34 in-language @test cases
extras/vscode/        syntax highlighting for VS Code / Cursor
install.sh/.ps1       put omni and omniscript on your PATH, from a release or a tree
uninstall.sh/.ps1     take them back out again
tools/                build_executable.py: the files a release carries
.github/workflows/    build.yml (CI) and release.yml (tagged releases)
```

## Testing

```bash
python3 -m unittest discover -s tests   # 215 interpreter cases
./omni test                             # the language's own 34 @test cases
```

The unittest count includes the installers and the update machinery: they are
driven against a fake GitHub release served from `localhost` (or from `file://`),
so the download, checksum, install, update and uninstall paths are all really
executed — on Windows too, wherever `pwsh` is installed.

Both suites also run every time the examples do:

```bash
for f in examples/*.omni; do ./omni "$f"; done
```

## Continuous integration

`.github/workflows/build.yml` runs on every push to `main` and on every pull
request:

| job | what it does |
| --- | --- |
| `lint` | ruff (pyflakes rules), `compileall`, metadata and workflow validity |
| `test` | both suites, all 10 examples, `docs`, and a PNG that is decoded chunk by chunk -- on ubuntu and macOS, Python 3.10 to 3.14 |
| `installer` | `install.sh` and `install.ps1` install, run and uninstall cleanly -- including on Windows, which the test matrix does not cover, and including the release channel served from `localhost` |
| `executable` | builds the standalone binary (PyInstaller) and the zipapp on ubuntu and Windows, and runs each one |
| `package` | builds the sdist and wheel, installs the wheel in a clean venv and runs it |

Linting is deliberately narrow: `select = ["E9", "F"]` in `pyproject.toml`
catches real mistakes (undefined names, dead imports, unused locals) and leaves
the hand-formatted source alone. `methods.py` is exempt from `F811` because it
defines `len`, `map` and friends once per type through a decorator.

## Releasing

`.github/workflows/release.yml` runs when a version tag is pushed:

```bash
# 1. bump both of these to the same value
#      VERSION in omniscript/stdlib/__init__.py
#      version in pyproject.toml
git commit -am "Release 1.1.0"
git tag v1.1.0
git push origin v1.1.0
```

The workflow refuses to continue unless the tag, `pyproject.toml` and
`omniscript.__version__` all agree, and re-runs the full test suite on the tagged
commit. Then, in parallel:

| job | what it produces |
| --- | --- |
| `build` | the sdist and the wheel, installed into a clean venv and exercised |
| `binaries` | a frozen executable per platform (Linux, Windows, macOS) plus one `.pyz`, each one run by the tool that built it |
| `release` | one GitHub Release carrying all of it with `SHA256SUMS.txt`, and notes measured from the tree -- line counts, built-in counts, example and test counts are read, not typed |

`build.yml` builds the same artifacts on every pull request, so a tag is never the
first time an executable has been made.

Publishing to PyPI is opt-in and off by default: add a repository variable
`PYPI_PUBLISH` set to `true` and configure trusted publishing for the project on
pypi.org, and the final job uploads with an OIDC token instead of a stored API
key. You can also run the workflow by hand from the Actions tab against a tag
that already exists.

## License

MIT.
