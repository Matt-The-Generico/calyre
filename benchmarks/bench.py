"""Reproducible micro-benchmarks for the reference interpreter.

    python3 benchmarks/bench.py

For each program it reports, as best-of-3 wall time in milliseconds, the three phases separately:
  parse    = tokenizing + parsing
  analyze  = name resolution and type checking
  run      = executing the program (output discarded)
Numbers depend on the machine; compare runs on the same machine only.
"""
import contextlib
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calyre.lexer import tokenize
from calyre.calyre_parser import parse
from calyre import typechecker
from calyre.interpreter import interpret

PROGRAMS = {
    "fib(22), recursion": 'func fib(n: int) -> int\n    if n < 2\n        return n\n    end\n    return fib(n - 1) + fib(n - 2)\nend\nprint(fib(22))',
    "loop, 200k additions": 'let t = 0\nlet i = 0\nwhile i < 200000\n    t = t + i\n    i = i + 1\nend\nprint(t)',
    "map, 20k writes + reads": 'let m: map<int, int> = {}\nfor i in range(20000)\n    m[i] = i * 2\nend\nlet s = 0\nfor k in m\n    s = s + m[k]\nend\nprint(s)',
    "list methods, 20k appends + sort": 'let xs: list<int> = []\nfor i in range(20000)\n    xs.append((i * 7919) % 10007)\nend\nxs.sort()\nprint(xs[0], xs[-1], len(xs))',
    "strings, 5k splits/joins": 'use text\nlet n = 0\nfor i in range(5000)\n    let parts = "a,b,c,{i}".split(",")\n    n = n + len(text.join(parts, "-").upper())\nend\nprint(n)',
    "generics, 20k calls": 'func pick<T>(a: T, b: T) -> T\n    return a\nend\nlet n = 0\nfor i in range(20000)\n    n = n + pick(i, 1)\nend\nprint(n)',
    "json round trip, 2k docs": 'use json\nlet n = 0\nfor i in range(2000)\n    let d = json.parse("""{"id": 1, "tags": ["a", "b"], "ok": true}""")\n    n = n + len(json.stringify(d))\nend\nprint(n)',
    "sqlite, 2k inserts + query": 'use sql\nlet db = sql.open("sqlite::memory:")\ndb.execute("CREATE TABLE t (v INTEGER)")\ndb.begin()\nfor i in range(2000)\n    db.execute("INSERT INTO t VALUES (?)", [i])\nend\ndb.commit()\nprint(len(db.query("SELECT v FROM t WHERE v % 2 = 0")))',
}


def phases(src):
    t0 = time.perf_counter()
    program = parse(tokenize(src))
    t1 = time.perf_counter()
    errors, _ = typechecker.analyze(program)
    assert not errors, errors
    t2 = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        interpret(program)
    t3 = time.perf_counter()
    return (t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000


print(f"{'program':34s} {'parse':>8s} {'analyze':>9s} {'run':>9s}   (ms, best of 3)")
for name, src in PROGRAMS.items():
    runs = [phases(src) for _ in range(3)]
    best = [min(r[i] for r in runs) for i in range(3)]
    print(f"{name:34s} {best[0]:8.2f} {best[1]:9.2f} {best[2]:9.1f}")
