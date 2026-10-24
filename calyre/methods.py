"""
Methods of the built-in types (`list`, `map`, `str`).

This is the ONE place that defines them: each entry holds the static signature used
by the type checker AND the implementation used by the interpreter, so they cannot
drift apart. Type variables E (list element), K / V (map key / value) are bound to the
receiver's type arguments at each use.

Design decisions (see docs/SPEC.md):
* Methods are the way to operate on a value: `items.append(x)`, `name.upper()`.
  Module functions (`math.sqrt`, `fs.read`) are for things that are not "a method of a value".
  The older `text.*` functions are kept for compatibility but frozen: no new text functions.
* Lists and maps have reference semantics: `append`, `remove`, `sort`, ... mutate in place;
  `copy()` makes a shallow copy. A `for` loop visits the elements the list had when it started.
* Strings are immutable Unicode texts: methods return new strings.
"""

from .types import NONE_T

E = ("tvar", "E")
K = ("tvar", "K")
V = ("tvar", "V")
OPT_INT = ("optional", "int")


def _err(message):
    from .interpreter import CalyreRuntimeError
    return CalyreRuntimeError(message)


def _eq(a, b):
    from .interpreter import _calyre_equals
    return _calyre_equals(a, b)


def _index_of(xs, x):
    for i, item in enumerate(xs):
        if _eq(item, x):
            return i
    return None


# ---- list -------------------------------------------------------------------

def _insert(xs, i, x):
    if not 0 <= i <= len(xs):
        raise _err(f"list.insert: index {i} is out of range (valid: 0 to {len(xs)})")
    xs.insert(i, x)


def _pop(xs):
    if not xs:
        raise _err("list.pop: the list is empty")
    return xs.pop()


def _remove_at(xs, i):
    if not -len(xs) <= i < len(xs):
        raise _err(f"list.remove_at: index {i} is out of range "
                   + (f"(valid: {-len(xs)} to {len(xs) - 1})" if xs else "(the list is empty)"))
    return xs.pop(i)


def _remove(xs, x):
    i = _index_of(xs, x)
    if i is None:
        return False
    del xs[i]
    return True


def _extend(xs, other):
    xs.extend(list(other))


def _reverse(xs):
    xs.reverse()


def _sort(xs):
    xs.sort()


LIST_METHODS = {
    "append": ([E], NONE_T, lambda xs, x: xs.append(x)),
    "insert": (["int", E], NONE_T, _insert),
    "pop": ([], E, _pop),
    "remove_at": (["int"], E, _remove_at),
    "remove": ([E], "bool", _remove),
    "contains": ([E], "bool", lambda xs, x: _index_of(xs, x) is not None),
    "index_of": ([E], OPT_INT, _index_of),
    "clear": ([], NONE_T, lambda xs: xs.clear()),
    "copy": ([], ("list", E), lambda xs: list(xs)),
    "extend": ([("list", E)], NONE_T, _extend),
    "reverse": ([], NONE_T, _reverse),
    "sort": ([], NONE_T, _sort),
    "slice": (["int", "int"], ("list", E), lambda xs, a, b: xs[a:b]),
}
SORTABLE = ("int", "float", "str")     # `sort` needs elements that can be ordered


# ---- map --------------------------------------------------------------------

def _map_remove(m, k):
    if k in m:
        del m[k]
        return True
    return False


MAP_METHODS = {
    "has": ([K], "bool", lambda m, k: k in m),
    "get": ([K], ("optional", V), lambda m, k: m.get(k)),
    "remove": ([K], "bool", _map_remove),
    "keys": ([], ("list", K), lambda m: list(m.keys())),
    "values": ([], ("list", V), lambda m: list(m.values())),
    "clear": ([], NONE_T, lambda m: m.clear()),
    "copy": ([], ("map", K, V), lambda m: dict(m)),
}


# ---- str --------------------------------------------------------------------

def _str_index_of(s, sub):
    i = s.find(sub)
    return None if i < 0 else i


def _str_split(s, sep):
    if sep == "":
        raise _err("str.split: the separator cannot be empty")
    return s.split(sep)


def _str_replace(s, old, new):
    if old == "":
        raise _err("str.replace: the text to replace cannot be empty")
    return s.replace(old, new)


def _str_repeat(s, n):
    if n < 0:
        raise _err("str.repeat: the count cannot be negative")
    return s * n


STR_METHODS = {
    "upper": ([], "str", lambda s: s.upper()),
    "lower": ([], "str", lambda s: s.lower()),
    "trim": ([], "str", lambda s: s.strip()),
    "contains": (["str"], "bool", lambda s, sub: sub in s),
    "starts_with": (["str"], "bool", lambda s, p: s.startswith(p)),
    "ends_with": (["str"], "bool", lambda s, p: s.endswith(p)),
    "replace": (["str", "str"], "str", _str_replace),
    "split": (["str"], ("list", "str"), _str_split),
    "index_of": (["str"], OPT_INT, _str_index_of),
    "slice": (["int", "int"], "str", lambda s, a, b: s[a:b]),
    "repeat": (["int"], "str", _str_repeat),
}

METHODS = {"list": LIST_METHODS, "map": MAP_METHODS, "str": STR_METHODS}


def method_table(value):
    """The method table for a runtime value, or None."""
    if isinstance(value, list):
        return LIST_METHODS
    if isinstance(value, dict):
        return MAP_METHODS
    if isinstance(value, str):
        return STR_METHODS
    native = getattr(value, "native_type", None)
    if native is not None:
        from .sqlmod import NATIVE_METHODS
        return NATIVE_METHODS.get(native)
    return None
