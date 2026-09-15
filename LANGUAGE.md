# The OmniScript language reference

Everything the language can say, in one document. Run any snippet with
`./omni -e '...'` or save it as a `.omni` file and use `./omni file.omni`.

* [1. Lexical rules](#1-lexical-rules)
* [2. Values](#2-values)
* [3. Bindings](#3-bindings)
* [4. Operators](#4-operators)
* [5. Functions](#5-functions)
* [6. Control flow](#6-control-flow)
* [7. Classes](#7-classes)
* [8. Errors](#8-errors)
* [9. Modules](#9-modules)
* [10. Attributes](#10-attributes)
* [11. Methods](#11-methods)
* [12. Built-in index](#12-built-in-index)

---

## 1. Lexical rules

**Statements end at a newline.** A `;` is allowed but never required. A `\` at
the end of a line continues onto the next one.

A line may also end **after an operator** — the expression simply carries on —
and a method chain may be indented onto the following line:

```omni
let words = text.lower() |>
  split(" ") |>
  filter((w) -> w.len() > 2)

chart(values, kind: "bar", title: "top")
  .save("chart.png")
```

```omni
let a = 1
let b = 2; let c = 3        # semicolons are optional
let d = 1 + \
        1                    # line continuation
```

**Comments.** `#` runs to the end of the line; `#{ ... }#` is a block comment
and may nest.

```omni
# a line comment
#{ a block
   comment }#
```

**Identifiers** start with a letter or `_` and may contain letters, digits and
`_`. Keywords are reserved:

```
let mut fn return if else for in while do match when class new self super
true false null and or not try catch finally throw break continue use as
from is isnt by
```

**Numbers.** All numbers are floating point; whole numbers print without a
decimal point.

```omni
42        3.14      .5        1e6       1_000_000
0xff      0b1010    0o17      -2.5e-2
```

**Strings.** Single or double quotes behave the same, except single quotes
must stay on one line. Three quotes span lines.

```omni
let s = "double"
let t = 'single'
let doc = """
  several
  lines
"""
```

Escapes: `\n \t \r \\ \' \" \0 \a \b \f \v \e \x41 \u{1F600}`.
`\$` prints a literal dollar sign, so `"\${not interpolated}"` stays as typed.

Interpolation, two spellings of the same thing:

```omni
let n = 4
"n = ${n}"          # any expression between ${ }
"n = \{n}"          # shorthand for simple names and expressions
"n = ${n * 2 + 1}"  # expressions nest, and strings nest inside them
```

Raw strings keep backslashes exactly as typed — ideal for regular expressions:

```omni
regex("2026-09-15", r"(\d+)-(\d+)-(\d+)")
```

---

## 2. Values

| kind    | literal                                | `type()` |
| ------- | -------------------------------------- | -------- |
| number  | `42`, `3.14`                           | `num`    |
| text    | `"hi"`                                 | `str`    |
| boolean | `true`, `false`                        | `bool`   |
| nothing | `null`                                 | `null`   |
| list    | `[1, 2, 3]`                            | `list`   |
| map     | `{a: 1, "b": 2}`                       | `map`    |
| range   | `1..5`                                 | `range`  |
| fn      | `(x) -> x`                             | `fn`     |

**Lists** keep order and allow repeats. Spread with `*`:

```omni
let xs = [1, 2, 3]
let ys = [*xs, 4, *xs]        # [1, 2, 3, 4, 1, 2, 3]
```

**Maps** are ordered key/value pairs. Keys may be bare names, strings,
numbers or `[expression]`:

```omni
let m = {name: "omni", "with space": 1, [1 + 1]: "two", -3: "neg"}
m.name          # "omni"
m["with space"] # 1
m.missing       # raises; use m?.missing or m.get("missing", 0)
```

Keys are text. A whole-number key and its text form are the *same* key, so both
lookups below work and `{1: "a", "1": "b"}` holds one entry:

```omni
{1: "a"}[1]      # "a"
{1: "a"}["1"]    # "a"
```

`true`, `false` and `null` become `"true"`, `"false"` and `"null"`. Fractional
numbers stay numbers. Use `[expression]` for a key you compute:
`{[user.id]: user}`.

Spread a map into another with `*` or `**`:

```omni
let merged = {a: 1, *{b: 2}}
```

**Ranges** are lazy sequences. `a..b` excludes `b`; `a..=b` includes it;
`a..b..step` steps. Open ranges (`1..`) are allowed where the end is unknown.

```omni
for i in 1..5 { }        # 1 2 3 4
for i in 1..=5 { }       # 1 2 3 4 5
for i in 10..0..-3 { }   # 10 7 4 1
let xs = [1..5]          # [1, 2, 3, 4]   (a range inside [] expands)
```

**Indexing and slicing.** Negative indexes count from the end. Slices use
ranges: `xs[1..3]`, `xs[..2]`, `xs[2..]`, `xs[::-1]`.

```omni
let xs = [10, 20, 30, 40]
xs[0]        # 10
xs[-1]       # 40
xs[1..3]     # [20, 30]
xs[..2]      # [10, 20]     open start
xs[..=2]     # [10, 20, 30] open start, inclusive end
xs[2..]      # [30, 40]     open end
xs[::-1]     # [40, 30, 20, 10]
"hello"[1]   # "e"
```

Range bounds may be arithmetic: `[0..xs.len() - 1]` means `0..(xs.len() - 1)`.

---

## 3. Bindings

`let` is immutable; `mut` may be reassigned. Reassigning a `let` is an error
with a hint telling you to switch to `mut`.

```omni
let pi_approx = 3.14
mut counter = 0
counter += 1
```

Several targets may be assigned at once; the right-hand side is read completely
before anything is written, so swapping is one statement:

```omni
mut a = 1
mut b = 2
a, b = b, a              # a is 2, b is 1
xs[0], ys[1] = 9, 8      # index targets work too
a, b, c = [10, 20, 30]   # ...and a single list on the right
```

**Destructuring** works in `let`, in `for` and in `match`:

```omni
let [a, b] = [1, 2]
let [first, *rest] = [1, 2, 3, 4]      # rest = [2, 3, 4]
let {name, age} = {name: "ada", age: 36}
let {name: who} = {name: "grace"}      # rename
let a, b = 1, 2

for [x, y] in [[1, 2], [3, 4]] { print(x + y) }
for k, v in {a: 1, b: 2} { print(k, v) }
for i, item in ["x", "y"] { print(i, item) }     # index, value
```

Type annotations are accepted and ignored at runtime — they document intent:

```omni
let count: num = 3
fn add(a: num, b: num) -> num { a + b }
```

---

## 4. Operators

From loosest to tightest binding:

| precedence | operators                                            |
| ---------- | ---------------------------------------------------- |
| assignment | `= += -= *= /= %= ^= \|= &= <<= >>=`, `++ --`        |
| pipeline   | `|>`  `||>`                                          |
| ternary    | `cond ? a : b`, `a ?: b`, `a ?? b`                    |
| or         | `or`, `||`                                            |
| and        | `and`, `&&`                                           |
| equality   | `== != is isnt`                                       |
| comparison | `< <= > >=`                                           |
| bitwise or | `|`                                                   |
| xor        | `^`                                                   |
| bitwise and| `&`                                                   |
| shift      | `<< >>`                                               |
| additive   | `+ -`                                                 |
| multiplicative | `* / % //`                                      |
| power      | `**` (right associative)                              |
| range      | `a..b  a..=b  a..b..step` (looser than `+`, so `0..n - 1` works) |
| unary      | `- not ! ~ new`                                       |
| postfix    | `. ?. [] ()`                                          |

Notes:

* `/` always divides exactly (`7 / 2` is `3.5`); `//` divides to whole numbers
  (`7 // 2` is `3`, `-7 // 2` is `-4`).
* Comparisons **chain**: `1 < x < 10` tests both halves, evaluates each operand
  once, and stops as soon as one fails.
* `and` / `or` short-circuit and return the deciding operand.
* `+` joins text when either side is text, and concatenates lists.
* `?? ` returns the left side unless it is `null`.
* `?:` returns the left side unless it is falsy.
* `?.` stops the chain at `null` **and** at a missing key — including calls:
  `config?.db?.host ?? "localhost"` and `config?.refresh()` both yield `null`
  instead of raising.
* `is` / `isnt` test types (`num str bool list map fn null range obj any int`)
  or classes: `x is Point`.
* `|>` feeds the left value in as the **first** argument; `||>` feeds it in as
  the **last**. `x |> .method(1)` calls a method on `x`.

```omni
"a,b" |> split(",") |> len()          # 2
[3, 1, 2] |> sorted |> join("-")      # "1-2-3"
5 |> add(10)                          # add(5, 10)
[1, 2, 3] |> .sum()                   # 6
[1, 2, 3] ||> last()                  # 3
```

---

## 5. Functions

```omni
fn greet(who, punctuation = "!") {
  "hello ${who}${punctuation}"        # the last expression is returned
}
greet("ada")                 # positional
greet("ada", "?")            # ...still positional
greet(punctuation: "?", who: "ada")   # by keyword, any order
```

* A body’s **last expression** is the return value; `return` exits early.
* `*rest` collects extra positional arguments; `**extra` collects unknown
  keywords. Parameters after `*rest` are keyword-only.
* Sorting callbacks may declare **one** parameter (a key function) or **two**
  (a comparator):

```omni
people.sort("age", desc: true)                 # by a field name
people.sort((p) -> p.age)                      # by a computed key
people.sort((a, b) -> len(a.name) - len(b.name))   # by comparing two
```
* Lambdas: `(x) -> x * 2` for one expression, `(x) -> { ... }` for a block.
  `fn (x) { ... }` also works. A brace that is clearly a map stays a map, so
  `(n) -> {word: n}` returns `{word: n}` instead of opening a block.
* Closures capture their surroundings and keep them alive.
* Callbacks may declare fewer parameters than they are given; extras are
  dropped. That is why `[1,2,3].map((x) -> x * 2)` works even though `map`
  offers `(item, index)`.
* Functions are values: pass them, return them, store them in maps.

```omni
fn make_counter() {
  mut n = 0
  fn bump() { n += 1; n }
  bump
}
let c = make_counter()
c()    # 1
c()    # 2
```

---

## 6. Control flow

**if / else** — a statement or an expression:

```omni
if score > 90 { print("A") } else if score > 80 { print("B") } else { print("C") }

let label = if score > 90 { "A" } else { "C" }
```

Brace-less single-line bodies are allowed: `if x > 1 print("big")`.

**for** — over lists, strings, maps, ranges and anything with an `iter()`
method. `by` sets a step.

```omni
for i in 1..=5 { total += i }
for i in 1..100 by 5 { print(i) }
for ch in "abc" { print(ch) }
for k, v in config { print(k, v) }
for i, item in items { print(i, item) }
```

**while / do-while**, **break / continue**:

```omni
while running { tick() }
do { work() } while not done()
for i in 1..10 { if i == 5 { continue }; if i == 8 { break } }
```

**match** — patterns, guards, bindings; also an expression:

```omni
match value {
  0 => "zero"                          # literal
  "quit" => "bye"                      # literal text
  [a, b] => "pair ${a} ${b}"           # list shape
  [first, *rest] => "head ${first}"    # rest binding
  {name, age} when age >= 18 => name   # map shape + guard
  x is num => "number ${x}"            # type pattern
  p is Point => "point"                # class pattern
  _ => "anything else"                 # catch-all
}
```

Arms are tried top to bottom; the first that fits wins. A missing catch-all
for an unmatched value is a runtime error, telling you to add `_ => ...`.

---

## 7. Classes

```omni
class Shape {
  name = "shape"                  # field with a default
  fn area() { 0 }
  fn describe() { "${self.name}: ${round_to(self.area(), 2)}" }
}

class Circle : Shape {            # single inheritance
  radius = 1
  new(radius) {                   # constructor
    self.radius = radius
    self.name = "circle"
  }
  fn area() { pi * self.radius ** 2 }
}

let c = new Circle(3)
c.area()          # 28.27...
c.describe()      # "circle: 28.27"
c is Circle       # true
c is Shape        # true
```

* Methods take `self` implicitly; fields live on `self`.
* `new Point(1, 2).length()` chains: the object is built first.
* Without a `new`, `new Class(a, b)` assigns arguments to fields in
  declaration order, and keywords by name.
* `super` refers to the parent class inside a method.
* Define `str()`, `eq()`, `len()` or `iter()` on a class and the language
  itself will use them for printing, `==`, `len()` and `for`.

---

## 8. Errors

```omni
try {
  risky()
} catch e {
  print(e.message, e.kind)
} finally {
  cleanup()
}
```

* `throw value` raises anything; `catch name` binds it.
* Built-in failures (type errors, bad indexes, division by zero) are catchable
  too, and arrive as an `Error` object with `message`, `kind`, `line`, `hint`.
* `error("message")` raises one on purpose.
* A `try` used as an expression yields the value of whichever branch ran.
* You can subclass the built-in `Error` class:

```omni
class ValidationError : Error {
  new(field, message) { self.field = field; self.message = message }
}
throw new ValidationError("age", "must be positive")
```

Uncaught errors print the message, the offending source line with a caret, the
call stack and a hint:

```
omni: name error: `nma` is not defined
  --> demo.omni:2:7
  2 | print(nma)
            ^
  call stack:
    in main() at line 2
  hint: did you mean `name`?
```

---

## 9. Modules

One file per module; `use` brings its definitions in. Paths resolve relative to
the importing file, then to the project root. The `.omni` suffix is optional.

```omni
use "./geometry.omni"            # everything public
use "./geometry.omni" as geo     # ...under a name: geo.area(...)
use {area, perimeter} from "./geometry.omni"
use std/math                     # ships with the language
use std/text
use std/list as L                # ...then L.transpose(m)
```

A module’s top-level `let`/`fn`/`class` definitions become its exports. Names
starting with `__` stay private.

`std/math`, `std/text` and `std/list` ship with the language and hold the
helpers that are useful but not universal: `factorial`, `is_prime`,
`primes_below`, `combinations`, `initials`, `truncate`, `pluralize`, `box`,
`cumulative`, `transpose`, `moving_average`, `pairwise`, `most_common`.

---

## 10. Attributes

Attributes sit above a `fn` or `class`:

| attribute        | effect                                              |
| ---------------- | --------------------------------------------------- |
| `@memo`          | cache results by arguments                           |
| `@test`          | register with `./omni test`                          |
| `@main`          | mark the entry point                                 |
| `@deprecated("why")` | warn on every call                               |

```omni
@memo
fn fibonacci(n) { if n < 2 { n } else { fibonacci(n - 1) + fibonacci(n - 2) } }

@test
fn addition_works() { assert_eq(1 + 1, 2) }
```

---

## 11. Methods

Every collection and text value carries methods; each one also exists as a
plain function, so pick the style you like.

```omni
[3, 1, 2].sort()            ==   sorted([3, 1, 2])
"abc".upper()               ==   upper("abc")
{a: 1}.keys()               ==   keys({a: 1})
```

Common list methods: `len size push pop shift unshift insert remove at first
last contains index_of take drop slice reverse sort sort_by unique flatten
join concat map map_each filter reject reduce each find some every sum avg
min max chunk zip pairs group_by to_map sample shuffle clear counts flat_map
take_while drop_while`.

`flatten()` unwraps one level; `flatten(depth: 2)` unwraps two;
`flatten(depth: -1)` unwraps all of them.

Common text methods: `len upper lower title capitalize trim split replace
contains starts_with ends_with index_of chars words lines bytes repeat
pad_start pad_end center reverse slice matches match find_all count to_num
to_json snake camel kebab wrap indent at`.

Common map methods: `len keys values entries has get set remove merge update
pick omit map filter each invert sort_by to_list to_json clear`.

Number methods: `abs round floor ceil sqrt pow clamp to_int to_str to_fixed
times up_to down_to is_even is_odd between percent_of gcd format ordinal`.

`5.times((i) -> ...)` and `3.up_to(7)` are particularly handy loops.

---

## 12. Built-in index

About 290 names are in scope in every program. Groups include:

* **I/O** – `print show input read write append read_lines write_lines read_csv
  write_csv read_json write_json table exit`
* **Text** – `split join trim upper lower title replace repeat pad_start
  pad_end format slug chars words lines starts_with ends_with ord chr`
* **Lists** – `len sorted reverse unique flatten chunk zip take drop push pop
  insert remove enumerate map_each filter reduce each find some every group_by
  count_by sum avg median min max first last`
* **Maps** – `keys values entries has get merge pick omit deep_copy`
* **Math** – `abs round floor ceil sqrt pow exp log sin cos tan atan2 hypot
  clamp lerp sign gcd lcm rand rand_int choice shuffle seed pi e tau`
* **Time** – `now today timestamp sleep stopwatch elapsed wait_for`
* **System** – `cmd cmd_print which cwd chdir home hostname platform env args
  arg exit_code`
* **Files** – `exists is_file is_dir remove remove_dir mkdir copy move list_dir
  glob walk file_info temp_path path_join path_dir path_base path_ext path_abs`
* **Network** – `http http_get http_post http_put http_patch http_delete
  download ping http_get_all url_encode url_decode url_parts`
* **Patterns** – `regex regex_all regex_named regex_test regex_replace
  regex_split regex_escape`. In a replacement, `$1`, `${1}`, `\1`, `$name`,
  `${name}` and `$<name>` all mean a capture group; `$$` is a literal `$`.
  `regex_all(text, pattern, groups: true)` returns the groups instead of the
  whole match.
* **Drawing** – `draw window window_size chart sparkline progress_bar rgb hsl
  mix_colors palette save_picture`
* **Concurrency** – `parallel parallel_map spawn repeat_for`
* **Testing** – `assert assert_eq assert_true assert_throws`
* **Meta** – `type str num int bool repr help hash`

See them all, live, with `./omni docs` or `help()`; explain one with
`./omni docs chart` or `help("chart")`.
