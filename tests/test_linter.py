"""`calyre lint`."""
import os
import unittest
from calyre.linter import lint_source, RULES
from tests.helpers import cli, project


def lint(src, disabled=(), library=False):
    # snippets that only declare functions would all trigger `library-without-pub`;
    # it is muted unless a test is about that rule
    off = set(disabled) | (set() if library else {"library-without-pub"})
    errors, diags = lint_source(src, "<source>", off)
    return errors, [(d.rule, d.line) for d in diags]


def rules(src, disabled=(), library=False):
    return sorted({r for r, _ in lint(src, disabled, library)[1]})


class TestRules(unittest.TestCase):
    def test_unused_variable(self):
        self.assertEqual(rules('func f()\n    let a = 1\nend'), ["unused-variable"])
        self.assertEqual(rules('func f()\n    let a = 1\n    print(a)\nend'), [])
        self.assertEqual(rules('func f()\n    let _a = 1\nend'), [])

    def test_write_only_variable_is_unused_but_read_modify_write_is_used(self):
        self.assertEqual(rules('func f()\n    let a = 1\n    a = 2\nend'), ["unused-variable"])
        self.assertEqual(rules('func f()\n    let a = 1\n    a = a + 1\n    print(a)\nend'), [])

    def test_collection_and_field_writes_count_as_use(self):
        self.assertEqual(rules('func f()\n    let xs = [1]\n    xs[0] = 2\nend'), [])
        self.assertEqual(rules('struct P\n    x: int\nend\nfunc f()\n    let p = P(x: 1)\n    p.x = 2\nend'), [])

    def test_use_inside_nested_blocks_and_interpolation(self):
        src = 'func f()\n    let a = 1\n    if true\n        print("v {a}")\n    end\nend'
        self.assertNotIn("unused-variable", rules(src))

    def test_unused_variable_in_nested_block(self):
        self.assertEqual(rules('func f()\n    for i in [1]\n        let t = i\n    end\nend'), ["unused-variable"])

    def test_loop_and_catch_variables_and_parameters_are_not_reported(self):
        self.assertEqual(rules('func f(a: int)\n    for i in [1]\n        print(1)\n    end\n'
                               '    try\n        error("x")\n    catch e\n        print(1)\n    end\nend'), [])

    def test_module_level_lets_are_not_reported(self):
        self.assertEqual(rules('let LIMIT = 3'), [])

    def test_unused_import(self):
        self.assertEqual(rules('use math\nprint(1)'), ["unused-import"])
        self.assertEqual(rules('use math\nprint(math.pi)'), [])
        self.assertEqual(rules('use math as m\nprint(m.pi)'), [])
        self.assertEqual(rules('use sqrt from math\nprint(1)'), ["unused-import"])

    def test_import_used_only_inside_a_function_defined_earlier(self):
        self.assertEqual(rules('use math\nfunc f() -> float\n    return math.pi\nend\nprint(f())'), [])

    def test_import_used_only_in_a_type_annotation(self):
        # the module is imported just to name its type
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "shapes.cly"), "w") as f:
                f.write("pub struct P\n    x: int\nend")
            errors, diags = lint_source('use shapes\nfunc f(p: shapes.P) -> int\n    return p.x\nend\n',
                                        os.path.join(d, "main.cly"))
            self.assertEqual([x.rule for x in diags], [])

    def test_unused_function_rules(self):
        self.assertEqual(rules('func _helper()\n    print(1)\nend'), ["unused-function"])
        self.assertEqual(rules('func helper()\n    print(1)\nend\nprint(2)'), [])           # script: might be exported
        self.assertEqual(rules('pub func a()\n    print(1)\nend\nfunc b()\n    print(2)\nend'), ["unused-function"])
        self.assertEqual(rules('pub func a()\n    print(1)\nend\nfunc b()\n    print(2)\nend\nb()'), [])
        self.assertEqual(rules('pub func a()\n    print(1)\nend\nfunc test_x()\n    print(2)\nend'), [])

    def test_unreachable_code(self):
        self.assertEqual(rules('func f() -> int\n    return 1\n    print(2)\nend'), ["unreachable-code"])
        self.assertEqual(rules('while true\n    break\n    print(1)\nend'), ["unreachable-code"])
        self.assertEqual(rules('func f()\n    error("x")\n    print(1)\nend'), ["unreachable-code"])
        self.assertEqual(rules('func f(a: int) -> int\n    if a > 0\n        return 1\n    else\n        return 2\n    end\n    print(1)\nend'),
                         ["unreachable-code"])
        self.assertEqual(rules('func f(a: int) -> int\n    if a > 0\n        return 1\n    end\n    return 2\nend'), [])

    def test_shadowed_builtin(self):
        self.assertEqual(rules('func f()\n    let len = 1\n    print(len)\nend'), ["shadowed-builtin"])
        self.assertEqual(rules('func str() -> int\n    return 1\nend\nprint(str())'), ["shadowed-builtin"])

    def test_naming(self):
        self.assertEqual(rules('func myFunc()\n    print(1)\nend\nmyFunc()'), ["naming-convention"])
        self.assertEqual(rules('struct point\n    x: int\nend'), ["naming-convention"])
        self.assertEqual(rules('let MAX_SIZE = 10\nlet max_size = 3\nprint(max_size)'), [])
        self.assertEqual(rules('func f()\n    let badName = 1\n    print(badName)\nend'), ["naming-convention"])
        self.assertEqual(rules('func f()\n    let _ = 1\n    let _tmp_1 = 2\n    print(_tmp_1)\nend'), [])        # `_` names are exempt

    def test_compare_to_bool_and_constant_conditions(self):
        self.assertEqual(rules('let a = true\nif a == true\n    print(1)\nend'), ["compare-to-bool"])
        self.assertEqual(rules('let a = true\nif a != false\n    print(1)\nend'), ["compare-to-bool"])
        self.assertEqual(rules('if true\n    print(1)\nend'), ["constant-condition"])
        self.assertEqual(rules('while false\n    print(1)\nend'), ["constant-condition"])
        self.assertEqual(rules('while true\n    break\nend'), [])                   # idiomatic: not reported
        self.assertEqual(rules('let a = 1\nif a == a\n    print(1)\nend'), ["constant-condition"])

    def test_library_without_pub(self):
        lib = 'func a() -> int\n    return 1\nend'
        self.assertEqual(rules(lib, library=True), ["library-without-pub"])
        self.assertEqual(rules('pub ' + lib, library=True), [])
        self.assertEqual(rules(lib + '\nprint(a())', library=True), [])                          # has executable code: a script

    def test_pub_missing_return_type(self):
        self.assertEqual(rules('pub func f(a: int)\n    return a\nend'), ["pub-missing-return-type"])
        self.assertEqual(rules('pub func f(a: int) -> int\n    return a\nend'), [])
        self.assertEqual(rules('pub func f(a: int)\n    print(a)\nend'), [])

    def test_sql_injection_risk(self):
        for q in ('"SELECT * FROM t WHERE n = \'" + name + "\'"', '"SELECT * FROM t WHERE n = {name}"'):
            for method in ("query", "execute", "query_one"):
                self.assertEqual(rules(f'use sql\nlet db = sql.open("sqlite::memory:")\nlet name = "a"\ndb.{method}({q})'),
                                 ["sql-injection-risk"], q)
        safe = ['db.query("SELECT * FROM t WHERE n = ?", [name])', 'db.execute("DELETE " + "FROM t")',
                'db.query("SELECT 1")', 'print("a" + name)']
        for call in safe:
            self.assertEqual(rules(f'use sql\nlet db = sql.open("sqlite::memory:")\nlet name = "a"\n{call}'), [], call)

    def test_checker_warnings_are_included(self):
        self.assertEqual(rules('let xs = []'), ["type-check"])

    def test_type_errors_are_returned_separately(self):
        errors, diags = lint('let a: int = "x"')
        self.assertEqual(len(errors), 1)

    def test_clean_code_has_no_findings(self):
        src = ('use math\n\npub struct Circle\n    radius: float\nend\n\n'
               'pub func area(c: Circle) -> float\n    return math.pi * c.radius * c.radius\nend\n')
        self.assertEqual(lint(src)[1], [])

    def test_every_rule_is_exercised_by_a_test_here(self):
        text = open(__file__).read()
        for r in RULES:
            self.assertIn(f'"{r}"', text, r)


class TestSuppression(unittest.TestCase):
    def test_disable_by_argument(self):
        self.assertEqual(rules('func f()\n    let a = 1\nend', disabled=["unused-variable"]), [])
        self.assertEqual(rules('func f()\n    let a = 1\nend', disabled=["unused-variable"], library=True),
                         ["library-without-pub"])

    def test_trailing_ignore_comment(self):
        self.assertEqual(rules('func f()\n    let a = 1  // lint-ignore\nend'), [])
        self.assertEqual(rules('func f()\n    let a = 1  // lint-ignore: unused-variable\nend'), [])

    def test_ignore_comment_above(self):
        self.assertEqual(rules('func f()\n    // lint-ignore: unused-variable\n    let a = 1\nend'), [])

    def test_ignore_is_per_rule_and_per_line(self):
        self.assertEqual(rules('func f()\n    let a = 1  // lint-ignore: naming-convention\nend'), ["unused-variable"])
        self.assertEqual(rules('func f()\n    let a = 1  // lint-ignore\n    let b = 2\nend'), ["unused-variable"])


class TestLintCli(unittest.TestCase):
    def test_exit_codes_and_format(self):
        with project({"a.cly": 'func f()\n    let a = 1\nend\n', "b.cly": 'print(1)\n'}) as d:
            code, out, _ = cli("lint", d)
            self.assertEqual(code, 1)
            self.assertIn("a.cly:2:5: warning: [unused-variable] 'a' is never used", out.replace("\\", "/").replace(d.replace("\\", "/") + "/", ""))
            self.assertNotIn("b.cly:", out)
            self.assertEqual(cli("lint", os.path.join(d, "b.cly"))[0], 0)

    def test_disable_option(self):
        with project({"a.cly": 'func f()\n    let a = 1\nend\n'}) as d:
            self.assertEqual(cli("lint", "--disable", "unused-variable,library-without-pub", d)[0], 0)
            code, _, err = cli("lint", "--disable", "nope", d)
            self.assertEqual((code, "unknown rule" in err), (1, True))

    def test_project_configuration(self):
        files = {"calyre.toml": '[project]\nname = "x"\n\n[lint]\ndisable = ["unused-variable", "library-without-pub"]\n',
                 "a.cly": 'func f()\n    let a = 1\nend\n'}
        with project(files) as d:
            self.assertEqual(cli("lint", d)[0], 0)

    def test_type_errors_and_syntax_errors_fail_the_lint(self):
        with project({"a.cly": 'let a: int = "x"\n'}) as d:
            self.assertEqual(cli("lint", d)[0], 1)
        with project({"a.cly": 'func f(\n'}) as d:
            code, _, err = cli("lint", d)
            self.assertEqual((code, "syntax error" in err), (1, True))

    def test_rules_listing_and_unknown_option(self):
        code, out, _ = cli("lint", "--rules")
        self.assertEqual(code, 0)
        self.assertEqual(out.split(), list(RULES))
        self.assertEqual(cli("lint", "--bogus")[0], 1)

    def test_the_shipped_examples_are_lint_clean(self):
        from tests.helpers import ROOT
        code, out, _ = cli("lint", os.path.join(ROOT, "examples"))
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
