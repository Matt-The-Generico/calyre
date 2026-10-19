# Calyre language reference (implemented behaviour)

This document describes what the reference implementation does **today**.
Anything not listed here is not implemented (see ROADMAP.md). Every rule below
is exercised by a test in `tests/`.

## 1. Lexical structure
* Source is UTF-8, line based; blocks are closed by `end` (indentation is not significant).
* Comments: `// to end of line` (discarded by the lexer).
* Keywords: `func let if elif else end while for in return break continue and or not true false none use as struct match case try catch assert pkg`.
* Literals: `42`, `3.14`, `"text"` (escapes `\n \t \" \\ \{`), `true`, `false`, `none`, `[1, 2]`, `{"k": v}`.
* String interpolation: `"Hello, {name}!"` — any expression inside `{}` (it may not contain a `}` of its own string).

## 2. Types
| Type | Notes |
|------|-------|
| `int`, `float`, `str`, `bool` | `int` is arbitrary precision. |
| `list<T>`, `map<K, V>` | One element type per collection (`[1, "a"]` is an error). Map keys are simple values. |
| `T?` | "a `T` or `none`" (see §6). |
| `any` | Intentionally dynamic: compatible with everything, never inferred silently. |
| structs | Nominal, declared with `struct Name ... end`, built with named arguments: `P(x: 1, y: 2)`. |
| `module.Type` | A struct exported by an imported module. |

Internally the checker also distinguishes `unknown` (unresolved, only after an error was
already reported, or while a return type is still being inferred) from `any`.
There are no user-written function types, unions, generics, aliases or enums yet.

### Inference
`let n = 1` infers `int`; a variable keeps that type. Function return types are
declared (`-> T`) or inferred from the `return` statements; recursion and forward
references work. If an unannotated function returns different types the result
is `any` and a warning is issued.

### No implicit numeric conversion
`int` and `float` are never mixed in arithmetic or comparisons (`1 + 1.5` is an error);
convert with `float(x)` / `int(x)`. `/` always yields `float`; `math.floor_div(a, b)` is
integer division. `+` joins two `str` or two lists; `str + int` is an error (use `str(x)` or interpolation).
Texts are not ordered (`"a" < "b"` is an error).

## 3. Declarations and scopes
* Scopes: module, function (parameters + body), and each block (`if`/`while`/`for`/`match`/`try`/`catch`).
* A name may be declared once per scope; redeclaring is an error. Shadowing an *outer* name is allowed.
* Top-level `use`, `struct` and `func` declarations are hoisted: they may be used before their line.
  `let` is not hoisted.
* Builtins (`print`, `len`, ...) live in an outer scope and can be shadowed at module level.
* Assigning needs a prior `let`; functions, structs and modules cannot be assigned to.

## 4. Functions
* `func name(a: T, b: U) -> R ... end`; parameter types are required, `-> R` is optional.
* With `-> R` (not `any`, not `R?`) **every path must return** a value: `return` at the end of
  every branch, `error(...)`, a `match` with `case _`, or `while true` without `break` all count.
* `return` outside a function, `break`/`continue` outside a loop are errors.
* Calls are positional only; named arguments exist only for building structs.
* Maximum call depth: 800 (a catchable runtime error beyond that).

## 5. Expressions
Precedence, loosest to tightest: `=` · `??` · `or` · `and` · `== !=` · `< > <= >=` · `+ -` · `* / %` · `not` / unary `-` · call `()`, `.field`, `[index]`.
* `and`, `or`, `not` always produce `bool`; operands may be any value (truthiness: `0`, `""`, empty collections, `none`, `false` are false).
* `a ?? b` — `b` is evaluated only when `a` is `none`.
* Lists accept negative indexes from the end (`xs[-1]`).

## 6. Optional values
`T?` is not usable where `T` is required, for arithmetic, member access, indexing or looping,
until it is **narrowed**:
* `if x != none ... end` — `x` is `T` inside; `if x == none ... else ... end` — `T` in the `else`.
* Early exit: `if x == none return end` (also `break`, `continue`, `error(...)`) narrows the rest of the block.
* `a and b` / `a or b` / `not a` narrow within the right operand and the branches.
* Any assignment to the variable cancels narrowing. Narrowing is only tracked for plain variables.
* `x ?? fallback` unwraps with a default (the fallback must have type `T`).

## 7. Statements
`let`, assignment (variables, fields, list/map elements), `if/elif/else`, `while`, `for x in list|map(keys)|str|range(...)`,
`match` (compared with `==`; `case _` is the default; no exhaustiveness check), `try/catch e` (`e.message`, `e.line`),
`assert cond[, message]` (on failure prints the values: `assertion failed: x > 10 (x = 5, 10 = 10)`), `use`, `struct`.

## 8. Modules and visibility
* `use name` / `use name as alias` / `use a.b` (→ `a/b.cly`). The module name (or alias) is bound as a namespace.
* Resolution order: relative to the importing file; then a `[dependencies]` entry of the nearest `calyre.toml`
  (`use dep` → `<path>/dep.cly`, `use dep.sub` → `<path>/sub.cly`). Local files win.
* Standard library modules: `math random time text fs python` (typed signatures in `calyre/stdlib_types.py`).
* A module is analysed and executed once. Everything declared at its top level is exported except names starting with `_`.
* Types cross module boundaries: the checker knows the signatures, constants and structs of imported modules.
* Circular imports, missing modules, missing/private members and errors inside a module are reported **statically**
  at the `use` line (and again at run time as a safety net).

## 9. Errors
* Runtime errors are `file:line: runtime error: message`, naming the file where they happened; they are catchable by
  `try/catch` and raised on purpose with `error("message")`.
* Static diagnostics are `file:line: error|warning: message` (+ optional `hint:`). **Errors block execution; warnings never do.**
  Warnings exist where a stricter rule would break programs that were valid before.
* An internal failure of the implementation itself prints `internal error ...` and exits with code 70.

Exit codes: `0` success · `1` program/analysis error · `70` internal error · `130` interrupted.

## 10. Python interoperability
`use python` then `python.call("module", "function", args...)`. Only `math random statistics datetime json` are allowed;
arguments and results must be int/float/str/bool/none/list/map; Python exceptions become catchable Calyre errors.
The result is `any` (a dynamic boundary on purpose). Third-party packages are not available.

## 11. Compatibility policy
Valid programs keep working unless a change is listed under "Changed (breaking)" in CHANGELOG.md with a migration path.
New strictness that could reject previously valid code is first introduced as a warning when a safe alternative exists.
