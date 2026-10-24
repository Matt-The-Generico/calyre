"""
Calyre CLI — the single official tool.

    calyre                       starts the interactive REPL
    calyre repl                  same as above, explicit
    calyre run <file.cly> [args]  type-checks and runs a program (args reach system.args())
    calyre check <file.cly>      type-checks a program without running it
    calyre fmt [--check|--stdout] [paths...]
                                 formats .cly files in place (default: current folder)
    calyre test [-v] [-k text] [paths...]
                                 runs test_*.cly / *_test.cly files (functions named test_*)
    calyre lint [--disable a,b] [--rules] [paths...]
                                 reports suspicious code (see `calyre lint --rules`)
    calyre init [dir]            scaffolds a minimal new project
    calyre add <name> --path P   declares a local dependency in calyre.toml
    calyre remove <name>         removes a dependency from calyre.toml
    calyre list                  lists the project's declared dependencies
    calyre version               prints the interpreter version

Not implemented yet (see docs/ROADMAP.md):
    remote packages              calyre add currently only supports local
                                  path dependencies; there is no package
                                  registry to fetch from yet
"""

import os
import sys

from . import __version__
from .lexer import tokenize, LexError
from .calyre_parser import parse, ParseError
from .interpreter import interpret, CalyreRuntimeError
from . import typechecker


def _read_source(path):
    if not path.endswith(".cly"):
        print(f"warning: Calyre files normally use the .cly extension ({path})", file=sys.stderr)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"calyre: file not found: {path}", file=sys.stderr)
        sys.exit(1)


def _analyze_or_exit(program, path):
    """Type-check; print warnings and errors; exit 1 if there are errors."""
    errors, warnings = typechecker.analyze(program, base_dir=os.path.dirname(os.path.abspath(path)))
    for d in warnings + errors:
        print(d.format(path), file=sys.stderr)
    if errors:
        n = len(errors)
        print(f"calyre: {n} error{'s' if n != 1 else ''} found in {path} - nothing was run",
              file=sys.stderr)
        sys.exit(1)
    return warnings


def cmd_run(path, program_args=()):
    from .stdlib import set_program_args
    set_program_args(program_args)
    source = _read_source(path)
    try:
        tokens = tokenize(source)
        program = parse(tokens)
    except LexError as e:
        print(f"calyre: {e}", file=sys.stderr)
        sys.exit(1)
    except ParseError as e:
        print(f"calyre: syntax error - {e}", file=sys.stderr)
        sys.exit(1)

    _analyze_or_exit(program, path)

    try:
        interpret(program, base_dir=os.path.dirname(os.path.abspath(path)), file=path)
    except CalyreRuntimeError as e:
        where = e.file or path
        loc = f"{where}:{e.line}" if e.line is not None else where
        print(f"{loc}: runtime error: {e.message}", file=sys.stderr)
        sys.exit(1)


def cmd_check(path):
    source = _read_source(path)
    try:
        tokens = tokenize(source)
        program = parse(tokens)
    except LexError as e:
        print(f"calyre: {e}", file=sys.stderr)
        sys.exit(1)
    except ParseError as e:
        print(f"calyre: syntax error - {e}", file=sys.stderr)
        sys.exit(1)

    warnings = _analyze_or_exit(program, path)
    extra = f" ({len(warnings)} warning{'s' if len(warnings) != 1 else ''})" if warnings else ""
    print(f"{path}: no errors found{extra}")


def cmd_version():
    print(f"calyre {__version__} (reference implementation - interpreter)")


_PROJECT_MAIN = '''// main.cly - the entry point of your Calyre project.

func main()
    print("Hello, world!")
end

main()
'''

_PROJECT_MANIFEST = '''# calyre.toml - project manifest.
# Deliberately tiny: a name, a version and local dependencies.
# Remote dependencies are not supported yet.

[project]
name = "{name}"
version = "0.1.0"

[dependencies]
# example (uncomment and adjust):
# some_lib = {{ path = "../some_lib" }}
'''


def cmd_init(target_dir):
    target_dir = target_dir or "."
    os.makedirs(target_dir, exist_ok=True)
    main_path = os.path.join(target_dir, "main.cly")
    manifest_path = os.path.join(target_dir, "calyre.toml")

    if os.path.exists(main_path) or os.path.exists(manifest_path):
        print(f"calyre: '{target_dir}' already contains a Calyre project (main.cly or calyre.toml exists)", file=sys.stderr)
        sys.exit(1)

    project_name = os.path.basename(os.path.abspath(target_dir))
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(_PROJECT_MAIN)
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(_PROJECT_MANIFEST.format(name=project_name))

    print(f"Calyre project created in '{target_dir}':")
    print("  main.cly       - your program")
    print("  calyre.toml    - the project manifest")
    print()
    print(f"To run it:  calyre run {os.path.join(target_dir, 'main.cly')}")


def _load_manifest(path="calyre.toml"):
    import tomllib
    if not os.path.exists(path):
        print(f"calyre: no '{path}' in this directory. Run 'calyre init' first.", file=sys.stderr)
        sys.exit(1)
    with open(path, "rb") as f:
        return tomllib.load(f)


def _write_manifest_deps(deps, path="calyre.toml"):
    # Minimal, deliberately naive TOML writer: this manifest format only
    # ever needs [project] + a flat [dependencies] table of {path=...}
    # entries, so a full TOML writer/library is not worth the dependency.
    manifest = _load_manifest(path)
    project = manifest.get("project", {})
    lines = [
        "# calyre.toml - project manifest.",
        "",
        "[project]",
        f'name = "{project.get("name", "project")}"',
        f'version = "{project.get("version", "0.1.0")}"',
        "",
        "[dependencies]",
    ]
    for name, spec in deps.items():
        dep_path = spec.get("path", "") if isinstance(spec, dict) else str(spec)
        lines.append(f'{name} = {{ path = "{dep_path}" }}')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def cmd_add(name, path_flag):
    if not path_flag:
        print(
            "calyre: 'calyre add' only supports local dependencies for now.\n"
            "        use: calyre add <name> --path <folder of the library>\n"
            "        (there is no remote package registry yet - see docs/ROADMAP.md)",
            file=sys.stderr,
        )
        sys.exit(1)
    manifest = _load_manifest()
    deps = manifest.get("dependencies", {})
    deps[name] = {"path": path_flag}
    _write_manifest_deps(deps)
    print(f"'{name}' added as a local dependency ({path_flag})")


def cmd_remove(name):
    manifest = _load_manifest()
    deps = manifest.get("dependencies", {})
    if name not in deps:
        print(f"calyre: '{name}' is not a dependency of this project", file=sys.stderr)
        sys.exit(1)
    del deps[name]
    _write_manifest_deps(deps)
    print(f"'{name}' removed")


def cmd_list():
    manifest = _load_manifest()
    deps = manifest.get("dependencies", {})
    if not deps:
        print("(no dependencies declared)")
        return
    for name, spec in deps.items():
        dep_path = spec.get("path", "?") if isinstance(spec, dict) else str(spec)
        print(f"{name}  (local: {dep_path})")


def _collect_cly(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in (".git", "dist", "build", "__pycache__", "node_modules"))
                files += [os.path.join(root, n) for n in sorted(names) if n.endswith(".cly")]
        else:
            files.append(p)
    return files


def cmd_fmt(args):
    from .formatter import format_source, FormatError
    check = "--check" in args
    to_stdout = "--stdout" in args
    paths = [a for a in args if not a.startswith("--")] or ["."]
    unknown = [a for a in args if a.startswith("--") and a not in ("--check", "--stdout")]
    if unknown:
        print(f"calyre fmt: unknown option {unknown[0]}", file=sys.stderr)
        sys.exit(1)
    files = _collect_cly(paths)
    if to_stdout and len(files) != 1:
        print("calyre fmt --stdout needs exactly one file", file=sys.stderr)
        sys.exit(1)
    if not files:
        print("calyre fmt: no .cly files found", file=sys.stderr)
        sys.exit(1)
    failed = changed = 0
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                source = f.read().replace("\r\n", "\n")
        except OSError as e:
            print(f"{path}: cannot read ({e.strerror})", file=sys.stderr)
            failed += 1
            continue
        try:
            result = format_source(source)
        except FormatError as e:
            where = f":{e.line}" if e.line else ""
            print(f"{path}{where}: cannot format: {e.message}", file=sys.stderr)
            failed += 1
            continue
        if to_stdout:
            sys.stdout.write(result)
            continue
        if result != source:
            changed += 1
            if check:
                print(f"{path}: would be reformatted")
            else:
                tmp = path + ".fmt-tmp"       # write-then-replace: never leave a half-written file
                with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                    f.write(result)
                os.replace(tmp, path)
                print(f"formatted {path}")
    if not to_stdout:
        verb = "would be reformatted" if check else "reformatted"
        print(f"{len(files)} file(s) checked, {changed} {verb}" + (f", {failed} failed" if failed else ""))
    if failed or (check and changed):
        sys.exit(1)


def cmd_test(args):
    from .testrunner import run_tests
    verbose = "-v" in args or "--verbose" in args
    pattern = None
    rest = []
    it = iter(args)
    for a in it:
        if a == "-k":
            pattern = next(it, None)
            if not pattern:
                print("calyre test: -k needs a text to match against test names", file=sys.stderr)
                sys.exit(1)
        elif a in ("-v", "--verbose"):
            continue
        elif a.startswith("-"):
            print(f"calyre test: unknown option {a}", file=sys.stderr)
            sys.exit(1)
        else:
            rest.append(a)
    results, seconds = run_tests(rest or ["."], pattern)
    if not results:
        print("calyre test: no tests found (test files are named test_*.cly or *_test.cly, "
              "test functions test_*)", file=sys.stderr)
        sys.exit(1)
    for r in results:
        if r.status == "pass":
            if verbose:
                print(f"PASS {r.file}::{r.name}")
            continue
        print(f"FAIL {r.file}::{r.name}")
        where = getattr(r, "file_of_error", r.file)
        loc = f"{where}:{r.line}" if r.line else where
        print(f"     {loc}: {r.message}")
        if r.output.strip():
            print("     output:")
            for ln in r.output.rstrip().splitlines():
                print(f"       {ln}")
    failed = sum(1 for r in results if r.status == "fail")
    passed = len(results) - failed
    print(f"{passed} passed, {failed} failed in {seconds:.2f}s")
    if failed:
        sys.exit(1)


def cmd_lint(args):
    from .linter import lint_source, load_config, RULES
    from .calyre_parser import ParseError
    disabled, paths, it = set(), [], iter(args)
    for a in it:
        if a == "--rules":
            print("\n".join(RULES))
            return
        if a == "--disable":
            names = (next(it, "") or "").split(",")
            bad = [n for n in names if n and n not in RULES and n != "type-check"]
            if bad:
                print(f"calyre lint: unknown rule '{bad[0]}' (see `calyre lint --rules`)", file=sys.stderr)
                sys.exit(1)
            disabled.update(n for n in names if n)
        elif a.startswith("-"):
            print(f"calyre lint: unknown option {a}", file=sys.stderr)
            sys.exit(1)
        else:
            paths.append(a)
    files = _collect_cly(paths or ["."])
    if not files:
        print("calyre lint: no .cly files found", file=sys.stderr)
        sys.exit(1)
    findings = 0
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            print(f"{path}: cannot read ({e.strerror})", file=sys.stderr)
            findings += 1
            continue
        config = load_config(os.path.dirname(os.path.abspath(path))) | disabled
        try:
            errors, diags = lint_source(source, path, config)
        except (LexError, ParseError) as e:
            print(f"{path}: syntax error - {e}", file=sys.stderr)
            findings += 1
            continue
        for d in errors:
            print(d.format(path))
        for d in diags:
            print(d.format(path))
        findings += len(errors) + len(diags)
    if findings:
        print(f"{findings} problem(s) found in {len(files)} file(s)")
        sys.exit(1)
    print(f"{len(files)} file(s) checked, no problems found")


def cmd_repl():
    from .repl import run_repl
    run_repl()


def _parse_flag(rest, flag):
    if flag in rest:
        i = rest.index(flag)
        if i + 1 < len(rest):
            return rest[i + 1]
    return None


def main(argv=None):
    try:
        _main(argv)
    except KeyboardInterrupt:
        print("\ncalyre: interrupted", file=sys.stderr)
        sys.exit(130)
    except (SystemExit, BrokenPipeError):
        raise
    except Exception as e:  # a bug in Calyre itself, never in the user's program
        if os.environ.get("CALYRE_DEBUG"):
            raise
        print(f"calyre: internal error ({type(e).__name__}: {e})\n"
              f"        this is a bug in Calyre, not in your program. "
              f"Re-run with CALYRE_DEBUG=1 for the full traceback.", file=sys.stderr)
        sys.exit(70)


def _main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]

    if not argv:
        cmd_repl()
        return

    command, *rest = argv

    if command in ("help", "--help", "-h"):
        print(__doc__.strip())
        return
    if command == "run":
        if not rest:
            print("usage: calyre run <file.cly>", file=sys.stderr)
            sys.exit(1)
        cmd_run(rest[0], rest[1:])
    elif command == "check":
        if not rest:
            print("usage: calyre check <file.cly>", file=sys.stderr)
            sys.exit(1)
        cmd_check(rest[0])
    elif command == "lint":
        cmd_lint(rest)
    elif command == "test":
        cmd_test(rest)
    elif command == "fmt":
        cmd_fmt(rest)
    elif command == "init":
        cmd_init(rest[0] if rest else ".")
    elif command in ("repl", "start"):
        cmd_repl()
    elif command == "add":
        if not rest:
            print("usage: calyre add <name> --path <folder>", file=sys.stderr)
            sys.exit(1)
        cmd_add(rest[0], _parse_flag(rest, "--path"))
    elif command == "remove":
        if not rest:
            print("usage: calyre remove <name>", file=sys.stderr)
            sys.exit(1)
        cmd_remove(rest[0])
    elif command == "list":
        cmd_list()
    elif command in ("version", "--version", "-v"):
        cmd_version()
    else:
        print(f"calyre: unknown command '{command}' (see `calyre help`)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
