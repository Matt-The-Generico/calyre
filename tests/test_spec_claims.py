"""One test per behavioural claim in docs/SPEC.md that no other test covers."""
import unittest
from tests.helpers import errors, run


class TestSpecClaims(unittest.TestCase):
    def test_builtin_can_be_shadowed_at_module_level(self):
        self.assertEqual(errors('func len(a: int) -> int\n    return a\nend\nprint(len(3))'), [])

    def test_while_narrowing(self):
        src = ('func f(a: int?) -> int\n    let n = 0\n    while a != none\n        n = n + a\n        a = none\n    end\n    return n\nend')
        self.assertEqual(errors(src), [])

    def test_for_over_map_iterates_keys(self):
        self.assertEqual(run('for k in {"a": 1, "b": 2}\n    print(k)\nend').split(), ["a", "b"])

    def test_interpolation_escape(self):
        self.assertEqual(run('print("\\{literal\\} {1 + 1}")').strip(), "{literal} 2")

    def test_truthiness_values(self):
        self.assertEqual(run('print(not 0)\nprint(not "")\nprint(not [])\nprint(not none)\nprint(not 1)').split(),
                         ["true", "true", "true", "true", "false"])

    def test_negative_index(self):
        self.assertEqual(run("let xs = [1, 2, 3]\nprint(xs[-1])").strip(), "3")

    def test_text_is_not_ordered(self):
        self.assertTrue(errors('print("a" < "b")'))

    def test_top_level_declarations_are_hoisted_but_let_is_not(self):
        self.assertEqual(errors('print(f())\nfunc f() -> int\n    return 1\nend'), [])
        self.assertTrue(errors('print(x)\nlet x = 1'))

    def test_int_is_arbitrary_precision(self):
        self.assertEqual(run("print(10000000000000000000000 * 10)").strip(), "100000000000000000000000")

    def test_catch_exposes_message_and_line(self):
        out = run('try\n    error("boom")\ncatch e\n    print(e.message)\n    print(e.line ?? 0)\nend')
        self.assertEqual(out.split()[0], "boom")

    def test_assert_message_shows_values(self):
        from calyre.interpreter import CalyreRuntimeError
        with self.assertRaises(CalyreRuntimeError) as ctx:
            run("let x = 5\nassert x > 10")
        self.assertIn("x > 10 (x = 5, 10 = 10)", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
