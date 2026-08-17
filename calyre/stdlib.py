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
            raise CalyreRuntimeError("math.sqrt: não é possível tirar raiz de um número negativo")
        return _math.sqrt(x)

    members = {
        "sqrt": BuiltinFunction("math.sqrt", sqrt),
        "floor": BuiltinFunction("math.floor", lambda x: _math.floor(x)),
        "ceil": BuiltinFunction("math.ceil", lambda x: _math.ceil(x)),
        "abs": BuiltinFunction("math.abs", lambda x: abs(x)),
        "pow": BuiltinFunction("math.pow", lambda x, y: x ** y),
        "min": BuiltinFunction("math.min", lambda a, b: min(a, b)),
        "max": BuiltinFunction("math.max", lambda a, b: max(a, b)),
        "round": BuiltinFunction("math.round", lambda x: round(x)),
        "pi": _math.pi,
        "e": _math.e,
    }
    return Module("math", members)


# ---- random ----

def _build_random():
    def rand_int(a, b):
        if a > b:
            raise CalyreRuntimeError("random.int: o primeiro valor precisa ser <= o segundo")
        return _random.randint(a, b)

    def rand_choice(items):
        if not isinstance(items, list) or not items:
            raise CalyreRuntimeError("random.choice: espera uma lista não vazia")
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
    def read(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError as e:
            raise CalyreRuntimeError(f"fs.read: arquivo '{path}' não encontrado") from e
        except IsADirectoryError as e:
            raise CalyreRuntimeError(f"fs.read: '{path}' é uma pasta, não um arquivo") from e

    def write(path, content):
        if not isinstance(content, str):
            raise CalyreRuntimeError("fs.write: o conteúdo precisa ser um texto (use str(...) se necessário)")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return None

    def list_dir(path):
        try:
            return sorted(_os.listdir(path))
        except FileNotFoundError as e:
            raise CalyreRuntimeError(f"fs.list_dir: pasta '{path}' não encontrada") from e

    def make_dir(path):
        _os.makedirs(path, exist_ok=True)
        return None

    members = {
        "read": BuiltinFunction("fs.read", read),
        "write": BuiltinFunction("fs.write", write),
        "exists": BuiltinFunction("fs.exists", lambda path: _os.path.exists(path)),
        "list_dir": BuiltinFunction("fs.list_dir", list_dir),
        "make_dir": BuiltinFunction("fs.make_dir", make_dir),
    }
    return Module("fs", members)


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
        "python interop: este valor não pode ser passado para Python "
        "(apenas int, float, str, bool, none, listas e mapas são suportados)",
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
        f"python interop: o resultado do Python é um objeto do tipo "
        f"'{type(value).__name__}', que não tem equivalente direto em Calyre "
        f"(apenas tipos simples, listas e mapas voltam automaticamente)",
        line,
    )


def _build_python():
    import importlib

    def py_call(module_name, func_name, *args):
        if module_name not in _PY_ALLOWED_MODULES:
            raise CalyreRuntimeError(
                f"python.call: o módulo Python '{module_name}' não está na lista "
                f"segura ({', '.join(sorted(_PY_ALLOWED_MODULES))}). Isso é uma "
                f"limitação deliberada desta fase — ver Fase 3, seção de "
                f"interoperabilidade com Python."
            )
        try:
            mod = importlib.import_module(module_name)
            fn = getattr(mod, func_name)
        except (ImportError, AttributeError) as e:
            raise CalyreRuntimeError(f"python.call: '{module_name}.{func_name}' não existe") from e

        py_args = [_to_python(a) for a in args]
        try:
            result = fn(*py_args)
        except Exception as e:
            # Python tracebacks never leak to Calyre users — converted to a
            # normal, catchable Calyre error instead.
            raise CalyreRuntimeError(f"python.call: {module_name}.{func_name} falhou — {e}") from e
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
    "python": lambda: _module("python", _build_python),
}
