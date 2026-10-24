# Roadmap

Phases are named by what they deliver and ordered by technical dependency (the older numbering collided: "Phase 4" meant two different things).
Status below is checked against the code and the tests, not against intentions.

## Done

| Phase | Delivered |
|-------|-----------|
| P0 Foundation and audit | audits ([AUDIT.md](AUDIT.md)), regression tests, CLI tests, specification, changelog |
| P1 Static semantics | scopes, declarations, return paths and inference, optionals with narrowing and `??`, typed modules, bool conditions |
| P2 Generics (first version) | generic functions and structs with inference by unification; generic stdlib signatures; methods on `list`/`map`/`str` |
| P4 Tooling core (first version) | columns in diagnostics, comments in the lexer, `calyre fmt` (idempotent, comment-safe), `calyre test`, `calyre lint` |
| P5 Standard library (first part) | `json`, `path`, `system`, `sql` (SQLite), extended `fs` |
| P6 Projects (first part) | `pub`, `use ... from`, imports by path, one canonical identity per module, local path dependencies |
| P8 Distribution (first part) | `scripts/build.py` with a smoke test of the built executable; Linux x86_64 built and verified |

## Next, in dependency order

1. **First-class functions** (function types, lambdas/anonymous functions). Needed for `map`/`filter`/`sort(key)`, callbacks and generic
   algorithms; it is the biggest missing piece of the type system. Depends on: function types in the checker, closures already exist.
2. **P3 type-system extensions:** aliases, enums + `match` exhaustiveness, interfaces/traits (define purpose first; they also give generics
   *bounds* such as "T can be ordered"), user-written unions with narrowing. Explicit instantiation (`first<int>(...)`) is not needed so far.
3. **Language server and VS Code extension.** The prerequisites are done (columns, comments, one parser and checker, diagnostics as data).
   Next: an LSP process (diagnostics, hover from inferred types, go to definition via the resolver, formatting via `calyre fmt`), then the extension.
4. **P5 standard library, rest:** `datetime` (needs a date/time value design and time zones), `process`, `regex`, `log`, then `http`
   (Python standard library, mandatory timeouts, visible errors, `json` integration), and `collections` if lists and maps prove insufficient.
5. **P6 projects:** lockfile and integrity for path and Git dependencies, transitive dependency rules, `calyre build`; a registry only much later.
6. **A native SQL engine** behind `sql.open("calyre:...")` (the API is ready; `calyre:` is reserved and reports "not implemented").
7. **P7 execution:** a bytecode VM only if realistic programs prove too slow (today parse and analysis are negligible and execution is about 4 µs per
   simple loop iteration); the tree-walking interpreter stays the reference and any VM needs equivalence tests.
8. **P8 distribution:** run the CI workflow, build and smoke-test Windows and macOS executables, installer, release process.

## Decisions taken

Conditions require `bool`; negative list indexes are allowed; `pub` is the explicit export (legacy modules without `pub` keep working);
diagnostics are English (no localisation machinery); `none` is the only absence value; texts: `"..."` interpolates, `"""..."""` is literal.

## Open questions

* Should the legacy "export everything without `pub`" rule start producing a warning in every importing project, and in which release does it end?
* Should `calyre lint` rules be enabled per-severity (`error`/`warn`/`off`) in `calyre.toml` rather than only disabled?
* A `date`/`time` representation: structs with fields, a single opaque type, or ISO texts?
