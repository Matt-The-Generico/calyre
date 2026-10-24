# Distribution

## What exists

| Artifact | How it is made | Verified |
|----------|----------------|----------|
| Source (Python 3.11+, no dependencies) | this repository | Tests pass on Linux, Windows, and macOS via GitHub Actions |
| Linux x86_64 executable | `python scripts/build.py` on Linux | Built and smoke-tested on Linux via GitHub Actions |
| Windows executable | `python scripts/build.py` on Windows | Built and smoke-tested on Windows via GitHub Actions |
| macOS executable | `python scripts/build.py` on macOS | Built and smoke-tested on macOS via GitHub Actions |

PyInstaller cannot cross-compile, so a Windows `.exe` or a macOS binary must be built on that system. `.github/workflows/ci.yml` runs
the tests and the build on all three systems; it was written but **never executed** in the environment that produced it, so treat
Windows and macOS support as unproven until it has run.

## Building one executable

```text
python -m pip install -r requirements-build.txt     # pins PyInstaller
python scripts/build.py
```

The script builds `dist/calyre-<os>-<arch>[.exe]` plus a `.sha256` file, then runs the **built executable** (not the sources) through:
`version`, running a program, a type error stopping execution, path imports, `fmt --check`, `test`, `lint`, SQLite, JSON, the REPL and
program arguments. It prints `SMOKE OK` or exits non-zero. Builds are reproducible in procedure (pinned PyInstaller, clean work folder) but
not bit-for-bit identical, because PyInstaller embeds timestamps; compare behaviour (the smoke test), not hashes, across rebuilds.

A user needs no Python, Node, compiler or other tool to run the executable: `calyre run program.cly`, or just `calyre` for the REPL.

## Languages

The canonical language of the syntax, keywords, standard library, messages and reference documentation is English.
[`docs/pt/COMECANDO.md`](pt/COMECANDO.md) is a Portuguese introduction for learners; code is identical in every language.
There is one implementation of the language and one REPL; no translated variants, no localisation machinery.
