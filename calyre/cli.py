"""
Calyre CLI: the single official tool.

    calyre                       starts the interactive REPL
    calyre repl                  same as above, explicit
    calyre run <file.cly>        type-checks and runs a program
    calyre check <file.cly>      type-checks a program without running it
    calyre init [dir]            scaffolds a minimal new project
    calyre add <name> --path P   declares a local dependency in calyre.toml
    calyre remove <name>         removes a dependency from calyre.toml
    calyre list                  lists the project's declared dependencies
    calyre version               prints the interpreter version

Not implemented in this phase:
    calyre fmt                   official formatter, deferred
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


def cmd_run(path):
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

    if command == "run":
        if not rest:
            print("usage: calyre run <file.cly>", file=sys.stderr)
            sys.exit(1)
        cmd_run(rest[0])
    elif command == "check":
        if not rest:
            print("usage: calyre check <file.cly>", file=sys.stderr)
            sys.exit(1)
        cmd_check(rest[0])
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
        print(f"calyre: unknown command '{command}'", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
