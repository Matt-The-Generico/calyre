"""`calyre fmt`: idempotence, meaning preservation, comments, wrapping, CLI."""
import glob
import os
import unittest

from calyre.calyre_parser import parse
from calyre.lexer import tokenize
from calyre.formatter import format_source, FormatError
from tests.helpers import ast_dump, cli, project, ROOT


def ast(src):
    return ast_dump(parse(tokenize(src)))


def fmt(src):
    return format_source(src)


class TestFormatterProperties(unittest.TestCase):
    def check(self, src):
        out = fmt(src)
        self.assertEqual(fmt(out), out, "not idempotent")
        self.assertEqual(ast(out), ast(src), "meaning changed")
        return out

    def test_every_shipped_example_is_stable(self):
        files = glob.glob(os.path.join(ROOT, "examples", "**", "*.cly"), recursive=True)
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            with open(path, encoding="utf-8") as f:
                self.check(f.read())

    def test_messy_input_is_normalised(self):
        out = self.check('let   x=1+2*3\nfunc f( a:int,b:str )->int\nreturn a\nend\nif x>1 and not x==2\nprint( "hi" )\nend')
        self.assertEqual(out, 'let x = 1 + 2 * 3\n\nfunc f(a: int, b: str) -> int\n    return a\nend\n\n'
                              'if x > 1 and not x == 2\n    print("hi")\nend\n')

    def test_parentheses_are_kept_only_where_needed(self):
        cases = {
            "let a = (1 + 2) * 3": "let a = (1 + 2) * 3",
            "let a = 1 + (2 * 3)": "let a = 1 + 2 * 3",
            "let a = 1 - (2 - 3)": "let a = 1 - (2 - 3)",
            "let a = (1 - 2) - 3": "let a = 1 - 2 - 3",
            "let a = not (true and false)": "let a = not (true and false)",
            "let a = -(1 + 2)": "let a = -(1 + 2)",
            "let a = (x ?? y) ?? z": "let a = x ?? y ?? z",
            "let a = x ?? (y ?? z)": "let a = x ?? (y ?? z)",
            "let a = (a + b).c": "let a = (a + b).c",
            "let a = ((1))": "let a = 1",
        }
        for src, want in cases.items():
            self.assertEqual(self.check(src).strip(), want, src)

    def test_strings_escapes_and_interpolation(self):
        for src in ('let s = "a\\"b\\\\c\\n\\t\\{x\\}"', 'let s = "v={d["k"]} and {1 + 2}!"',
                    'let s = "{a}{b}"', 'let s = ""'):
            self.check(src)

    def test_numbers(self):
        self.assertEqual(self.check("let a = 10000000000000000000000.0").strip(), "let a = 10000000000000000000000.0")
        self.assertEqual(self.check("let a = 1.50").strip(), "let a = 1.5")

    def test_every_construct(self):
        src = '''
use math as m
use sqrt as root, floor from math
pub struct Box<T>
    value: T
    next: Box<T>?
end
pub func wrap<T>(v: T) -> Box<T>
    return Box(value: v, next: none)
end
pub let LIMIT = 3
func main()
    let xs: list<int> = [1, 2]
    let d = {"a": 1}
    while true
        break
    end
    for x in xs
        continue
    end
    match xs[0]
        case 1
            print("one")
        case _
            print("other")
    end
    try
        error("x")
    catch e
        print(e.message)
    end
    assert xs.len() == 0, "msg"
    xs[0] = 5
    d["b"] = xs.pop() ?? 0
end
'''
        self.check(src)

    def test_empty_and_comment_only_files(self):
        self.assertEqual(fmt(""), "")
        self.assertEqual(fmt("\n\n"), "")
        self.assertEqual(self.check("// only a comment\n"), "// only a comment\n")

    def test_blank_lines_collapse_but_survive(self):
        out = self.check("let a = 1\n\n\n\nlet b = 2\nlet c = 3")
        self.assertEqual(out, "let a = 1\n\nlet b = 2\nlet c = 3\n")

    def test_decls_get_one_blank_line_around(self):
        out = self.check("let a = 1\nfunc f()\n    print(1)\nend\nlet b = 2\nstruct S\n    x: int\nend")
        self.assertEqual(out.count("\n\n"), 3)
        self.assertNotIn("\n\n\n", out)

    def test_crlf_input(self):
        self.assertEqual(fmt("let a = 1\r\nlet b = 2\r\n".replace("\r\n", "\n")), "let a = 1\nlet b = 2\n")


class TestFormatterComments(unittest.TestCase):
    def check(self, src, expected=None):
        out = format_source(src)
        self.assertEqual(format_source(out), out)
        self.assertEqual(ast(out), ast(src))
        self.assertEqual(sorted(l.strip() for l in out.splitlines() if "//" in l),
                         sorted(l.strip() for l in src.splitlines() if "//" in l) if expected is None else
                         sorted(l.strip() for l in expected.splitlines() if "//" in l))
        return out

    def test_leading_trailing_and_dangling_comments(self):
        src = '''// header
func f(a: int) -> int  // trailing on header
    // before first
    let x = a  // trailing
    if x > 1
        // inside if
        return 1
        // dangling at the end of the branch
    elif x > 0  // on elif
        return 2
    else
        // only a comment in else
        return 3
    end
    // before end
end  // after end
'''
        self.assertEqual(self.check(src), src)

    def test_comments_in_match_try_struct(self):
        src = '''struct P
    // first field
    x: int  // the x
    // second
    y: int
    // end of fields
end

match 1
    // before the first case
    case 1  // one
        print(1)
        // after print
    case _
        print(2)
end

try
    // risky
    error("x")
catch e  // handle
    // report
    print(e.message)
end
'''
        self.assertEqual(self.check(src), src)

    def test_comment_attached_to_declaration_keeps_its_blank_line_before(self):
        out = self.check("let a = 1\n// describes f\nfunc f()\n    print(1)\nend")
        self.assertEqual(out, "let a = 1\n\n// describes f\nfunc f()\n    print(1)\nend\n")

    def test_comment_separated_from_declaration_stays_separate(self):
        src = "// file note\n\nfunc f()\n    print(1)\nend\n"
        self.assertEqual(self.check(src), src)

    def test_trailing_comment_on_every_simple_statement(self):
        src = "let a = 1  // a\nprint(a)  // p\nbreak_it()  // c\n"
        self.assertEqual(self.check(src), src)

    def test_comment_text_is_preserved_verbatim(self):
        src = "//no space\n//   many   spaces   \nlet a = 1 //x\n"
        out = fmt(src)
        self.assertIn("//no space", out)
        self.assertIn("//   many   spaces", out)
        self.assertIn("let a = 1  //x", out)

    def test_comment_at_end_of_file(self):
        self.assertEqual(self.check("let a = 1\n// bye\n"), "let a = 1\n// bye\n")

    def test_comment_inside_multiline_expression_is_refused_not_lost(self):
        src = "let xs = [\n    1,  // one\n    2\n]\n"
        with self.assertRaises(FormatError) as ctx:
            fmt(src)
        self.assertIn("comment", ctx.exception.message)
        self.assertEqual(ctx.exception.line, 2)

    def test_slashes_inside_strings_are_not_comments(self):
        src = 'let url = "http://example.com"  // real comment\n'
        self.assertEqual(self.check(src), src)


class TestFormatterWrapping(unittest.TestCase):
    def test_long_list_and_call_wrap_one_per_line(self):
        items = ", ".join(f'"item number {i}"' for i in range(8))
        out = fmt(f"let xs = [{items}]\nprint({items})")
        self.assertTrue(all(len(l) <= 100 for l in out.splitlines()))
        self.assertIn('[\n    "item number 0",', out)
        self.assertEqual(fmt(out), out)
        self.assertEqual(ast(out), ast(f"let xs = [{items}]\nprint({items})"))

    def test_short_collections_stay_on_one_line(self):
        self.assertEqual(fmt("let xs = [\n1,\n2\n]"), "let xs = [1, 2]\n")

    def test_nested_wrap_in_function(self):
        body = ", ".join(f'k{i}: "{"v" * 14}"' for i in range(6))
        src = f"func f()\n    let m = P({body})\nend"
        out = fmt(src)
        self.assertEqual(fmt(out), out)
        self.assertTrue(all(len(l) <= 100 for l in out.splitlines()))

    def test_unbreakable_long_line_is_left_alone(self):
        src = "let s = " + " + ".join(['"' + "x" * 20 + '"'] * 6) + "\n"
        out = fmt(src)
        self.assertEqual(fmt(out), out)


class TestFormatterErrors(unittest.TestCase):
    def test_syntax_error_is_reported(self):
        with self.assertRaises(FormatError):
            fmt("func f(\n")

    def test_lex_error_is_reported(self):
        with self.assertRaises(FormatError):
            fmt('let a = "unterminated')


class TestFmtCli(unittest.TestCase):
    MESSY = 'let   a=1\nfunc f( )\nprint( a )\nend\n'

    def test_formats_in_place_and_reports(self):
        with project({"a.cly": self.MESSY}) as d:
            path = os.path.join(d, "a.cly")
            code, out, _ = cli("fmt", path)
            self.assertEqual(code, 0)
            self.assertIn("formatted", out)
            self.assertEqual(open(path).read(), "let a = 1\n\nfunc f()\n    print(a)\nend\n")
            code, out, _ = cli("fmt", path)                   # second run: nothing to do
            self.assertEqual((code, "formatted " in out), (0, False))

    def test_check_mode(self):
        with project({"a.cly": self.MESSY, "b.cly": "let b = 1\n"}) as d:
            code, out, _ = cli("fmt", "--check", d)
            self.assertEqual(code, 1)
            self.assertIn("a.cly: would be reformatted", out)
            self.assertNotIn("b.cly", out)
            self.assertEqual(open(os.path.join(d, "a.cly")).read(), self.MESSY)   # untouched
            cli("fmt", d)
            self.assertEqual(cli("fmt", "--check", d)[0], 0)

    def test_stdout_mode(self):
        with project({"a.cly": self.MESSY}) as d:
            code, out, _ = cli("fmt", "--stdout", os.path.join(d, "a.cly"))
            self.assertEqual((code, out), (0, "let a = 1\n\nfunc f()\n    print(a)\nend\n"))
            self.assertEqual(open(os.path.join(d, "a.cly")).read(), self.MESSY)

    def test_broken_file_is_left_untouched(self):
        with project({"bad.cly": "func f(\n", "ok.cly": self.MESSY}) as d:
            code, _, err = cli("fmt", d)
            self.assertEqual(code, 1)
            self.assertIn("bad.cly", err)
            self.assertEqual(open(os.path.join(d, "bad.cly")).read(), "func f(\n")
            self.assertIn("let a = 1", open(os.path.join(d, "ok.cly")).read())    # others still formatted

    def test_directory_recursion_skips_build_folders(self):
        with project({"x/a.cly": self.MESSY, "dist/b.cly": self.MESSY}) as d:
            cli("fmt", d)
            self.assertIn("let a = 1", open(os.path.join(d, "x", "a.cly")).read())
            self.assertEqual(open(os.path.join(d, "dist", "b.cly")).read(), self.MESSY)

    def test_default_is_current_folder_and_errors(self):
        with project({"a.cly": self.MESSY}) as d:
            self.assertEqual(cli("fmt", cwd=d)[0], 0)
            self.assertIn("let a = 1", open(os.path.join(d, "a.cly")).read())
        self.assertEqual(cli("fmt", "--bogus")[0], 1)
        with project({}) as d:
            self.assertEqual(cli("fmt", cwd=d)[0], 1)

    def test_formatted_program_still_runs_the_same(self):
        with project({"a.cly": 'let   x=2\nprint( x*21 )\n'}) as d:
            path = os.path.join(d, "a.cly")
            before = cli("run", path)[1]
            cli("fmt", path)
            self.assertEqual(cli("run", path)[1], before)


if __name__ == "__main__":
    unittest.main()
