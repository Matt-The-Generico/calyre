# Changelog

## Unreleased

### Added
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

### Changed (breaking)
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

### Warnings (for compatibility)
* Empty collection without annotation (`let xs = []`), write `let xs: list<int> = []`.
* `let x = none`, declare `let x: int? = none`.
* Unannotated function returning different types, annotate the return type.
* `==` between types that can never be equal; `??` on a value that is never none.

### Fixed
Python tracebacks on bad builtin arguments, deep recursion (now a catchable error at depth 800),
stray `break`/`continue`/`return`; `break` escaping a function; out-of-range list assignment.

### Performance
Cached AST dispatch: 25–35% faster on the included benchmarks.
