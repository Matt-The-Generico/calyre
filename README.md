# Calyre

![Calyre logo](./assets/calyre-logo.png)

A statically typed, readable programming language. This repository holds the
reference implementation (lexer, parser, type checker, interpreter, REPL, CLI).
Official language: English (syntax, keywords, standard library, documentation).

```calyre
use math

func area(radius: float) -> float
    return math.pi * radius * radius
end

let name: str? = none
print("Hello, {name ?? "world"}! Area: {area(2.0)}")
```

## Use it

```bash
python3 calyre_entry.py run examples/hello.cly     # or ./dist/calyre run ...
python3 calyre_entry.py check examples/demo.cly    # analyze only
python3 calyre_entry.py                            # REPL
python3 calyre_entry.py init my_project
python3 -m unittest discover -s tests              # 215 tests
python3 benchmarks/bench.py                        # reproducible timings
```

Requires Python 3.11+ only to run from source. `dist/calyre` is a single
PyInstaller executable (Linux x86_64) that needs no Python.
There is also a calyre.exe for Windows.

Documents: [docs/SPEC.md](docs/SPEC.md) (language reference) ·
[docs/ROADMAP.md](docs/ROADMAP.md) (consolidated plan) ·
[CHANGELOG.md](CHANGELOG.md) (incl. breaking changes and migration).

---

## Audit (Phase 4, version 0.2.0 stable)

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

### Still open (not done in this version)

* Generics (`func f<T>`, `struct Box<T>`), so `math.abs/min/max/pow` and
  `random.choice` are still typed `any` on purpose; lists have no `append` yet.
* Diagnostics carry a line but no column (blocks an LSP and good editor squiggles).
* Comments are discarded by the lexer (blocks a formatter that preserves them).
* No formatter, linter, `calyre test`, debugger, LSP or VS Code extension (yet!).
* Standard library lacks json, path, system/env/args, process, datetime, regex, http (planned on next version).
* `if`/`while` accept any value as a condition (truthiness), a pending design decision (it will change next version).
* Execution is a tree-walking interpreter (≈0.8 s for 200k loop iterations);
  call depth is capped at 800. No evidence yet justifies a VM.
* Only Linux was tested.
* Interactive features (`input_*`, arrow-key history) are only covered by piped-stdin tests.

### Benchmarks (best of 3, type check excluded, same Linux machine)

| program | before | after |
|---------|-------:|------:|
| fib(22) recursion | 445 ms | 323 ms |
| 200k loop additions | 1221 ms | 812 ms |
| 20k map writes+reads | 131 ms | 84 ms |
