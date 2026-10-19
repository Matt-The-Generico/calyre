"""
Calyre interactive REPL.

Uses the exact same lexer, parser, type checker and interpreter as a
normal .cly file.
"""

import os
import sys

from . import __version__
from .lexer import tokenize, LexError
from .calyre_parser import parse, ParseError
from . import ast_nodes as A
from . import typechecker
from .interpreter import Interpreter, Environment, CalyreRuntimeError, calyre_repr

_BLOCK_OPENERS = {"FUNC", "IF", "WHILE", "FOR", "MATCH", "STRUCT", "TRY"}

_HELP_TEXT = """\
REPL commands:
  help       show this help
  exit       leave the REPL
  clear      clear the screen
  history    show what you typed in this session

Type any Calyre code. If a block is not closed yet (for example a
'func' without its 'end'), the REPL shows '...' and waits for the rest.

Example:
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
        # Windows). the REPL still works, just without arrow-key history.
        return False


class Repl:
    def __init__(self):
        self.interp = Interpreter(base_dir=os.getcwd())
        # one persistent checker: the REPL is "one growing .cly file"
        self.checker = typechecker.Checker(base_dir=os.getcwd(), repl=True)
        self.history = []

    def run(self):
        has_readline = _try_enable_history()
        print(f"Calyre {__version__}")
        print('Type "help" for help or "exit" to quit.')
        if not has_readline:
            print("(arrow-key history is unavailable on this platform - 'history' still works)")
        print()

        while True:
            try:
                block = self._read_block()
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print("\n(Ctrl+C - type 'exit' to quit)")
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
                # might just be an unfinished string/interpolation
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
            print(f"Error: {e}")
            return
        except ParseError as e:
            print(f"Syntax error: {e}")
            return

        # Check atomically: if this input has errors nothing it declared is kept,
        # so the checker and the runtime never disagree about what exists.
        saved = (dict(self.checker.module_scope.vars), dict(self.checker.registry),
                 dict(self.checker.types))
        diags = self.checker.check_program(program)
        errors = [d for d in diags if d.severity == "error"]
        for d in diags:
            if d.severity == "warning":
                print(f"Warning: {d.message}")
        if errors:
            for d in errors:
                print(f"Error: {d.message}" + (f"\n  hint: {d.hint}" if d.hint else ""))
            (self.checker.module_scope.vars, self.checker.registry, self.checker.types) = (
                saved[0], saved[1], saved[2])
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
                print(f"Error: {e.message}")
                return


def run_repl():
    Repl().run()
