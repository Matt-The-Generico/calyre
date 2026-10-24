# Calyre

![Calyre logo](./assets/calyre-logo.png)

A statically typed, readable programming language. This repository is the reference implementation: lexer, parser, type checker,
interpreter, REPL and the official tools (formatter, test runner, linter). The language, its keywords, standard library, messages and
reference documentation are in English; [`docs/pt/COMECANDO.md`](docs/pt/COMECANDO.md) is an introduction in Portuguese.

```calyre run
use json

struct Reading
    city: str
    celsius: float?
end

func describe(r: Reading) -> str
    return "{r.city}: {r.celsius ?? 0.0} degrees"
end

let readings = [Reading(city: "Fortaleza", celsius: 31.5), Reading(city: "Oslo", celsius: none)]
for r in readings
    print(describe(r))
end
print(json.stringify(readings[0]))
```

```output
Fortaleza: 31.5 degrees
Oslo: 0.0 degrees
{"city":"Fortaleza","celsius":31.5}
```

## Use it

```text
python3 calyre_entry.py run examples/hello.cly      # from source: Python 3.11+, no dependencies
python3 calyre_entry.py                             # the REPL
python3 calyre_entry.py test examples/testing_demo  # run Calyre tests
python3 -m unittest discover -s tests               # the implementation's own tests
python3 scripts/build.py                            # standalone executable for this OS (needs PyInstaller)
python3 benchmarks/bench.py                         # timings per phase
```

The executable needs no Python, compiler or any other tool. Executables for other operating systems must be built on those systems:
see [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for what is verified and what is not.

## What the language has

Static types with inference · generics for functions and structs · `T?` optionals with flow-sensitive narrowing and `??` ·
typed lists and maps · methods on lists, maps and texts · structs · modules with explicit `pub` exports and imports by name or by file path ·
`try/catch` · self-explaining `assert` · `"""` literal texts · diagnostics with file, line, column and hints ·
a standard library (`math random time fs path json system sql`) · a restricted Python bridge.

Tools: `calyre run | check | fmt | test | lint | init | add | remove | list | version`, and a REPL. See [docs/TOOLS.md](docs/TOOLS.md).

## Documentation

| Document | Contents |
|----------|----------|
| [docs/SPEC.md](docs/SPEC.md) | the language reference (every example is executed by the tests) |
| [docs/STDLIB.md](docs/STDLIB.md) | builtins, methods, modules (the tests fail if anything is undocumented) |
| [docs/TOOLS.md](docs/TOOLS.md) | CLI, formatter, test runner, linter, projects, exit codes |
| [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) | building and verifying executables |
| [docs/ROADMAP.md](docs/ROADMAP.md) | the consolidated plan and what is done |
| [docs/AUDIT.md](docs/AUDIT.md) | findings of each audit round |
| [CHANGELOG.md](CHANGELOG.md) | changes, breaking changes and migrations |

The older `calyre-fase*.md` design notes are historical (Portuguese) and superseded by the documents above.

## Status

Reference interpreter (tree-walking); the type checker, formatter, test runner and linter share one parser and one AST.
Tested on Linux only: the Windows and macOS builds and the CI workflow have not been run. Known gaps (language server, VS Code extension,
first-class functions, enums and unions, more standard modules, package registry and lockfile) are listed in the roadmap.

Performance (see `benchmarks/bench.py`): parsing and analysis take well under a millisecond for these programs; execution dominates,
at roughly 4 µs per simple loop iteration. There is no evidence yet that a bytecode VM is needed.
