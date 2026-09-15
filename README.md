# OmniScript

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

OmniScript needs only **Python 3.10+** — no third-party packages at all.

```bash
git clone https://github.com/OmniNodeCo/OmniScript
cd OmniScript
./omni --version

# optional: put it on your PATH as `omniscript`
pip install -e .
```

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
./omni docs                           # list all 290 built-ins
./omni docs chart                     # explain one of them
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
  std/                importable .omni modules: math, text, list, stats
examples/             10 runnable programs (outputs land in .preview/)
tests/                78 interpreter cases + 24 in-language @test cases
extras/vscode/        syntax highlighting for VS Code / Cursor
```

## Testing

```bash
python3 -m unittest discover -s tests   # the interpreter test suite
./omni test                             # the language's own @test suite
```

## License

MIT.
