# Useful built-in packages

OmniScript includes practical packages that work immediately—no package download, dependency file, or complicated setup. Import one with `use`:

```omni
use "crypto"
emit crypto.sha256("hello")
```

## `data` — everyday list operations

```omni
use "data"

assert data.unique([1, 1, 2]) == [1, 2]
assert data.flatten([1, [2, [3]]]) == [1, 2, 3]
assert data.chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
assert data.sum([2, 4, 6]) == 12
assert data.average([2, 4, 6]) == 4
```

| Craft | Purpose |
|---|---|
| `unique(list)` | Keep the first occurrence of each value |
| `flatten(list)` | Recursively flatten nested lists |
| `chunk(list, size)` | Split a list into smaller lists |
| `sum(list)` | Add numbers |
| `average(list)` | Average numbers; `void` for an empty list |

## `csv` — spreadsheets and tabular text

```omni
use "csv" as table

seal people := table.parse("name,score\nAda,10\nLin,8\n")
emit people[0].name

seal output := table.stringify([
    {name: "Ada", score: 10},
    {name: "Lin", score: 8}
])
write("scores.csv", output)
```

- `csv.parse(text, delimiter := ",")` uses the first row as map keys.
- `csv.rows(text, delimiter := ",")` returns lists without treating the first row specially.
- `csv.stringify(rows, delimiter := ",")` accepts a list of maps or a list of lists.

## `http` — straightforward web requests

```omni
use "http"

seal response := http.get("https://example.com/api/items")
emit response.status
emit response.body

seal created := http.post(
    "https://example.com/api/items",
    {name: "New item"},
    {Authorization: "Bearer token"}
)
```

Responses are ordinary maps:

```omni
{
    status: 200,
    ok: true,
    body: "...",
    headers: {content_type: "..."},
    content_type: "application/json"
}
```

- `http.get(url, headers := {}, timeout := 15)`
- `http.post(url, body := "", headers := {}, timeout := 15)`
- `http.json(url, headers := {}, timeout := 15)` parses a JSON response directly.

HTTP 4xx/5xx responses are returned with `ok: false` so applications can handle them normally. Network failures remain readable runtime errors.

## `crypto` — IDs, hashes, and safe random tokens

```omni
use "crypto"

emit crypto.sha256("password")
emit crypto.sha512("document")
emit crypto.uuid()
emit crypto.token(32)
emit crypto.base64_decode(crypto.base64_encode("hello"))
```

These tools are useful for checksums and identifiers. Password storage still requires a dedicated password-hashing system supplied by the host application.

## `date` — dates and timing

```omni
use "date"

seal now := date.now()
emit date.format(now)                         // 2026-08-17 13:45:00
emit date.format(now, "%Y-%m-%d")
emit date.iso(now)

seal launch := date.parse("2026-08-17", "%Y-%m-%d")
assert date.format(launch, "%Y-%m-%d") == "2026-08-17"
```

`date.sleep(seconds)` pauses execution when a short delay is needed.

## `system` — host information and safe process execution

```omni
use "system"

emit system.info()
emit system.cwd()
emit system.home()
emit system.env("PATH", "not set")

seal result := system.run(["git", "--version"])
when result.ok {
    emit result.output
} otherwise {
    emit result.error
}
```

`system.run` takes a list, never a shell command string. This keeps spaces and arguments understandable and avoids accidental shell interpolation. Its result contains `code`, `ok`, `output`, and `error`.

## Package safety

The packages use only the Python standard library bundled with OmniScript. `http`, `system.run`, file operations, and environment operations access host resources; OmniScript remains a programming language rather than a security sandbox.
