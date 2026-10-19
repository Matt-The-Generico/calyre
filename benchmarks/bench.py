"""Reproducible micro-benchmarks for the reference interpreter.
Run:  python3 benchmarks/bench.py
Reports best-of-3 wall time per program (type check + run, no I/O)."""
import contextlib, io, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calyre.lexer import tokenize
from calyre.calyre_parser import parse
from calyre import typechecker
from calyre.interpreter import interpret

PROGRAMS = {
    "fib(22) recursion": 'func fib(n: int) -> int\n    if n < 2\n        return n\n    end\n    return fib(n - 1) + fib(n - 2)\nend\nprint(fib(22))',
    "loop 200k additions": 'let t = 0\nlet i = 0\nwhile i < 200000\n    t = t + i\n    i = i + 1\nend\nprint(t)',
    "list/map 20k ops": 'let m: map<int, int> = {}\nfor i in range(20000)\n    m[i] = i * 2\nend\nlet s = 0\nfor k in m\n    s = s + m[k]\nend\nprint(s)',
}

def once(src):
    program = parse(tokenize(src))
    errs, _ = typechecker.analyze(program)
    assert not errs, errs
    with contextlib.redirect_stdout(io.StringIO()):
        t = time.perf_counter(); interpret(program); return time.perf_counter() - t

for name, src in PROGRAMS.items():
    best = min(once(src) for _ in range(3))
    print(f"{name:24s} {best*1000:9.1f} ms")
