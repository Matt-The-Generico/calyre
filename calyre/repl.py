"""
Calyre interactive REPL.

Uses the exact same lexer, parser, type checker and interpreter as a
normal .cly file — there is no separate "mini Calyre" here. State (
variables, functions, structs, imported modules) persists for the whole
session, the same way it would inside one growing .cly file.
"""

import os
import sys

from . import __version__
from .lexer import tokenize, LexError
from .calyre_parser import parse, ParseError
from . import ast_nodes as A
from . import typechecker
from .typechecker import TypeEnv
from .types import ANY, type_name
from .interpreter import Interpreter, Environment, CalyreRuntimeError, calyre_repr

_BLOCK_OPENERS = {"FUNC", "IF", "WHILE", "FOR", "MATCH", "STRUCT", "TRY"}

_HELP_TEXT = """\
Comandos do REPL:
  help       mostra esta ajuda
  exit       sai do REPL
  clear      limpa a tela
  history    mostra os comandos digitados nesta sessão

Digite qualquer código Calyre normalmente. Se um bloco não estiver
fechado (por exemplo, 'func' sem 'end'), o REPL mostra '...' e continua
esperando o resto do bloco.

Exemplo:
  > let name = "Alice"
  > print("Hello, " + name)
  Hello, Alice
"""


def _is_incomplete(tokens):
    depth = 0
    brackets = 0
    for tok in tokens:
        if tok.type in _BLOCK_OPENERS:
            depth += 1
        elif tok.type == "END":
            depth -= 1
        elif tok.type in ("LPAREN", "LBRACKET", "LBRACE"):
            brackets += 1
        elif tok.type in ("RPAREN", "RBRACKET", "RBRACE"):
            brackets -= 1
    return depth > 0 or brackets > 0


def _try_enable_history():
    try:
        import readline  # noqa: F401
        return True
    except ImportError:
        # readline isn't available on some platforms (notably parts of
        # Windows) — the REPL still works, just without arrow-key history.
        return False


class Repl:
    def __init__(self):
        self.interp = Interpreter(base_dir=os.getcwd())
        self.type_env = TypeEnv()
        self.checker = typechecker.Checker()
        for name in typechecker._BUILTIN_RETURN_TYPES:
            self.type_env.define(name, ANY)
        self.history = []

    def run(self):
        has_readline = _try_enable_history()
        print(f"Calyre {__version__}")
        print('Digite "help" para ajuda ou "exit" para sair.')
        if not has_readline:
            print("(histórico com setas indisponível nesta plataforma — 'history' ainda funciona)")
        print()

        while True:
            try:
                block = self._read_block()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print("\n(Ctrl+C — digite 'exit' para sair)")
                continue

            if block is None:
                continue
            if block.strip() == "":
                continue

            stripped = block.strip().lower()
            if stripped == "exit":
                break
            if stripped == "help":
                print(_HELP_TEXT)
                continue
            if stripped == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                continue
            if stripped == "history":
                for i, entry in enumerate(self.history, 1):
                    print(f"{i}: {entry}")
                continue

            self.history.append(block)
            self._eval_block(block)

    def _read_block(self):
        line = input("> ")
        buf = [line]
        while True:
            try:
                tokens = tokenize("\n".join(buf))
            except LexError:
                # might just be an unfinished string/interpolation — keep reading
                tokens = None
            if tokens is not None and not _is_incomplete(tokens):
                break
            try:
                nxt = input("... ")
            except EOFError:
                break
            buf.append(nxt)
        return "\n".join(buf)

    def _eval_block(self, source):
        try:
            tokens = tokenize(source)
            program = parse(tokens)
        except LexError as e:
            print(f"Erro: {e}")
            return
        except ParseError as e:
            print(f"Erro de sintaxe: {e}")
            return

        # Register any struct/func signatures from this input so later
        # inputs (and this one) can see them, mirroring Checker.check_program's
        # two-pass approach but incrementally across REPL turns.
        for stmt in program.statements:
            if isinstance(stmt, A.StructDecl):
                self.checker._register_struct(stmt)
        self.checker._resolve_struct_fields()
        for stmt in program.statements:
            if isinstance(stmt, A.FuncDecl):
                self.checker._register_func_sig(stmt, self.type_env)

        had_type_error = False
        for stmt in program.statements:
            before = len(self.checker.errors)
            self.checker.check_stmt(stmt, self.type_env)
            if len(self.checker.errors) > before:
                had_type_error = True
        if had_type_error:
            for err in self.checker.errors[-len(program.statements):]:
                print(f"Erro de tipo: {err.message}")
            # don't execute this input, but keep prior state intact
            return

        for stmt in program.statements:
            try:
                if isinstance(stmt, A.ExprStmt):
                    value = self.interp.eval(stmt.expr, self.interp.globals)
                    if value is not None:
                        print(calyre_repr(value))
                else:
                    self.interp.exec_stmt(stmt, self.interp.globals)
            except CalyreRuntimeError as e:
                print(f"Erro: {e.message}")
                return


def run_repl():
    Repl().run()
