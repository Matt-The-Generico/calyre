"""
Calyre static type checker.

Walks the AST *before* execution and reports type errors the way a
careful teacher would: what went wrong, where, and (when possible) how to
fix it. It intentionally does not try to verify everything — see the
module docstring in `types.py` for why unresolved things become `any`.

Usage:

    errors = check(program)
    if errors:
        ... print them, don't run the program ...
"""

from . import ast_nodes as A
from .types import (
    ANY, NONE_T, type_name, compatible, resolve_type_ann, is_numeric, is_optional,
)


class TypeCheckError:
    def __init__(self, message, line):
        self.message = message
        self.line = line

    def __str__(self):
        loc = f"[linha {self.line}] " if self.line is not None else ""
        return f"{loc}Erro de tipo: {self.message}"


class TypeEnv:
    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def define(self, name, t):
        self.vars[name] = t

    def get(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        return None


_BUILTIN_RETURN_TYPES = {
    "print": NONE_T,
    "str": "str",
    "int": "int",
    "float": "float",
    "len": "int",
    "range": ("list", "int"),
    "input": "str",
    "input_int": "int",
    "input_float": "float",
    "input_bool": "bool",
    "error": NONE_T,
}


class Checker:
    def __init__(self):
        self.errors = []
        self.struct_registry = {}
        self.return_stack = []   # expected return type of the innermost func being checked

    def check_program(self, program: A.Program):
        env = TypeEnv()
        for name in _BUILTIN_RETURN_TYPES:
            env.define(name, ANY)

        for stmt in program.statements:
            if isinstance(stmt, A.StructDecl):
                self._register_struct(stmt)
        self._resolve_struct_fields()
        for stmt in program.statements:
            if isinstance(stmt, A.FuncDecl):
                self._register_func_sig(stmt, env)

        for stmt in program.statements:
            self.check_stmt(stmt, env)

        return self.errors

    def error(self, message, line):
        self.errors.append(TypeCheckError(message, line))

    def _register_struct(self, stmt: A.StructDecl):
        if stmt.name in self.struct_registry:
            self.error(f"struct '{stmt.name}' is declared more than once", stmt.line)
            return
        fields = {}
        for f in stmt.fields:
            fields[f.name] = f.type_ann
        self.struct_registry[stmt.name] = fields

    def _resolve_struct_fields(self):
        resolved = {}
        for name, fields in self.struct_registry.items():
            resolved[name] = {
                fname: resolve_type_ann(fann, self.struct_registry)
                for fname, fann in fields.items()
            }
        self.struct_registry = resolved

    def _register_func_sig(self, stmt: A.FuncDecl, env):
        param_types = [resolve_type_ann(p.type_ann, self.struct_registry) for p in stmt.params]
        return_type = resolve_type_ann(stmt.return_type, self.struct_registry) if stmt.return_type else ANY
        env.define(stmt.name, ("func", param_types, return_type))

    def check_stmt(self, stmt, env):
        method = getattr(self, f"check_{type(stmt).__name__}", None)
        if method is None:
            return
        method(stmt, env)

    def check_LetStmt(self, stmt: A.LetStmt, env):
        value_t = self.check_expr(stmt.value, env)
        if stmt.type_ann is not None:
            declared = resolve_type_ann(stmt.type_ann, self.struct_registry)
            if not compatible(declared, value_t):
                self.error(
                    f"'{stmt.name}' is declared as {type_name(declared)}, but is being "
                    f"initialized with a value of type {type_name(value_t)}",
                    stmt.line,
                )
            env.define(stmt.name, declared)
        else:
            env.define(stmt.name, value_t)

    def check_FuncDecl(self, stmt: A.FuncDecl, env):
        func_t = env.get(stmt.name)
        _, param_types, return_type = func_t if func_t else (None, [], ANY)
        body_env = TypeEnv(env)
        for p, pt in zip(stmt.params, param_types):
            body_env.define(p.name, pt)
        self.return_stack.append((return_type, stmt.name))
        for s in stmt.body:
            self.check_stmt(s, body_env)
        self.return_stack.pop()

    def check_StructDecl(self, stmt: A.StructDecl, env):
        pass

    def check_IfStmt(self, stmt: A.IfStmt, env):
        for cond, block in stmt.branches:
            self.check_expr(cond, env)
            block_env = TypeEnv(env)
            for s in block:
                self.check_stmt(s, block_env)
        if stmt.else_block is not None:
            block_env = TypeEnv(env)
            for s in stmt.else_block:
                self.check_stmt(s, block_env)

    def check_WhileStmt(self, stmt: A.WhileStmt, env):
        self.check_expr(stmt.condition, env)
        block_env = TypeEnv(env)
        for s in stmt.body:
            self.check_stmt(s, block_env)

    def check_ForStmt(self, stmt: A.ForStmt, env):
        iterable_t = self.check_expr(stmt.iterable, env)
        if isinstance(iterable_t, tuple) and iterable_t[0] == "list":
            item_t = iterable_t[1]
        elif iterable_t == "str":
            item_t = "str"
        elif isinstance(iterable_t, tuple) and iterable_t[0] == "map":
            item_t = iterable_t[1]
        else:
            item_t = ANY
        block_env = TypeEnv(env)
        block_env.define(stmt.var_name, item_t)
        for s in stmt.body:
            self.check_stmt(s, block_env)

    def check_MatchStmt(self, stmt: A.MatchStmt, env):
        self.check_expr(stmt.subject, env)
        for pattern, block in stmt.cases:
            if pattern is not None:
                self.check_expr(pattern, env)
            block_env = TypeEnv(env)
            for s in block:
                self.check_stmt(s, block_env)

    def check_TryStmt(self, stmt: A.TryStmt, env):
        try_env = TypeEnv(env)
        for s in stmt.try_block:
            self.check_stmt(s, try_env)
        catch_env = TypeEnv(env)
        self.struct_registry.setdefault("Error", {"message": "str", "line": ("optional", "int")})
        catch_env.define(stmt.err_name, ("struct", "Error"))
        for s in stmt.catch_block:
            self.check_stmt(s, catch_env)

    def check_AssertStmt(self, stmt: A.AssertStmt, env):
        self.check_expr(stmt.expr, env)
        if stmt.message is not None:
            self.check_expr(stmt.message, env)

    def check_ReturnStmt(self, stmt: A.ReturnStmt, env):
        actual = self.check_expr(stmt.value, env) if stmt.value is not None else NONE_T
        if self.return_stack:
            expected_return, func_name = self.return_stack[-1]
            if expected_return != ANY and not compatible(expected_return, actual):
                self.error(
                    f"'{func_name}' is declared to return {type_name(expected_return)}, "
                    f"but this 'return' gives a value of type {type_name(actual)}",
                    stmt.line,
                )

    def check_BreakStmt(self, stmt, env):
        pass

    def check_ContinueStmt(self, stmt, env):
        pass

    def check_UseStmt(self, stmt: A.UseStmt, env):
        bound_name = stmt.alias or stmt.path.split(".")[-1]
        env.define(bound_name, ANY)

    def check_ExprStmt(self, stmt: A.ExprStmt, env):
        self.check_expr(stmt.expr, env)

    def check_expr(self, node, env):
        method = getattr(self, f"check_expr_{type(node).__name__}", None)
        if method is None:
            return ANY
        return method(node, env)

    def check_expr_Literal(self, node: A.Literal, env):
        v = node.value
        if v is None:
            return NONE_T
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        if isinstance(v, str):
            return "str"
        return ANY

    def check_expr_InterpString(self, node: A.InterpString, env):
        for kind, part in node.parts:
            if kind == "expr":
                self.check_expr(part, env)
        return "str"

    def check_expr_ListLiteral(self, node: A.ListLiteral, env):
        elem_types = {self.check_expr(e, env) for e in node.elements}
        if len(elem_types) == 1:
            return ("list", elem_types.pop())
        return ("list", ANY)

    def check_expr_MapLiteral(self, node: A.MapLiteral, env):
        key_types, val_types = set(), set()
        for k, v in node.pairs:
            key_types.add(self.check_expr(k, env))
            val_types.add(self.check_expr(v, env))
        key_t = key_types.pop() if len(key_types) == 1 else ANY
        val_t = val_types.pop() if len(val_types) == 1 else ANY
        return ("map", key_t, val_t)

    def check_expr_Identifier(self, node: A.Identifier, env):
        t = env.get(node.name)
        if t is None:
            self.error(f"'{node.name}' is not defined", node.line)
            return ANY
        return t

    def check_expr_UnaryOp(self, node: A.UnaryOp, env):
        t = self.check_expr(node.operand, env)
        if node.op == "not":
            return "bool"
        if node.op == "-":
            if t != ANY and not is_numeric(t):
                self.error(f"'-' expects a number, got {type_name(t)}", node.line)
                return ANY
            return t
        return ANY

    def check_expr_BinaryOp(self, node: A.BinaryOp, env):
        op = node.op
        left = self.check_expr(node.left, env)
        right = self.check_expr(node.right, env)

        if op in ("and", "or"):
            return "bool"
        if op in ("==", "!="):
            return "bool"

        if op == "+":
            if left == ANY or right == ANY:
                return left if left != ANY else right
            if left == "str" and right == "str":
                return "str"
            if isinstance(left, tuple) and left[0] == "list" and isinstance(right, tuple) and right[0] == "list":
                return ("list", left[1] if left[1] == right[1] else ANY)
            if is_numeric(left) and is_numeric(right):
                if left != right:
                    self.error(
                        "Calyre does not mix int and float automatically — "
                        f"left side is {type_name(left)}, right side is {type_name(right)}. "
                        "Convert one of them explicitly (e.g. float(x) or int(x))",
                        node.line,
                    )
                    return ANY
                return left
            self.error(
                f"'+' cannot be used between {type_name(left)} and {type_name(right)}",
                node.line,
            )
            return ANY

        if op in ("-", "*", "/", "%"):
            if left == ANY or right == ANY:
                return left if left != ANY else right
            if not is_numeric(left) or not is_numeric(right):
                self.error(
                    f"'{op}' expects two numbers, got {type_name(left)} and {type_name(right)}",
                    node.line,
                )
                return ANY
            if left != right:
                self.error(
                    "Calyre does not mix int and float automatically — "
                    f"left side is {type_name(left)}, right side is {type_name(right)}. "
                    "Convert one of them explicitly (e.g. float(x) or int(x))",
                    node.line,
                )
                return ANY
            return left

        if op in ("<", ">", "<=", ">="):
            if left == ANY or right == ANY:
                return "bool"
            if not is_numeric(left) or not is_numeric(right):
                self.error(
                    f"'{op}' expects two numbers, got {type_name(left)} and {type_name(right)}",
                    node.line,
                )
            elif left != right:
                self.error(
                    "Calyre does not mix int and float automatically in comparisons — "
                    f"left side is {type_name(left)}, right side is {type_name(right)}",
                    node.line,
                )
            return "bool"

        return ANY

    def check_expr_Call(self, node: A.Call, env):
        if isinstance(node.callee, A.Identifier) and node.callee.name in self.struct_registry:
            struct_name = node.callee.name
            fields = self.struct_registry[struct_name]
            seen = set()
            for arg in node.args:
                if arg.name is None:
                    self.error(
                        f"building a '{struct_name}' needs named arguments, "
                        f"e.g. {struct_name}(field: value)",
                        node.line,
                    )
                    continue
                if arg.name not in fields:
                    self.error(f"'{struct_name}' has no field '{arg.name}'", node.line)
                    continue
                seen.add(arg.name)
                val_t = self.check_expr(arg.value, env)
                if not compatible(fields[arg.name], val_t):
                    self.error(
                        f"field '{arg.name}' of '{struct_name}' expects "
                        f"{type_name(fields[arg.name])}, got {type_name(val_t)}",
                        node.line,
                    )
            missing = set(fields) - seen
            if missing:
                self.error(
                    f"missing field(s) when building '{struct_name}': {', '.join(sorted(missing))}",
                    node.line,
                )
            return ("struct", struct_name)

        if isinstance(node.callee, A.Identifier) and node.callee.name in _BUILTIN_RETURN_TYPES:
            for arg in node.args:
                self.check_expr(arg.value, env)
            return _BUILTIN_RETURN_TYPES[node.callee.name]

        callee_t = self.check_expr(node.callee, env)
        for arg in node.args:
            self.check_expr(arg.value, env)

        if isinstance(callee_t, tuple) and callee_t[0] == "func":
            _, param_types, return_type = callee_t
            positional = [a for a in node.args if a.name is None]
            if len(positional) != len(param_types):
                self.error(
                    f"expected {len(param_types)} argument(s), got {len(positional)}",
                    node.line,
                )
            else:
                for i, (arg, expected) in enumerate(zip(positional, param_types)):
                    actual = self.check_expr(arg.value, env)
                    if not compatible(expected, actual):
                        self.error(
                            f"argument {i + 1} expects {type_name(expected)}, "
                            f"got {type_name(actual)}",
                            node.line,
                        )
            return return_type

        return ANY

    def check_expr_Get(self, node: A.Get, env):
        obj_t = self.check_expr(node.obj, env)
        if isinstance(obj_t, tuple) and obj_t[0] == "struct":
            fields = self.struct_registry.get(obj_t[1], {})
            if node.name in fields:
                return fields[node.name]
            if fields:
                self.error(f"'{obj_t[1]}' has no field '{node.name}'", node.line)
            return ANY
        return ANY

    def check_expr_Index(self, node: A.Index, env):
        obj_t = self.check_expr(node.obj, env)
        self.check_expr(node.index, env)
        if isinstance(obj_t, tuple) and obj_t[0] == "list":
            return obj_t[1]
        if isinstance(obj_t, tuple) and obj_t[0] == "map":
            return obj_t[2]
        if obj_t == "str":
            return "str"
        return ANY

    def check_expr_Assign(self, node: A.Assign, env):
        value_t = self.check_expr(node.value, env)
        target = node.target
        if isinstance(target, A.Identifier):
            declared = env.get(target.name)
            if declared is None:
                self.error(
                    f"cannot assign to '{target.name}' before declaring it with 'let'",
                    node.line,
                )
            elif not compatible(declared, value_t):
                self.error(
                    f"cannot assign a value of type {type_name(value_t)} to "
                    f"'{target.name}', which is {type_name(declared)}",
                    node.line,
                )
        elif isinstance(target, A.Get):
            self.check_expr(target, env)
        elif isinstance(target, A.Index):
            self.check_expr(target, env)
        return value_t


def check(program: A.Program):
    return Checker().check_program(program)
