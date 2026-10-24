"""
`calyre test`: discover and run tests written in Calyre.

Convention (deliberately tiny):
* A test file is named `test_*.cly` or `*_test.cly`.
* A test is a top-level function named `test_*` that takes no parameters.
* A test passes when it finishes; it fails when it raises a runtime error, which is what
  `assert` and `error(...)` do. Output printed by a test is shown only if the test fails.
* The file's top-level statements run once, before its tests; tests run in definition order.
"""

import contextlib
import io
import os
import time

from . import ast_nodes as A
from . import typechecker
from .calyre_parser import parse, ParseError
from .interpreter import Interpreter, CalyreFunction, CalyreRuntimeError
from .lexer import tokenize, LexError

SKIP_DIRS = (".git", "dist", "build", "__pycache__", "node_modules")


def is_test_file(name):
    return name.endswith(".cly") and (name.startswith("test_") or name.endswith("_test.cly"))


def discover(paths):
    """Test files under `paths` (files are taken as given; folders are searched)."""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                files += [os.path.join(root, n) for n in sorted(names) if is_test_file(n)]
        else:
            files.append(p)
    return files


class Result:
    def __init__(self, file, name, status, message="", line=None, output=""):
        self.file, self.name, self.status = file, name, status     # status: pass | fail
        self.message, self.line, self.output = message, line, output


def run_file(path, pattern=None):
    """Run every test of one file; returns a list of Result (a broken file is one failure)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        return [Result(path, "<file>", "fail", f"cannot read the file ({e.strerror})")]
    try:
        program = parse(tokenize(source))
    except (LexError, ParseError) as e:
        return [Result(path, "<file>", "fail", f"syntax error: {e}", getattr(e, "line", None))]
    errors, _ = typechecker.analyze(program, base_dir=os.path.dirname(os.path.abspath(path)))
    if errors:
        d = errors[0]
        more = f" (and {len(errors) - 1} more error(s))" if len(errors) > 1 else ""
        return [Result(path, "<file>", "fail", f"does not compile: {d.message}{more}", d.line)]

    tests = [s for s in program.statements if isinstance(s, A.FuncDecl) and s.name.startswith("test_")]
    if pattern:
        tests = [t for t in tests if pattern in t.name]
    results = []
    interp = Interpreter(base_dir=os.path.dirname(os.path.abspath(path)), file=path)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            interp.run(program)
    except CalyreRuntimeError as e:
        return [Result(path, "<file>", "fail", f"error while loading the file: {e.message}", e.line, out.getvalue())]
    except SystemExit as e:
        return [Result(path, "<file>", "fail", f"the file called system.exit({e.code}) while loading", None, out.getvalue())]
    for t in tests:
        if t.params:
            results.append(Result(path, t.name, "fail", "a test function must not take parameters", t.line))
            continue
        fn = interp.globals.get(t.name)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                fn.call(interp, [], t.line)
            results.append(Result(path, t.name, "pass"))
        except SystemExit as e:
            results.append(Result(path, t.name, "fail",
                                  f"the test called system.exit({e.code}), which would end the whole run",
                                  t.line, out.getvalue()))
        except CalyreRuntimeError as e:
            where = e.file or path
            results.append(Result(path, t.name, "fail", e.message, e.line, out.getvalue()))
            results[-1].file_of_error = where
    return results


def run_tests(paths, pattern=None):
    started = time.perf_counter()
    results = []
    for f in discover(paths):
        results += run_file(f, pattern)
    return results, time.perf_counter() - started
