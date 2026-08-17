"""
Calyre tree-walking interpreter.

This is the *reference* execution engine for the language core described in
"Calyre — Fase 2: Sintaxe, Gramática e Tipos". It is intentionally a
tree-walking interpreter, not a compiler: the goal of this phase is a
correct, readable implementation of the full core grammar. Types are
enforced at *runtime* here — full static (compile-time) type-checking is
scoped for a later phase, and the language design already assumes it.
"""

from . import ast_nodes as A


class CalyreRuntimeError(Exception):
    """A runtime error. Anything of this type is catchable by `try/catch`."""

    def __init__(self, message, line=None):
        loc = f"[linha {line}] " if line is not None else ""
        super().__init__(f"{loc}Erro em tempo de execução: {message}")
        self.line = line
        self.message = message


class CalyreUserError(CalyreRuntimeError):
    """Raised by the builtin `error(message)` — a deliberate, catchable failure."""
    pass


class _ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


class Environment:
    """Lexical scope with a parent link (closures work for free)."""

    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def define(self, name, value):
        self.vars[name] = value

    def get(self, name, line=None):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise CalyreRuntimeError(f"nome '{name}' não foi definido", line)

    def set(self, name, value, line=None):
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        raise CalyreRuntimeError(
            f"não é possível atribuir a '{name}' antes de declará-lo com 'let'", line
        )


class StructType:
    """Represents a `struct` declaration: a callable that builds instances."""

    def __init__(self, name, fields):
        self.name = name
        self.field_names = [f.name for f in fields]

    def __call__(self, **kwargs):
        missing = [f for f in self.field_names if f not in kwargs]
        if missing:
            raise CalyreRuntimeError(
                f"faltam campos ao construir '{self.name}': {', '.join(missing)}"
            )
        extra = [k for k in kwargs if k not in self.field_names]
        if extra:
            raise CalyreRuntimeError(
                f"'{self.name}' não possui os campos: {', '.join(extra)}"
            )
        return StructInstance(self.name, dict(kwargs))

    def __repr__(self):
        return f"<struct {self.name}>"


class StructInstance:
    __slots__ = ("type_name", "fields")

    def __init__(self, type_name, fields):
        self.type_name = type_name
        self.fields = fields

    def __repr__(self):
        inner = ", ".join(f"{k}: {calyre_repr(v)}" for k, v in self.fields.items())
        return f"{self.type_name}({inner})"


class Module:
    """A namespace: either a local .cly file loaded via `use`, or a
    Python-backed standard-library module (math, text, fs, ...)."""

    def __init__(self, name, members):
        self.name = name
        self.members = members

    def get(self, name, line=None):
        if name not in self.members:
            raise CalyreRuntimeError(f"module '{self.name}' has no member '{name}'", line)
        return self.members[name]

    def __repr__(self):
        return f"<module {self.name}>"


class CalyreFunction:
    def __init__(self, decl: A.FuncDecl, closure: Environment):
        self.decl = decl
        self.closure = closure

    @property
    def name(self):
        return self.decl.name

    def call(self, interpreter, args):
        env = Environment(self.closure)
        params = self.decl.params
        if len(args) != len(params):
            raise CalyreRuntimeError(
                f"'{self.name}' espera {len(params)} argumento(s), recebeu {len(args)}",
                self.decl.line,
            )
        for param, value in zip(params, args):
            env.define(param.name, value)
        try:
            interpreter.exec_block(self.decl.body, env)
        except _ReturnSignal as r:
            return r.value
        return None

    def __repr__(self):
        return f"<func {self.name}>"


class BuiltinFunction:
    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def call(self, interpreter, args):
        return self.fn(*args)

    def __repr__(self):
        return f"<builtin {self.name}>"


def calyre_repr(value):
    """How a Calyre value renders when printed / concatenated with strings."""
    if value is None:
        return "none"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        if value == int(value):
            return f"{value:.1f}"
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(calyre_repr(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{calyre_repr(k)}: {calyre_repr(v)}" for k, v in value.items())
        return "{" + inner + "}"
    return str(value)


def _builtin_print(*args):
    print(" ".join(calyre_repr(a) for a in args))
    return None


def _builtin_str(value):
    return calyre_repr(value)


def _builtin_int(value):
    if isinstance(value, bool):
        raise CalyreRuntimeError("não é possível converter bool para int diretamente")
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as e:
            raise CalyreRuntimeError(f"'{value}' não é um int válido") from e
    return int(value)


def _builtin_float(value):
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as e:
            raise CalyreRuntimeError(f"'{value}' não é um float válido") from e
    return float(value)


def _builtin_len(value):
    if isinstance(value, (list, str, dict)):
        return len(value)
    raise CalyreRuntimeError("'len' espera uma lista, um mapa ou um texto")


def _builtin_range(*args):
    if len(args) == 1:
        return list(range(args[0]))
    if len(args) == 2:
        return list(range(args[0], args[1]))
    if len(args) == 3:
        return list(range(args[0], args[1], args[2]))
    raise CalyreRuntimeError("'range' aceita de 1 a 3 argumentos")


def _builtin_input(prompt=""):
    try:
        return input(calyre_repr(prompt) if not isinstance(prompt, str) else prompt)
    except EOFError as e:
        raise CalyreRuntimeError(
            "'input' não conseguiu ler nenhuma entrada (fim do stream)"
        ) from e


def _builtin_input_int(prompt=""):
    raw = _builtin_input(prompt)
    try:
        return int(raw.strip())
    except ValueError as e:
        raise CalyreRuntimeError(
            f"'{raw}' não é um int válido — digite apenas números inteiros"
        ) from e


def _builtin_input_float(prompt=""):
    raw = _builtin_input(prompt)
    try:
        return float(raw.strip())
    except ValueError as e:
        raise CalyreRuntimeError(
            f"'{raw}' não é um float válido — digite um número, ex: 3.14"
        ) from e


def _builtin_input_bool(prompt=""):
    raw = _builtin_input(prompt).strip().lower()
    if raw in ("true", "yes", "y", "1"):
        return True
    if raw in ("false", "no", "n", "0"):
        return False
    raise CalyreRuntimeError(
        f"'{raw}' não é um bool válido — responda com true/false, yes/no ou y/n"
    )


def _builtin_error(message):
    raise CalyreUserError(calyre_repr(message) if not isinstance(message, str) else message)


BUILTINS = {
    "print": BuiltinFunction("print", _builtin_print),
    "str": BuiltinFunction("str", _builtin_str),
    "int": BuiltinFunction("int", _builtin_int),
    "float": BuiltinFunction("float", _builtin_float),
    "len": BuiltinFunction("len", _builtin_len),
    "range": BuiltinFunction("range", _builtin_range),
    "input": BuiltinFunction("input", _builtin_input),
    "input_int": BuiltinFunction("input_int", _builtin_input_int),
    "input_float": BuiltinFunction("input_float", _builtin_input_float),
    "input_bool": BuiltinFunction("input_bool", _builtin_input_bool),
    "error": BuiltinFunction("error", _builtin_error),
}


class Interpreter:
    def __init__(self, base_dir=None, module_cache=None, loading_stack=None):
        self.globals = Environment()
        for name, fn in BUILTINS.items():
            self.globals.define(name, fn)
        # base_dir: directory used to resolve local `use module_name` imports.
        # module_cache/loading_stack are shared across an import graph so a
        # module is only loaded once, and circular imports are reported
        # clearly instead of recursing forever.
        import os
        self.base_dir = base_dir or os.getcwd()
        self.module_cache = module_cache if module_cache is not None else {}
        self.loading_stack = loading_stack if loading_stack is not None else []

    # ---- entry point ----

    def run(self, program: A.Program):
        self.exec_block(program.statements, self.globals)

    # ---- statement execution ----

    def exec_block(self, statements, env):
        for stmt in statements:
            self.exec_stmt(stmt, env)

    def exec_stmt(self, stmt, env):
        method = getattr(self, f"exec_{type(stmt).__name__}", None)
        if method is None:
            raise CalyreRuntimeError(f"instrução não suportada: {type(stmt).__name__}")
        method(stmt, env)

    def exec_LetStmt(self, stmt: A.LetStmt, env):
        value = self.eval(stmt.value, env)
        env.define(stmt.name, value)

    def exec_FuncDecl(self, stmt: A.FuncDecl, env):
        env.define(stmt.name, CalyreFunction(stmt, env))

    def exec_StructDecl(self, stmt: A.StructDecl, env):
        env.define(stmt.name, StructType(stmt.name, stmt.fields))

    def exec_IfStmt(self, stmt: A.IfStmt, env):
        for cond, block in stmt.branches:
            if _truthy(self.eval(cond, env)):
                self.exec_block(block, Environment(env))
                return
        if stmt.else_block is not None:
            self.exec_block(stmt.else_block, Environment(env))

    def exec_WhileStmt(self, stmt: A.WhileStmt, env):
        while _truthy(self.eval(stmt.condition, env)):
            try:
                self.exec_block(stmt.body, Environment(env))
            except _BreakSignal:
                break
            except _ContinueSignal:
                continue

    def exec_ForStmt(self, stmt: A.ForStmt, env):
        iterable = self.eval(stmt.iterable, env)
        if isinstance(iterable, dict):
            iterable = list(iterable.keys())  # `for k in a_map` iterates over keys
        if not isinstance(iterable, (list, str)):
            raise CalyreRuntimeError(
                "'for ... in' espera uma lista, um mapa, um texto, ou 'range(...)'", stmt.line
            )
        for item in iterable:
            loop_env = Environment(env)
            loop_env.define(stmt.var_name, item)
            try:
                self.exec_block(stmt.body, loop_env)
            except _BreakSignal:
                break
            except _ContinueSignal:
                continue

    def exec_MatchStmt(self, stmt: A.MatchStmt, env):
        subject = self.eval(stmt.subject, env)
        for pattern, block in stmt.cases:
            if pattern is None:  # wildcard `case _`
                self.exec_block(block, Environment(env))
                return
            if subject == self.eval(pattern, env):
                self.exec_block(block, Environment(env))
                return

    def exec_ReturnStmt(self, stmt: A.ReturnStmt, env):
        value = self.eval(stmt.value, env) if stmt.value is not None else None
        raise _ReturnSignal(value)

    def exec_BreakStmt(self, stmt: A.BreakStmt, env):
        raise _BreakSignal()

    def exec_ContinueStmt(self, stmt: A.ContinueStmt, env):
        raise _ContinueSignal()

    def exec_UseStmt(self, stmt: A.UseStmt, env):
        from .stdlib import STDLIB_MODULES

        bound_name = stmt.alias or stmt.path.split(".")[-1]

        if stmt.path in STDLIB_MODULES:
            module = STDLIB_MODULES[stmt.path]()
            env.define(bound_name, module)
            return

        module = self._load_local_module(stmt.path, stmt.line)
        env.define(bound_name, module)

    def _load_local_module(self, path, line):
        import os

        file_path = os.path.join(self.base_dir, *path.split(".")) + ".cly"
        file_path = os.path.normpath(file_path)

        if file_path in self.module_cache:
            return self.module_cache[file_path]

        if file_path in self.loading_stack:
            cycle = " -> ".join(self.loading_stack + [file_path])
            raise CalyreRuntimeError(f"importação circular detectada: {cycle}", line)

        if not os.path.isfile(file_path):
            raise CalyreRuntimeError(
                f"'use {path}' — não foi possível encontrar '{file_path}'. "
                f"Módulos locais precisam de um arquivo .cly no mesmo projeto "
                f"(bibliotecas remotas ainda não são suportadas — ver calyre.toml)",
                line,
            )

        from .lexer import tokenize, LexError
        from .calyre_parser import parse, ParseError
        from . import typechecker

        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        try:
            tokens = tokenize(source)
            program = parse(tokens)
        except (LexError, ParseError) as e:
            raise CalyreRuntimeError(f"erro ao carregar módulo '{path}': {e}", line) from e

        errors = typechecker.check(program)
        if errors:
            details = "; ".join(str(err) for err in errors)
            raise CalyreRuntimeError(
                f"módulo '{path}' tem erro(s) de tipo: {details}", line
            )

        self.loading_stack.append(file_path)
        module_interp = Interpreter(
            base_dir=os.path.dirname(file_path),
            module_cache=self.module_cache,
            loading_stack=self.loading_stack,
        )
        try:
            module_interp.run(program)
        finally:
            self.loading_stack.pop()

        exported = {
            name: value
            for name, value in module_interp.globals.vars.items()
            if not name.startswith("_") and name not in BUILTINS
        }
        module = Module(path, exported)
        self.module_cache[file_path] = module
        return module

    def exec_TryStmt(self, stmt: A.TryStmt, env):
        try_env = Environment(env)
        try:
            self.exec_block(stmt.try_block, try_env)
        except CalyreRuntimeError as e:
            catch_env = Environment(env)
            err_value = StructInstance("Error", {"message": e.message, "line": e.line})
            catch_env.define(stmt.err_name, err_value)
            self.exec_block(stmt.catch_block, catch_env)

    def exec_AssertStmt(self, stmt: A.AssertStmt, env):
        result = self.eval(stmt.expr, env)
        if _truthy(result):
            return
        if stmt.message is not None:
            detail = calyre_repr(self.eval(stmt.message, env))
        else:
            detail = _describe_failed_assert(stmt.expr, env, self)
        raise CalyreRuntimeError(f"assertion failed: {detail}", stmt.line)

    def exec_ExprStmt(self, stmt: A.ExprStmt, env):
        self.eval(stmt.expr, env)

    # ---- expression evaluation ----

    def eval(self, node, env):
        method = getattr(self, f"eval_{type(node).__name__}", None)
        if method is None:
            raise CalyreRuntimeError(f"expressão não suportada: {type(node).__name__}")
        return method(node, env)

    def eval_Literal(self, node: A.Literal, env):
        return node.value

    def eval_ListLiteral(self, node: A.ListLiteral, env):
        return [self.eval(e, env) for e in node.elements]

    def eval_MapLiteral(self, node: A.MapLiteral, env):
        result = {}
        for key_node, val_node in node.pairs:
            key = self.eval(key_node, env)
            if isinstance(key, (list, dict)):
                raise CalyreRuntimeError("chaves de mapa precisam ser um valor simples (não lista/mapa)", node.line)
            result[key] = self.eval(val_node, env)
        return result

    def eval_InterpString(self, node: A.InterpString, env):
        parts = []
        for kind, part in node.parts:
            if kind == "str":
                parts.append(part)
            else:
                parts.append(calyre_repr(self.eval(part, env)))
        return "".join(parts)

    def eval_Identifier(self, node: A.Identifier, env):
        return env.get(node.name, node.line)

    def eval_UnaryOp(self, node: A.UnaryOp, env):
        value = self.eval(node.operand, env)
        if node.op == "not":
            return not _truthy(value)
        if node.op == "-":
            _check_number(value, node.line)
            return -value
        raise CalyreRuntimeError(f"operador unário desconhecido '{node.op}'", node.line)

    def eval_BinaryOp(self, node: A.BinaryOp, env):
        op = node.op
        if op == "and":
            left = self.eval(node.left, env)
            if not _truthy(left):
                return left
            return self.eval(node.right, env)
        if op == "or":
            left = self.eval(node.left, env)
            if _truthy(left):
                return left
            return self.eval(node.right, env)

        left = self.eval(node.left, env)
        right = self.eval(node.right, env)
        return _apply_binop(op, left, right, node.line)

    def eval_Call(self, node: A.Call, env):
        callee = self.eval(node.callee, env)
        if isinstance(callee, StructType):
            kwargs = {}
            for i, arg in enumerate(node.args):
                if arg.name is None:
                    raise CalyreRuntimeError(
                        f"ao construir '{callee.name}', use argumentos nomeados "
                        f"(ex: {callee.name}(campo: valor))",
                        node.line,
                    )
                kwargs[arg.name] = self.eval(arg.value, env)
            return callee(**kwargs)

        if not (isinstance(callee, (CalyreFunction, BuiltinFunction))):
            raise CalyreRuntimeError("tentativa de chamar algo que não é uma função", node.line)

        args = []
        for arg in node.args:
            if arg.name is not None:
                raise CalyreRuntimeError(
                    "argumentos nomeados só são aceitos ao construir structs", node.line
                )
            args.append(self.eval(arg.value, env))
        return callee.call(self, args)

    def eval_Get(self, node: A.Get, env):
        obj = self.eval(node.obj, env)
        if isinstance(obj, StructInstance):
            if node.name not in obj.fields:
                raise CalyreRuntimeError(
                    f"'{obj.type_name}' não possui o campo '{node.name}'", node.line
                )
            return obj.fields[node.name]
        if isinstance(obj, Module):
            return obj.get(node.name, node.line)
        raise CalyreRuntimeError(
            f"'.{node.name}' não pode ser usado em um valor deste tipo", node.line
        )

    def eval_Index(self, node: A.Index, env):
        obj = self.eval(node.obj, env)
        idx = self.eval(node.index, env)
        if isinstance(obj, dict):
            if idx not in obj:
                raise CalyreRuntimeError(f"chave {calyre_repr(idx)} não existe no mapa", node.line)
            return obj[idx]
        if not isinstance(obj, (list, str)):
            raise CalyreRuntimeError("apenas listas, mapas e textos podem ser indexados", node.line)
        if not isinstance(idx, int) or isinstance(idx, bool):
            raise CalyreRuntimeError("o índice precisa ser um int", node.line)
        try:
            return obj[idx]
        except IndexError as e:
            raise CalyreRuntimeError(f"índice {idx} fora do intervalo", node.line) from e

    def eval_Assign(self, node: A.Assign, env):
        value = self.eval(node.value, env)
        target = node.target
        if isinstance(target, A.Identifier):
            env.set(target.name, value, node.line)
            return value
        if isinstance(target, A.Get):
            obj = self.eval(target.obj, env)
            if not isinstance(obj, StructInstance):
                raise CalyreRuntimeError("atribuição de campo em valor que não é struct", node.line)
            obj.fields[target.name] = value
            return value
        if isinstance(target, A.Index):
            obj = self.eval(target.obj, env)
            idx = self.eval(target.index, env)
            if isinstance(obj, dict):
                obj[idx] = value
                return value
            if not isinstance(obj, list):
                raise CalyreRuntimeError("apenas listas e mapas podem ser atribuídos por índice", node.line)
            obj[idx] = value
            return value
        raise CalyreRuntimeError("alvo de atribuição inválido", node.line)


def _truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return bool(value)


def _check_number(value, line):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalyreRuntimeError("esperava um número (int ou float)", line)


_NUMERIC_OPS = {"+", "-", "*", "/", "%", "<", ">", "<=", ">="}


def _apply_binop(op, left, right, line):
    if op == "+":
        if isinstance(left, str) or isinstance(right, str):
            if not (isinstance(left, str) and isinstance(right, str)):
                raise CalyreRuntimeError(
                    "não é possível somar texto com um valor que não é texto — "
                    "use str(...) para converter primeiro",
                    line,
                )
            return left + right
        if isinstance(left, list) and isinstance(right, list):
            return left + right
        _check_same_numeric_type(left, right, line)
        return left + right

    if op in _NUMERIC_OPS:
        _check_same_numeric_type(left, right, line)
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise CalyreRuntimeError("divisão por zero", line)
            if isinstance(left, int) and isinstance(right, int):
                return left // right if left % right == 0 else left / right
            return left / right
        if op == "%":
            if right == 0:
                raise CalyreRuntimeError("módulo por zero", line)
            return left % right
        if op == "<":
            return left < right
        if op == ">":
            return left > right
        if op == "<=":
            return left <= right
        if op == ">=":
            return left >= right

    if op == "==":
        return _calyre_equals(left, right)
    if op == "!=":
        return not _calyre_equals(left, right)

    raise CalyreRuntimeError(f"operador desconhecido '{op}'", line)


def _check_same_numeric_type(left, right, line):
    for v in (left, right):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CalyreRuntimeError("operador numérico usado em valor que não é número", line)
    if isinstance(left, int) and isinstance(right, float):
        raise CalyreRuntimeError(
            "Calyre não converte int e float automaticamente — "
            "use float(...) ou int(...) para converter explicitamente",
            line,
        )
    if isinstance(left, float) and isinstance(right, int):
        raise CalyreRuntimeError(
            "Calyre não converte int e float automaticamente — "
            "use float(...) ou int(...) para converter explicitamente",
            line,
        )


def _calyre_equals(left, right):
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right


_COMPARISON_OPS = {"==", "!=", "<", ">", "<=", ">="}


def _unparse(node):
    """Best-effort reconstruction of an expression's source text, used to
    make `assert` failures self-explaining without the user writing a
    custom message. Not a full pretty-printer — just enough for common
    expressions (see Phase 3 notes on the `assert` feature)."""
    if isinstance(node, A.Literal):
        return calyre_repr(node.value) if not isinstance(node.value, str) else f'"{node.value}"'
    if isinstance(node, A.Identifier):
        return node.name
    if isinstance(node, A.BinaryOp):
        return f"{_unparse(node.left)} {node.op} {_unparse(node.right)}"
    if isinstance(node, A.UnaryOp):
        return f"{node.op} {_unparse(node.operand)}"
    if isinstance(node, A.Call):
        args = ", ".join(_unparse(a.value) for a in node.args)
        return f"{_unparse(node.callee)}({args})"
    if isinstance(node, A.Get):
        return f"{_unparse(node.obj)}.{node.name}"
    if isinstance(node, A.Index):
        return f"{_unparse(node.obj)}[{_unparse(node.index)}]"
    return "<expr>"


def _describe_failed_assert(node, env, interpreter):
    """Calyre's `assert` is self-explaining: it doesn't just say the
    condition was false, it shows the values that made it false — an
    original, small feature aimed squarely at reducing the distance
    between 'my program is wrong' and 'I know why'."""
    text = _unparse(node)
    if isinstance(node, A.BinaryOp) and node.op in _COMPARISON_OPS:
        try:
            left_val = interpreter.eval(node.left, env)
            right_val = interpreter.eval(node.right, env)
            return f"{text} ({_unparse(node.left)} = {calyre_repr(left_val)}, {_unparse(node.right)} = {calyre_repr(right_val)})"
        except CalyreRuntimeError:
            pass
    return text


def interpret(program: A.Program, base_dir=None):
    Interpreter(base_dir=base_dir).run(program)
