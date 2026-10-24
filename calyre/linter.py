"""
`calyre lint`: scope-aware checks for code that is legal but probably not what you meant.

Rules (kebab-case names; disable with `[lint] disable = [...]` in calyre.toml, `--disable a,b`,
or per line with a `// lint-ignore` / `// lint-ignore: rule, rule` comment on that line or above it):

  unused-variable        a local `let` that is never read              (prefix with _ to silence)
  unused-import          a `use` that is never referenced
  unused-function        a private function that is never referenced
  unreachable-code       statements after return / break / continue / error(...)
  shadowed-builtin       a name that hides print, len, str, ...
  naming-convention      snake_case for functions/variables, PascalCase for structs
  compare-to-bool        `x == true` / `x != false`
  constant-condition     `if true`, `if false`, `x == x`
  library-without-pub    a file that only declares things but exports them all by the legacy rule
  pub-missing-return-type  a `pub` function that returns a value but declares no return type
  sql-injection-risk     a query built by joining text or interpolating values: use `?` parameters

The checker's own warnings (empty collections, ...) are reported too, under `type-check`.
Every rule is meant to have near-zero false positives; when in doubt a rule stays silent.
"""

import os
import re

from . import ast_nodes as A
from .calyre_parser import parse
from .lexer import tokenize
from .stdlib_types import BUILTIN_SPECS
from .typechecker import _stmt_terminates, analyze

RULES = ("unused-variable", "unused-import", "unused-function", "unreachable-code", "shadowed-builtin",
         "naming-convention", "compare-to-bool", "constant-condition", "library-without-pub",
         "pub-missing-return-type", "sql-injection-risk")

_SNAKE = re.compile(r"^_*[a-z][a-z0-9]*(_[a-z0-9]+)*_*$|^_+$")
_UPPER_CONST = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")
_PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_IGNORE = re.compile(r"lint-ignore(?::\s*([\w\-,\s]+))?")


class LintDiagnostic:
    def __init__(self, rule, message, node, hint=None, severity="warning"):
        self.rule, self.message, self.hint, self.severity = rule, message, hint, severity
        self.line = getattr(node, "line", node if isinstance(node, int) else 0)
        self.col = getattr(node, "col", 0)

    def format(self, path):
        pos = f"{self.line}:{self.col}" if self.col else f"{self.line}"
        text = f"{path}:{pos}: {self.severity}: [{self.rule}] {self.message}"
        return text + (f"\n    hint: {self.hint}" if self.hint else "")


class _Info:
    __slots__ = ("kind", "node", "used")

    def __init__(self, kind, node):
        self.kind, self.node, self.used = kind, node, False


class _Scope:
    def __init__(self, parent=None, local=False):
        self.vars, self.parent, self.local = {}, parent, local

    def lookup(self, name):
        s = self
        while s is not None:
            if name in s.vars:
                return s.vars[name]
            s = s.parent
        return None


class _Linter:
    def __init__(self, program, path):
        self.program, self.path = program, path
        self.out = []
        self.deferred = []
        self.module = _Scope()
        self.explicit = any(getattr(s, "public", False) for s in program.statements)

    def add(self, rule, message, node, hint=None):
        self.out.append(LintDiagnostic(rule, message, node, hint))

    # ---- driver
    def run(self):
        stmts = self.program.statements
        for s in stmts:                                   # hoisted declarations
            if isinstance(s, A.UseStmt):
                self.declare_use(s, self.module)
            elif isinstance(s, A.FuncDecl):
                self.declare(self.module, s.name, "func", s)
                self.module.vars[s.name].used = s.public
            elif isinstance(s, A.StructDecl):
                self.declare(self.module, s.name, "struct", s)
                self.module.vars[s.name].used = s.public
        self.block(stmts, self.module, top=True)
        while self.deferred:
            fn, scope = self.deferred.pop(0)
            self.function_body(fn, scope)
        self.report_module_level()
        self.file_level_rules()
        return self.out

    def declare(self, scope, name, kind, node):
        info = _Info(kind, node)
        scope.vars.setdefault(name, info)
        return info

    def declare_use(self, s, scope):
        if s.names is not None:
            for name, alias in s.names:
                self.declare(scope, alias or name, "import", s)
        else:
            self.declare(scope, s.alias or s.default_name(), "import", s)

    # ---- blocks and statements
    def block(self, stmts, scope, top=False):
        for i, s in enumerate(stmts):
            if i > 0 and _stmt_terminates(stmts[i - 1], True):
                self.add("unreachable-code", "this code can never run", s,
                         "it comes after a return, break, continue or error(...)")
                break
            self.stmt(s, scope, top)

    def child(self, scope, local=True):
        return _Scope(scope, local or scope.local)

    def close(self, scope):
        if not scope.local:
            return
        for name, info in scope.vars.items():
            if info.kind == "var" and not info.used and not name.startswith("_"):
                self.add("unused-variable", f"'{name}' is never used", info.node,
                         "remove it, or start the name with _ if that is intentional")

    def stmt(self, s, scope, top):
        getattr(self, f"s_{type(s).__name__}", lambda *a: None)(s, scope, top)

    def s_LetStmt(self, s, scope, top):
        self.expr(s.value, scope)
        self.types(s.type_ann, scope)
        self.check_name(s.name, s, "let", constant_ok=top)
        if s.name in BUILTIN_SPECS:
            self.add("shadowed-builtin", f"'{s.name}' hides the builtin of the same name", s)
        info = self.declare(scope, s.name, "var", s)
        if top and not scope.local:
            info.used = True                       # module-level lets may be exported / used by importers

    def s_FuncDecl(self, s, scope, top):
        if scope is not self.module:
            self.declare(scope, s.name, "func", s)
            scope.vars[s.name].used = True
        self.check_name(s.name, s, "function")
        if s.name in BUILTIN_SPECS and scope is self.module:
            self.add("shadowed-builtin", f"'{s.name}' hides the builtin of the same name", s)
        for p in s.params:
            self.types(p.type_ann, scope)
        self.types(s.return_type, scope)
        if s.public and s.return_type is None and self.returns_value(s.body):
            self.add("pub-missing-return-type", f"public function '{s.name}' returns a value but has no return type",
                     s, "declare it so importers can rely on it, e.g. `-> int`")
        self.deferred.append((s, scope))

    def function_body(self, s, scope):
        fscope = _Scope(scope, True)
        for p in s.params:
            info = self.declare(fscope, p.name, "param", s)
            info.used = True
            self.check_name(p.name, s, "parameter")
        self.block(s.body, fscope)
        self.close(fscope)

    def s_StructDecl(self, s, scope, top):
        if scope is not self.module:
            self.declare(scope, s.name, "struct", s)
            scope.vars[s.name].used = True
        if not _PASCAL.match(s.name):
            self.add("naming-convention", f"struct '{s.name}' should be written in PascalCase", s)
        for f in s.fields:
            self.types(f.type_ann, scope)

    def s_UseStmt(self, s, scope, top):
        if scope is not self.module:
            self.declare_use(s, scope)

    def s_ExprStmt(self, s, scope, top):
        self.expr(s.expr, scope)

    def s_ReturnStmt(self, s, scope, top):
        if s.value is not None:
            self.expr(s.value, scope)

    def s_AssertStmt(self, s, scope, top):
        self.expr(s.expr, scope)
        if s.message is not None:
            self.expr(s.message, scope)

    def s_IfStmt(self, s, scope, top):
        for cond, body in s.branches:
            self.expr(cond, scope)
            if isinstance(cond, A.Literal) and isinstance(cond.value, bool):
                self.add("constant-condition", f"this condition is always {'true' if cond.value else 'false'}", cond)
            inner = self.child(scope)
            self.block(body, inner)
            self.close(inner)
        if s.else_block is not None:
            inner = self.child(scope)
            self.block(s.else_block, inner)
            self.close(inner)

    def s_WhileStmt(self, s, scope, top):
        self.expr(s.condition, scope)
        if isinstance(s.condition, A.Literal) and s.condition.value is False:
            self.add("constant-condition", "this loop never runs: the condition is always false", s.condition)
        inner = self.child(scope)
        self.block(s.body, inner)
        self.close(inner)

    def s_ForStmt(self, s, scope, top):
        self.expr(s.iterable, scope)
        inner = self.child(scope)
        self.declare(inner, s.var_name, "loopvar", s)
        self.block(s.body, inner)
        self.close(inner)

    def s_MatchStmt(self, s, scope, top):
        self.expr(s.subject, scope)
        for pattern, body in s.cases:
            if pattern is not None:
                self.expr(pattern, scope)
            inner = self.child(scope)
            self.block(body, inner)
            self.close(inner)

    def s_TryStmt(self, s, scope, top):
        inner = self.child(scope)
        self.block(s.try_block, inner)
        self.close(inner)
        inner = self.child(scope)
        self.declare(inner, s.err_name, "loopvar", s)
        self.block(s.catch_block, inner)
        self.close(inner)

    # ---- expressions and types
    def types(self, t, scope):
        if t is None:
            return
        head = t.name.split(".")[0]
        info = scope.lookup(head)
        if info:
            info.used = True
        for p in t.params:
            self.types(p, scope)

    def use_name(self, name, scope):
        info = scope.lookup(name)
        if info:
            info.used = True

    def expr(self, n, scope):
        if isinstance(n, A.Identifier):
            self.use_name(n.name, scope)
        elif isinstance(n, A.InterpString):
            for kind, part in n.parts:
                if kind == "expr":
                    self.expr(part, scope)
        elif isinstance(n, A.ListLiteral):
            for e in n.elements:
                self.expr(e, scope)
        elif isinstance(n, A.MapLiteral):
            for k, v in n.pairs:
                self.expr(k, scope)
                self.expr(v, scope)
        elif isinstance(n, A.UnaryOp):
            self.expr(n.operand, scope)
        elif isinstance(n, A.BinaryOp):
            self.expr(n.left, scope)
            self.expr(n.right, scope)
            self.binary_rules(n)
        elif isinstance(n, A.Call):
            self.sql_rule(n)
            self.expr(n.callee, scope)
            for a in n.args:
                self.expr(a.value, scope)
        elif isinstance(n, A.Get):
            self.expr(n.obj, scope)
        elif isinstance(n, A.Index):
            self.expr(n.obj, scope)
            self.expr(n.index, scope)
        elif isinstance(n, A.Assign):
            self.expr(n.value, scope)
            if isinstance(n.target, A.Identifier):
                pass                                   # a write is not a use
            else:
                self.expr(n.target, scope)

    _SQL_METHODS = ("execute", "query", "query_one")

    def sql_rule(self, call):
        """db.execute("... " + value) / db.query("... {value}"): values must be `?` parameters."""
        if not (isinstance(call.callee, A.Get) and call.callee.name in self._SQL_METHODS and call.args):
            return
        q = call.args[0].value
        built = (isinstance(q, A.BinaryOp) and q.op == "+" and not (
                    isinstance(q.left, A.Literal) and isinstance(q.right, A.Literal))) or \
                (isinstance(q, A.InterpString) and any(k == "expr" for k, _ in q.parts))
        if built:
            self.add("sql-injection-risk", "this query is built from text pieces, which allows SQL injection",
                     q, 'write the values as ? placeholders and pass them in a list: '
                        'db.query("SELECT * FROM t WHERE id = ?", [id])')

    def binary_rules(self, n):
        if n.op in ("==", "!="):
            for side in (n.left, n.right):
                if isinstance(side, A.Literal) and isinstance(side.value, bool):
                    want = (side.value is True) == (n.op == "==")
                    self.add("compare-to-bool", "comparing a bool with true/false is redundant", n,
                             "write the condition itself" + ("" if want else ", with `not`"))
                    return
            if isinstance(n.left, A.Identifier) and isinstance(n.right, A.Identifier) and n.left.name == n.right.name:
                self.add("constant-condition", f"'{n.left.name}' is compared with itself", n)

    # ---- naming, returns
    def check_name(self, name, node, what, constant_ok=False):
        if _SNAKE.match(name) or (constant_ok and _UPPER_CONST.match(name)):
            return
        self.add("naming-convention", f"{what} '{name}' should be written in snake_case", node,
                 "functions and variables use lower_case_with_underscores"
                 + (" (constants may be UPPER_CASE)" if constant_ok else ""))

    def returns_value(self, body):
        for s in body:
            if isinstance(s, A.ReturnStmt) and s.value is not None:
                return True
            if isinstance(s, A.FuncDecl):
                continue
            for inner in _inner_blocks(s):
                if self.returns_value(inner):
                    return True
        return False

    # ---- module-level reports
    def report_module_level(self):
        for name, info in self.module.vars.items():
            if info.used or name.startswith("_") and info.kind == "import":
                continue
            if info.kind == "import":
                self.add("unused-import", f"'{name}' is imported but never used", info.node,
                         "remove the `use`, or use the module")
            elif info.kind == "func":
                fn = info.node
                if fn.name.startswith("test_") or fn.public:
                    continue
                if fn.name.startswith("_") or self.explicit:
                    self.add("unused-function", f"function '{name}' is never used", fn,
                             "remove it, or mark it `pub` if other files should call it")

    def file_level_rules(self):
        stmts = self.program.statements
        base = os.path.basename(self.path or "")
        if self.explicit or not stmts or base == "main.cly" or base.startswith("test_") or base.endswith("_test.cly"):
            return
        decls = [s for s in stmts if isinstance(s, (A.FuncDecl, A.StructDecl))]
        only_declarations = all(isinstance(s, (A.FuncDecl, A.StructDecl, A.UseStmt, A.LetStmt)) for s in stmts)
        if decls and only_declarations and any(not d.name.startswith("_") for d in decls):
            self.add("library-without-pub",
                     "this file only declares things but exports every one of them (no `pub` anywhere)",
                     decls[0], "add `pub` before what other files should use; the rest becomes private")


def _inner_blocks(s):
    if isinstance(s, A.IfStmt):
        for _, b in s.branches:
            yield b
        if s.else_block is not None:
            yield s.else_block
    elif isinstance(s, (A.WhileStmt, A.ForStmt)):
        yield s.body
    elif isinstance(s, A.MatchStmt):
        for _, b in s.cases:
            yield b
    elif isinstance(s, A.TryStmt):
        yield s.try_block
        yield s.catch_block


def _ignores(comments):
    """line -> set of rule names ({'*'} = all) suppressed on that line."""
    out = {}
    for c in comments:
        m = _IGNORE.search(c.text)
        if not m:
            continue
        rules = {r.strip() for r in m.group(1).split(",") if r.strip()} if m.group(1) else {"*"}
        target = c.line + 1 if c.own_line else c.line
        out.setdefault(target, set()).update(rules)
    return out


def load_config(start_dir):
    """The `[lint] disable = [...]` list of the nearest calyre.toml."""
    from . import resolver
    manifest = resolver.find_manifest(start_dir)
    if not manifest:
        return set()
    import tomllib
    try:
        with open(manifest, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    disabled = data.get("lint", {}).get("disable", [])
    return set(disabled) if isinstance(disabled, list) else set()


def lint_source(source, path="<source>", disabled=()):
    """Return (type_errors, diagnostics): type-check errors, then lint + checker warnings."""
    comments = []
    program = parse(tokenize(source, comments))
    base = os.path.dirname(os.path.abspath(path)) if path != "<source>" else None
    errors, warnings = analyze(program, base_dir=base)
    diags = [LintDiagnostic("type-check", w.message, w.line if not w.col else _Pos(w.line, w.col), w.hint)
             for w in warnings]
    diags += _Linter(program, path).run()
    ignored = _ignores(comments)
    disabled = set(disabled)
    kept = []
    for d in diags:
        if d.rule in disabled:
            continue
        marks = ignored.get(d.line, ())
        if "*" in marks or d.rule in marks:
            continue
        kept.append(d)
    kept.sort(key=lambda d: (d.line, d.col, d.rule))
    return errors, kept


class _Pos:
    def __init__(self, line, col):
        self.line, self.col = line, col
