"""
Calyre standard library.

Each module is a `Module` value bound at import time (`use math`), backed
by Python functions. This is the "category A" library described in the
Phase 3 design notes: it ships with Calyre itself, as opposed to local
user libraries (plain .cly files loaded via the module loader in
interpreter.py) or external libraries (not implemented — see notes).

Modules are constructed lazily and cached, so `use math` twice in the
same program does no repeated work.
"""

import math as _math
import random as _random
import time as _time
import os as _os
import re as _re
import sys as _sys
import json as _json
import functools as _functools
import posixpath as _posixpath

from .interpreter import Module, BuiltinFunction, CalyreRuntimeError, calyre_repr


_cache = {}


def _module(name, builder):
    if name not in _cache:
        _cache[name] = builder()
    return _cache[name]


# ---- math ----

def _build_math():
    def sqrt(x):
        if x < 0:
            raise CalyreRuntimeError("math.sqrt: cannot take the square root of a negative number")
        return _math.sqrt(x)

    def pow_(x, y):
        try:
            result = float(x) ** y
        except ZeroDivisionError as e:
            raise CalyreRuntimeError("math.pow: zero cannot be raised to a negative power") from e
        except OverflowError as e:
            raise CalyreRuntimeError("math.pow: the result is too large") from e
        if isinstance(result, complex):
            raise CalyreRuntimeError("math.pow: a negative base needs a whole-number exponent")
        return result

    def floor_div(a, b):
        if b == 0:
            raise CalyreRuntimeError("math.floor_div: division by zero")
        return a // b

    members = {
        "sqrt": BuiltinFunction("math.sqrt", sqrt),
        "floor": BuiltinFunction("math.floor", lambda x: _math.floor(x)),
        "ceil": BuiltinFunction("math.ceil", lambda x: _math.ceil(x)),
        "abs": BuiltinFunction("math.abs", lambda x: abs(x)),
        "pow": BuiltinFunction("math.pow", pow_),
        "min": BuiltinFunction("math.min", lambda a, b: min(a, b)),
        "max": BuiltinFunction("math.max", lambda a, b: max(a, b)),
        "round": BuiltinFunction("math.round", lambda x: round(x)),
        "floor_div": BuiltinFunction("math.floor_div", floor_div),
        "pi": _math.pi,
        "e": _math.e,
    }
    return Module("math", members)


# ---- random ----

def _build_random():
    def rand_int(a, b):
        if a > b:
            raise CalyreRuntimeError("random.int: the first value must be <= the second")
        return _random.randint(a, b)

    def rand_choice(items):
        if not isinstance(items, list) or not items:
            raise CalyreRuntimeError("random.choice: expects a non-empty list")
        return _random.choice(items)

    members = {
        "int": BuiltinFunction("random.int", rand_int),
        "float": BuiltinFunction("random.float", lambda a, b: _random.uniform(a, b)),
        "choice": BuiltinFunction("random.choice", rand_choice),
    }
    return Module("random", members)


# ---- time ----

def _build_time():
    members = {
        "now": BuiltinFunction("time.now", lambda: _time.time()),
        "sleep": BuiltinFunction("time.sleep", lambda seconds: _time.sleep(seconds)),
    }
    return Module("time", members)


# ---- text ----

def _build_text():
    def split(s, sep):
        return s.split(sep)

    members = {
        "upper": BuiltinFunction("text.upper", lambda s: s.upper()),
        "lower": BuiltinFunction("text.lower", lambda s: s.lower()),
        "trim": BuiltinFunction("text.trim", lambda s: s.strip()),
        "split": BuiltinFunction("text.split", split),
        "join": BuiltinFunction("text.join", lambda items, sep: sep.join(calyre_repr(i) if not isinstance(i, str) else i for i in items)),
        "replace": BuiltinFunction("text.replace", lambda s, old, new: s.replace(old, new)),
        "contains": BuiltinFunction("text.contains", lambda s, sub: sub in s),
        "starts_with": BuiltinFunction("text.starts_with", lambda s, prefix: s.startswith(prefix)),
        "ends_with": BuiltinFunction("text.ends_with", lambda s, suffix: s.endswith(suffix)),
        "repeat": BuiltinFunction("text.repeat", lambda s, n: s * n),
    }
    return Module("text", members)


# ---- fs ----

def _build_fs():
    """Everything that touches the disk. Text is UTF-8; reads translate \\r\\n to \\n, writes never
    translate (a file written on Windows and on Linux is byte-for-byte the same)."""

    def fail(op, path, e):
        if isinstance(e, FileNotFoundError):
            why = "no such file or folder"
        elif isinstance(e, PermissionError):
            why = "permission denied"
        elif isinstance(e, IsADirectoryError):
            why = "it is a folder, not a file"
        elif isinstance(e, NotADirectoryError):
            why = "it is a file, not a folder"
        elif isinstance(e, UnicodeDecodeError):
            why = "the file is not valid UTF-8 text"
        else:
            why = e.strerror or str(e)
        return CalyreRuntimeError(f"fs.{op}: '{path}': {why}")

    def text_arg(op, value):
        if not isinstance(value, str):
            raise CalyreRuntimeError(f"fs.{op}: the content must be a text (use str(...) if needed)")

    def read(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError) as e:
            raise fail("read", path, e) from e

    def write(path, content, mode="write"):
        text_arg(mode, content)
        try:
            with open(path, "w" if mode == "write" else "a", encoding="utf-8", newline="\n") as f:
                f.write(content)
        except OSError as e:
            if isinstance(e, FileNotFoundError):
                raise CalyreRuntimeError(
                    f"fs.{mode}: '{path}': the folder does not exist (create it with fs.make_dir)") from e
            raise fail(mode, path, e) from e
        return None

    def list_dir(path):
        try:
            return sorted(_os.listdir(path))
        except OSError as e:
            raise fail("list_dir", path, e) from e

    def make_dir(path):
        try:
            _os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise fail("make_dir", path, e) from e
        return None

    def remove(path):
        if _os.path.isdir(path):
            raise CalyreRuntimeError(f"fs.remove: '{path}' is a folder; fs.remove only deletes files "
                                     f"(use fs.remove_dir for an empty folder)")
        try:
            _os.remove(path)
        except OSError as e:
            raise fail("remove", path, e) from e
        return None

    def remove_dir(path):
        try:
            _os.rmdir(path)
        except OSError as e:
            if _os.path.isdir(path) and _os.listdir(path):
                raise CalyreRuntimeError(f"fs.remove_dir: '{path}' is not empty "
                                         f"(Calyre never deletes folders recursively)") from e
            raise fail("remove_dir", path, e) from e
        return None

    def size(path):
        try:
            return _os.path.getsize(path)
        except OSError as e:
            raise fail("size", path, e) from e

    def rename(src, dst):
        if _os.path.exists(dst):
            raise CalyreRuntimeError(f"fs.rename: '{dst}' already exists (it would be overwritten on "
                                     f"some systems and not on others, so Calyre refuses)")
        try:
            _os.rename(src, dst)
        except OSError as e:
            raise fail("rename", src, e) from e
        return None

    members = {
        "read": BuiltinFunction("fs.read", read),
        "write": BuiltinFunction("fs.write", lambda path, content: write(path, content, "write")),
        "append": BuiltinFunction("fs.append", lambda path, content: write(path, content, "append")),
        "exists": BuiltinFunction("fs.exists", lambda path: _os.path.exists(path)),
        "is_file": BuiltinFunction("fs.is_file", lambda path: _os.path.isfile(path)),
        "is_dir": BuiltinFunction("fs.is_dir", lambda path: _os.path.isdir(path)),
        "list_dir": BuiltinFunction("fs.list_dir", list_dir),
        "make_dir": BuiltinFunction("fs.make_dir", make_dir),
        "remove": BuiltinFunction("fs.remove", remove),
        "remove_dir": BuiltinFunction("fs.remove_dir", remove_dir),
        "size": BuiltinFunction("fs.size", size),
        "rename": BuiltinFunction("fs.rename", rename),
    }
    return Module("fs", members)


# ---- path (pure text manipulation: no disk access, same result on every OS) ----

_DRIVE = _re.compile(r"^[A-Za-z]:/")


def _build_path():
    """Calyre paths always use `/`; backslashes in input are accepted and converted."""

    def norm(p):
        return p.replace("\\", "/")

    def is_absolute(p):
        p = norm(p)
        return p.startswith("/") or bool(_DRIVE.match(p))

    def join(a, b):
        a, b = norm(a), norm(b)
        if is_absolute(b) or a == "":
            return b
        return a + b if a.endswith("/") else a + "/" + b

    def clean(p):
        p = norm(p)
        return p.rstrip("/") if len(p) > 1 and not _DRIVE.fullmatch(p) and p != "/" else p

    def basename(p):
        c = clean(p)
        return "" if c == "/" else c.rsplit("/", 1)[-1] if not _DRIVE.fullmatch(c) else ""

    def dirname(p):
        c = clean(p)
        if "/" not in c:
            return ""
        head = c.rsplit("/", 1)[0]
        return head if head else "/"

    def split_ext(name):
        i = name.rfind(".")
        return (name, "") if i <= 0 else (name[:i], name[i:])

    def with_extension(p, ext):
        if ext != "" and (not ext.startswith(".") or len(ext) == 1 or "/" in ext):
            raise CalyreRuntimeError("path.with_extension: the extension must be empty or look like '.txt'")
        stem, _ = split_ext(basename(p))
        d = dirname(p)
        return join(d, stem + ext) if d else stem + ext

    def normalize(p):
        out = _posixpath.normpath(norm(p))
        return "." if out == "" else out

    def parts(p):
        p = norm(p)
        out = [x for x in p.split("/") if x not in ("", ".")]
        if p.startswith("/"):
            out.insert(0, "/")
        return out

    def relative_to(p, start):
        a, b = norm(p), norm(start)
        if is_absolute(a) != is_absolute(b):
            raise CalyreRuntimeError("path.relative_to: both paths must be absolute or both relative")
        if not is_absolute(a):
            a, b = "/" + a, "/" + b
        return _posixpath.relpath(a, b)

    def absolute(p):
        return _os.path.abspath(p).replace("\\", "/")

    members = {
        "join": BuiltinFunction("path.join", join),
        "join_all": BuiltinFunction("path.join_all", lambda items: _functools.reduce(join, items, "")),
        "basename": BuiltinFunction("path.basename", basename),
        "dirname": BuiltinFunction("path.dirname", dirname),
        "stem": BuiltinFunction("path.stem", lambda p: split_ext(basename(p))[0]),
        "extension": BuiltinFunction("path.extension", lambda p: split_ext(basename(p))[1]),
        "with_extension": BuiltinFunction("path.with_extension", with_extension),
        "normalize": BuiltinFunction("path.normalize", normalize),
        "parts": BuiltinFunction("path.parts", parts),
        "is_absolute": BuiltinFunction("path.is_absolute", is_absolute),
        "relative_to": BuiltinFunction("path.relative_to", relative_to),
        "absolute": BuiltinFunction("path.absolute", absolute),
    }
    return Module("path", members)


# ---- json ----

def _json_to_calyre_error(e):
    return CalyreRuntimeError(f"json.parse: invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}")


def _build_json():
    from .interpreter import StructInstance

    def parse(text):
        def refuse(const):
            raise CalyreRuntimeError(f"json.parse: '{const}' is not valid JSON")
        try:
            return _json.loads(text, parse_constant=refuse)
        except _json.JSONDecodeError as e:
            raise _json_to_calyre_error(e) from e
        except RecursionError as e:
            raise CalyreRuntimeError("json.parse: the document is nested too deeply") from e

    def convert(v, path="value"):
        if v is None or isinstance(v, (bool, int, str)):
            return v
        if isinstance(v, float):
            if v != v or v in (float("inf"), float("-inf")):
                raise CalyreRuntimeError(f"json.stringify: {path} is {v}, which JSON cannot represent")
            return v
        if isinstance(v, list):
            return [convert(x, f"{path}[{i}]") for i, x in enumerate(v)]
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                if not isinstance(k, str):
                    raise CalyreRuntimeError(f"json.stringify: {path} has a map key that is not a text "
                                             f"({calyre_repr(k)}); JSON object keys are always texts")
                out[k] = convert(x, f"{path}[{k!r}]")
            return out
        if isinstance(v, StructInstance):
            return {k: convert(x, f"{path}.{k}") for k, x in v.fields.items()}
        raise CalyreRuntimeError(f"json.stringify: {path} cannot be turned into JSON "
                                 f"(it is not a text, number, bool, none, list, map or struct)")

    def stringify(value, indent=None):
        try:
            return _json.dumps(convert(value), ensure_ascii=False, indent=indent,
                               separators=(",", ":") if indent is None else (",", ": "))
        except RecursionError as e:
            raise CalyreRuntimeError("json.stringify: the value is nested too deeply") from e

    members = {
        "parse": BuiltinFunction("json.parse", parse),
        "stringify": BuiltinFunction("json.stringify", lambda value: stringify(value)),
        "pretty": BuiltinFunction("json.pretty", lambda value: stringify(value, 2)),
    }
    return Module("json", members)


# ---- sql ----

def _build_sql():
    from .sqlmod import open_database, ENGINES, NativeTypeMarker
    members = {
        "open": BuiltinFunction("sql.open", open_database),
        "engines": BuiltinFunction("sql.engines", lambda: list(ENGINES)),
        "Database": NativeTypeMarker(),
    }
    return Module("sql", members)


# ---- system ----

PROGRAM_ARGS = []


def set_program_args(args):
    """Called by the CLI: `calyre run file.cly a b` makes system.args() == ["a", "b"]."""
    PROGRAM_ARGS[:] = list(args)


def _build_system():
    def platform():
        p = _sys.platform
        return "windows" if p.startswith("win") else "macos" if p == "darwin" else "linux" if p.startswith("linux") else p

    def exit_(code):
        if isinstance(code, bool) or not isinstance(code, int) or not 0 <= code <= 255:
            raise CalyreRuntimeError("system.exit: the exit code must be a whole number from 0 to 255")
        _sys.stdout.flush()
        raise SystemExit(code)

    members = {
        "args": BuiltinFunction("system.args", lambda: list(PROGRAM_ARGS)),
        "env": BuiltinFunction("system.env", lambda name: _os.environ.get(name)),
        "platform": BuiltinFunction("system.platform", platform),
        "cwd": BuiltinFunction("system.cwd", lambda: _os.getcwd().replace("\\", "/")),
        "exit": BuiltinFunction("system.exit", exit_),
    }
    return Module("system", members)


# ---- python (interoperability bridge — see Phase 3 notes for scope/limits) ----

_PY_ALLOWED_MODULES = {"math", "random", "statistics", "datetime", "json"}


def _to_python(value, line=None):
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_to_python(v, line) for v in value]
    if isinstance(value, dict):
        return {k: _to_python(v, line) for k, v in value.items()}
    raise CalyreRuntimeError(
        "python interop: this value cannot be passed to Python "
        "(only int, float, str, bool, none, lists and maps are supported)",
        line,
    )


def _to_calyre(value, line=None):
    if isinstance(value, bool) or value is None or isinstance(value, (int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_to_calyre(v, line) for v in value]
    if isinstance(value, dict):
        return {k: _to_calyre(v, line) for k, v in value.items()}
    raise CalyreRuntimeError(
        f"python interop: the Python result is an object of type "
        f"'{type(value).__name__}', which has no direct Calyre equivalent "
        f"(only simple types, lists and maps come back automatically)",
        line,
    )


def _build_python():
    import importlib

    def py_call(module_name, func_name, *args):
        if module_name not in _PY_ALLOWED_MODULES:
            raise CalyreRuntimeError(
                f"python.call: the Python module '{module_name}' is not on the "
                f"safe list ({', '.join(sorted(_PY_ALLOWED_MODULES))}). This is a "
                f"deliberate restriction (see docs/SPEC.md, Python interoperability)."
            )
        try:
            mod = importlib.import_module(module_name)
            fn = getattr(mod, func_name)
        except (ImportError, AttributeError) as e:
            raise CalyreRuntimeError(f"python.call: '{module_name}.{func_name}' does not exist") from e

        py_args = [_to_python(a) for a in args]
        try:
            result = fn(*py_args)
        except Exception as e:
            # Python tracebacks never leak to Calyre users — converted to a
            # normal, catchable Calyre error instead.
            raise CalyreRuntimeError(f"python.call: {module_name}.{func_name} failed - {e}") from e
        return _to_calyre(result)

    members = {
        "call": BuiltinFunction("python.call", py_call),
    }
    return Module("python", members)


STDLIB_MODULES = {
    "math": lambda: _module("math", _build_math),
    "random": lambda: _module("random", _build_random),
    "time": lambda: _module("time", _build_time),
    "text": lambda: _module("text", _build_text),
    "fs": lambda: _module("fs", _build_fs),
    "path": lambda: _module("path", _build_path),
    "json": lambda: _module("json", _build_json),
    "sql": lambda: _module("sql", _build_sql),
    "system": lambda: _module("system", _build_system),
    "python": lambda: _module("python", _build_python),
}
