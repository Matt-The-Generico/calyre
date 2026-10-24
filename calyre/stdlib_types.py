"""
Static signatures of the Calyre standard library, used by the type checker.

Kept separate from stdlib.py (the implementations) so the checker never has
to import the runtime. `tests/test_stdlib_signatures.py` verifies that every
member listed here exists in the runtime module and vice versa, so the two
cannot silently drift apart.

`any` return types below are deliberate: they mark functions whose result type
depends on their argument types (math.abs, math.min, random.choice, ...) and
need generics; `abs/min/max` and `random.choice` / `text.join` now use type variables.
The only `any` left are the dynamic boundaries: `python.call` and `json.parse` / `json.stringify`.
"""

from .types import ANY, NONE_T, NUMBER

N = ("tvar", "N", NUMBER)       # a number: int or float, the same kind in and out
T = ("tvar", "T")


def G(tvars, params, ret):
    return ("gfunc", tuple(tvars), list(params), ret)


def F(params, ret, variadic=False):
    return ("func", list(params), ret, True) if variadic else ("func", list(params), ret)


STDLIB_SIGNATURES = {
    "math": {
        "sqrt": F([NUMBER], "float"),
        "floor": F([NUMBER], "int"),
        "ceil": F([NUMBER], "int"),
        "round": F([NUMBER], "int"),
        "abs": G([N], [N], N),
        "pow": F([NUMBER, NUMBER], "float"),
        "min": G([N], [N, N], N),
        "max": G([N], [N, N], N),
        "floor_div": F(["int", "int"], "int"),
        "pi": "float",
        "e": "float",
    },
    "random": {
        "int": F(["int", "int"], "int"),
        "float": F([NUMBER, NUMBER], "float"),
        "choice": G([T], [("list", T)], T),
    },
    "time": {
        "now": F([], "float"),
        "sleep": F([NUMBER], NONE_T),
    },
    "text": {
        "upper": F(["str"], "str"),
        "lower": F(["str"], "str"),
        "trim": F(["str"], "str"),
        "split": F(["str", "str"], ("list", "str")),
        "join": G([T], [("list", T), "str"], "str"),
        "replace": F(["str", "str", "str"], "str"),
        "contains": F(["str", "str"], "bool"),
        "starts_with": F(["str", "str"], "bool"),
        "ends_with": F(["str", "str"], "bool"),
        "repeat": F(["str", "int"], "str"),
    },
    "fs": {
        "read": F(["str"], "str"),
        "write": F(["str", "str"], NONE_T),
        "append": F(["str", "str"], NONE_T),
        "exists": F(["str"], "bool"),
        "is_file": F(["str"], "bool"),
        "is_dir": F(["str"], "bool"),
        "list_dir": F(["str"], ("list", "str")),
        "make_dir": F(["str"], NONE_T),
        "remove": F(["str"], NONE_T),
        "remove_dir": F(["str"], NONE_T),
        "size": F(["str"], "int"),
        "rename": F(["str", "str"], NONE_T),
    },
    "path": {
        "join": F(["str", "str"], "str"),
        "join_all": F([("list", "str")], "str"),
        "basename": F(["str"], "str"),
        "dirname": F(["str"], "str"),
        "stem": F(["str"], "str"),
        "extension": F(["str"], "str"),
        "with_extension": F(["str", "str"], "str"),
        "normalize": F(["str"], "str"),
        "parts": F(["str"], ("list", "str")),
        "is_absolute": F(["str"], "bool"),
        "relative_to": F(["str", "str"], "str"),
        "absolute": F(["str"], "str"),
    },
    "json": {
        "parse": F(["str"], ANY),          # JSON is dynamic data: a dynamic boundary on purpose
        "stringify": F([ANY], "str"),
        "pretty": F([ANY], "str"),
    },
    "sql": {
        "open": F(["str"], ("struct", "sql.Database")),
        "engines": F([], ("list", "str")),
        "Database": ("structdef", "sql.Database"),
    },
    "system": {
        "args": F([], ("list", "str")),
        "env": F(["str"], ("optional", "str")),
        "platform": F([], "str"),
        "cwd": F([], "str"),
        "exit": F(["int"], NONE_T),
    },
    "python": {
        "call": F(["str", "str"], ANY, variadic=True),
    },
}

# Builtin functions: name -> (min_args, max_args or None, param types or None, return type)
BUILTIN_SPECS = {
    "print": (0, None, None, NONE_T),
    "str": (1, 1, [ANY], "str"),
    "int": (1, 1, [ANY], "int"),
    "float": (1, 1, [ANY], "float"),
    "len": (1, 1, [ANY], "int"),
    "range": (1, 3, ["int", "int", "int"], ("list", "int")),
    "input": (0, 1, ["str"], "str"),
    "input_int": (0, 1, ["str"], "int"),
    "input_float": (0, 1, ["str"], "float"),
    "input_bool": (0, 1, ["str"], "bool"),
    "error": (1, 1, [ANY], NONE_T),
}
