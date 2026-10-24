# Calyre language reference

This describes what the reference implementation does **today**. Anything not listed is not implemented
(see [ROADMAP.md](ROADMAP.md)). Every `calyre` example below is parsed and type-checked by the test suite;
`calyre run` examples are executed and their output compared. Library functions: [STDLIB.md](STDLIB.md).
Tools: [TOOLS.md](TOOLS.md).

## 1. Lexical structure

* Source is UTF-8. Blocks end with `end`; indentation is not significant (the formatter uses 4 spaces).
* Comments: `// to the end of the line`.
* Reserved words: `func let if elif else end while for in return break continue and or not true false none use as struct match case try catch assert pkg`.
  `pub` and `from` are *contextual*: they only mean something in `pub func|struct|let` and `use a from m`, so they stay valid names elsewhere.
* Numbers: `42`, `3.14`. Texts: `"text"` with escapes `\n \t \" \\ \{`. Names: letters, digits, `_`, not starting with a digit.

### Texts

```calyre run
let name = "Ana"
print("Hello, {name}! 1 + 1 = {1 + 1}")
print("literal brace: \{ok\}")
let json = """{"id": 7, "tag": "{not interpolated}"}"""
print(json)
```

```output
Hello, Ana! 1 + 1 = 2
literal brace: {ok}
{"id": 7, "tag": "{not interpolated}"}
```

* `"..."` supports `{expression}` interpolation and escapes.
* `"""..."""` is taken literally: no escapes, no interpolation; quotes and newlines are allowed. One newline right after the opening
  `"""` is dropped. A triple-quoted text cannot *end* with a `"` character (the first `"""` closes it).

## 2. Types

| Type | Meaning |
|------|---------|
| `int`, `float`, `str`, `bool` | `int` has arbitrary precision |
| `list<T>`, `map<K, V>` | one element type per collection; map keys are simple values |
| `T?` | a `T` or `none` (see section 6) |
| `any` | intentionally dynamic: compatible with everything, never inferred silently |
| `Name`, `Name<T>` | a struct, optionally generic |
| `module.Name` | a struct exported by an imported module |
| `T` | a type parameter inside a generic function or struct |

`none` is Calyre's only "no value"; there is no `null`.

### Inference

A variable keeps the type of its first value, and a function without `-> T` gets its return type from its `return` statements
(recursion and forward references work):

```calyre
let count = 3
func double(n: int)
    return n * 2
end
let doubled: int = double(count)
```

```calyre error
let count = 3
count = "three"
```

```output
main.cly:2:9: error: cannot assign str to 'count', which is int
```

### No implicit numeric conversion

`int` and `float` are never mixed (`1 + 1.5` is an error); convert with `float(x)` or `int(x)`. `/` always gives a `float`;
`math.floor_div(a, b)` is integer division. `+` joins two texts or two lists; `str + int` is an error (use `str(x)` or interpolation).
Texts are not ordered (`"a" < "b"` is an error).

### Conditions are `bool`

`if`, `elif`, `while`, `assert`, `and`, `or` and `not` need real booleans: no implicit truthiness.

```calyre error
let items = [1, 2]
if items
    print("not empty")
end
```

```output
main.cly:2:4: error: an 'if' condition must be a bool, but this is list<int>
    hint: Calyre has no implicit truthiness: write a comparison such as `x != 0`, `len(xs) > 0`, `s != ""` or `x != none`
```

## 3. Declarations and scopes

* Scopes: module, function (parameters + body), and each block (`if`/`while`/`for`/`match`/`try`/`catch`).
* A name is declared once per scope (redeclaring is an error); shadowing an outer name is allowed.
* Top-level `use`, `struct` and `func` are hoisted (usable before their line); `let` is not.
* Builtins live in an outer scope and can be shadowed at module level (the linter warns).

## 4. Functions and generics

`func name(a: T, b: U) -> R ... end`. Parameter types are required; `-> R` is optional. With a declared return type (other than
`any` or `R?`) **every path must return**: a `return` ending each branch, `error(...)`, a `match` with `case _`, or `while true`
without `break`. `return` outside a function and `break`/`continue` outside a loop are errors. Calls are positional; named arguments
exist only for building structs. The call depth is limited to 800 (a catchable error beyond that).

### Generics

Type parameters are written after the name and inferred at each call from the arguments:

```calyre run
func first<T>(items: list<T>) -> T
    return items[0]
end

struct Box<T>
    value: T
end

let a: int = first([10, 20])
let b: str = first(["x", "y"])
let box = Box(value: 2.5)
let c: float = box.value
print("{a} {b} {c}")
```

```output
10 x 2.5
```

Inside the body a type parameter is opaque: you can store, pass, return and compare (`==`) values of type `T`, but not add or
order them. A parameter that no argument mentions cannot be inferred and is rejected, and so is an empty `[]` where it is the only
evidence of `T`.

```calyre error
func first<T>(items: list<T>) -> T
    return items[0]
end
let x = first([])
```

```output
main.cly:4:9: error: cannot infer the type parameter T of 'first'
    hint: give an argument with a concrete type (an empty list `[]` carries no element type)
```

## 5. Expressions

Precedence, loosest to tightest: `=` · `??` · `or` · `and` · `== !=` · `< > <= >=` · `+ -` · `* / %` · `not` / unary `-` · call `()`, `.name`, `[index]`.
`a ?? b` evaluates `b` only when `a` is `none`. Lists accept negative indexes (`xs[-1]` is the last element); an index outside
`-len .. len-1` is a runtime error that names the valid range.

### Collections and methods

Values of the built-in types have methods (full list in [STDLIB.md](STDLIB.md)). Lists and maps have reference semantics:
mutating methods change the value in place and `copy()` makes a shallow copy. A `for` loop visits the elements the list had
when the loop started.

```calyre run
let names: list<str> = []
names.append("Bruno")
names.append("Ana")
names.sort()
print(names)
let ages = {"Ana": 30}
ages["Bruno"] = 25
print(ages.get("Carla") ?? -1)
print("  Hello  ".trim().upper())
```

```output
["Ana", "Bruno"]
-1
HELLO
```

A list or map literal may mix element types only where the expected type is explicitly `any` (`list<any>`, an `any` parameter):

```calyre
let mixed: list<any> = [1, "two", [3.0, none]]
print(mixed)
```

## 6. Optional values

`T?` cannot be used where `T` is needed until it is **narrowed**:

```calyre run
func describe(nickname: str?) -> str
    if nickname == none
        return "anonymous"
    end
    // from here `nickname` is a str
    return nickname.upper()
end

print(describe(none))
print(describe("ana"))
print((none ?? "fallback"))
```

```output
anonymous
ANA
fallback
```

* `if x != none` (and `and`, `or`, `not`, `while x != none`) narrows inside the branch; `if x == none return end` narrows the rest of the block
  (also with `break`, `continue`, `error(...)`).
* `assert x != none` narrows the rest of its block too (it stops the program when false).
* Any assignment to the variable cancels narrowing. Only plain variables are narrowed.
* `x ?? fallback` unwraps with a default of the same type.

```calyre error
func shout(name: str?) -> str
    return name.upper()
end
```

```output
main.cly:2:17: error: '.upper' cannot be used on a value of type str?
    hint: the value may be none: check `!= none` first, or use `??` to give a default
```

## 7. Statements

`let`, assignment (variable, field, list/map element), `if`/`elif`/`else`, `while`, `for x in list | map (keys) | str | range(...)`,
`match` (cases compared with `==`, `case _` is the default, no exhaustiveness check yet), `try`/`catch e` (`e.message`, `e.line`),
`assert condition[, message]`, `use`, `struct`, `func`.

`assert` explains itself: on failure it shows the values involved.

```calyre run
func safe_div(a: float, b: float) -> float
    if b == 0.0
        error("cannot divide {a} by zero")
    end
    return a / b
end

try
    print(safe_div(1.0, 0.0))
catch e
    print("caught: {e.message}")
end
```

```output
caught: cannot divide 1.0 by zero
```

## 8. Modules and visibility

Ways to import:

```text
use math                      a standard library module, or <folder of this file>/math.cly
use math as m                 under another name
use sqrt, floor from math     bind members directly (also: use sqrt as root from math)
use "./lib.cly"               a file by path
use "../shared/util"          ".cly" may be omitted; the name is the file's stem
use "/abs/path/lib.cly"       absolute path; "C:/Users/me/lib.cly" on Windows
use "./lib" as l              any of the path forms can use `as` or `from`
```

Resolution is the same for the type checker and the interpreter:

1. A **name** (`use shapes`, `use a.b` → `a/b.cly`) is looked for relative to the file that contains the `use`, then in the
   `[dependencies]` of the nearest `calyre.toml` (`use dep` → `<path>/dep.cly`, `use dep.sub` → `<path>/sub.cly`). Local files win.
2. A **path** is relative to the file that contains the `use`, **never** to the current working directory. `\` and `/` both
   separate folders on every platform, and `.cly` is added if missing. Only `.cly` files can be imported.
3. Files are identified by their real path: the same file imported by name and by path is one module, loaded and run once,
   with one set of types. Circular imports are reported with the whole chain.

A missing module is a static error that says where it looked.

**Exports.** If a module declares anything with `pub` (`pub func`, `pub struct`, `pub let`), exactly the `pub` declarations are exported.
A module with no `pub` at all exports every top-level name not starting with `_` (the rule of earlier versions, kept so existing
libraries still work; `calyre lint` suggests adding `pub`). `pub` is only allowed at the top level.

Types cross module boundaries: the checker knows the signatures, constants, generics and structs of imported modules.

## 9. Errors and diagnostics

* Static diagnostics are `file:line:column: error|warning: message`, optionally followed by an indented `hint:`.
  **Errors stop the program before it runs; warnings never do.** Warnings exist where a stricter rule would break programs that were valid before.
* Runtime errors are `file:line: runtime error: message`, naming the file where they happened. They are catchable with `try/catch`;
  `error("message")` raises one on purpose. `system.exit(code)` is not catchable.
* An internal failure of the implementation prints `internal error ...` and exits with 70 (`CALYRE_DEBUG=1` shows the traceback).
* Exit codes: `0` success · `1` program, analysis or tool failure · `70` internal error · `130` interrupted.

## 10. Python interoperability

`use python`, then `python.call("module", "function", args...)`. Only `math random statistics datetime json` may be called;
arguments and results must be int/float/str/bool/none/list/map; Python exceptions become catchable Calyre errors. The result is
`any` (a deliberate dynamic boundary). Third-party Python packages are not available.

## 11. Compatibility

Valid programs keep working unless a change is listed under "Changed (breaking)" in [CHANGELOG.md](../CHANGELOG.md) with a migration path.
Stricter rules that could reject previously valid code are introduced as warnings first when a safe alternative exists.
