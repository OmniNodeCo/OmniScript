# Contributing to OmniScript

Thank you for improving the language or toolchain.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

## Language changes

A syntax or semantic change should include:

1. lexer/parser/runtime implementation as applicable;
2. checker support;
3. positive and diagnostic tests;
4. updates to `docs/grammar.ebnf` and `docs/language-guide.md`;
5. TextMate grammar/snippet updates when editor behavior changes;
6. a note in `CHANGELOG.md`.

Keep the runtime dependency-free unless there is a compelling portability reason. User-facing failures should be `OmniError` diagnostics with source spans, not raw Python exceptions.

## Validation

```bash
make test
make check
make examples
```

Use small, focused commits. Do not include virtual environments, generated VSIX files, Python wheels, or build output.
