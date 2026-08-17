# Language guide

## Source and statements

OmniScript files are UTF-8 and use `.omni`. Identifiers are case-sensitive and may contain Unicode letters, digits after the first character, and `_`. Keywords are lowercase.

Statements end at a newline, `;`, `}`, or end of file. Use `;` to put statements on one line. Expressions may span lines while delimiters remain open.

```omni
# shell-style line comment
// C-style line comment
/* Nested
   /* block */ comment */
```

## Values

| Kind | Examples | Falsey? |
|---|---|---|
| `number` | `42`, `3.14`, `0xFF`, `0b1010`, `1_000` | zero |
| `truth` | `true`, `false` | `false` |
| `text` | `"hello"`, `'world'`, `"A\u03a9"` | empty text |
| `list` | `[1, 2, 3]` | empty list |
| `map` | `{name: "Ada", "score": 42}` | empty map |
| `void` | `void` | yes |
| callable | crafts, shapes, native crafts | no |
| instance/module | created shapes and imported modules | no |

Text escapes are `\n`, `\r`, `\t`, `\0`, `\\`, escaped quotes, and four-digit `\uXXXX`.

## Bindings

`bind` creates a mutable name. `seal` creates a name that cannot be reassigned. Both require the declaration operator `:=`; mutation uses `<-`.

```omni
bind count := 1
count <- count + 1

seal answer := 42
// answer <- 0  // checker error
```

Sealing a name is shallow: a sealed list cannot be rebound, but `push(list, value)` may still mutate the list.

## Operators

From tightest to loosest (postfix calls/index/properties bind tighter than this table):

| Operators | Meaning |
|---|---|
| `not`, `!`, unary `+`, unary `-` | unary operations |
| `**` | exponentiation (right associative) |
| `*`, `/`, `%` | multiply, divide, remainder |
| `+`, `-` | arithmetic; `+` also joins two texts/lists |
| `..` | inclusive integer range, ascending or descending |
| `<`, `<=`, `>`, `>=`, `in` | comparison and membership |
| `==`, `!=` | equality |
| `??` | use right value only when left is `void` |
| `and`, `&&` | short-circuit conjunction |
| `or`, `||` | short-circuit alternative |
| `|>` | pass the left value as one argument to the right craft |
| `condition ? yes : no` | conditional expression |
| `<-` | right-associative assignment |

```omni
bind names := ["sam", "lin", "ada"]
seal count_text := names |> len |> text
seal descending := 3..1       // [3, 2, 1]
seal label := void ?? "none"  // "none"
assert "ada" in names
```

`and` and `or` return one of their operands. Every other logical condition uses the truthiness table above.

## Lists, maps, and access

```omni
bind colors := ["red", "green"]
push(colors, "blue")
colors[0] <- "crimson"

bind user := {name: "Mira", roles: ["author"]}
user.active <- true
user["score"] <- 10
emit user.name, user.roles[0]
```

Property notation on maps is shorthand for a text key. List/text indexes are zero-based and accept negative indexes. Maps accept any hashable scalar key.

## Branching

```omni
when temperature > 30 {
    emit "hot"
} otherwise when temperature < 10 {
    emit "cold"
} otherwise {
    emit "mild"
}
```

Branches have lexical scope. A binding declared inside braces does not escape them.

## Loops

```omni
bind n := 0
whilst n < 3 {
    n <- n + 1
}

each value, index in [10, 20, 30] {
    when value == 20 { continue }
    emit index, value
}

each value in 1..100 {
    when value > 3 { break }
}
```

The optional second name in `each item, index in iterable` receives a zero-based index. Iterating a map visits keys.

## Crafts

A `craft` is a first-class callable with lexical closure. Parameters after the first default must also have defaults.

```omni
craft power(base, exponent := 2) {
    return base ** exponent
}

craft factorial(n) {
    when n <= 1 { return 1 }
    return n * factorial(n - 1)
}

seal square := power
assert square(5) == 25
```

Craft names are sealed. Parameters are mutable local bindings. A craft with no explicit return yields `void`.

## Shapes

Shapes provide compact user-defined data and behavior. Shape parameters become instance fields; defaults may refer to earlier parameters. Methods access an automatically bound, sealed `self`.

```omni
shape Rectangle(width, height := width) {
    craft area() {
        return self.width * self.height
    }

    craft resize(scale) {
        self.width <- self.width * scale
        self.height <- self.height * scale
        return self
    }
}

bind card := Rectangle(3, 2)
assert card.area() == 6
card.resize(2)
assert card.width == 6
```

Instances permit additional fields through property assignment. Shape methods are sealed by the shape, while fields are mutable.

## Output and assertions

```omni
emit "score", 42, true  // score 42 true
assert 6 * 7 == 42
assert false, "custom failure message"
```

`emit` converts values with OmniScript's display representation and separates multiple values by one space. A falsey assertion raises a source-located runtime error.

## Modules

```omni
use "math"
use "./helpers" as helpers
emit math.sqrt(16), helpers.label(4)
```

See [Modules and projects](modules-and-projects.md).

## Errors

The reference toolchain distinguishes syntax, check, and runtime errors:

```text
runtime error: division by zero
 --> example.omni:3:16
  |
3 | seal result := amount / count
  |                ^
  at divide (example.omni:7:20)
```

Run `omni check` before execution in automation. Runtime checks remain active even with `run --no-check`.
