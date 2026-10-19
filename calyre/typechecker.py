"""
Calyre static type checker (semantic analysis).

Runs after parsing and before execution. It resolves names, scopes, types,
imports and return paths, and reports diagnostics the way a careful teacher
would: what is wrong, where, and (when possible) how to fix it.

Design rules (see docs/SPEC.md, "Type system"):

* `any` is intentional dynamism (explicit `any`, python.call results). It is
  never produced silently by this checker.
* `unknown` only exists after an error was already reported (so one mistake
  gives one message) or while a return type is still being inferred.
* Errors block execution; warnings never do. Warnings are used where a
  stricter rule would break programs that were valid before (compatibility).
"""

import difflib
import os

from . import ast_nodes as A
from .lexer import tokenize, LexError
from .calyre_parser import parse, ParseError
from . import resolver
from .stdlib_types import STDLIB_SIGNATURES, BUILTIN_SPECS
from .types import (
    ANY, UNKNOWN, NONE_T, type_name, compatible, is_numeric, is_optional,
    is_permissive, contains_unknown, strip_optional,
)

_PRIMITIVES = ("int", "float", "str", "bool", "any")
_ERROR_KEY = "$Error"


class Diagnostic:
    def __init__(self, message, line, severity="error", hint=None):
        self.message = message
        self.line = line
        self.severity = severity
        self.hint = hint

    def format(self, path):
        text = f"{path}:{self.line}: {self.severity}: {self.message}"
        if self.hint:
            text += f"\n    hint: {self.hint}"
        return text

    def __str__(self):
        loc = f"line {self.line}: " if self.line is not None else ""
        return f"{loc}{self.message}"


TypeCheckError = Diagnostic   # backwards-compatible name


class Binding:
    __slots__ = ("decl", "cur", "line", "narrowed")

    def __init__(self, decl, cur, line, narrowed=False):
        self.decl = decl          # type the variable was declared with
        self.cur = cur            # type right now (may be narrowed by `!= none` checks)
        self.line = line
        self.narrowed = narrowed


class Scope:
    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def lookup(self, name):
        s = self
        while s is not None:
            b = s.vars.get(name)
            if b is not None:
                return b
            s = s.parent
        return None

    def names(self):
        out, s = set(), self
        while s is not None:
            out.update(s.vars)
            s = s.parent
        return out


class ModuleInfo:
    def __init__(self, members, registry, errors):
        self.members = members
        self.registry = registry
        self.errors = errors


class Context:
    """State shared by every checker of one import graph."""

    def __init__(self):
        self.cache = {}
        self.stack = []


# ---------------------------------------------------------------- helpers

def _suggest(name, candidates):
    match = difflib.get_close_matches(name, sorted(candidates), n=1, cutoff=0.6)
    return f"did you mean '{match[0]}'?" if match else None


def _is_none_literal(node):
    return isinstance(node, A.Literal) and node.value is None


def _is_exit_call(stmt):
    return (isinstance(stmt, A.ExprStmt) and isinstance(stmt.expr, A.Call)
            and isinstance(stmt.expr.callee, A.Identifier) and stmt.expr.callee.name == "error")


def block_terminates(block, loop_exits=False):
    """True if execution can never fall off the end of `block`.
    With loop_exits, break/continue also count (used for `!= none` narrowing)."""
    return any(_stmt_terminates(s, loop_exits) for s in block)


def _stmt_terminates(s, loop_exits):
    if isinstance(s, A.ReturnStmt) or _is_exit_call(s):
        return True
    if loop_exits and isinstance(s, (A.BreakStmt, A.ContinueStmt)):
        return True
    if isinstance(s, A.IfStmt):
        return (s.else_block is not None
                and all(block_terminates(b, loop_exits) for _, b in s.branches)
                and block_terminates(s.else_block, loop_exits))
    if isinstance(s, A.MatchStmt):
        has_default = any(p is None for p, _ in s.cases)
        return has_default and all(block_terminates(b, loop_exits) for _, b in s.cases)
    if isinstance(s, A.TryStmt):
        return block_terminates(s.try_block, loop_exits) and block_terminates(s.catch_block, loop_exits)
    if isinstance(s, A.WhileStmt):
        forever = isinstance(s.condition, A.Literal) and s.condition.value is True
        return forever and not _contains_break(s.body)
    return False


def _contains_break(block):
    for s in block:
        if isinstance(s, A.BreakStmt):
            return True
        if isinstance(s, A.IfStmt):
            if any(_contains_break(b) for _, b in s.branches) or (s.else_block and _contains_break(s.else_block)):
                return True
        elif isinstance(s, A.MatchStmt):
            if any(_contains_break(b) for _, b in s.cases):
                return True
        elif isinstance(s, A.TryStmt):
            if _contains_break(s.try_block) or _contains_break(s.catch_block):
                return True
        # breaks inside nested while/for belong to those loops
    return False


def _requalify(t, prefix, local_keys):
    if isinstance(t, tuple):
        if t[0] in ("struct", "structdef") and t[1] in local_keys:
            return (t[0], f"{prefix}.{t[1]}")
        if t[0] in ("list", "optional"):
            return (t[0], _requalify(t[1], prefix, local_keys))
        if t[0] == "map":
            return ("map", _requalify(t[1], prefix, local_keys), _requalify(t[2], prefix, local_keys))
        if t[0] == "func":
            rest = t[3:]
            return ("func", [_requalify(p, prefix, local_keys) for p in t[1]],
                    _requalify(t[2], prefix, local_keys)) + rest
    return t


# ---------------------------------------------------------------- checker

class Checker:
    def __init__(self, base_dir=None, ctx=None, repl=False):
        self.diagnostics = []
        self.base_dir = base_dir or os.getcwd()
        self.ctx = ctx or Context()
        self.repl = repl
        self.silent = 0
        self.registry = {_ERROR_KEY: {"message": "str", "line": ("optional", "int")}}
        self.types = {}                 # struct name -> registry key
        self.pending_structs = []
        self.predeclared = set()        # id() of top-level funcs/structs declared in pass 1
        self.builtin_scope = Scope()
        for name in BUILTIN_SPECS:
            self.builtin_scope.vars[name] = Binding(("builtin", name), ("builtin", name), None)
        self.module_scope = Scope(self.builtin_scope)
        self.frames = [{"name": None, "loop": 0, "expected": None, "returns": []}]

    # ----- diagnostics

    def error(self, message, line, hint=None):
        if not self.silent:
            self.diagnostics.append(Diagnostic(message, line, "error", hint))

    def warn(self, message, line, hint=None):
        if not self.silent:
            self.diagnostics.append(Diagnostic(message, line, "warning", hint))

    # ----- entry point

    def check_program(self, program):
        start = len(self.diagnostics)
        scope = self.module_scope
        stmts = program.statements

        for s in stmts:                      # imports first: signatures may mention `mod.Type`
            if isinstance(s, A.UseStmt):
                self.check_UseStmt(s, scope)
                self.predeclared.add(id(s))
        for s in stmts:
            if isinstance(s, A.StructDecl):
                self.declare_struct(s, scope)
        self.resolve_pending_structs(scope)
        for s in stmts:
            if isinstance(s, A.FuncDecl):
                self.declare_func(s, scope)
                self.predeclared.add(id(s))

        unannotated = [s for s in stmts if isinstance(s, A.FuncDecl) and s.return_type is None]
        if unannotated:                      # dry run: infer return types without reporting
            self.silent += 1
            for _ in range(2):
                for s in unannotated:
                    self.check_function(s, scope, update_binding=True)
            self.silent -= 1

        for s in stmts:
            self.check_stmt(s, scope)

        new = self.diagnostics[start:]
        new.sort(key=lambda d: (d.line if d.line is not None else 0))   # stable => deterministic
        self.diagnostics[start:] = new
        return new

    # ----- declarations

    def declare(self, scope, name, t, line, what="name"):
        prior = scope.vars.get(name)
        if prior is not None and not prior.narrowed and not (self.repl and scope is self.module_scope):
            where = f" (first declared on line {prior.line})" if prior.line else ""
            self.error(f"'{name}' is already declared in this scope{where}", line,
                       "use a different name, or assign with `name = value` to change the existing variable"
                       if what == "variable" else "use a different name")
        scope.vars[name] = Binding(t, t, line)

    def declare_struct(self, stmt, scope):
        if stmt.name in self.types and not self.repl:
            self.error(f"struct '{stmt.name}' is declared more than once", stmt.line)
            return
        key = stmt.name
        self.types[stmt.name] = key
        self.registry[key] = {}
        self.pending_structs.append((key, stmt))
        self.declare(scope, stmt.name, ("structdef", key), stmt.line)

    def resolve_pending_structs(self, scope):
        pending, self.pending_structs = self.pending_structs, []
        for key, stmt in pending:
            fields = {}
            for f in stmt.fields:
                if f.name in fields:
                    self.error(f"struct '{stmt.name}' has two fields named '{f.name}'", stmt.line)
                    continue
                fields[f.name] = self.resolve_ann(f.type_ann, scope, stmt.line)
            self.registry[key] = fields

    def declare_func(self, stmt, scope):
        ptypes, seen = [], set()
        for p in stmt.params:
            if p.name in seen:
                self.error(f"function '{stmt.name}' has two parameters named '{p.name}'", stmt.line)
            seen.add(p.name)
            ptypes.append(self.resolve_ann(p.type_ann, scope, stmt.line))
        ret = self.resolve_ann(stmt.return_type, scope, stmt.line) if stmt.return_type else UNKNOWN
        self.declare(scope, stmt.name, ("func", ptypes, ret), stmt.line)

    def resolve_ann(self, ann, scope, line):
        line = ann.line or line
        name = ann.name
        if "." in name:
            mod_name, _, member = name.partition(".")
            b = scope.lookup(mod_name)
            if b and isinstance(b.cur, tuple) and b.cur[0] == "module":
                m = b.cur[2].get(member)
                if isinstance(m, tuple) and m[0] == "structdef":
                    base = ("struct", m[1])
                else:
                    self.error(f"module '{mod_name}' has no type '{member}'", line)
                    base = UNKNOWN
            else:
                self.error(f"'{mod_name}' is not an imported module", line,
                           f"add `use {mod_name}` first")
                base = UNKNOWN
        elif name == "list":
            if len(ann.params) != 1:
                self.error("'list' needs exactly one element type, e.g. list<int>", line)
                base = ("list", UNKNOWN)
            else:
                base = ("list", self.resolve_ann(ann.params[0], scope, line))
        elif name == "map":
            if len(ann.params) != 2:
                self.error("'map' needs a key type and a value type, e.g. map<str, int>", line)
                base = ("map", UNKNOWN, UNKNOWN)
            else:
                base = ("map", self.resolve_ann(ann.params[0], scope, line),
                        self.resolve_ann(ann.params[1], scope, line))
        elif name in _PRIMITIVES:
            if ann.params:
                self.error(f"type '{name}' does not take type arguments", line)
            base = name
        elif name in self.types:
            base = ("struct", self.types[name])
        else:
            known = list(_PRIMITIVES) + ["list", "map"] + list(self.types)
            self.error(f"unknown type '{name}'", line, _suggest(name, known))
            base = UNKNOWN
        return ("optional", base) if ann.optional and base != UNKNOWN else base

    # ----- functions

    def check_function(self, stmt, scope, update_binding):
        binding = scope.lookup(stmt.name)
        ptypes = binding.cur[1] if binding and binding.cur[0] == "func" else [UNKNOWN] * len(stmt.params)
        declared = None
        if stmt.return_type is not None and binding:
            declared = binding.cur[2]
        fscope = Scope(scope)
        for p, t in zip(stmt.params, ptypes):
            self.declare(fscope, p.name, t, stmt.line)
        frame = {"name": stmt.name, "loop": 0, "expected": declared, "returns": []}
        self.frames.append(frame)
        for s in stmt.body:
            self.check_stmt(s, fscope)
        self.frames.pop()
        falls = not block_terminates(stmt.body)

        if declared is not None:
            needs_value = not (is_permissive(declared) or is_optional(declared) or declared == NONE_T)
            if falls and needs_value:
                self.error(
                    f"'{stmt.name}' is declared to return {type_name(declared)}, "
                    f"but some paths reach the end without returning a value", stmt.line,
                    "add a `return` at the end, or declare the return type as optional "
                    f"({type_name(declared)}?)")
        else:
            inferred = self.infer_return(stmt, frame["returns"], falls)
            if update_binding and binding:
                binding.decl = binding.cur = ("func", binding.cur[1], inferred) + binding.cur[3:]

    def infer_return(self, stmt, returns, falls):
        types = [t for t, _ in returns]
        valued = [t for t in types if t != NONE_T]
        if not valued:
            return NONE_T
        known = []
        for t in valued:
            if t == UNKNOWN:
                continue
            if not any(self.same(t, k) for k in known):
                known.append(t)
        if not known:
            return UNKNOWN
        if len(known) > 1:
            names = " and ".join(type_name(k) for k in known)
            self.warn(f"'{stmt.name}' returns values of different types ({names}); "
                      f"callers will get an unchecked 'any'", stmt.line,
                      "declare a return type, e.g. `-> int`, and return that type on every path")
            return ANY
        result = known[0]
        if (NONE_T in types or falls) and not is_optional(result) and not is_permissive(result):
            result = ("optional", result)
        return result

    @staticmethod
    def same(a, b):
        return compatible(a, b) and compatible(b, a)

    # ----- statements

    def check_stmt(self, stmt, scope):
        if isinstance(stmt, A.UseStmt) and id(stmt) in self.predeclared:
            return                           # already handled when imports were hoisted
        m = getattr(self, f"check_{type(stmt).__name__}", None)
        if m is not None:
            m(stmt, scope)

    def check_block(self, block, scope):
        for s in block:
            self.check_stmt(s, scope)

    def check_LetStmt(self, stmt, scope):
        vt = self.check_expr(stmt.value, scope)
        if stmt.type_ann is not None:
            declared = self.resolve_ann(stmt.type_ann, scope, stmt.line)
            if not compatible(declared, vt):
                self.error(f"'{stmt.name}' is declared as {type_name(declared)}, but the value "
                           f"has type {type_name(vt)}", stmt.line, self.optional_hint(vt))
            t = declared
        else:
            t = vt
            if vt == NONE_T:
                self.warn(f"'{stmt.name}' starts as none, so it can never hold another type", stmt.line,
                          f"declare it as optional, e.g. `let {stmt.name}: int? = none`")
                t = ANY
            elif contains_unknown(vt):
                self.warn(f"cannot infer the element type of '{stmt.name}' from an empty collection",
                          stmt.line, f"write the type, e.g. `let {stmt.name}: list<int> = []`")
                t = self.unknown_to_any(vt)
        self.declare(scope, stmt.name, t, stmt.line, "variable")

    def unknown_to_any(self, t):
        if t == UNKNOWN:
            return ANY
        if isinstance(t, tuple):
            if t[0] in ("list", "optional"):
                return (t[0], self.unknown_to_any(t[1]))
            if t[0] == "map":
                return ("map", self.unknown_to_any(t[1]), self.unknown_to_any(t[2]))
        return t

    def check_FuncDecl(self, stmt, scope):
        if id(stmt) not in self.predeclared:
            self.declare_func(stmt, scope)
            self.check_function(stmt, scope, update_binding=True)
        else:
            self.check_function(stmt, scope, update_binding=False)

    def check_StructDecl(self, stmt, scope):
        if id(stmt) not in self.predeclared and not (stmt.name in self.registry and scope is self.module_scope):
            self.declare_struct(stmt, scope)
            self.resolve_pending_structs(scope)
        elif self.repl:
            self.declare_struct(stmt, scope)
            self.resolve_pending_structs(scope)

    def check_IfStmt(self, stmt, scope):
        accumulated = {}
        flows_out = True
        for cond, block in stmt.branches:
            cscope = Scope(scope)
            self.apply_narrowing(cscope, accumulated)
            self.check_expr(cond, cscope)
            when_true, when_false = self.narrowings(cond, cscope)
            bscope = Scope(cscope)
            self.apply_narrowing(bscope, when_true)
            self.check_block(block, bscope)
            accumulated.update(when_false)
            flows_out = flows_out and block_terminates(block, loop_exits=True)
        if stmt.else_block is not None:
            escope = Scope(scope)
            self.apply_narrowing(escope, accumulated)
            self.check_block(stmt.else_block, escope)
        if flows_out:
            # every `if` branch leaves (return/break/...): code after runs only when
            # all conditions were false, e.g. `if x == none return end` => x is not none
            self.apply_narrowing(scope, accumulated)

    def narrowings(self, cond, scope):
        if isinstance(cond, A.UnaryOp) and cond.op == "not":
            t, f = self.narrowings(cond.operand, scope)
            return f, t
        if isinstance(cond, A.BinaryOp):
            if cond.op == "and":
                tl, _ = self.narrowings(cond.left, scope)
                tr, _ = self.narrowings(cond.right, scope)
                return {**tl, **tr}, {}
            if cond.op == "or":
                _, fl = self.narrowings(cond.left, scope)
                _, fr = self.narrowings(cond.right, scope)
                return {}, {**fl, **fr}
            if cond.op in ("==", "!="):
                name = None
                if isinstance(cond.left, A.Identifier) and _is_none_literal(cond.right):
                    name = cond.left.name
                elif isinstance(cond.right, A.Identifier) and _is_none_literal(cond.left):
                    name = cond.right.name
                if name:
                    b = scope.lookup(name)
                    if b is not None and is_optional(b.cur):
                        inner = b.cur[1]
                        if cond.op == "!=":
                            return {name: inner}, {name: NONE_T}
                        return {name: NONE_T}, {name: inner}
        return {}, {}

    def apply_narrowing(self, scope, narrowed):
        for name, t in narrowed.items():
            b = scope.lookup(name)
            if b is not None:
                scope.vars[name] = Binding(b.decl, t, b.line, narrowed=True)

    def check_WhileStmt(self, stmt, scope):
        cscope = Scope(scope)
        self.check_expr(stmt.condition, cscope)
        when_true, _ = self.narrowings(stmt.condition, cscope)
        bscope = Scope(cscope)
        self.apply_narrowing(bscope, when_true)
        self.frames[-1]["loop"] += 1
        self.check_block(stmt.body, bscope)
        self.frames[-1]["loop"] -= 1

    def check_ForStmt(self, stmt, scope):
        it = self.check_expr(stmt.iterable, scope)
        if is_permissive(it):
            item = it
        elif isinstance(it, tuple) and it[0] == "list":
            item = it[1]
        elif isinstance(it, tuple) and it[0] == "map":
            item = it[1]
        elif it == "str":
            item = "str"
        else:
            self.error(f"cannot loop over a value of type {type_name(it)}", stmt.line,
                       self.optional_hint(it) or "loops work on lists, maps, texts and range(...)")
            item = UNKNOWN
        bscope = Scope(scope)
        self.declare(bscope, stmt.var_name, item, stmt.line)
        self.frames[-1]["loop"] += 1
        self.check_block(stmt.body, bscope)
        self.frames[-1]["loop"] -= 1

    def check_MatchStmt(self, stmt, scope):
        st = self.check_expr(stmt.subject, scope)
        for pattern, block in stmt.cases:
            if pattern is not None:
                pt = self.check_expr(pattern, scope)
                if not self.comparable(st, pt):
                    self.error(f"this case has type {type_name(pt)} and can never match a "
                               f"{type_name(st)}", stmt.line)
            self.check_block(block, Scope(scope))

    def check_TryStmt(self, stmt, scope):
        self.check_block(stmt.try_block, Scope(scope))
        cscope = Scope(scope)
        self.declare(cscope, stmt.err_name, ("struct", _ERROR_KEY), stmt.line)
        self.check_block(stmt.catch_block, cscope)

    def check_AssertStmt(self, stmt, scope):
        self.check_expr(stmt.expr, scope)
        if stmt.message is not None:
            self.check_expr(stmt.message, scope)

    def check_ReturnStmt(self, stmt, scope):
        vt = self.check_expr(stmt.value, scope) if stmt.value is not None else NONE_T
        frame = self.frames[-1]
        if frame["name"] is None:
            self.error("'return' can only be used inside a function", stmt.line)
            return
        frame["returns"].append((vt, stmt.line))
        expected = frame["expected"]
        if expected is not None and not compatible(expected, vt):
            self.error(f"'{frame['name']}' is declared to return {type_name(expected)}, but this "
                       f"'return' gives {type_name(vt)}", stmt.line, self.optional_hint(vt))

    def check_BreakStmt(self, stmt, scope):
        if self.frames[-1]["loop"] == 0:
            self.error("'break' can only be used inside a loop", stmt.line)

    def check_ContinueStmt(self, stmt, scope):
        if self.frames[-1]["loop"] == 0:
            self.error("'continue' can only be used inside a loop", stmt.line)

    def check_UseStmt(self, stmt, scope):
        name = stmt.alias or stmt.path.split(".")[-1]
        t = self.load_module_type(stmt.path, stmt.line)
        self.declare(scope, name, t, stmt.line)

    def check_ExprStmt(self, stmt, scope):
        self.check_expr(stmt.expr, scope)

    # ----- modules

    def load_module_type(self, path, line):
        if path in STDLIB_SIGNATURES:
            return ("module", path, dict(STDLIB_SIGNATURES[path]))
        file_path = resolver.resolve(path, self.base_dir)
        ctx = self.ctx
        if file_path is None:
            self.error(f"cannot find module '{path}'", line,
                       _suggest(path, list(STDLIB_SIGNATURES) + resolver.local_candidates(self.base_dir))
                       or f"looked for {os.path.join(self.base_dir, *path.split('.'))}.cly "
                          f"and for a dependency named '{path.split('.')[0]}' in calyre.toml")
            return UNKNOWN
        if file_path in ctx.stack:
            chain = " -> ".join(os.path.basename(p) for p in ctx.stack + [file_path])
            self.error(f"circular import: {chain}", line)
            return UNKNOWN
        info = ctx.cache.get(file_path)
        if info is None:
            info = self.analyze_module(path, file_path)
            ctx.cache[file_path] = info
        if info.errors:
            shown = "\n".join(f"      {os.path.basename(file_path)}:{d.line}: {d.message}" for d in info.errors[:3])
            more = f"\n      ... and {len(info.errors) - 3} more" if len(info.errors) > 3 else ""
            self.error(f"module '{path}' has {len(info.errors)} error(s):\n{shown}{more}", line,
                       f"run `calyre check {os.path.basename(file_path)}` to see all of them")
            return UNKNOWN
        self.registry.update(info.registry)
        return ("module", path, info.members)

    def analyze_module(self, path, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            program = parse(tokenize(source))
        except (LexError, ParseError) as e:
            return ModuleInfo({}, {}, [Diagnostic(f"syntax error: {e}", getattr(e, "line", 0))])
        sub = Checker(base_dir=os.path.dirname(file_path), ctx=self.ctx)
        self.ctx.stack.append(file_path)
        try:
            diags = sub.check_program(program)
        finally:
            self.ctx.stack.pop()
        errors = [d for d in diags if d.severity == "error"]
        local_keys = {k for k in sub.registry if "." not in k and k != _ERROR_KEY}
        registry = {}
        for key, fields in sub.registry.items():
            if key == _ERROR_KEY:
                continue
            new_key = key if "." in key else f"{path}.{key}"
            registry[new_key] = {n: _requalify(t, path, local_keys) for n, t in fields.items()}
        members = {}
        for name, b in sub.module_scope.vars.items():
            if name.startswith("_") or b.narrowed:
                continue
            members[name] = _requalify(b.cur, path, local_keys)
        return ModuleInfo(members, registry, errors)

    # ----- expressions

    def check_expr(self, node, scope):
        m = getattr(self, f"expr_{type(node).__name__}", None)
        return UNKNOWN if m is None else m(node, scope)

    def optional_hint(self, t):
        if is_optional(t):
            return "the value may be none: check `!= none` first, or use `??` to give a default"
        return None

    def comparable(self, a, b):
        if is_permissive(a) or is_permissive(b):
            return True
        if is_numeric(a) and is_numeric(b):
            return True
        a2, b2 = strip_optional(a), strip_optional(b)
        if a == NONE_T or b == NONE_T:
            return is_optional(a) or is_optional(b) or a == b
        return compatible(a2, b2) or compatible(b2, a2)

    def expr_Literal(self, node, scope):
        v = node.value
        if v is None:
            return NONE_T
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        return "str"

    def expr_InterpString(self, node, scope):
        for kind, part in node.parts:
            if kind == "expr":
                self.check_expr(part, scope)
        return "str"

    def unify(self, types, line, what):
        result = None
        for t in types:
            if result is None:
                result = t
            elif self.same(result, t):
                if contains_unknown(result) and not contains_unknown(t):
                    result = t
            elif result == NONE_T and t != NONE_T:
                result = t if is_optional(t) else ("optional", t)
            elif t == NONE_T and not is_optional(result):
                result = ("optional", result)
            elif is_optional(result) and compatible(result, t):
                pass
            else:
                self.error(f"{what} must all have the same type (found {type_name(result)} "
                           f"and {type_name(t)})", line,
                           "Calyre collections are typed; use a struct to group different kinds of values")
                return UNKNOWN
        return result

    def expr_ListLiteral(self, node, scope):
        types = [self.check_expr(e, scope) for e in node.elements]
        return ("list", UNKNOWN if not types else self.unify(types, node.line, "list elements"))

    def expr_MapLiteral(self, node, scope):
        keys, vals = [], []
        for k, v in node.pairs:
            kt = self.check_expr(k, scope)
            if isinstance(kt, tuple) and kt[0] in ("list", "map"):
                self.error("map keys must be simple values (int, str, bool, float)", node.line)
            keys.append(kt)
            vals.append(self.check_expr(v, scope))
        if not keys:
            return ("map", UNKNOWN, UNKNOWN)
        return ("map", self.unify(keys, node.line, "map keys"), self.unify(vals, node.line, "map values"))

    def expr_Identifier(self, node, scope):
        b = scope.lookup(node.name)
        if b is None:
            self.error(f"'{node.name}' is not defined", node.line, _suggest(node.name, scope.names()))
            return UNKNOWN
        return b.cur

    def expr_UnaryOp(self, node, scope):
        t = self.check_expr(node.operand, scope)
        if node.op == "not":
            return "bool"
        if is_permissive(t) or is_numeric(t):
            return t
        self.error(f"'-' expects a number, got {type_name(t)}", node.line, self.optional_hint(t))
        return UNKNOWN

    def expr_BinaryOp(self, node, scope):
        op = node.op
        lt = self.check_expr(node.left, scope)
        if op in ("and", "or"):
            # short-circuit: the right side only runs when the left was true (and) / false (or)
            when_true, when_false = self.narrowings(node.left, scope)
            rscope = Scope(scope)
            self.apply_narrowing(rscope, when_true if op == "and" else when_false)
            self.check_expr(node.right, rscope)
            return "bool"
        rt = self.check_expr(node.right, scope)
        if op == "??":
            return self.coalesce(node, lt, rt)
        if op in ("==", "!="):
            if not self.comparable(lt, rt):
                self.warn(f"comparing {type_name(lt)} with {type_name(rt)} is always "
                          f"{'false' if op == '==' else 'true'}", node.line)
            return "bool"

        if is_permissive(lt) or is_permissive(rt):
            if op in ("<", ">", "<=", ">="):
                return "bool"
            if op == "/":
                return "float"
            if lt == ANY or rt == ANY:
                return ANY
            return UNKNOWN

        if op == "+":
            if lt == "str" and rt == "str":
                return "str"
            if isinstance(lt, tuple) and lt[0] == "list" and isinstance(rt, tuple) and rt[0] == "list":
                if compatible(lt, rt) or compatible(rt, lt):
                    return lt if not contains_unknown(lt) else rt
                self.error(f"cannot join {type_name(lt)} with {type_name(rt)}", node.line)
                return UNKNOWN
            if "str" in (lt, rt) and (is_numeric(lt) or is_numeric(rt) or lt == "bool" or rt == "bool"):
                self.error(f"'+' cannot join {type_name(lt)} with {type_name(rt)}", node.line,
                           "convert with str(value), or use interpolation: \"text {value}\"")
                return UNKNOWN
        if op in ("+", "-", "*", "/", "%", "<", ">", "<=", ">="):
            if not (is_numeric(lt) and is_numeric(rt)):
                self.error(f"'{op}' cannot be used between {type_name(lt)} and {type_name(rt)}",
                           node.line, self.optional_hint(lt) or self.optional_hint(rt))
                return UNKNOWN
            if lt != rt:
                self.error(f"Calyre never mixes int and float automatically: left is {type_name(lt)}, "
                           f"right is {type_name(rt)}", node.line,
                           "convert one side explicitly: float(x) or int(x)")
                return UNKNOWN
            if op in ("<", ">", "<=", ">="):
                return "bool"
            return "float" if op == "/" else lt
        return UNKNOWN

    def coalesce(self, node, lt, rt):
        if is_permissive(lt):
            return rt
        if lt == NONE_T:
            return rt
        if not is_optional(lt):
            self.warn(f"the left side of '??' is {type_name(lt)}, which is never none", node.line,
                      "the fallback will never be used")
            return lt
        inner = lt[1]
        if rt == NONE_T:
            return lt
        if is_optional(rt):
            if compatible(inner, rt[1]):
                return lt
        elif compatible(inner, rt):
            return inner
        self.error(f"the fallback of '??' has type {type_name(rt)}, but the value is {type_name(lt)}",
                   node.line, f"use a fallback of type {type_name(inner)}")
        return inner

    def expr_Call(self, node, scope):
        ct = self.check_expr(node.callee, scope)
        arg_types = [(a.name, self.check_expr(a.value, scope)) for a in node.args]
        name = node.callee.name if isinstance(node.callee, A.Identifier) else (
            node.callee.name if isinstance(node.callee, A.Get) else "function")

        if is_permissive(ct):
            return ct
        if not isinstance(ct, tuple):
            self.error(f"cannot call a value of type {type_name(ct)}", node.line)
            return UNKNOWN
        if ct[0] == "structdef":
            return self.construct(node, ct[1], arg_types)
        if ct[0] == "builtin":
            return self.call_builtin(node, ct[1], arg_types)
        if ct[0] == "func":
            return self.call_func(node, name, ct, arg_types)
        self.error(f"cannot call a value of type {type_name(ct)}", node.line)
        return UNKNOWN

    def call_func(self, node, name, ft, arg_types):
        params, ret = ft[1], ft[2]
        variadic = len(ft) > 3 and ft[3]
        if any(n is not None for n, _ in arg_types):
            self.error(f"'{name}' does not take named arguments", node.line,
                       "named arguments are only used to build structs")
            return ret
        n = len(arg_types)
        if n < len(params) or (n > len(params) and not variadic):
            self.error(f"'{name}' expects {len(params)} argument(s), got {n}", node.line)
            return ret
        for i, (expected, (_, actual)) in enumerate(zip(params, arg_types), 1):
            if not compatible(expected, actual):
                self.error(f"argument {i} of '{name}' expects {type_name(expected)}, "
                           f"got {type_name(actual)}", node.line, self.optional_hint(actual))
        return ret

    def call_builtin(self, node, name, arg_types):
        lo, hi, params, ret = BUILTIN_SPECS[name]
        n = len(arg_types)
        if any(nm is not None for nm, _ in arg_types):
            self.error(f"'{name}' does not take named arguments", node.line)
        elif n < lo or (hi is not None and n > hi):
            want = f"{lo}" if lo == hi else f"{lo} to {hi if hi is not None else 'any number of'}"
            self.error(f"'{name}' expects {want} argument(s), got {n}", node.line)
        elif params:
            for i, (expected, (_, actual)) in enumerate(zip(params, arg_types), 1):
                if not compatible(expected, actual):
                    self.error(f"argument {i} of '{name}' expects {type_name(expected)}, "
                               f"got {type_name(actual)}", node.line, self.optional_hint(actual))
        if name == "len" and len(arg_types) == 1:
            t = arg_types[0][1]
            if not is_permissive(t) and not (t == "str" or (isinstance(t, tuple) and t[0] in ("list", "map"))):
                self.error(f"'len' works on texts, lists and maps, not {type_name(t)}", node.line,
                           self.optional_hint(t))
        return ret

    def construct(self, node, key, arg_types):
        fields = self.registry.get(key, {})
        display = type_name(("struct", key))
        seen = set()
        for (nm, actual) in arg_types:
            if nm is None:
                self.error(f"building a '{display}' needs named arguments, e.g. "
                           f"{display.split('.')[-1]}(field: value)", node.line)
            elif nm not in fields:
                self.error(f"'{display}' has no field '{nm}'", node.line, _suggest(nm, fields))
            elif nm in seen:
                self.error(f"field '{nm}' is given twice", node.line)
            else:
                seen.add(nm)
                if not compatible(fields[nm], actual):
                    self.error(f"field '{nm}' of '{display}' expects {type_name(fields[nm])}, got "
                               f"{type_name(actual)}", node.line, self.optional_hint(actual))
        missing = [f for f in fields if f not in seen]
        if missing and all(nm is not None for nm, _ in arg_types):
            self.error(f"missing field(s) when building '{display}': {', '.join(missing)}", node.line)
        return ("struct", key)

    def expr_Get(self, node, scope):
        ot = self.check_expr(node.obj, scope)
        if is_permissive(ot):
            return ot
        if isinstance(ot, tuple) and ot[0] == "struct":
            fields = self.registry.get(ot[1], {})
            if node.name in fields:
                return fields[node.name]
            self.error(f"'{type_name(ot)}' has no field '{node.name}'", node.line, _suggest(node.name, fields))
            return UNKNOWN
        if isinstance(ot, tuple) and ot[0] == "module":
            members = ot[2]
            if node.name.startswith("_"):
                self.error(f"'{node.name}' is private to module '{ot[1]}'", node.line,
                           "names starting with '_' are not exported")
                return UNKNOWN
            if node.name not in members:
                self.error(f"module '{ot[1]}' has no member '{node.name}'", node.line,
                           _suggest(node.name, [m for m in members if not m.startswith("_")]))
                return UNKNOWN
            return members[node.name]
        self.error(f"'.{node.name}' cannot be used on a value of type {type_name(ot)}", node.line,
                   self.optional_hint(ot))
        return UNKNOWN

    def expr_Index(self, node, scope):
        ot = self.check_expr(node.obj, scope)
        it = self.check_expr(node.index, scope)
        if is_permissive(ot):
            return ot
        if isinstance(ot, tuple) and ot[0] == "list" or ot == "str":
            if not compatible("int", it):
                self.error(f"an index must be an int, got {type_name(it)}", node.line)
            return "str" if ot == "str" else ot[1]
        if isinstance(ot, tuple) and ot[0] == "map":
            if not compatible(ot[1], it):
                self.error(f"this map has {type_name(ot[1])} keys, but the key is {type_name(it)}", node.line)
            return ot[2]
        self.error(f"a value of type {type_name(ot)} cannot be indexed", node.line, self.optional_hint(ot))
        return UNKNOWN

    def expr_Assign(self, node, scope):
        vt = self.check_expr(node.value, scope)
        target = node.target
        if isinstance(target, A.Identifier):
            b = scope.lookup(target.name)
            if b is None:
                self.error(f"cannot assign to '{target.name}' before declaring it", node.line,
                           f"declare it first: let {target.name} = ...")
            elif isinstance(b.decl, tuple) and b.decl[0] in ("func", "structdef", "module", "builtin"):
                self.error(f"'{target.name}' is a {type_name(b.decl).split()[0]}, not a variable", node.line)
            else:
                if not compatible(b.decl, vt):
                    self.error(f"cannot assign {type_name(vt)} to '{target.name}', which is "
                               f"{type_name(b.decl)}", node.line, self.optional_hint(vt))
                s = scope                     # a write invalidates `!= none` narrowing
                while s is not None:
                    local = s.vars.get(target.name)
                    if local is not None:
                        if local.narrowed:
                            local.cur = local.decl
                        else:
                            break
                    s = s.parent
        elif isinstance(target, A.Get):
            ot = self.check_expr(target.obj, scope)
            if isinstance(ot, tuple) and ot[0] == "struct":
                fields = self.registry.get(ot[1], {})
                if target.name not in fields:
                    self.error(f"'{type_name(ot)}' has no field '{target.name}'", node.line,
                               _suggest(target.name, fields))
                elif not compatible(fields[target.name], vt):
                    self.error(f"field '{target.name}' is {type_name(fields[target.name])}, cannot assign "
                               f"{type_name(vt)}", node.line, self.optional_hint(vt))
            elif isinstance(ot, tuple) and ot[0] == "module":
                self.error("module members cannot be reassigned from outside the module", node.line)
            elif not is_permissive(ot):
                self.error(f"'.{target.name}' cannot be assigned on a value of type {type_name(ot)}", node.line)
        elif isinstance(target, A.Index):
            ot = self.check_expr(target.obj, scope)
            it = self.check_expr(target.index, scope)
            if isinstance(ot, tuple) and ot[0] == "list":
                if not compatible("int", it):
                    self.error(f"an index must be an int, got {type_name(it)}", node.line)
                if not compatible(ot[1], vt):
                    self.error(f"this list holds {type_name(ot[1])}, cannot store {type_name(vt)}", node.line)
            elif isinstance(ot, tuple) and ot[0] == "map":
                if not compatible(ot[1], it):
                    self.error(f"this map has {type_name(ot[1])} keys, but the key is {type_name(it)}", node.line)
                if not compatible(ot[2], vt):
                    self.error(f"this map holds {type_name(ot[2])}, cannot store {type_name(vt)}", node.line)
            elif not is_permissive(ot):
                self.error(f"a value of type {type_name(ot)} cannot be assigned by index", node.line)
        return vt


# ---------------------------------------------------------------- API

def analyze(program, base_dir=None):
    """Return (errors, warnings) for a parsed program."""
    diags = Checker(base_dir=base_dir).check_program(program)
    return ([d for d in diags if d.severity == "error"],
            [d for d in diags if d.severity == "warning"])


def check(program, base_dir=None):
    """Return only the errors (kept for backwards compatibility)."""
    return analyze(program, base_dir)[0]
