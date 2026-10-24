"""Triple-quoted texts: literal, multi-line, no escapes, no {interpolation}."""
import unittest
from calyre.lexer import tokenize, LexError
from calyre.formatter import format_source
from tests.helpers import run, errors, ast_dump
from calyre.calyre_parser import parse


class TestRawStrings(unittest.TestCase):
    def test_content_is_literal(self):
        out = run('print("""{"a": 1} \\n {x} \\" """)').strip()
        self.assertEqual(out, '{"a": 1} \\n {x} \\"')

    def test_no_interpolation_and_no_escapes(self):
        self.assertEqual(run('let x = 5\nprint("""v={x}""")').strip(), "v={x}")
        self.assertEqual(run('print("""a\\tb""")').strip(), "a\\tb")

    def test_first_newline_is_dropped_and_lines_are_kept(self):
        self.assertEqual(run('print("""\nline one\n  line two\n""")'), "line one\n  line two\n\n")
        self.assertEqual(run('print("""\n\nx""")'), "\nx\n")

    def test_type_is_str_and_methods_work(self):
        self.assertEqual(errors('let s: str = """a"""'), [])
        self.assertTrue(errors('let n: int = """a"""'))
        self.assertEqual(run('print("""a,b""".split(","))').strip(), '["a", "b"]')

    def test_line_numbers_after_a_multiline_text(self):
        toks = tokenize('let a = """x\ny\nz"""\nlet b = 1')
        self.assertEqual([t.line for t in toks if t.type == "LET"], [1, 4])

    def test_unterminated(self):
        with self.assertRaises(LexError):
            tokenize('let a = """never closed')

    def test_empty_triple_quoted_text(self):
        self.assertEqual(run('print("""""" == "")').strip(), "true")

    def test_old_programs_are_unaffected(self):
        # `""` followed by a space and another text were never adjacent before; normal strings unchanged
        self.assertEqual(run('print("" + "a")').strip(), "a")
        self.assertEqual(run('print("a\\"b")').strip(), 'a"b')

    def test_formatter_keeps_triple_quoted_form_and_is_stable(self):
        src = 'let j = """{"a": [1, 2], "b": "{x}"}"""\nlet m = """\nline one\n\n  line "two"\n"""\nprint(j)  // c\n'
        out = format_source(src)
        self.assertEqual(out, src)
        self.assertEqual(format_source(out), out)

    def test_formatter_does_not_invent_blank_lines_after_multiline_text(self):
        src = 'let m = """\na\nb\n"""\nprint(m)\n'
        self.assertEqual(format_source(src), src)

    def test_formatter_never_changes_the_value(self):
        for body in ('x', '\nx', 'a\n', '\n\nq\n', '"quoted" x', '{b}'):
            src = f'let t = """{body}"""\n'
            out = format_source(src)
            self.assertEqual(ast_dump(parse(tokenize(out))), ast_dump(parse(tokenize(src))), repr(body))

    def test_a_text_cannot_end_with_a_quote_character(self):
        # documented limitation (same as Python): the first """ closes the text
        with self.assertRaises(LexError):
            tokenize('let t = """say "hi""""')
        self.assertEqual(run('print("""say "hi" """.trim())').strip(), 'say "hi"')

    def test_normal_strings_ending_with_a_quote_format_stably(self):
        out = format_source('let t = "say \\"hi\\""\n')
        self.assertEqual(format_source(out), out)


if __name__ == "__main__":
    unittest.main()
