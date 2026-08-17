# OmniScript documentation

OmniScript is an original programming language and integrated toolchain. Source files use the `.omni` extension and are executed directly by the reference interpreter.

## Start here

1. [Install OmniScript and run a program](getting-started.md).
2. Work through the [language guide](language-guide.md).
3. Learn the [CLI](cli.md) and [project/module model](modules-and-projects.md).
4. Install the [VS Code extension](vscode.md).

## Reference

- [Formal grammar](grammar.ebnf)
- [Standard library](standard-library.md)
- [Embedding API](embedding.md)
- [Design and semantics](design.md)

## Toolchain stages

A source file follows this pipeline:

```text
.omni text → Lexer → Tokens → Parser → AST → Checker → Interpreter
```

The lexer, AST, checker, and runtime are separately importable. `omni tokens` and `omni ast` expose the first two intermediate representations for language tooling and debugging.
