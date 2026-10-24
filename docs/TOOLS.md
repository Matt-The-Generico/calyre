# Tools

One program, `calyre`. Every command below exists and is covered by tests (`tests/test_cli.py`, `test_formatter.py`,
`test_testrunner.py`, `test_linter.py`).

```text
calyre                         start the REPL (also: calyre repl, calyre start)
calyre run file.cly [args]     type-check, then run; args reach system.args()
calyre check file.cly          type-check only
calyre fmt [--check|--stdout] [paths...]
calyre test [-v] [-k text] [paths...]
calyre lint [--disable a,b] [--rules] [paths...]
calyre init [folder]           create main.cly + calyre.toml
calyre add NAME --path DIR     declare a local dependency in calyre.toml
calyre remove NAME
calyre list                    list the declared dependencies
calyre version
calyre help                    (also --help, -h)
```

**Exit codes:** `0` success · `1` the program, the analysis or the tool failed (type errors, failing tests, lint findings,
`fmt --check` would change something) · `70` internal error (a bug in Calyre; `CALYRE_DEBUG=1` shows the traceback) ·
`130` interrupted · or the code given to `system.exit(n)`.

## `calyre run` and `calyre check`

`run` analyzes first; a program with errors is never started. Warnings are printed and do not stop it. Diagnostics look like
`path:line:column: error: message`, with an optional `hint:` line; runtime errors look like `path:line: runtime error: message`
and name the file where they happened, even inside an imported module.

```text
$ calyre check main.cly
main.cly:3:14: error: 'total' is declared as int, but the value has type float
    hint: `/` always gives a float; for integer division use math.floor_div(a, b), or convert with int(a / b)
calyre: 1 error found in main.cly - nothing was run
```

## `calyre fmt`

Rewrites `.cly` files in the one official style. With no path it formats the current folder (skipping `.git`, `dist`, `build`).

* `--check` changes nothing and exits 1 if any file would change (for CI). `--stdout FILE` prints the result.
* **Idempotent** (formatting twice changes nothing) and **meaning-preserving** (the program has the same syntax tree); both are tested
  on every shipped example and on generated cases.
* Style: 4-space indent; `end` on its own line; one blank line around top-level `func`/`struct`; your other blank lines are kept (at most one);
  spaces around operators; parentheses only where precedence needs them; lines over 100 columns are broken by putting list/map
  elements and call arguments on separate lines; `"""` texts stay as written.
* **Comments are never lost or moved across statements.** They are kept above a statement, after it on the same line, or at the end of its block.
  A comment inside a multi-line expression cannot be placed safely, so the formatter refuses that file and tells you the line instead of guessing.
* A file with a syntax error is reported and left untouched; other files are still formatted. Writes go through a temporary file.

## `calyre test`

```calyre
use math

func test_floor_div()
    assert math.floor_div(7, 2) == 3
end

func test_sqrt()
    assert math.sqrt(9.0) == 3.0, "square root of 9"
end
```

* A test file is named `test_*.cly` or `*_test.cly`; a test is a top-level function named `test_*` with no parameters.
  Files are found under the given folders (default: the current one).
* A test passes if it finishes and fails if it raises a runtime error, which is what `assert` and `error(...)` do. `assert` shows the
  values involved: `assertion failed: add(1, 2) == 4 (add(1, 2) = 3, 4 = 4)`.
* The file's top-level code runs once; tests run in definition order and a failure never stops the others. A test that calls
  `system.exit` fails (it does not end the run). Output printed by a test is shown only when it fails.
* A file that does not compile or parse is one failure and its code is not run. `-v` lists passing tests, `-k text` runs the tests whose name contains `text`.
  Exit code 1 if anything failed or if no tests were found.

```text
$ calyre test
FAIL tests/test_math.cly::test_add
     tests/test_math.cly:7: assertion failed: add(1, 2) == 4 (add(1, 2) = 3, 4 = 4)
12 passed, 1 failed in 0.03s
```

## `calyre lint`

Reports code that is legal but probably not what you meant, plus the type checker's warnings (rule `type-check`). Type errors and syntax
errors are reported too. Every rule aims at near-zero false positives; when in doubt it stays quiet. Exit code 1 if anything is reported.

| Rule | Reports |
|------|---------|
| `unused-variable` | a local `let` that is never read (write-only counts as unused; names starting with `_` are exempt) |
| `unused-import` | a `use` that is never referenced |
| `unused-function` | a private function that is never used (`_name`, or any non-`pub` function in a file that uses `pub`) |
| `unreachable-code` | statements after `return`, `break`, `continue` or `error(...)` |
| `shadowed-builtin` | a name that hides `print`, `len`, `str`, ... |
| `naming-convention` | `snake_case` for functions/variables/parameters (module-level `UPPER_CASE` constants allowed), `PascalCase` for structs |
| `compare-to-bool` | `x == true`, `x != false` |
| `constant-condition` | `if true`, `while false`, `x == x` (`while true` is idiomatic and fine) |
| `library-without-pub` | a file that only declares things and exports all of it by the legacy rule: add `pub` |
| `pub-missing-return-type` | a `pub` function that returns a value without declaring `-> type` |
| `sql-injection-risk` | `db.query/execute/query_one` with a query built by `+` or `{interpolation}`: use `?` parameters |
| `type-check` | warnings from the type checker (empty collection without a type, `let x = none`, ...) |

Silence a finding where you mean it: `// lint-ignore` or `// lint-ignore: rule, rule` on the same line or on the line above.
Turn rules off for a project in `calyre.toml`, or for one run with `--disable`:

```text
[lint]
disable = ["naming-convention"]
```

## Projects and dependencies

`calyre init my_app` creates `main.cly` and `calyre.toml`. A project is a folder; every `.cly` file in it is already a library
(`use name`, `use "./name.cly"`). Dependencies are **local folders** declared in `calyre.toml`:

```text
[project]
name = "my_app"
version = "0.1.0"

[dependencies]
mylib = { path = "../mylib" }
```

`use mylib` then loads `../mylib/mylib.cly`, and `use mylib.extra` loads `../mylib/extra.cly`. `calyre add NAME --path DIR`,
`calyre remove NAME` and `calyre list` edit and show that table. There is no package registry and no lockfile yet, and `calyre add`
without `--path` says so. Importing a file is not installing a package: files are loaded where they are, never copied.

## The REPL

`calyre` starts an interactive session that uses the same lexer, parser, type checker and interpreter as files. State persists for
the session (it behaves like one growing file, so you may redeclare a name). Blocks continue on `...` lines until `end`. An input with an
error is rejected as a whole, leaving no half-declared names. Commands: `help`, `exit`, `clear`, `history`. Relative `use "./x.cly"` paths
are relative to the folder where you started `calyre`. The REPL's text is English, like every message Calyre prints.
