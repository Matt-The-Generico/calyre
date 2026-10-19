"""
Static signatures of the Calyre standard library, used by the type checker.

Kept separate from stdlib.py (the implementations) so the checker never has
to import the runtime. `tests/test_stdlib_signatures.py` verifies that every
member listed here exists in the runtime module and vice versa, so the two
cannot silently drift apart.

`any` return types below are deliberate: they mark functions whose result type
depends on their argument types (math.abs, math.min, random.choice, ...) and
need generics, which are planned (see docs/ROADMAP.md, phase 3).
"""

from .types import ANY, NONE_T, NUMBER


def F(params, ret, variadic=False):
    return ("func", list(params), ret, True) if variadic else ("func", list(params), ret)


STDLIB_SIGNATURES = {
    "math": {
        "sqrt": F([NUMBER], "float"),
        "floor": F([NUMBER], "int"),
        "ceil": F([NUMBER], "int"),
        "round": F([NUMBER], "int"),
        "abs": F([NUMBER], ANY),
        "pow": F([NUMBER, NUMBER], ANY),
        "min": F([NUMBER, NUMBER], ANY),
        "max": F([NUMBER, NUMBER], ANY),
        "floor_div": F(["int", "int"], "int"),
        "pi": "float",
        "e": "float",
    },
    "random": {
        "int": F(["int", "int"], "int"),
        "float": F([NUMBER, NUMBER], "float"),
        "choice": F([("list", ANY)], ANY),
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
        "join": F([("list", ANY), "str"], "str"),
        "replace": F(["str", "str", "str"], "str"),
        "contains": F(["str", "str"], "bool"),
        "starts_with": F(["str", "str"], "bool"),
        "ends_with": F(["str", "str"], "bool"),
        "repeat": F(["str", "int"], "str"),
    },
    "fs": {
        "read": F(["str"], "str"),
        "write": F(["str", "str"], NONE_T),
        "exists": F(["str"], "bool"),
        "list_dir": F(["str"], ("list", "str")),
        "make_dir": F(["str"], NONE_T),
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
