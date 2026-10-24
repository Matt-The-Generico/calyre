# Changelog

## Unreleased (proposed next version: 0.3.0, it contains breaking changes)

### Added
* **Generics** for functions and structs (`func first<T>(items: list<T>) -> T`, `struct Box<T>`), inferred at each call; generic standard library
  signatures (`math.abs/min/max`, `random.choice`, `text.join`).
* **Methods** on `list`, `map` and `str` (`items.append(x)`, `ages.get(k) ?? 0`, `name.trim().upper()`): see docs/STDLIB.md.
* **`pub` visibility**, `use a, b from m`, and **imports by file path** (`use "./lib.cly"`, `use "../shared/util"`, absolute paths);
  one canonical identity per file, path resolution relative to the importing file.
* **`"""` literal texts** (multi-line, no escapes, no interpolation: ideal for JSON and SQL).
* **Tools:** `calyre fmt`, `calyre test`, `calyre lint` (11 rules + the checker's warnings), `calyre help`; program arguments (`calyre run f.cly a b`).
* **Standard library:** `json`, `path`, `system`, `sql` (SQLite, one API for future engines), more `fs` (`append is_file is_dir size remove remove_dir rename`).
* **Diagnostics with columns** (`file:line:column`), pointing at the offending value; comments kept by the lexer (for tools).
* `assert x != none` narrows the rest of its block; contextual typing lets heterogeneous literals be passed where `any` is expected.
* `scripts/build.py` (standalone executable + smoke test), `requirements-build.txt`, a CI workflow (not yet run), tested documentation.
* Earlier in this release line: full semantic analysis, optionals with narrowing, `??`, typed modules, `calyre.toml` path dependencies (see the first round below).

### Changed (breaking): and how to migrate
| Change | Why | Migration |
|--------|-----|-----------|
| `if`/`elif`/`while`/`assert`/`and`/`or`/`not` require a `bool` | no implicit truthiness | write a comparison: `len(xs) > 0`, `s != ""`, `x != 0`, `x != none` |
| `math.pow(x, y)` always returns `float` (was `int` for `int` arguments) | result type must not depend on values | `int(math.pow(2, 3))`, or multiply |
| `math.min/max(a, b)` need the same numeric kind | typed with a type variable | `math.min(float(a), b)` |
| Printed lists, maps and structs quote their texts: `["a", "b"]` | `[a, b]` was ambiguous | none (output format only) |
| `fs.write`/`fs.append` never translate `\n` (on Windows they used to write `\r\n`) | same bytes on every OS | none unless you relied on CRLF |
| `fs` errors have new wording and `fs.write` into a missing folder says so | readable errors | none |
| A module that uses `pub` exports only its `pub` declarations | explicit visibility | modules with no `pub` behave as before; add `pub` to what you export |
| Heterogeneous list/map literals are rejected unless `any` is expected | typed collections | `let xs: list<any> = [1, "a"]` or use a struct |
| `examples/modules_demo` now uses `pub` | examples follow the recommended style | none |

### Fixed
Optionals are now usable after `assert`; clear index-out-of-range messages that name the valid range; errors raised inside builtins carry the
call-site line; qualified generic types (`box.Box<int>`); imports are hoisted before declarations that mention `mod.Type`.

### Performance
Builtin calls no longer inspect their signature: 3-6x faster on programs dominated by list/map/text/JSON/SQL calls (see docs/AUDIT.md).

---

## First round of this release line

### Added (round 1)
* Full semantic analysis: scopes, declarations, return paths, return-type inference,
  unknown-type errors with "did you mean" hints, determinism (diagnostics sorted by line).
* Optional narrowing: `if x != none`, `if x == none return`, `and`/`or`, `while x != none`.
* `??` (none-coalescing) operator: `name ?? "guest"`.
* Types across modules and for the whole standard library (signatures in `stdlib_types.py`);
  module-qualified types in annotations (`let p: shapes.Point`).
* `calyre.toml` path dependencies are resolved by `use` (`calyre/resolver.py`).
* `math.floor_div(a, b)` for integer division.
* Diagnostics format `file:line: error|warning: message` plus `hint:` line; warnings never block.
* Runtime errors report the file where they happened: `util.cly:2: runtime error: ...`.
* `CALYRE_DEBUG=1` shows the Python traceback of an internal error (exit code 70).

### Changed (breaking) — and how to migrate
| Change | Why | Migration |
|--------|-----|-----------|
| Re-declaring a name in the same scope is an error | silently changed a variable's type | use `x = value` to assign; pick a new name to declare |
| Declared return type must be returned on every path | `-> int` could return `none` | add the missing `return`, or declare `-> int?` |
| Unknown type names are errors | typos became `any` | fix the name; write `any` explicitly if dynamic |
| `/` always returns `float` (`6 / 2` is `3.0`) | result type depended on values | use `math.floor_div(a, b)` for int division, or `int(a / b)` |
| `and` / `or` always return `bool` | typed `bool`, returned operands | use `??` for defaults |
| Lists/maps must have one element type (`[1, "a"]` is an error) | silent `list<any>` | use a struct, or `list<any>` explicitly |
| Optionals are not usable as plain values until narrowed | `int?` was silently accepted as `int` | check `!= none` or use `??` |
| Importing a missing module is a static error | failed only at run time | create the file or fix the name |
| Runtime/CLI messages are now English | official language rule | none |

### Warnings (not errors, for compatibility)
* Empty collection without annotation (`let xs = []`) — write `let xs: list<int> = []`.
* `let x = none` — declare `let x: int? = none`.
* Unannotated function returning different types — annotate the return type.
* `==` between types that can never be equal; `??` on a value that is never none.

### Fixed
Python tracebacks on bad builtin arguments, deep recursion (now a catchable error at depth 800),
stray `break`/`continue`/`return`; `break` escaping a function; out-of-range list assignment.

### Performance
Cached AST dispatch: 25–35% faster on the included benchmarks.
