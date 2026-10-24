"""`use "path"`: imports by file path (relative to the importing file, or absolute)."""
import os
import unittest
from tests.helpers import cli, errors, analyze, project, run, ast_dump
from calyre.formatter import format_source

LIB = 'pub func hello(n: str) -> str\n    return "hi {n}"\nend\npub struct Tag\n    id: int\nend'


class TestPathImports(unittest.TestCase):
    def test_relative_with_and_without_extension(self):
        with project({"lib.cly": LIB}) as d:
            for spec in ("./lib.cly", "./lib", "lib.cly"):
                self.assertEqual(errors(f'use "{spec}"\nlet s: str = lib.hello("x")', d), [], spec)
                self.assertEqual(run(f'use "{spec}"\nprint(lib.hello("x"))', d).strip(), "hi x")

    def test_alias_and_names_from_path(self):
        with project({"lib.cly": LIB}) as d:
            self.assertEqual(run('use "./lib.cly" as l\nprint(l.hello("a"))', d).strip(), "hi a")
            self.assertEqual(run('use hello, Tag from "./lib.cly"\nlet t: Tag = Tag(id: 1)\nprint(hello("b"))', d).strip(), "hi b")

    def test_parent_and_nested_folders(self):
        with project({"shared/util.cly": LIB, "app/sub/main.cly": 'use "../../shared/util"\nprint(util.hello("up"))'}) as d:
            code, out, err = cli("run", os.path.join(d, "app", "sub", "main.cly"), cwd="/")
            self.assertEqual((code, out.strip()), (0, "hi up"), err)

    def test_relative_to_the_importing_file_not_the_working_directory(self):
        files = {"proj/main.cly": 'use "./lib.cly"\nprint(lib.hello("w"))', "proj/lib.cly": LIB,
                 "elsewhere/lib.cly": 'pub func hello(n: str) -> str\n    return "WRONG"\nend'}
        with project(files) as d:
            code, out, _ = cli("run", os.path.join(d, "proj", "main.cly"), cwd=os.path.join(d, "elsewhere"))
            self.assertEqual(out.strip(), "hi w")

    def test_a_module_resolves_its_own_imports_relative_to_itself(self):
        files = {"main.cly": 'use "./lib/outer.cly"\nprint(outer.twice("x"))',
                 "lib/outer.cly": 'use "./inner.cly"\npub func twice(s: str) -> str\n    return inner.hello(s) + inner.hello(s)\nend',
                 "lib/inner.cly": LIB}
        with project(files) as d:
            code, out, err = cli("run", os.path.join(d, "main.cly"), cwd="/")
            self.assertEqual((code, out.strip()), (0, "hi xhi x"), err)

    def test_absolute_path_unix_style(self):
        with project({"lib/lib.cly": LIB, "app/main.cly": ""}) as d:
            absolute = os.path.join(d, "lib", "lib.cly").replace("\\", "/")
            src = f'use "{absolute}"\nprint(lib.hello("abs"))'
            self.assertEqual(run(src, os.path.join(d, "app")).strip(), "hi abs")

    def test_path_with_spaces(self):
        with project({"my libs/the lib.cly": LIB}) as d:
            src = 'use "./my libs/the lib.cly" as the_lib\nprint(the_lib.hello("sp"))'
            self.assertEqual(run(src, d).strip(), "hi sp")

    def test_backslashes_are_separators_on_every_platform(self):
        with project({"sub/lib.cly": LIB}) as d:
            self.assertEqual(run('use ".\\\\sub\\\\lib.cly"\nprint(lib.hello("bs"))', d).strip(), "hi bs")

    def test_same_file_by_name_and_by_path_is_one_module(self):
        files = {"lib.cly": 'print("loading lib")\n' + LIB}
        with project(files) as d:
            src = ('use lib\nuse "./lib.cly" as again\nlet t: lib.Tag = again.Tag(id: 1)\n'
                   'print(lib.hello("one"))')
            self.assertEqual(errors(src, d), [])                    # same types: one module
            self.assertEqual(run(src, d).split("\n")[:1], ["loading lib"])
            self.assertEqual(run(src, d).count("loading lib"), 1)   # loaded once

    def test_two_different_files_with_the_same_name_do_not_mix_their_types(self):
        files = {"a/lib.cly": 'pub struct T\n    x: int\nend', "b/lib.cly": 'pub struct T\n    x: int\nend'}
        with project(files) as d:
            src = 'use "./a/lib.cly" as one\nuse "./b/lib.cly" as two\nlet t: one.T = two.T(x: 1)'
            self.assertTrue(errors(src, d))

    def test_missing_file_names_where_it_looked(self):
        with project({}) as d:
            diag = analyze('use "./nope.cly"', d)[0][0]
            self.assertIn('cannot find module "./nope.cly"', diag.message)
            self.assertIn(os.path.join(d, "nope.cly"), diag.hint)
            self.assertIn("not to the current folder", diag.hint)
            self.assertEqual((diag.line, diag.col), (1, 1))

    def test_only_cly_files_can_be_imported(self):
        with project({"data.txt": "x"}) as d:
            diag = analyze('use "./data.txt"', d)[0][0]
            self.assertIn("only .cly files", diag.hint)

    def test_directory_is_not_a_module(self):
        with project({"folder/x.cly": LIB}) as d:
            self.assertTrue(errors('use "./folder"', d))

    def test_name_that_is_not_an_identifier_needs_an_alias(self):
        with project({"my-lib.cly": LIB}) as d:
            self.assertTrue(any("cannot use 'my-lib'" in m for m in errors('use "./my-lib.cly"', d)))
            self.assertEqual(errors('use "./my-lib.cly" as mylib\nlet s: str = mylib.hello("x")', d), [])

    def test_windows_drive_path_on_a_non_windows_machine_is_a_clear_error(self):
        if os.name == "nt":
            self.skipTest("only meaningful off Windows")
        diag = analyze('use "C:/Users/someone/Downloads/lib.cly"')[0][0]
        self.assertIn("cannot find module", diag.message)

    def test_interpolated_or_empty_paths_are_syntax_errors(self):
        from calyre.lexer import tokenize
        from calyre.calyre_parser import parse, ParseError
        for src in ('let x = "a"\nuse "./{x}.cly"', 'use ""'):
            with self.assertRaises(ParseError):
                parse(tokenize(src))

    def test_circular_import_through_paths(self):
        with project({"a.cly": 'use "./b.cly"\n', "b.cly": 'use "./a.cly"\n'}) as d:
            self.assertTrue(any("circular" in m for m in errors('use "./a.cly"', d)))

    def test_visibility_applies_to_path_imports(self):
        with project({"lib.cly": 'pub func a() -> int\n    return 1\nend\nfunc b() -> int\n    return 2\nend'}) as d:
            self.assertTrue(any("not public" in m for m in errors('use "./lib.cly"\nlib.b()', d)))

    def test_module_with_errors_is_reported_at_the_import(self):
        with project({"bad.cly": 'let x: int = "no"'}) as d:
            diags = analyze('use "./bad.cly"', d)[0]
            self.assertEqual(len(diags), 1)
            self.assertIn("bad.cly:1", diags[0].message)

    def test_runtime_error_in_path_imported_module_names_that_file(self):
        files = {"main.cly": 'use "./sub/boom.cly"\nprint(boom.go())',
                 "sub/boom.cly": 'pub func go() -> float\n    return 1 / 0\nend'}
        with project(files) as d:
            code, _, err = cli("run", os.path.join(d, "main.cly"))
            self.assertEqual(code, 1)
            self.assertIn("boom.cly:2: runtime error: division by zero", err)

    def test_formatter_keeps_path_imports(self):
        src = 'use "./lib.cly" as l\nuse "../x y/z" as z\nuse a, b as c from "./m.cly"\n'
        out = format_source(src)
        self.assertEqual(out, src)
        self.assertEqual(ast_dump(__import__("calyre.calyre_parser", fromlist=["parse"]).parse(
            __import__("calyre.lexer", fromlist=["tokenize"]).tokenize(out))),
            ast_dump(__import__("calyre.calyre_parser", fromlist=["parse"]).parse(
                __import__("calyre.lexer", fromlist=["tokenize"]).tokenize(src))))

    def test_path_imports_work_in_tests_and_dependencies(self):
        files = {"src/lib.cly": 'pub func double(n: int) -> int\n    return n * 2\nend',
                 "tests/test_lib.cly": 'use "../src/lib.cly"\nfunc test_double()\n    assert lib.double(4) == 8\nend'}
        with project(files) as d:
            code, out, err = cli("test", d)
            self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
