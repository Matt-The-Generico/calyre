"""
Calyre CLI — the single official tool.

    calyre                       starts the interactive REPL
    calyre repl                  same as above, explicit
    calyre run <file.cly>        type-checks and runs a program
    calyre check <file.cly>      type-checks a program without running it
    calyre init [dir]            scaffolds a minimal new project
    calyre add <name> --path P   declares a local dependency in calyre.toml
    calyre remove <name>         removes a dependency from calyre.toml
    calyre list                  lists the project's declared dependencies
    calyre version               prints the interpreter version

Not implemented in this phase (see the Phase 3 design notes for why):
    calyre fmt                   official formatter — deferred
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
        print(f"Aviso: arquivos Calyre normalmente usam a extensão .cly ({path})", file=sys.stderr)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"calyre: arquivo não encontrado: {path}", file=sys.stderr)
        sys.exit(1)


def cmd_run(path):
    source = _read_source(path)
    try:
        tokens = tokenize(source)
        program = parse(tokens)
    except LexError as e:
        print(f"calyre: {e}", file=sys.stderr)
        sys.exit(1)
    except ParseError as e:
        print(f"calyre: erro de sintaxe — {e}", file=sys.stderr)
        sys.exit(1)

    errors = typechecker.check(program)
    if errors:
        for err in errors:
            print(f"calyre: {path}: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        interpret(program, base_dir=os.path.dirname(os.path.abspath(path)))
    except CalyreRuntimeError as e:
        print(f"calyre: {e}", file=sys.stderr)
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
        print(f"calyre: erro de sintaxe — {e}", file=sys.stderr)
        sys.exit(1)

    errors = typechecker.check(program)
    if errors:
        for err in errors:
            print(f"calyre: {path}: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"{path}: nenhum erro de sintaxe ou de tipo encontrado")


def cmd_version():
    print(f"calyre {__version__} (implementação de referência — interpretador)")


_PROJECT_MAIN = '''// main.cly — o ponto de entrada do seu projeto Calyre.

func main()
    print("Olá, mundo!")
end

main()
'''

_PROJECT_MANIFEST = '''# calyre.toml — manifesto do projeto.
# Formato deliberadamente pequeno: nome, versão, e dependências locais.
# Dependências remotas ainda não são suportadas nesta fase.

[project]
name = "{name}"
version = "0.1.0"

[dependencies]
# exemplo (descomente e ajuste):
# some_lib = {{ path = "../some_lib" }}
'''


def cmd_init(target_dir):
    target_dir = target_dir or "."
    os.makedirs(target_dir, exist_ok=True)
    main_path = os.path.join(target_dir, "main.cly")
    manifest_path = os.path.join(target_dir, "calyre.toml")

    if os.path.exists(main_path) or os.path.exists(manifest_path):
        print(f"calyre: '{target_dir}' já contém um projeto Calyre (main.cly ou calyre.toml existe)", file=sys.stderr)
        sys.exit(1)

    project_name = os.path.basename(os.path.abspath(target_dir))
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(_PROJECT_MAIN)
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(_PROJECT_MANIFEST.format(name=project_name))

    print(f"Projeto Calyre criado em '{target_dir}':")
    print("  main.cly       — seu programa")
    print("  calyre.toml    — manifesto do projeto")
    print()
    print(f"Para rodar:  calyre run {os.path.join(target_dir, 'main.cly')}")


def _load_manifest(path="calyre.toml"):
    import tomllib
    if not os.path.exists(path):
        print(f"calyre: nenhum '{path}' encontrado neste diretório. Rode 'calyre init' primeiro.", file=sys.stderr)
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
        "# calyre.toml — manifesto do projeto.",
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
            "calyre: 'calyre add' nesta fase só suporta dependências locais.\n"
            "        use: calyre add <nome> --path <caminho para a pasta da biblioteca>\n"
            "        (não existe ainda um registro remoto de pacotes — ver Fase 3, seção 5)",
            file=sys.stderr,
        )
        sys.exit(1)
    manifest = _load_manifest()
    deps = manifest.get("dependencies", {})
    deps[name] = {"path": path_flag}
    _write_manifest_deps(deps)
    print(f"'{name}' adicionado como dependência local ({path_flag})")


def cmd_remove(name):
    manifest = _load_manifest()
    deps = manifest.get("dependencies", {})
    if name not in deps:
        print(f"calyre: '{name}' não está entre as dependências deste projeto", file=sys.stderr)
        sys.exit(1)
    del deps[name]
    _write_manifest_deps(deps)
    print(f"'{name}' removido")


def cmd_list():
    manifest = _load_manifest()
    deps = manifest.get("dependencies", {})
    if not deps:
        print("(nenhuma dependência declarada)")
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
    argv = argv if argv is not None else sys.argv[1:]

    if not argv:
        cmd_repl()
        return

    command, *rest = argv

    if command == "run":
        if not rest:
            print("uso: calyre run <arquivo.cly>", file=sys.stderr)
            sys.exit(1)
        cmd_run(rest[0])
    elif command == "check":
        if not rest:
            print("uso: calyre check <arquivo.cly>", file=sys.stderr)
            sys.exit(1)
        cmd_check(rest[0])
    elif command == "init":
        cmd_init(rest[0] if rest else ".")
    elif command in ("repl", "start"):
        cmd_repl()
    elif command == "add":
        if not rest:
            print("uso: calyre add <nome> --path <caminho>", file=sys.stderr)
            sys.exit(1)
        cmd_add(rest[0], _parse_flag(rest, "--path"))
    elif command == "remove":
        if not rest:
            print("uso: calyre remove <nome>", file=sys.stderr)
            sys.exit(1)
        cmd_remove(rest[0])
    elif command == "list":
        cmd_list()
    elif command in ("version", "--version", "-v"):
        cmd_version()
    else:
        print(f"calyre: comando desconhecido '{command}'", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
