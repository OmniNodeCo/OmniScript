# OmniScript Language Specification v1.0

## File Extension
`.omni`

## Comments

## Data Types
- Int: `42`, `-7`, `0`
- Float: `3.14`, `-0.5`
- String: `"hello"`, `'world'`
- Bool: `true`, `false`
- Array: `[1, 2, 3]`
- Null: returned implicitly when no return value

## Variables
let x = 10
let name = "Omni"
x = 20


## Operators
- Arithmetic: `+`, `-`, `*`, `/`, `%`
- Comparison: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Logical: `and`, `or`, `not`
- String concatenation: `+`

## Control Flow
if condition {
...
} elif condition {
...
} else {
...
}

while condition {
...
}

loop i in 0..10 {
...
}


## Functions
func name(param1, param2) {
return param1 + param2
}


## Built-in Functions
- `show(args...)` — print to stdout
- `input(prompt?)` — read from stdin
- `len(val)` — length of string or array
- `str(val)` — convert to string
- `int(val)` — convert to integer
- `float(val)` — convert to float
- `type(val)` — get type name
- `push(arr, val)` — append to array
- `pop(arr)` — remove and return last element

## Arrays
let arr = [1, 2, 3]
show(arr[0])
push(arr, 4)
let last = pop(arr)
show(len(arr))