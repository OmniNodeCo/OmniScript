# Standard library

The standard library consists of sealed global crafts and built-in modules. Values are dynamically checked and invalid arguments produce runtime diagnostics.

## Global crafts

| Craft | Result |
|---|---|
| `len(value)` | Number of items in text/list/map |
| `kind(value)` | OmniScript kind name as text |
| `text(value)` | Display representation as text |
| `number(value)` | Parse/convert to a number |
| `integer(value)` | Convert to an integer |
| `truthy(value)` | Truthiness as `true` or `false` |
| `clock()` | Unix time in fractional seconds |
| `input(prompt := "")` | Show prompt and read one text line |
| `keys(map)` | List of map keys |
| `values(map)` | List of map values |
| `has(container, value)` | Membership test |
| `push(list, value)` | Append in place and return the list |
| `pop(list)` | Remove and return the final item |
| `sort(list)` | Return a sorted copy |
| `reverse(iterable)` | Return a reversed list |
| `map(iterable, craft)` | Call craft once per value and return results |
| `filter(iterable, craft)` | Keep values for which craft is truthy |
| `reduce(iterable, craft, initial)` | Fold with `craft(accumulator, value)` |
| `read(path)` | Read a UTF-8 text file |
| `write(path, text)` | Write a UTF-8 text file and return `void` |
| `panic(message)` | Raise a runtime error |

`read` and `write` are host filesystem operations. OmniScript does not claim to sandbox scripts.

## `math`

```omni
use "math"
```

Constants: `pi`, `e`, `tau`.

Crafts: `abs(x)`, `ceil(x)`, `floor(x)`, `round(x)`, `sqrt(x)`, `sin(x)`, `cos(x)`, `tan(x)`, `log(x, base := e)`, `min(a, b)`, and `max(a, b)`.

## `text`

```omni
use "text" as words
```

- `upper(value)`, `lower(value)`, `trim(value)`
- `split(value, delimiter)` → list
- `join(delimiter, iterable)` → text
- `contains(value, fragment)` → truth
- `replace(value, old, replacement)` → text

## `json`

- `parse(text)` parses JSON into OmniScript scalar/list/map values.
- `stringify(value)` returns compact JSON text. Shape instances encode as maps of their fields. Crafts, shapes, and modules cannot be encoded.

```omni
use "json"
seal payload := json.parse('{"ready": true}')
assert payload.ready
emit json.stringify({answer: 42})
```

## `path`

- `join(parent, child)`
- `name(path)`
- `stem(path)`
- `exists(path)`

Paths use host platform semantics.

## `random`

- `number()` returns a fractional number from zero (inclusive) to one (exclusive).
- `integer(min, max)` returns an integer with inclusive bounds.
- `pick(sequence)` returns a random item.

The random module is not suitable for cryptography.

## Utility package collection

OmniScript also includes dependency-free `http`, `csv`, `crypto`, `date`, `system`, and `data` packages. They cover web requests, spreadsheet data, hashes/tokens, dates, host information/processes, and common list transformations. See [Useful built-in packages](packages.md) for their complete APIs and examples.

## `gui`

The optional desktop package creates native windows with automatic vertical layout and both basic and advanced controls:

```omni
use "gui"
seal window := gui.window("Hello", 400, 240)
window.label("A small, readable app")
window.run()
```

It includes labels, inputs, buttons, checkboxes, textboxes, dialogs, and ordinary craft callbacks. Use `gui.available()` to detect Tk support. See the [GUI package guide](gui.md) for the complete beginner-oriented API.
