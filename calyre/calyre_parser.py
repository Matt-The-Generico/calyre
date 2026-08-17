"""
Calyre parser.

Recursive-descent parser implementing the EBNF grammar from
"Calyre — Fase 2: Sintaxe, Gramática e Tipos" (core subset).
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
        if tok.type in dispatch:
            return dispatch[tok.type]()
        expr = self.parse_expression()
        return A.ExprStmt(expr, tok.line)

    def parse_type(self):
        tok = self.expect("IDENT", "Expected a type name")
        params = []
        if self.match("LT"):
            params.append(self.parse_type())
            while self.match("COMMA"):
                params.append(self.parse_type())
            self.expect("GT", "Expected '>' to close generic type")
        optional = bool(self.match("QUESTION"))
        return A.TypeAnn(tok.value, optional, params)

    def parse_param(self):
        name = self.expect("IDENT").value
        self.expect("COLON", f"Expected ':' after parameter/field name '{name}'")
        type_ann = self.parse_type()
        return A.Param(name, type_ann)

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
        return A.FuncDecl(name, params, return_type, body, tok.line)

    def parse_struct(self):
        tok = self.expect("STRUCT")
        name = self.expect("IDENT").value
        fields = []
        while not self.check("END"):
            fields.append(self.parse_param())
        self.expect("END", f"Expected 'end' to close struct '{name}'")
        return A.StructDecl(name, fields, tok.line)

    def parse_if(self):
        tok = self.expect("IF")
        cond = self.parse_expression()
        block = self.parse_block({"ELIF", "ELSE", "END"})
        branches = [(cond, block)]
        while self.check("ELIF"):
            self.advance()
            cond2 = self.parse_expression()
            block2 = self.parse_block({"ELIF", "ELSE", "END"})
            branches.append((cond2, block2))
        else_block = None
        if self.match("ELSE"):
            else_block = self.parse_block({"END"})
        self.expect("END", "Expected 'end' to close if statement")
        return A.IfStmt(branches, else_block, tok.line)

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
        while self.match("CASE"):
            if self.check("IDENT") and self.peek().value == "_":
                self.advance()
                pattern = None
            else:
                pattern = self.parse_expression()
            block = self.parse_block({"CASE", "END"})
            cases.append((pattern, block))
        self.expect("END", "Expected 'end' to close match statement")
        return A.MatchStmt(subject, cases, tok.line)

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
        path = self.expect("IDENT").value
        while self.match("DOT"):
            path += "." + self.expect("IDENT").value
        alias = None
        if self.match("AS"):
            alias = self.expect("IDENT").value
        return A.UseStmt(path, alias, tok.line)

    def parse_try(self):
        tok = self.expect("TRY")
        try_block = self.parse_block({"CATCH"})
        self.expect("CATCH", "Expected 'catch' after 'try' block")
        err_name = self.expect("IDENT", "Expected an error variable name after 'catch'").value
        catch_block = self.parse_block({"END"})
        self.expect("END", "Expected 'end' to close try/catch")
        return A.TryStmt(try_block, err_name, catch_block, tok.line)

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
        left = self.parse_or()
        if self.match("EQ"):
            tok = self.peek()
            value = self.parse_assignment()
            return A.Assign(left, value, tok.line)
        return left

    def parse_or(self):
        left = self.parse_and()
        while self.check("OR"):
            tok = self.advance()
            right = self.parse_and()
            left = A.BinaryOp("or", left, right, tok.line)
        return left

    def parse_and(self):
        left = self.parse_equality()
        while self.check("AND"):
            tok = self.advance()
            right = self.parse_equality()
            left = A.BinaryOp("and", left, right, tok.line)
        return left

    def parse_equality(self):
        left = self.parse_comparison()
        while self.check("EQEQ", "NOTEQ"):
            tok = self.advance()
            right = self.parse_comparison()
            left = A.BinaryOp(tok.value, left, right, tok.line)
        return left

    def parse_comparison(self):
        left = self.parse_term()
        while self.check("LT", "GT", "LTEQ", "GTEQ"):
            tok = self.advance()
            right = self.parse_term()
            left = A.BinaryOp(tok.value, left, right, tok.line)
        return left

    def parse_term(self):
        left = self.parse_factor()
        while self.check("PLUS", "MINUS"):
            tok = self.advance()
            right = self.parse_factor()
            left = A.BinaryOp(tok.value, left, right, tok.line)
        return left

    def parse_factor(self):
        left = self.parse_unary()
        while self.check("STAR", "SLASH", "PERCENT"):
            tok = self.advance()
            right = self.parse_unary()
            left = A.BinaryOp(tok.value, left, right, tok.line)
        return left

    def parse_unary(self):
        if self.check("NOT", "MINUS"):
            tok = self.advance()
            operand = self.parse_unary()
            op = "not" if tok.type == "NOT" else "-"
            return A.UnaryOp(op, operand, tok.line)
        return self.parse_call()

    def parse_call(self):
        expr = self.parse_primary()
        while True:
            if self.match("LPAREN"):
                tok = self.tokens[self.pos - 1]
                args = self.parse_args()
                self.expect("RPAREN", "Expected ')' to close call arguments")
                expr = A.Call(expr, args, tok.line)
            elif self.match("DOT"):
                tok = self.tokens[self.pos - 1]
                name = self.expect("IDENT").value
                expr = A.Get(expr, name, tok.line)
            elif self.match("LBRACKET"):
                tok = self.tokens[self.pos - 1]
                index = self.parse_expression()
                self.expect("RBRACKET", "Expected ']' to close index expression")
                expr = A.Index(expr, index, tok.line)
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
            return A.Literal(tok.value, tok.line)
        if tok.type == "STRING":
            self.advance()
            return A.Literal(tok.value, tok.line)
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
            return A.InterpString(parts, tok.line)
        if tok.type == "TRUE":
            self.advance()
            return A.Literal(True, tok.line)
        if tok.type == "FALSE":
            self.advance()
            return A.Literal(False, tok.line)
        if tok.type == "NONE":
            self.advance()
            return A.Literal(None, tok.line)
        if tok.type == "IDENT":
            self.advance()
            return A.Identifier(tok.value, tok.line)
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
            return A.ListLiteral(elements, tok.line)
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
            return A.MapLiteral(pairs, tok.line)
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
