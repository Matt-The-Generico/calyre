"""
Official Calyre formatter (`calyre fmt`).

Properties (all enforced by tests):
* Deterministic and idempotent: format(format(x)) == format(x).
* Semantics-preserving: parse(format(x)) has the same AST as parse(x).
* Never loses a comment. Comments are placed before statements, after them on the same line,
  or at the end of a block. A comment in a spot the formatter cannot place (inside a
  multi-line expression) makes it refuse the file with a clear message instead.
* Style: 4-space indent, `end` on its own line, one blank line around top-level
  func/struct declarations, blank lines elsewhere kept (at most one), lines wrapped at 100
  columns by putting list/map elements and call arguments on separate lines.
"""

from decimal import Decimal

from . import ast_nodes as A
from .lexer import tokenize, LexError
from .calyre_parser import parse, ParseError

INDENT = "    "
LIMIT = 100

_PREC = {"??": 1, "or": 2, "and": 3, "==": 4, "!=": 4, "<": 5, ">": 5, "<=": 5, ">=": 5,
         "+": 6, "-": 6, "*": 7, "/": 7, "%": 7}
_UNARY, _POSTFIX, _ATOM = 8, 9, 10


class FormatError(Exception):
    def __init__(self, message, line=None):
        super().__init__(message)
        self.message = message
        self.line = line


# ------------------------------------------------------------------ text helpers

def _escape(text):
    return (text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            .replace("\t", "\\t").replace("{", "\\{"))


def _float_text(v):
    r = repr(v)
    if "e" in r or "E" in r:
        r = format(Decimal(r), "f")
    return r if "." in r else r + ".0"


def type_text(t):
    out = t.name
    if t.params:
        out += "<" + ", ".join(type_text(p) for p in t.params) + ">"
    return out + ("?" if t.optional else "")


# ------------------------------------------------------------------ expressions

def flat(node, parent=0):
    """Single-line text of an expression, parenthesised only where precedence needs it."""
    if isinstance(node, A.Literal):
        v = node.value
        if v is None:
            return "none"
        if v is True:
            return "true"
        if v is False:
            return "false"
        if isinstance(v, str):
            if getattr(node, "raw", False) and '"""' not in v and not v.endswith('"'):
                return '"""' + ("\n" if "\n" in v else "") + v + '"""'
            return f'"{_escape(v)}"'
        if isinstance(v, float):
            return _float_text(v)
        return str(v)
    if isinstance(node, A.Identifier):
        return node.name
    if isinstance(node, A.InterpString):
        out = []
        for kind, part in node.parts:
            out.append(_escape(part) if kind == "str" else "{" + flat(part) + "}")
        return '"' + "".join(out) + '"'
    if isinstance(node, A.ListLiteral):
        return "[" + ", ".join(flat(e) for e in node.elements) + "]"
    if isinstance(node, A.MapLiteral):
        return "{" + ", ".join(f"{flat(k)}: {flat(v)}" for k, v in node.pairs) + "}"
    if isinstance(node, A.UnaryOp):
        sep = " " if node.op == "not" else ""
        text = f"{node.op}{sep}{flat(node.operand, _UNARY)}"
        return text if parent <= _UNARY else f"({text})"
    if isinstance(node, A.BinaryOp):
        p = _PREC[node.op]
        text = f"{flat(node.left, p)} {node.op} {flat(node.right, p + 1)}"
        return text if parent <= p else f"({text})"
    if isinstance(node, A.Call):
        return f"{flat(node.callee, _POSTFIX)}({', '.join(_arg(a) for a in node.args)})"
    if isinstance(node, A.Get):
        return f"{flat(node.obj, _POSTFIX)}.{node.name}"
    if isinstance(node, A.Index):
        return f"{flat(node.obj, _POSTFIX)}[{flat(node.index)}]"
    if isinstance(node, A.Assign):
        text = f"{flat(node.target, _POSTFIX)} = {flat(node.value)}"
        return text if parent == 0 else f"({text})"
    raise FormatError(f"cannot format expression {type(node).__name__}")


def _arg(a):
    return flat(a.value) if a.name is None else f"{a.name}: {flat(a.value)}"


def expr(node, col, depth, parent=0):
    """Expression text starting at column `col`; breaks lists, maps and call arguments
    over several lines (one element per line) when the flat form would pass LIMIT."""
    text = flat(node, parent)
    if col + len(text) <= LIMIT or "\n" in text:
        return text
    ind1, ind0 = INDENT * (depth + 1), INDENT * depth
    if isinstance(node, A.ListLiteral) and node.elements:
        items = [ind1 + expr(e, len(ind1), depth + 1) for e in node.elements]
        return "[\n" + ",\n".join(items) + "\n" + ind0 + "]"
    if isinstance(node, A.MapLiteral) and node.pairs:
        items = []
        for k, v in node.pairs:
            head = f"{flat(k)}: "
            items.append(ind1 + head + expr(v, len(ind1) + len(head), depth + 1))
        return "{\n" + ",\n".join(items) + "\n" + ind0 + "}"
    if isinstance(node, A.Call) and node.args:
        callee = flat(node.callee, _POSTFIX)
        items = []
        for a in node.args:
            head = "" if a.name is None else f"{a.name}: "
            items.append(ind1 + head + expr(a.value, len(ind1) + len(head), depth + 1))
        return callee + "(\n" + ",\n".join(items) + "\n" + ind0 + ")"
    return text


# ------------------------------------------------------------------ statements

class Formatter:
    def __init__(self, comments):
        self.comments = sorted(comments, key=lambda c: c.line)
        self.used = set()
        self.by_line = {c.line: i for i, c in enumerate(self.comments)}
        self.out = []
        self.last_line = None      # source line where the previous emitted item ended
        self.last_decl = False     # previous top-level item was a func/struct

    # --- output primitives
    def trailing(self, line):
        i = self.by_line.get(line)
        if i is not None and i not in self.used and not self.comments[i].own_line:
            self.used.add(i)
            return "  //" + self.comments[i].text.rstrip()
        return ""

    def emit(self, depth, text, src_line=None, trailing_line=None):
        """Write a (possibly multi-line) piece of code; only its first line is indented here
        (continuation lines of broken expressions already carry their own indentation)."""
        line = trailing_line if trailing_line is not None else src_line
        suffix = self.trailing(line) if line is not None else ""
        lines = text.split("\n")
        lines[-1] += suffix
        lines[0] = INDENT * depth + lines[0]
        self.out.extend(lines)

    def blank(self):
        if self.out and self.out[-1] != "":
            self.out.append("")

    # --- comment handling
    def own_comments(self, lo, hi):
        """Indexes of unused own-line comments with lo < line < hi."""
        return [i for i, c in enumerate(self.comments)
                if c.own_line and i not in self.used and lo < c.line < hi]

    def emit_comment(self, depth, i, blank):
        c = self.comments[i]
        self.used.add(i)
        if blank:
            self.blank()
        self.out.append(INDENT * depth + "//" + c.text.rstrip())
        self.last_line = c.line
        self.last_decl = False

    def want_blank(self, item_line, is_decl_start, depth, started):
        if not started:
            return False
        if depth == 0 and (is_decl_start or self.last_decl):
            return True                      # one blank line around top-level func/struct
        return item_line - self.last_line > 1     # keep the author's blank line (at most one)

    def block(self, stmts, depth, lo, hi):
        self.last_line, self.last_decl, started = lo, False, False
        for s in stmts:
            is_decl = depth == 0 and isinstance(s, (A.FuncDecl, A.StructDecl))
            idxs = self.own_comments(self.last_line, s.line)
            attached_first = None
            if is_decl and idxs and self.comments[idxs[-1]].line == s.line - 1:
                k = len(idxs) - 1                    # the comment run glued to the declaration
                while k > 0 and self.comments[idxs[k - 1]].line + 1 == self.comments[idxs[k]].line:
                    k -= 1
                attached_first = idxs[k]
            for i in idxs:
                c = self.comments[i]
                self.emit_comment(depth, i, self.want_blank(c.line, i == attached_first, depth, started))
                started = True
            self.emit_pending_blank = None
            if self.want_blank(s.line, is_decl and not idxs, depth, started) and not (idxs and self.comments[idxs[-1]].line == s.line - 1):
                self.blank()
            self.stmt(s, depth)
            started = True
            self.last_decl, self.last_line = is_decl, s.end_line
            self.check_inside(s)
        for i in self.own_comments(self.last_line, hi):
            self.emit_comment(depth, i, self.want_blank(self.comments[i].line, False, depth, started))
            started = True
        self.last_decl = False

    def check_inside(self, s):
        """Simple statements must not hide a comment inside a multi-line expression."""
        if isinstance(s, (A.IfStmt, A.WhileStmt, A.ForStmt, A.MatchStmt, A.TryStmt, A.FuncDecl, A.StructDecl)):
            return
        for i, c in enumerate(self.comments):
            if i not in self.used and s.line <= c.line <= s.end_line:
                raise FormatError("a comment inside a multi-line expression cannot be formatted "
                                  "safely; move it above or after the statement", c.line)

    def stmt(self, s, depth):
        m = getattr(self, f"s_{type(s).__name__}")
        m(s, depth)

    @staticmethod
    def pub(s):
        return "pub " if getattr(s, "public", False) else ""

    def s_LetStmt(self, s, d):
        head = f"{self.pub(s)}let {s.name}" + (f": {type_text(s.type_ann)}" if s.type_ann else "") + " = "
        self.emit(d, head + expr(s.value, len(INDENT * d) + len(head), d), trailing_line=s.end_line)

    def s_ExprStmt(self, s, d):
        self.emit(d, expr(s.expr, len(INDENT * d), d), trailing_line=s.end_line)

    def s_ReturnStmt(self, s, d):
        text = "return" if s.value is None else "return " + expr(s.value, len(INDENT * d) + 7, d)
        self.emit(d, text, trailing_line=s.end_line)

    def s_BreakStmt(self, s, d):
        self.emit(d, "break", trailing_line=s.end_line)

    def s_ContinueStmt(self, s, d):
        self.emit(d, "continue", trailing_line=s.end_line)

    def s_AssertStmt(self, s, d):
        text = "assert " + flat(s.expr)
        if s.message is not None:
            text += ", " + flat(s.message)
        self.emit(d, text, trailing_line=s.end_line)

    def s_UseStmt(self, s, d):
        target = f'"{_escape(s.path)}"' if s.by_path else s.path
        if s.names is not None:
            names = ", ".join(n if a is None else f"{n} as {a}" for n, a in s.names)
            text = f"use {names} from {target}"
        else:
            text = f"use {target}" + (f" as {s.alias}" if s.alias else "")
        self.emit(d, text, trailing_line=s.end_line)

    def s_FuncDecl(self, s, d):
        tp = f"<{', '.join(s.type_params)}>" if s.type_params else ""
        params = ", ".join(f"{p.name}: {type_text(p.type_ann)}" for p in s.params)
        ret = f" -> {type_text(s.return_type)}" if s.return_type else ""
        self.emit(d, f"{self.pub(s)}func {s.name}{tp}({params}){ret}", src_line=s.line)
        self.block(s.body, d + 1, s.line, s.end_line)
        self.emit(d, "end", trailing_line=s.end_line)

    def s_StructDecl(self, s, d):
        tp = f"<{', '.join(s.type_params)}>" if s.type_params else ""
        self.emit(d, f"{self.pub(s)}struct {s.name}{tp}", src_line=s.line)
        self.last_line, started = s.line, False
        for f in s.fields:
            for i in self.own_comments(self.last_line, f.line):
                self.emit_comment(d + 1, i, started and self.comments[i].line - self.last_line > 1)
                started = True
            self.emit(d + 1, f"{f.name}: {type_text(f.type_ann)}", trailing_line=f.line)
            self.last_line, started = f.line, True
        for i in self.own_comments(self.last_line, s.end_line):
            self.emit_comment(d + 1, i, started and self.comments[i].line - self.last_line > 1)
        self.emit(d, "end", trailing_line=s.end_line)

    def s_IfStmt(self, s, d):
        kws = s.kw_lines
        ends = kws[1:] + [s.else_line if s.else_line else s.end_line]
        for k, (cond, body) in enumerate(s.branches):
            head = ("if " if k == 0 else "elif ") + expr(cond, len(INDENT * d) + (3 if k == 0 else 5), d)
            self.emit(d, head, src_line=kws[k])
            self.block(body, d + 1, kws[k], ends[k])
        if s.else_block is not None:
            self.emit(d, "else", src_line=s.else_line)
            self.block(s.else_block, d + 1, s.else_line, s.end_line)
        self.emit(d, "end", trailing_line=s.end_line)

    def s_WhileStmt(self, s, d):
        self.emit(d, "while " + expr(s.condition, len(INDENT * d) + 6, d), src_line=s.line)
        self.block(s.body, d + 1, s.line, s.end_line)
        self.emit(d, "end", trailing_line=s.end_line)

    def s_ForStmt(self, s, d):
        head = f"for {s.var_name} in "
        self.emit(d, head + expr(s.iterable, len(INDENT * d) + len(head), d), src_line=s.line)
        self.block(s.body, d + 1, s.line, s.end_line)
        self.emit(d, "end", trailing_line=s.end_line)

    def s_MatchStmt(self, s, d):
        self.emit(d, "match " + expr(s.subject, len(INDENT * d) + 6, d), src_line=s.line)
        first = s.case_lines[0] if s.case_lines else s.end_line
        self.last_line = s.line
        for i in self.own_comments(s.line, first):
            self.emit_comment(d + 1, i, False)
        ends = s.case_lines[1:] + [s.end_line]
        for k, (pattern, body) in enumerate(s.cases):
            pat = "_" if pattern is None else flat(pattern)
            self.emit(d + 1, f"case {pat}", src_line=s.case_lines[k])
            self.block(body, d + 2, s.case_lines[k], ends[k])
        self.emit(d, "end", trailing_line=s.end_line)

    def s_TryStmt(self, s, d):
        self.emit(d, "try", src_line=s.line)
        self.block(s.try_block, d + 1, s.line, s.catch_line)
        self.emit(d, f"catch {s.err_name}", src_line=s.catch_line)
        self.block(s.catch_block, d + 1, s.catch_line, s.end_line)
        self.emit(d, "end", trailing_line=s.end_line)


# ------------------------------------------------------------------ API

def format_source(source):
    """Return the formatted text of `source`. Raises FormatError for invalid or unsafe input."""
    comments = []
    try:
        program = parse(tokenize(source, comments))
    except (LexError, ParseError) as e:
        raise FormatError(f"syntax error: {e}", getattr(e, "line", None)) from e
    f = Formatter(comments)
    total_lines = source.count("\n") + 2
    f.block(program.statements, 0, 0, total_lines)
    for i, c in enumerate(f.comments):
        if i not in f.used:
            raise FormatError("this comment cannot be placed safely by the formatter; "
                              "move it above or after a statement", c.line)
    while f.out and f.out[-1] == "":
        f.out.pop()
    return "\n".join(f.out) + "\n" if f.out else ""
