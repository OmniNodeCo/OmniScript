# Language design

## Goals

OmniScript follows four principles:

1. **A visible data-flow language.** `:=` declares, `<-` mutates, `|>` flows, and `..` constructs. Distinct operators make state transitions easy to scan.
2. **One approachable runtime model.** Values are dynamic; lexical scope, sealed names, closures, maps, and shapes are consistent at top level and in modules.
3. **Tools are part of the language.** The reference distribution includes checking, formatting, testing, project scaffolding, inspection, installers, an editor extension, and an embedding API.
4. **Portable reference behavior.** The interpreter has no runtime dependency beyond Python 3.10+, and diagnostics carry source spans throughout the pipeline.

## Originality and implementation

OmniScript defines its own source grammar and semantics; it is not a compatibility layer, preprocessor, or syntax skin for an existing language. Like any interpreter, its implementation is hosted on another platform—in this case Python—but user programs are parsed as OmniScript and evaluated against the OmniScript runtime model rather than translated into Python source.

Familiar ideas such as lexical scope, first-class functions, structured loops, and modules are intentionally retained because they are useful language concepts. The distinctive vocabulary and operator system are designed as one coherent whole rather than to copy a specific language.

## Scope and mutation

Every braced block introduces lexical scope. `bind` and parameters create mutable bindings; `seal`, craft names, shape names, module aliases, `self`, built-ins, and loop indexes are sealed. Sealing applies to a binding, not recursively to the object it references.

A closure captures an environment by reference, so it observes later mutation of captured bindings. Each `each` iteration receives a fresh item environment, which is important for future anonymous-craft support.

## Evaluation

Evaluation is strict and left-to-right except:

- `and`, `or`, and `??` short-circuit;
- conditional expressions evaluate one branch;
- craft default expressions are evaluated at call time after earlier parameters are bound;
- a shape default is evaluated at construction time after earlier fields are available by name.

`..` materializes an inclusive list. This is intentionally simple and observable through `kind(1..3) == "list"`.

## Compatibility policy

The 0.x series may revise syntax. Once 1.0 is reached:

- valid 1.x programs should remain valid throughout 1.x;
- new keywords require a minor release and migration note;
- runtime bug fixes may change behavior that contradicted the language guide;
- the AST dataclasses and Python embedding surface follow semantic versioning separately from private implementation helpers.

## Current deliberate limits

The 0.1 reference release has no concurrency, inheritance, anonymous crafts, bytecode backend, package registry, debugger protocol, or static type system. These are potential future features, not partially specified behavior. The existing interpreter, module system, CLI, and editor integration are complete enough to build and test multi-file command-line programs.
