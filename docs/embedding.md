# Embedding OmniScript

The Python package exposes a small public API:

```python
from omniscript import OmniEngine

engine = OmniEngine()
result = engine.run('emit "hello"\n6 * 7')

assert result.output == ["hello"]
assert result.value == 42
```

Provide host I/O callbacks:

```python
engine = OmniEngine(
    output=lambda line: application_log.append(line),
    input_provider=lambda prompt: prompt_user(prompt),
)
engine.run_file("script.omni")
```

## Compile stages

```python
from omniscript import OmniEngine

source = "seal answer := 42"
tokens = OmniEngine.tokens(source, "example.omni")
program = OmniEngine.parse(source, "example.omni")
problems = OmniEngine.check(source, "example.omni")
```

`Program` and its nodes are dataclasses in `omniscript.ast_nodes`. Tokens include `Span` objects with source, line, column, and source-line text.

## Persistent environments

By default each `run` gets a fresh environment. Reuse one for a session:

```python
engine = OmniEngine()
environment = engine.interpreter.new_environment()
engine.run("bind counter := 1", environment=environment)
result = engine.run("counter <- counter + 1", environment=environment, check=False)
assert result.value == 2
```

The checker works from one source unit and therefore does not know names from a prior call; persistent hosts can check a complete unit or use `check=False` after validating input themselves.

## Errors

`OmniSyntaxError`, `OmniCheckError`, and `OmniRuntimeError` derive from `OmniError`. Call `error.render()` to get the same source diagnostic used by the CLI. Host applications should catch `OmniError`, not general Python exceptions.

The embedding API is source execution, not a security sandbox. Built-ins can read and write files; do not execute untrusted programs without OS-level isolation.
