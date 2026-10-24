"""Documentation is tested: examples must work, references must be complete.

Fence conventions in the .md files:
  ```calyre          parsed and type-checked: must have no errors
  ```calyre run      executed; if the next block is ```output it must match the printed text exactly
  ```calyre error    must be rejected; the next ```output block holds the diagnostics (formatted as main.cly)
  ```text            not checked (illustrations, shell sessions, grammar)
"""
import contextlib
import glob
import io
import os
import re
import unittest

from calyre import typechecker
from calyre.calyre_parser import parse
from calyre.interpreter import interpret
from calyre.lexer import tokenize
from calyre.linter import RULES
from calyre.methods import METHODS
from calyre.sqlmod import NATIVE_METHODS
from calyre.stdlib_types import STDLIB_SIGNATURES, BUILTIN_SPECS
from tests.helpers import ROOT

FENCE = re.compile(r"^```(.*)$")


def doc_files():
    files = [os.path.join(ROOT, "README.md")] + sorted(glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True))
    return [f for f in files if os.path.exists(f)]


def blocks(path):
    """[(info, text, start_line)] for every fenced block of a markdown file."""
    out, cur, info, start = [], None, None, 0
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for n, line in enumerate(lines, 1):
        m = FENCE.match(line)
        if m and cur is None:
            info, cur, start = m.group(1).strip(), [], n
        elif line.startswith("```") and cur is not None:
            out.append((info, "\n".join(cur) + "\n", start))
            cur = None
        elif cur is not None:
            cur.append(line)
    return out


def rel(path):
    return os.path.relpath(path, ROOT)


class TestDocExamples(unittest.TestCase):
    def test_there_are_examples_to_check(self):
        total = sum(1 for f in doc_files() for i, _, _ in blocks(f) if i.split()[:1] == ["calyre"])
        self.assertGreaterEqual(total, 30)

    def test_every_calyre_block_behaves_as_documented(self):
        for path in doc_files():
            bl = blocks(path)
            for k, (info, text, line) in enumerate(bl):
                words = info.split()
                if not words or words[0] != "calyre":
                    continue
                mode = words[1] if len(words) > 1 else "check"
                where = f"{rel(path)}:{line}"
                nxt = bl[k + 1] if k + 1 < len(bl) and bl[k + 1][0] == "output" else None
                program = parse(tokenize(text))
                errs, _ = typechecker.analyze(program)
                if mode == "error":
                    self.assertTrue(errs, f"{where}: documented as an error but it compiles")
                    if nxt:
                        got = "\n".join(d.format("main.cly") for d in errs) + "\n"
                        self.assertEqual(got, nxt[1], f"{where}: diagnostics differ")
                    continue
                self.assertEqual([str(d) for d in errs], [], f"{where}: example does not compile")
                if mode == "run":
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        interpret(program)
                    if nxt:
                        self.assertEqual(buf.getvalue(), nxt[1], f"{where}: output differs")


class TestReferencesAreComplete(unittest.TestCase):
    def doc(self, name):
        with open(os.path.join(ROOT, "docs", name), encoding="utf-8") as f:
            return f.read()

    def test_every_stdlib_member_is_documented(self):
        text = self.doc("STDLIB.md")
        for module, members in STDLIB_SIGNATURES.items():
            for member in members:
                self.assertIn(f"{module}.{member}", text, f"STDLIB.md does not document {module}.{member}")

    def test_every_builtin_is_documented(self):
        text = self.doc("STDLIB.md")
        for name in BUILTIN_SPECS:
            self.assertIn(f"`{name}(", text, f"STDLIB.md does not document the builtin {name}")

    def test_every_method_is_documented(self):
        text = self.doc("STDLIB.md")
        for kind, table in list(METHODS.items()) + list(NATIVE_METHODS.items()):
            for name in table:
                self.assertIn(f".{name}(", text, f"STDLIB.md does not document {kind}.{name}")

    def test_every_lint_rule_is_documented(self):
        text = self.doc("TOOLS.md")
        for rule in RULES:
            self.assertIn(f"`{rule}`", text, f"TOOLS.md does not document the lint rule {rule}")

    def test_every_cli_command_is_documented(self):
        text = self.doc("TOOLS.md")
        for command in ("run", "check", "fmt", "test", "lint", "init", "add", "remove", "list", "version", "help"):
            self.assertIn(f"calyre {command}", text, command)


if __name__ == "__main__":
    unittest.main()
