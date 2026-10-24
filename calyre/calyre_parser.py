"""
Calyre parser.

Recursive-descent parser implementing the EBNF grammar from
the grammar documented in docs/SPEC.md.
"""
from . import ast_nodes as A

BLOCK_TERMINATORS = {"END", "ELIF", "ELSE", "CASE", "CATCH", "EOF"}
STATEMENT_STARTERS = {
    "LET", "FUNC", "STRUCT", "IF", "WHILE", "FOR", "MATCH",
    "RETURN", "BREAK", "CONTINUE", "USE", "TRY", "ASSERT",
}


class ParseError(Exception):
    def __init__(self, message, line):
        super().__init__(f"Line {line}: {message}")
        self.line = line


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # ---- low-level helpers ----

    @staticmethod
    def _at(node, col):
        """Remember the source column of a node (used by diagnostics and tools)."""
        node.col = col
        return node

    def peek(self, offset=0):
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def advance(self):
        tok = self.tokens[self.pos]
        if tok.type != "EOF":
            self.pos += 1
        return tok

    def check(self, *types):
        return self.peek().type in types

    def match(self, *types):
        if self.check(*types):
            return self.advance()
        return None

    def expect(self, type_, message=None):
        if self.check(type_):
            return self.advance()
        tok = self.peek()
        raise ParseError(
            message or f"Expected {type_} but found {tok.type} ({tok.value!r})",
            tok.line,
        )

    # ---- entry point ----

    def parse_program(self):
        statements = []
        while not self.check("EOF"):
            statements.append(self.parse_statement())
        return A.Program(statements)

    def parse_block(self, terminators):
        statements = []
        while not self.check(*terminators, "EOF"):
            statements.append(self.parse_statement())
        return statements

    # ---- statements ----

    def parse_statement(self):
        start = self.peek()
        stmt = self._parse_statement()
        stmt.col = start.col
        last = self.tokens[self.pos - 1]
        stmt.end_line = last.end_line or last.line
        return stmt

    def _parse_statement(self):
        tok = self.peek()
        dispatch = {
            "LET": self.parse_let,
            "FUNC": self.parse_func,
            "STRUCT": self.parse_struct,
            "IF": self.parse_if,
            "WHILE": self.parse_while,
            "FOR": self.parse_for,
            "MATCH": self.parse_match,
            "RETURN": self.parse_return,
            "BREAK": self.parse_break,
            "CONTINUE": self.parse_continue,
            "USE": self.parse_use,
            "TRY": self.parse_try,
            "ASSERT": self.parse_assert,
        }
        if (tok.type == "IDENT" and tok.value == "pub"
                and self.peek(1).type in ("FUNC", "STRUCT", "LET")):
            # `pub` is contextual (not a reserved word), so old programs that use
            # `pub` as an ordinary name keep working.
            self.advance()
            stmt = dispatch[self.peek().type]()
            stmt.public = True
            return stmt
        if tok.type in dispatch:
            return dispatch[tok.type]()
        expr = self.parse_expression()
        return A.ExprStmt(expr, tok.line)

    def parse_type(self):
        tok = self.expect("IDENT", "Expected a type name")
        type_name = tok.value
        while self.check("DOT"):          # module-qualified type: shapes.Point
            self.advance()
            type_name += "." + self.expect("IDENT", "Expected a type name after '.'").value
        params = []
        if self.match("LT"):
            params.append(self.parse_type())
            while self.match("COMMA"):
                params.append(self.parse_type())
            self.expect("GT", "Expected '>' to close generic type")
        optional = bool(self.match("QUESTION"))
        return self._at(A.TypeAnn(type_name, optional, params, tok.line), tok.col)

    def parse_param(self):
        first = self.peek()
        name = self.expect("IDENT").value
        self.expect("COLON", f"Expected ':' after parameter/field name '{name}'")
        type_ann = self.parse_type()
        param = A.Param(name, type_ann)
        param.line, param.col = first.line, first.col       # for tools (comments in struct bodies)
        return param

    def parse_let(self):
        tok = self.expect("LET")
        name = self.expect("IDENT").value
        type_ann = None
        if self.match("COLON"):
            type_ann = self.parse_type()
        self.expect("EQ", "Expected '=' in let statement")
        value = self.parse_expression()
        return A.LetStmt(name, type_ann, value, tok.line)

    def parse_func(self):
        tok = self.expect("FUNC")
        name = self.expect("IDENT").value
        type_params = self.parse_type_params()
        self.expect("LPAREN")
        params = []
        if not self.check("RPAREN"):
            params.append(self.parse_param())
            while self.match("COMMA"):
                params.append(self.parse_param())
        self.expect("RPAREN")
        return_type = None
        if self.match("ARROW"):
            return_type = self.parse_type()
        body = self.parse_block({"END"})
        self.expect("END", f"Expected 'end' to close function '{name}'")
        return A.FuncDecl(name, params, return_type, body, tok.line, type_params)

    def parse_type_params(self):
        """Optional `<T, U>` after a function or struct name."""
        params = []
        if self.match("LT"):
            params.append(self.expect("IDENT", "Expected a type parameter name, e.g. <T>").value)
            while self.match("COMMA"):
                params.append(self.expect("IDENT", "Expected a type parameter name").value)
            self.expect("GT", "Expected '>' to close the type parameters")
            if len(set(params)) != len(params):
                raise ParseError("Duplicate type parameter name", self.peek().line)
        return params

    def parse_struct(self):
        tok = self.expect("STRUCT")
        name = self.expect("IDENT").value
        type_params = self.parse_type_params()
        fields = []
        while not self.check("END"):
            fields.append(self.parse_param())
        self.expect("END", f"Expected 'end' to close struct '{name}'")
        return A.StructDecl(name, fields, tok.line, type_params)

    def parse_if(self):
        tok = self.expect("IF")
        cond = self.parse_expression()
        block = self.parse_block({"ELIF", "ELSE", "END"})
        branches = [(cond, block)]
        kw_lines = [tok.line]
        while self.check("ELIF"):
            kw_lines.append(self.advance().line)
            cond2 = self.parse_expression()
            block2 = self.parse_block({"ELIF", "ELSE", "END"})
            branches.append((cond2, block2))
        else_block = None
        else_line = None
        if self.check("ELSE"):
            else_line = self.advance().line
            else_block = self.parse_block({"END"})
        self.expect("END", "Expected 'end' to close if statement")
        node = A.IfStmt(branches, else_block, tok.line)
        node.kw_lines, node.else_line = kw_lines, else_line     # for tools (formatter)
        return node

    def parse_while(self):
        tok = self.expect("WHILE")
        cond = self.parse_expression()
        body = self.parse_block({"END"})
        self.expect("END", "Expected 'end' to close while loop")
        return A.WhileStmt(cond, body, tok.line)

    def parse_for(self):
        tok = self.expect("FOR")
        var_name = self.expect("IDENT").value
        self.expect("IN")
        iterable = self.parse_expression()
        body = self.parse_block({"END"})
        self.expect("END", "Expected 'end' to close for loop")
        return A.ForStmt(var_name, iterable, body, tok.line)

    def parse_match(self):
        tok = self.expect("MATCH")
        subject = self.parse_expression()
        cases = []
        case_lines = []
        while self.check("CASE"):
            case_lines.append(self.advance().line)
            if self.check("IDENT") and self.peek().value == "_":
                self.advance()
                pattern = None
            else:
                pattern = self.parse_expression()
            block = self.parse_block({"CASE", "END"})
            cases.append((pattern, block))
        self.expect("END", "Expected 'end' to close match statement")
        node = A.MatchStmt(subject, cases, tok.line)
        node.case_lines = case_lines
        return node

    def parse_return(self):
        tok = self.expect("RETURN")
        if self.check(*BLOCK_TERMINATORS, *STATEMENT_STARTERS):
            return A.ReturnStmt(None, tok.line)
        value = self.parse_expression()
        return A.ReturnStmt(value, tok.line)

    def parse_break(self):
        tok = self.expect("BREAK")
        return A.BreakStmt(tok.line)

    def parse_continue(self):
        tok = self.expect("CONTINUE")
        return A.ContinueStmt(tok.line)

    def parse_use(self):
        tok = self.expect("USE")
        if self.check("STRING") or self.check("TEMPLATE_STRING"):        # use "./lib.cly" [as x]
            path = self._path_literal()
            alias = self.expect("IDENT", "Expected an alias after 'as'").value if self.match("AS") else None
            return A.UseStmt(path, alias, tok.line, None, True)
        first = self.expect("IDENT", "Expected a module name or a quoted file path after 'use'")
        # `use a, b from m` / `use a as x from m` (`from` is contextual, not reserved)
        if self.check("COMMA") or self._is_from() or (self.check("AS") and self._names_form_ahead()):
            names = [self._use_name(first)]
            while self.match("COMMA"):
                names.append(self._use_name(self.expect("IDENT", "Expected a name to import")))
            if not self._is_from():
                raise ParseError("Expected 'from <module>' after the imported names", self.peek().line)
            self.advance()
            if self.check("STRING") or self.check("TEMPLATE_STRING"):
                return A.UseStmt(self._path_literal(), None, tok.line, names, True)
            path = self.expect("IDENT", "Expected a module name or a quoted file path after 'from'").value
            while self.match("DOT"):
                path += "." + self.expect("IDENT").value
            return A.UseStmt(path, None, tok.line, names)
        path = first.value
        while self.match("DOT"):
            path += "." + self.expect("IDENT").value
        alias = None
        if self.match("AS"):
            alias = self.expect("IDENT").value
        return A.UseStmt(path, alias, tok.line)

    def _path_literal(self):
        tok = self.advance()
        if tok.type != "STRING":
            raise ParseError("an import path must be a plain text; it cannot contain {interpolation}", tok.line)
        if not tok.value:
            raise ParseError("an import path cannot be empty", tok.line)
        return tok.value

    def _is_from(self):
        t = self.peek()
        return t.type == "IDENT" and t.value == "from"

    def _names_form_ahead(self):
        # at `as`: it is the names form if `as <alias>` is followed by `,` or `from`
        a, b = self.peek(1), self.peek(2)
        return a.type == "IDENT" and (b.type == "COMMA" or (b.type == "IDENT" and b.value == "from"))

    def _use_name(self, ident_tok):
        alias = None
        if self.match("AS"):
            alias = self.expect("IDENT", "Expected an alias after 'as'").value
        return (ident_tok.value, alias)

    def parse_try(self):
        tok = self.expect("TRY")
        try_block = self.parse_block({"CATCH"})
        catch_line = self.expect("CATCH", "Expected 'catch' after 'try' block").line
        err_name = self.expect("IDENT", "Expected an error variable name after 'catch'").value
        catch_block = self.parse_block({"END"})
        self.expect("END", "Expected 'end' to close try/catch")
        node = A.TryStmt(try_block, err_name, catch_block, tok.line)
        node.catch_line = catch_line
        return node

    def parse_assert(self):
        tok = self.expect("ASSERT")
        expr = self.parse_expression()
        message = None
        if self.match("COMMA"):
            message = self.parse_expression()
        return A.AssertStmt(expr, message, tok.line)

    # ---- expressions (precedence climbing) ----

    def parse_expression(self):
        return self.parse_assignment()

    def parse_assignment(self):
        left = self.parse_coalesce()
        if self.match("EQ"):
            tok = self.peek()
            value = self.parse_assignment()
            return self._at(A.Assign(left, value, tok.line), getattr(left, "col", tok.col))
        return left

    def parse_coalesce(self):
        # `value ?? fallback` — use the fallback when value is none
        left = self.parse_or()
        while self.check("COALESCE"):
            tok = self.advance()
            right = self.parse_or()
            left = self._at(A.BinaryOp("??", left, right, tok.line), getattr(left, "col", tok.col))
        return left

    def parse_or(self):
        left = self.parse_and()
        while self.check("OR"):
            tok = self.advance()
            right = self.parse_and()
            left = self._at(A.BinaryOp("or", left, right, tok.line), getattr(left, "col", tok.col))
        return left

    def parse_and(self):
        left = self.parse_equality()
        while self.check("AND"):
            tok = self.advance()
            right = self.parse_equality()
            left = self._at(A.BinaryOp("and", left, right, tok.line), getattr(left, "col", tok.col))
        return left

    def parse_equality(self):
        left = self.parse_comparison()
        while self.check("EQEQ", "NOTEQ"):
            tok = self.advance()
            right = self.parse_comparison()
            left = self._at(A.BinaryOp(tok.value, left, right, tok.line), getattr(left, "col", tok.col))
        return left

    def parse_comparison(self):
        left = self.parse_term()
        while self.check("LT", "GT", "LTEQ", "GTEQ"):
            tok = self.advance()
            right = self.parse_term()
            left = self._at(A.BinaryOp(tok.value, left, right, tok.line), getattr(left, "col", tok.col))
        return left

    def parse_term(self):
        left = self.parse_factor()
        while self.check("PLUS", "MINUS"):
            tok = self.advance()
            right = self.parse_factor()
            left = self._at(A.BinaryOp(tok.value, left, right, tok.line), getattr(left, "col", tok.col))
        return left

    def parse_factor(self):
        left = self.parse_unary()
        while self.check("STAR", "SLASH", "PERCENT"):
            tok = self.advance()
            right = self.parse_unary()
            left = self._at(A.BinaryOp(tok.value, left, right, tok.line), getattr(left, "col", tok.col))
        return left

    def parse_unary(self):
        if self.check("NOT", "MINUS"):
            tok = self.advance()
            operand = self.parse_unary()
            op = "not" if tok.type == "NOT" else "-"
            return self._at(A.UnaryOp(op, operand, tok.line), tok.col)
        return self.parse_call()

    def parse_call(self):
        expr = self.parse_primary()
        while True:
            if self.match("LPAREN"):
                tok = self.tokens[self.pos - 1]
                args = self.parse_args()
                self.expect("RPAREN", "Expected ')' to close call arguments")
                expr = self._at(A.Call(expr, args, tok.line), getattr(expr, "col", tok.col))
            elif self.match("DOT"):
                tok = self.tokens[self.pos - 1]
                name_tok = self.expect("IDENT", "Expected a field or method name after '.'")
                expr = self._at(A.Get(expr, name_tok.value, tok.line), name_tok.col)
            elif self.match("LBRACKET"):
                tok = self.tokens[self.pos - 1]
                index = self.parse_expression()
                self.expect("RBRACKET", "Expected ']' to close index expression")
                expr = self._at(A.Index(expr, index, tok.line), getattr(expr, "col", tok.col))
            else:
                break
        return expr

    def parse_args(self):
        args = []
        if self.check("RPAREN"):
            return args
        args.append(self.parse_arg())
        while self.match("COMMA"):
            args.append(self.parse_arg())
        return args

    def parse_arg(self):
        if self.check("IDENT") and self.peek(1).type == "COLON":
            name = self.advance().value
            self.advance()  # consume ':'
            value = self.parse_expression()
            return A.Arg(name, value)
        return A.Arg(None, self.parse_expression())

    def parse_primary(self):
        tok = self.peek()
        if tok.type == "INT" or tok.type == "FLOAT":
            self.advance()
            return self._at(A.Literal(tok.value, tok.line), tok.col)
        if tok.type == "STRING":
            self.advance()
            lit = self._at(A.Literal(tok.value, tok.line), tok.col)
            if tok.raw:
                lit.raw = True          # remembered so the formatter keeps the """ form
            return lit
        if tok.type == "TEMPLATE_STRING":
            self.advance()
            parts = []
            for kind, text in tok.value:
                if kind == "str":
                    if text:
                        parts.append(("str", text))
                else:
                    sub_tokens = _tokenize_for_interp(text, tok.line)
                    sub_expr = Parser(sub_tokens).parse_expression()
                    parts.append(("expr", sub_expr))
            return self._at(A.InterpString(parts, tok.line), tok.col)
        if tok.type == "TRUE":
            self.advance()
            return self._at(A.Literal(True, tok.line), tok.col)
        if tok.type == "FALSE":
            self.advance()
            return self._at(A.Literal(False, tok.line), tok.col)
        if tok.type == "NONE":
            self.advance()
            return self._at(A.Literal(None, tok.line), tok.col)
        if tok.type == "IDENT":
            self.advance()
            return self._at(A.Identifier(tok.value, tok.line), tok.col)
        if tok.type == "LPAREN":
            self.advance()
            expr = self.parse_expression()
            self.expect("RPAREN", "Expected ')' to close parenthesized expression")
            return expr
        if tok.type == "LBRACKET":
            self.advance()
            elements = []
            if not self.check("RBRACKET"):
                elements.append(self.parse_expression())
                while self.match("COMMA"):
                    elements.append(self.parse_expression())
            self.expect("RBRACKET", "Expected ']' to close list literal")
            return self._at(A.ListLiteral(elements, tok.line), tok.col)
        if tok.type == "LBRACE":
            self.advance()
            pairs = []
            if not self.check("RBRACE"):
                pairs.append(self.parse_map_pair())
                while self.match("COMMA"):
                    if self.check("RBRACE"):
                        break
                    pairs.append(self.parse_map_pair())
            self.expect("RBRACE", "Expected '}' to close map literal")
            return self._at(A.MapLiteral(pairs, tok.line), tok.col)
        raise ParseError(f"Unexpected token {tok.type} ({tok.value!r})", tok.line)

    def parse_map_pair(self):
        key = self.parse_expression()
        self.expect("COLON", "Expected ':' between a map key and its value")
        value = self.parse_expression()
        return (key, value)


def _tokenize_for_interp(source, line):
    """Tokenize the source text found inside a `{...}` string interpolation."""
    from .lexer import tokenize, LexError
    try:
        return tokenize(source)
    except LexError as e:
        raise ParseError(
            f"invalid expression inside string interpolation '{{{source}}}': {e.args[0]}",
            line,
        ) from e


def parse(tokens):
    return Parser(tokens).parse_program()
