# Modules and projects

## Source modules

`use` executes a source module once and binds its public top-level declarations to a sealed module value:

```omni
use "./geometry.omni" as geometry
use "./format" as format  // .omni is optional

emit geometry.area(4)
```

Without `as`, the filename becomes the alias:

```omni
use "./geometry"
emit geometry.area(4)
```

Relative paths resolve from the importing file, not the process working directory. Absolute paths are accepted. Imports are cached by canonical path, so repeated imports share module state. Circular imports are diagnosed.

Every file execution receives a sealed `__file__` containing its source path. Names beginning with `_`, including `__file__`, are private. All other top-level declarations are exposed. A module cannot mutate another module's exported table, although mutable values it exposes retain their normal behavior.

Example `geometry.omni`:

```omni
use "math"

seal _unit := "square units"
craft area(radius) { return math.pi * radius ** 2 }
craft describe(radius) { return text(area(radius)) + " " + _unit }
```

## Built-in modules

Built-in modules use the same syntax and do not touch the filesystem:

```omni
use "math"
use "json" as codec
```

Available modules are `math`, `text`, `json`, `path`, and `random`. Their members are listed in the [standard library reference](standard-library.md).

## Project manifest

`omni.toml` currently recognizes:

```toml
[project]
name = "my-project"
version = "0.1.0"
entry = "src/main.omni"
```

`entry` is used by `omni run` when no file is supplied. `name` and `version` document the project and are reserved for future package tooling.

## Testing convention

`omni test [directory]` discovers filenames ending in `_test.omni`. Each file receives a fresh global environment, but imports within that file use a shared module cache. Tests are ordinary programs using `assert`:

```omni
use "../src/geometry" as geometry

assert geometry.area(0) == 0
assert geometry.area(2) > 12, "a radius of two should exceed twelve"
```
