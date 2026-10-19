"""Shared helpers for the test suite."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile

from calyre.lexer import tokenize
from calyre.calyre_parser import parse
from calyre import typechecker
from calyre.interpreter import interpret

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def analyze(src, base_dir=None):
    return typechecker.analyze(parse(tokenize(src)), base_dir=base_dir)


def errors(src, base_dir=None):
    return [d.message for d in analyze(src, base_dir)[0]]


def warnings(src, base_dir=None):
    return [d.message for d in analyze(src, base_dir)[1]]


def run(src, base_dir=None, check=True):
    """Parse, (optionally) type-check, run; return captured stdout."""
    program = parse(tokenize(src))
    if check:
        errs, _ = typechecker.analyze(program, base_dir=base_dir)
        assert not errs, [d.message for d in errs]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        interpret(program, base_dir=base_dir)
    return buf.getvalue()


def cli(*args, cwd=None, stdin=None):
    """Run the real CLI in a subprocess; return (exit_code, stdout, stderr)."""
    p = subprocess.run([sys.executable, os.path.join(ROOT, "calyre_entry.py"), *args],
                       capture_output=True, text=True, cwd=cwd, input=stdin, timeout=60)
    return p.returncode, p.stdout, p.stderr


@contextlib.contextmanager
def project(files):
    """A temporary directory populated with {filename: content}."""
    with tempfile.TemporaryDirectory() as d:
        for name, content in files.items():
            path = os.path.join(d, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        yield d
