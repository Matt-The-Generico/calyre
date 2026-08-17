"""
Calyre lexer.

Converts raw source text into a flat list of Token objects.
No external dependencies — pure Python standard library.
"""
from dataclasses import dataclass

KEYWORDS = {
    "func", "let", "if", "elif", "else", "end", "while", "for", "in",
    "return", "break", "continue", "and", "or", "not", "true", "false",
    "none", "use", "struct", "match", "case", "pkg",
    "try", "catch", "assert", "as",
}

SYMBOLS_MULTI = [
    ("->", "ARROW"),
    ("==", "EQEQ"),
    ("!=", "NOTEQ"),
    ("<=", "LTEQ"),
    (">=", "GTEQ"),
]

SYMBOLS_SINGLE = {
    "+": "PLUS", "-": "MINUS", "*": "STAR", "/": "SLASH", "%": "PERCENT",
    "=": "EQ", "<": "LT", ">": "GT",
    "(": "LPAREN", ")": "RPAREN",
    "[": "LBRACKET", "]": "RBRACKET",
    "{": "LBRACE", "}": "RBRACE",
    ",": "COMMA", ".": "DOT", ":": "COLON", "?": "QUESTION",
}


class LexError(Exception):
    def __init__(self, message, line):
        super().__init__(f"Line {line}: {message}")
        self.line = line


@dataclass
class Token:
    type: str
    value: object
    line: int

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, line={self.line})"


def tokenize(source: str):
    tokens = []
    i = 0
    line = 1
    n = len(source)

    while i < n:
        c = source[i]

        # whitespace (not newline)
        if c in " \t\r":
            i += 1
            continue

        # newline
        if c == "\n":
            line += 1
            i += 1
            continue

        # comments
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                i += 1
            continue

        # strings (plain or interpolated, e.g. "Hello, {name}!")
        if c == '"':
            start_line = line
            i += 1
            parts = []          # list of ("str", text) / ("expr", source)
            buf = []
            has_interp = False
            while i < n and source[i] != '"':
                ch = source[i]
                if ch == "\\" and i + 1 < n:
                    nxt = source[i + 1]
                    escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "{": "{"}
                    buf.append(escapes.get(nxt, nxt))
                    i += 2
                    continue
                if ch == "{":
                    has_interp = True
                    parts.append(("str", "".join(buf)))
                    buf = []
                    i += 1
                    depth = 1
                    expr_start = i
                    while i < n and depth > 0:
                        if source[i] == "{":
                            depth += 1
                        elif source[i] == "}":
                            depth -= 1
                            if depth == 0:
                                break
                        elif source[i] == "\n":
                            line += 1
                        i += 1
                    if i >= n:
                        raise LexError(
                            "'{' opened for string interpolation was never closed with '}'",
                            start_line,
                        )
                    parts.append(("expr", source[expr_start:i]))
                    i += 1  # consume '}'
                    continue
                if ch == "\n":
                    line += 1
                buf.append(ch)
                i += 1
            if i >= n:
                raise LexError("Unterminated string literal", start_line)
            i += 1  # closing quote
            parts.append(("str", "".join(buf)))
            if has_interp:
                tokens.append(Token("TEMPLATE_STRING", parts, start_line))
            else:
                tokens.append(Token("STRING", "".join(p[1] for p in parts), start_line))
            continue

        # numbers
        if c.isdigit():
            start = i
            is_float = False
            while i < n and source[i].isdigit():
                i += 1
            if i < n and source[i] == "." and i + 1 < n and source[i + 1].isdigit():
                is_float = True
                i += 1
                while i < n and source[i].isdigit():
                    i += 1
            text = source[start:i]
            if is_float:
                tokens.append(Token("FLOAT", float(text), line))
            else:
                tokens.append(Token("INT", int(text), line))
            continue

        # identifiers / keywords
        if c.isalpha() or c == "_":
            start = i
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            text = source[start:i]
            if text in KEYWORDS:
                tokens.append(Token(text.upper(), text, line))
            else:
                tokens.append(Token("IDENT", text, line))
            continue

        # multi-char symbols
        matched = False
        for sym, kind in SYMBOLS_MULTI:
            if source.startswith(sym, i):
                tokens.append(Token(kind, sym, line))
                i += len(sym)
                matched = True
                break
        if matched:
            continue

        # single-char symbols
        if c in SYMBOLS_SINGLE:
            tokens.append(Token(SYMBOLS_SINGLE[c], c, line))
            i += 1
            continue

        raise LexError(f"Unexpected character {c!r}", line)

    tokens.append(Token("EOF", None, line))
    return tokens
