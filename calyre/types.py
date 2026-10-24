"""
Static types for the Calyre type checker.

A type is either a plain string or a tuple:

    "int" "float" "str" "bool" "none"          primitives
    "any"                                       INTENTIONALLY dynamic: the author
                                                asked for it (`any`) or the value
                                                comes from a dynamic boundary
                                                (python.call). Compatible with all.
    "unknown"                                   NOT RESOLVED: a type the checker
                                                could not determine. It only appears
                                                after a diagnostic was already
                                                reported (error recovery) or while a
                                                return type is still being inferred.
                                                It suppresses follow-up errors so a
                                                single mistake yields a single message.
    ("list", T)   ("map", K, V)   ("optional", T)
    ("struct", key)  or  ("struct", key, (T1, ...))
                                                instance of a struct (with type arguments
                                                when the struct is generic: Box<int>)
    ("tvar", name)  or  ("tvar", name, bound)   a type parameter (inside a generic function
                                                or struct); opaque: only compatible with
                                                itself. `bound` restricts what it may be
                                                bound to (used by the stdlib: number)
    ("gfunc", (tvars...), [params], ret)        a generic function; instantiated at each call
    ("structdef", key)                          the struct itself (its constructor)
    ("func", [params], ret)  or  ("func", [params], ret, True)   # True = extra args allowed
    ("builtin", name)                           a builtin function (see BUILTIN_SPECS)
    ("module", name, {member: type})            an imported module namespace
    ("union", (T1, T2, ...))                    only used inside stdlib signatures
                                                (e.g. number = int | float); there is
                                                no user syntax for unions yet.
"""

ANY = "any"
UNKNOWN = "unknown"
NONE_T = "none"
NUMBER = ("union", ("int", "float"))


def is_optional(t):
    return isinstance(t, tuple) and t[0] == "optional"


def is_numeric(t):
    return t in ("int", "float")


def is_permissive(t):
    return t == ANY or t == UNKNOWN


def contains_unknown(t):
    if t == UNKNOWN:
        return True
    if isinstance(t, tuple):
        if t[0] in ("list", "optional"):
            return contains_unknown(t[1])
        if t[0] == "map":
            return contains_unknown(t[1]) or contains_unknown(t[2])
    return False


def type_name(t):
    if isinstance(t, str):
        return t
    kind = t[0]
    if kind == "list":
        return f"list<{type_name(t[1])}>"
    if kind == "map":
        return f"map<{type_name(t[1])}, {type_name(t[2])}>"
    if kind == "optional":
        return f"{type_name(t[1])}?"
    if kind == "struct":
        base = t[1].lstrip("$")      # "$Error" is the reserved key of the builtin Error struct
        if len(t) > 2 and t[2]:
            return f"{base}<{', '.join(type_name(a) for a in t[2])}>"
        return base
    if kind == "tvar":
        return t[1]
    if kind == "gfunc":
        names = ", ".join(v[1] for v in t[1])
        return f"func<{names}>({', '.join(type_name(p) for p in t[2])}) -> {type_name(t[3])}"
    if kind == "structdef":
        return f"struct {t[1]}"
    if kind == "func":
        return f"func({', '.join(type_name(p) for p in t[1])}) -> {type_name(t[2])}"
    if kind == "builtin":
        return f"builtin {t[1]}"
    if kind == "module":
        return f"module {t[1]}"
    if kind == "union":
        return " | ".join(type_name(m) for m in t[1])
    return str(t)


def compatible(expected, actual):
    """True if a value of type `actual` may be used where `expected` is required."""
    if is_permissive(expected) or is_permissive(actual):
        return True
    if isinstance(actual, tuple) and actual[0] == "union":
        return all(compatible(expected, m) for m in actual[1])
    if isinstance(expected, tuple) and expected[0] == "union":
        return any(compatible(m, actual) for m in expected[1])
    if is_optional(expected):
        if actual == NONE_T:
            return True
        if is_optional(actual):
            return compatible(expected[1], actual[1])
        return compatible(expected[1], actual)
    if actual == NONE_T:
        return False
    if is_optional(actual):
        return False          # an optional value is NOT usable where a plain one is required
    if isinstance(expected, tuple) and expected[0] == "tvar":
        return isinstance(actual, tuple) and actual[0] == "tvar" and actual[1] == expected[1]
    if isinstance(actual, tuple) and actual[0] == "tvar":
        return False
    if isinstance(expected, tuple) and isinstance(actual, tuple):
        if expected[0] != actual[0]:
            return False
        if expected[0] == "struct":
            if expected[1] != actual[1]:
                return False
            ea = expected[2] if len(expected) > 2 else ()
            aa = actual[2] if len(actual) > 2 else ()
            return len(ea) == len(aa) and all(compatible(x, y) for x, y in zip(ea, aa))
        if expected[0] == "list":
            return compatible(expected[1], actual[1])
        if expected[0] == "map":
            return compatible(expected[1], actual[1]) and compatible(expected[2], actual[2])
        return expected == actual
    return expected == actual


def has_tvars(t):
    if isinstance(t, tuple):
        k = t[0]
        if k == "tvar":
            return True
        if k in ("list", "optional"):
            return has_tvars(t[1])
        if k == "map":
            return has_tvars(t[1]) or has_tvars(t[2])
        if k == "struct" and len(t) > 2:
            return any(has_tvars(a) for a in t[2])
    return False


def tvar_names(t):
    """Names of every type variable occurring in `t`."""
    if isinstance(t, tuple):
        k = t[0]
        if k == "tvar":
            return {t[1]}
        if k in ("list", "optional"):
            return tvar_names(t[1])
        if k == "map":
            return tvar_names(t[1]) | tvar_names(t[2])
        if k == "struct" and len(t) > 2:
            return set().union(*(tvar_names(a) for a in t[2])) if t[2] else set()
    return set()


def subst(t, mapping):
    """Replace type variables by name; variables missing from `mapping` become UNKNOWN."""
    if isinstance(t, tuple):
        k = t[0]
        if k == "tvar":
            return mapping.get(t[1], UNKNOWN)
        if k in ("list", "optional"):
            return (k, subst(t[1], mapping))
        if k == "map":
            return ("map", subst(t[1], mapping), subst(t[2], mapping))
        if k == "struct" and len(t) > 2:
            return ("struct", t[1], tuple(subst(a, mapping) for a in t[2]))
    return t


def strip_optional(t):
    return t[1] if is_optional(t) else t
