"""
Static type representation used by the Calyre type checker.

Types are represented as either a plain string ("int", "float", "str",
"bool", "none", "any") or a tuple for compound types:

    ("list", elem_type)
    ("map", key_type, value_type)
    ("optional", inner_type)
    ("struct", struct_name)
    ("func", [param_types], return_type)

"any" is used for values the checker intentionally does not try to pin
down precisely — the result of a stdlib call, a module member, or a
function without a declared return type. This is a deliberate choice:
Calyre's type checker aims to catch *obvious* mistakes, not to be a
complete verifier. Treating unknown things as "any" (compatible with
everything) avoids false positives that would make the checker feel
unpredictable or overly strict to a beginner.
"""

ANY = "any"
NONE_T = "none"


def is_optional(t):
    return isinstance(t, tuple) and t[0] == "optional"


def is_numeric(t):
    return t in ("int", "float")


def type_name(t):
    """Render a type for human-facing error messages, e.g. list<int>, str?, Reading"""
    if isinstance(t, str):
        return t
    if isinstance(t, tuple):
        if t[0] == "list":
            return f"list<{type_name(t[1])}>"
        if t[0] == "map":
            return f"map<{type_name(t[1])}, {type_name(t[2])}>"
        if t[0] == "optional":
            return f"{type_name(t[1])}?"
        if t[0] == "struct":
            return t[1]
        if t[0] == "func":
            params = ", ".join(type_name(p) for p in t[1])
            return f"func({params}) -> {type_name(t[2])}"
    return str(t)


def compatible(expected, actual):
    """True if a value of type `actual` may be used where `expected` is required."""
    if expected == ANY or actual == ANY:
        return True

    if is_optional(expected):
        if actual == NONE_T:
            return True
        inner = expected[1]
        if is_optional(actual):
            return compatible(inner, actual[1])
        return compatible(inner, actual)

    if actual == NONE_T:
        # `none` is only valid where an optional type (or any) is expected.
        return False

    if isinstance(expected, tuple) and isinstance(actual, tuple):
        if expected[0] != actual[0]:
            return False
        if expected[0] == "list":
            return compatible(expected[1], actual[1])
        if expected[0] == "map":
            return compatible(expected[1], actual[1]) and compatible(expected[2], actual[2])
        if expected[0] == "struct":
            return expected[1] == actual[1]
        return expected == actual

    return expected == actual


def resolve_type_ann(type_ann, struct_registry):
    """Convert an ast_nodes.TypeAnn (parsed syntax) into an internal type value."""
    if type_ann is None:
        return ANY
    name = type_ann.name
    if name == "list":
        elem = resolve_type_ann(type_ann.params[0], struct_registry) if type_ann.params else ANY
        base = ("list", elem)
    elif name == "map":
        if len(type_ann.params) == 2:
            key = resolve_type_ann(type_ann.params[0], struct_registry)
            val = resolve_type_ann(type_ann.params[1], struct_registry)
        else:
            key, val = ANY, ANY
        base = ("map", key, val)
    elif name in ("int", "float", "str", "bool"):
        base = name
    elif name in struct_registry:
        base = ("struct", name)
    else:
        # Unknown type name (e.g. a type from a module not yet resolved).
        # Treated as `any` rather than a hard error — cross-module type
        # tracking is out of scope for this phase (see Phase 3 notes).
        base = ANY
    if type_ann.optional:
        base = ("optional", base)
    return base
