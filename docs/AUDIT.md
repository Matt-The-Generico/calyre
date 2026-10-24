# Audit history

Findings are only listed if they were reproduced before being fixed; each fix has a regression test that failed before it.

## Round 2

Validation of round 1 first (215 tests, examples, REPL, module and CLI flows, every documented breaking change), then the new work.

| Severity | Finding (reproduced) | Status |
|----------|----------------------|--------|
| high | Conditions accepted any value as a truthy/falsy "bool" (a decision: conditions must be `bool`) | fixed (static error + runtime check at dynamic boundaries) |
| high | The checkpoint ZIP shipped a stale Linux executable and committed `__pycache__/*.pyc` files | fixed: ZIP is built from tracked source only (`git archive`) and its contents are checked |
| medium | After `assert x != none` (the natural way to unwrap in tests) `x` stayed optional | fixed: `assert` narrows the rest of its block |
| medium | `math.abs/min/max/pow`, `random.choice`, `text.join` were typed `any` | fixed with generics (`pow` now always `float`) |
| medium | Heterogeneous literals could not be passed where `any` was expected (`json.stringify([1, "a"])`) | fixed: contextual typing for explicit `any` |
| medium | Writing JSON text in Calyre needed every `{` escaped (interpolation) | fixed: `"""` literal texts |
| medium | Strings inside printed lists/maps/structs were unquoted (`[a, b]`), ambiguous | fixed: quoted |
| medium | Out-of-range index errors did not say the valid range; `6 / 2` into an `int` gave no migration hint | fixed |
| medium | Errors raised by builtins had no line; module-qualified generics and `use` hoisting bugs found while implementing | fixed |
| low | `calyre --help` was an "unknown command" | fixed |
| low | Every builtin call inspected its signature (list `append` 17 µs, string work 6x slower than needed) | fixed: 3-6x faster on builtin-heavy programs |

Not done in round 2: see [ROADMAP.md](ROADMAP.md) (LSP, VS Code extension, `process`/`datetime`/`regex`/`http`/`log`, first-class functions, unions and enums, lockfile).

## Round 1


Method: baseline test run, then ~15 probe programs written to contradict the
documentation. Every finding below was reproduced before being fixed; each fix
has a regression test that failed before the fix.

**Initial state:** 76 tests, all passing. 2,812 lines of Python. The tests only
covered valid programs and a few type errors, which is why the bugs below survived.

| # | Severity | Finding (reproduced) | Status |
|---|----------|----------------------|--------|
| 1 | high | Python tracebacks leaked: wrong builtin arity (`len(1,2)`), infinite recursion, top-level `break`/`return`, list assignment out of range | fixed |
| 2 | high | `break` inside a function escaped into the *caller's* loop | fixed |
| 3 | high | Duplicate `let`/`func`/`struct`/parameter/field silently accepted (`let x = 1` then `let x = "a"`) | fixed (error) |
| 4 | high | Declared return types never verified for missing paths: `-> int` falling off the end returned `none` | fixed |
| 5 | high | Unknown type names (`let p: Pointt`) silently became `any` | fixed (error + suggestion) |
| 6 | high | `/` on ints returned an int or a float depending on the *values* (`6/2`→3, `7/2`→3.5) while the checker claimed `int` | fixed: `/` is always float |
| 7 | high | Optionals were unusable: no way to narrow or unwrap | fixed: narrowing + `??` |
| 8 | high | Types did not cross modules (member calls were `any`); missing modules only failed at run time | fixed |
| 9 | medium | `and`/`or` returned operands at run time but were typed `bool` | fixed: always bool |
| 10 | medium | Struct field assignment unchecked; mixed lists silently became `list<any>` | fixed |
| 11 | medium | `calyre add` wrote `calyre.toml` but `use` never read it (dependencies did nothing) | fixed |
| 12 | medium | Runtime errors in an imported module were reported against the main file; messages mixed Portuguese and English | fixed |
| 13 | medium | Functions without a return annotation returned unchecked `any` | fixed: inferred |
| 14 | low | Dispatch built an f-string per AST node | fixed (~30% faster) |

**State after this round:** 215 tests passing (76 original + 139 new: semantics,
cross-module types, runtime regressions, dependencies, end-to-end CLI).
One original test was changed on purpose: it asserted that importing a
non-existent module is accepted silently; it now asserts the opposite.

### Still open after round 1 (see ROADMAP.md for the current state)

* Generics (`func f<T>`, `struct Box<T>`), so `math.abs/min/max/pow` and
  `random.choice` are still typed `any` on purpose; lists have no `append` yet.
* Diagnostics carry a line but no column (blocks an LSP and good editor squiggles).
* Comments are discarded by the lexer (blocks a formatter that preserves them).
* No formatter, linter, `calyre test`, debugger, LSP or VS Code extension.
* Standard library lacks json, path, system/env/args, process, datetime, regex, http.
* `if`/`while` accept any value as a condition (truthiness) — a pending design decision.
* Execution is a tree-walking interpreter (≈0.8 s for 200k loop iterations);
  call depth is capped at 800. No evidence yet justifies a VM.
* Only Linux was tested; the executable was not rebuilt/verified on Windows or macOS.
* Interactive features (`input_*`, arrow-key history) are only covered by piped-stdin tests.

### Benchmarks (best of 3, type check excluded, same machine)

| program | before | after |
|---------|-------:|------:|
| fib(22) recursion | 445 ms | 323 ms |
| 200k loop additions | 1221 ms | 812 ms |
| 20k map writes+reads | 131 ms | 84 ms |
