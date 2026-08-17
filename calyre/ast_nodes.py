"""
AST node definitions for Calyre.

Kept as plain dataclasses: no behavior lives here, only structure.
The interpreter (interpreter.py) walks these nodes.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Any


# ---- type annotations ----

@dataclass
class TypeAnn:
    name: str                       # "int", "float", "bool", "str", "list", or a struct name
    optional: bool = False           # trailing "?"
    params: List["TypeAnn"] = field(default_factory=list)  # for list<T>, Foo<T,...>


# ---- top level / statements ----

@dataclass
class Program:
    statements: list


@dataclass
class LetStmt:
    name: str
    type_ann: Optional[TypeAnn]
    value: Any
    line: int


@dataclass
class Param:
    name: str
    type_ann: TypeAnn


@dataclass
class FuncDecl:
    name: str
    params: List[Param]
    return_type: Optional[TypeAnn]
    body: list
    line: int


@dataclass
class StructDecl:
    name: str
    fields: List[Param]
    line: int


@dataclass
class IfStmt:
    branches: List[tuple]   # list of (condition_expr, block)
    else_block: Optional[list]
    line: int


@dataclass
class WhileStmt:
    condition: Any
    body: list
    line: int


@dataclass
class ForStmt:
    var_name: str
    iterable: Any
    body: list
    line: int


@dataclass
class MatchStmt:
    subject: Any
    cases: List[tuple]     # list of (pattern_expr_or_None_for_wildcard, block)
    line: int


@dataclass
class ReturnStmt:
    value: Optional[Any]
    line: int


@dataclass
class BreakStmt:
    line: int


@dataclass
class ContinueStmt:
    line: int


@dataclass
class UseStmt:
    path: str
    alias: Optional[str]
    line: int


@dataclass
class TryStmt:
    try_block: list
    err_name: str
    catch_block: list
    line: int


@dataclass
class AssertStmt:
    expr: Any
    message: Optional[Any]     # optional custom message expression
    line: int


@dataclass
class ExprStmt:
    expr: Any
    line: int


# ---- expressions ----

@dataclass
class Literal:
    value: Any
    line: int


@dataclass
class ListLiteral:
    elements: list
    line: int


@dataclass
class MapLiteral:
    pairs: list                # list of (key_expr, value_expr)
    line: int


@dataclass
class InterpString:
    parts: list                 # list of ("str", text) or ("expr", ast_node)
    line: int


@dataclass
class Identifier:
    name: str
    line: int


@dataclass
class BinaryOp:
    op: str
    left: Any
    right: Any
    line: int


@dataclass
class UnaryOp:
    op: str
    operand: Any
    line: int


@dataclass
class Call:
    callee: Any
    args: list                 # list of Arg
    line: int


@dataclass
class Arg:
    name: Optional[str]        # None for positional, str for named ("city: ...")
    value: Any


@dataclass
class Get:
    obj: Any
    name: str
    line: int


@dataclass
class Index:
    obj: Any
    index: Any
    line: int


@dataclass
class Assign:
    target: Any                # Identifier, Get, or Index
    value: Any
    line: int
