# Consolidated roadmap

| Old reference | Now |
|---|---|
| Phase 2 "syntax + keyword language" | done (English keywords, see SPEC.md) |
| Phase 3 "type system" | done in part: P1 below; remainder → P2/P3 |
| Phase 4 "generics/traits/cross-module" | cross-module done (P1); generics → P2, traits → P3 |
| Phase 4 "memory model / compiler / performance" | → P7, only if measurements justify it |
| Phase 5 stdlib · Phase 6 tooling · Phase 7 modules/packages · Phase 8 docs | → P5 · P4 · P6 · continuous |

## Status
* **P0 Foundation & audit**, done (README audit, regression tests, CLI tests, spec, changelog).
* **P1 Static semantics**, done: scopes, duplicates, return paths + inference, unknown types, optionals + narrowing + `??`,
  cross-module and stdlib typing, shared module resolver, `calyre.toml` path dependencies.

## Next, in dependency order
1. **P2 , Generics.** `func f<T>`, `struct Box<T>`, generic stdlib signatures (removes the deliberate `any` in `math.abs/min/max/pow`,
   `random.choice`, `text.join`), list functions (`append`, `pop`, `contains`, `sort`, `map`/`filter` if they earn their place).
   *Prerequisite for a useful stdlib.* Needs: type parameters in `TypeAnn`/checker, instantiation at call sites, tests for inference failures.
2. **P3 , Type-system extensions.** Aliases, enums, `match` exhaustiveness, interfaces/traits (define purpose first), user-written unions with
   narrowing. Depends on P2 (generic machinery) and on a decision about truthiness in conditions (`if x` on non-bool).
3. **P4 , Tooling core.** *Prerequisites first:* columns in diagnostics and AST nodes; comments kept by the lexer. Then `calyre fmt`
   (idempotent AST printer), `calyre test` (collect `test_*` functions, built on `assert`), `calyre lint`, then LSP reusing `Checker`
   (diagnostics, hover from inferred types, go-to-definition via the resolver), then a VS Code extension.
4. **P5 , Standard library.** Priority: `json`, `path`, `system` (args/env/exit), `process`, `datetime`, then `regex`, `http`, `log`.
   Each with typed signatures in `stdlib_types.py` (a test already enforces runtime/signature parity) and security tests for paths/processes.
5. **P6 , Projects and dependencies.** Lockfile + integrity for path/git dependencies, dependency-of-dependency rules,
   `calyre test/build` project layout, then (only later) a registry.
6. **P7 , Execution.** Benchmarks exist (`benchmarks/bench.py`). Consider a bytecode VM only if realistic programs are too slow after P2–P5;
   it must keep the tree-walking interpreter as the reference and add equivalence tests. Native compilation is not a goal yet.
7. **P8 , Distribution.** Build and test the executable on Windows and macOS, install-without-Python test, release process.
   Documentation (tutorial, reference, examples that run in CI) grows with every phase.

## Open design questions (I'll decide later)
* Should conditions require `bool` (stricter, clearer errors) or keep truthiness?
* Negative list indexes (`xs[-1]`) , keep or require `len(xs) - 1`?
* Visibility: keep the `_prefix` convention or add an explicit `pub`?
* Should `calyre` messages be localizable (catalog) while syntax stays English?
