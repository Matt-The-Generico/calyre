import unittest
from calyre.lexer import tokenize, LexError


class TestLexer(unittest.TestCase):
    def test_basic_tokens(self):
        toks = tokenize("let x = 5")
        types = [t.type for t in toks]
        self.assertEqual(types, ["LET", "IDENT", "EQ", "INT", "EOF"])

    def test_keywords_recognized(self):
        toks = tokenize("func if else end while for in return break continue try catch assert as")
        types = [t.type for t in toks[:-1]]
        self.assertEqual(
            types,
            ["FUNC", "IF", "ELSE", "END", "WHILE", "FOR", "IN", "RETURN",
             "BREAK", "CONTINUE", "TRY", "CATCH", "ASSERT", "AS"],
        )

    def test_float_vs_int(self):
        toks = tokenize("1 1.5 10")
        self.assertEqual(toks[0].type, "INT")
        self.assertEqual(toks[0].value, 1)
        self.assertEqual(toks[1].type, "FLOAT")
        self.assertEqual(toks[1].value, 1.5)

    def test_string_escapes(self):
        toks = tokenize(r'"a\nb\tc\"d"')
        self.assertEqual(toks[0].value, "a\nb\tc\"d")

    def test_comment_ignored(self):
        toks = tokenize("let x = 1 // this is a comment\nlet y = 2")
        types = [t.type for t in toks]
        self.assertNotIn("COMMENT", types)
        self.assertEqual(types.count("LET"), 2)

    def test_unterminated_string_raises(self):
        with self.assertRaises(LexError):
            tokenize('"unterminated')

    def test_unexpected_char_raises(self):
        with self.assertRaises(LexError):
            tokenize("let x = 5 @")

    def test_template_string_produces_special_token(self):
        toks = tokenize('"Hello, {name}!"')
        self.assertEqual(toks[0].type, "TEMPLATE_STRING")
        parts = toks[0].value
        self.assertEqual(parts[0], ("str", "Hello, "))
        self.assertEqual(parts[1], ("expr", "name"))
        self.assertEqual(parts[2], ("str", "!"))

    def test_plain_string_without_braces_is_normal_string(self):
        toks = tokenize('"no interpolation here"')
        self.assertEqual(toks[0].type, "STRING")
        self.assertEqual(toks[0].value, "no interpolation here")

    def test_escaped_brace_is_literal(self):
        toks = tokenize(r'"literal \{brace\}"')
        self.assertEqual(toks[0].type, "STRING")
        self.assertEqual(toks[0].value, "literal {brace}")

    def test_braces_tokens_for_maps(self):
        toks = tokenize("{ }")
        types = [t.type for t in toks]
        self.assertEqual(types, ["LBRACE", "RBRACE", "EOF"])

    def test_line_tracking(self):
        toks = tokenize("let x = 1\nlet y = 2")
        let_tokens = [t for t in toks if t.type == "LET"]
        self.assertEqual(let_tokens[0].line, 1)
        self.assertEqual(let_tokens[1].line, 2)


if __name__ == "__main__":
    unittest.main()
