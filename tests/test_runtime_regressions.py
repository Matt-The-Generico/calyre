"""Regression tests for bugs found by the Phase 4 audit (each failed before its fix)."""
import unittest
from tests.helpers import run
from calyre.interpreter import CalyreRuntimeError


class TestRuntimeRegressions(unittest.TestCase):
    def test_builtin_wrong_arity_is_a_calyre_error_not_a_python_traceback(self):
        with self.assertRaises(CalyreRuntimeError):
            run("print(len(1, 2))", check=False)

    def test_stdlib_wrong_argument_type_is_a_calyre_error(self):
        with self.assertRaises(CalyreRuntimeError):
            run("use text\nprint(text.upper(5))", check=False)

    def test_infinite_recursion_is_a_calyre_error(self):
        with self.assertRaises(CalyreRuntimeError) as ctx:
            run("func f(n: int) -> int\n    return f(n + 1)\nend\nprint(f(0))")
        self.assertIn("maximum call depth", str(ctx.exception))

    def test_recursion_of_reasonable_depth_works(self):
        src = ("func sum_to(n: int) -> int\n    if n == 0\n        return 0\n    end\n"
               "    return n + sum_to(n - 1)\nend\nprint(sum_to(500))")
        self.assertEqual(run(src).strip(), "125250")

    def test_depth_counter_recovers_after_error_caught(self):
        src = ('func f(n: int) -> int\n    return f(n + 1)\nend\n'
               'try\n    f(0)\ncatch e\n    print("caught")\nend\n'
               'func g() -> int\n    return 1\nend\nprint(g())')
        self.assertEqual(run(src).split(), ["caught", "1"])

    def test_break_inside_function_does_not_escape_into_callers_loop(self):
        with self.assertRaises(CalyreRuntimeError):
            run("func f()\n    break\nend\nwhile true\n    f()\nend", check=False)

    def test_top_level_break_and_return_are_calyre_errors(self):
        with self.assertRaises(CalyreRuntimeError):
            run("break", check=False)
        with self.assertRaises(CalyreRuntimeError):
            run("return 5", check=False)

    def test_list_assignment_out_of_range_is_a_calyre_error(self):
        with self.assertRaises(CalyreRuntimeError):
            run("let xs: list<int> = []\nxs[0] = 1")

    def test_division_always_returns_float(self):
        self.assertEqual(run("print(6 / 2)\nprint(7 / 2)").split(), ["3.0", "3.5"])

    def test_floor_div(self):
        self.assertEqual(run("use math\nprint(math.floor_div(7, 2))").strip(), "3")

    def test_and_or_return_booleans(self):
        self.assertEqual(run('print(true and false)\nprint(false or true)\nprint(not false)').split(),
                         ["false", "true", "true"])

    def test_non_bool_conditions_are_runtime_errors_at_dynamic_boundaries(self):
        # the checker rejects these statically; `any` values are checked when they run
        for src in ('let a: any = 1\nif a\n    print(1)\nend', 'let a: any = 0\nwhile a\n    break\nend',
                    'let a: any = "x"\nprint(not a)', 'let a: any = 1\nprint(a and true)'):
            with self.assertRaises(CalyreRuntimeError) as ctx:
                run(src)
            self.assertIn("must be a bool", str(ctx.exception))

    def test_and_or_short_circuit(self):
        self.assertEqual(run('func boom() -> bool\n    error("no")\nend\nprint(false and boom())\nprint(true or boom())').split(),
                         ["false", "true"])

    def test_coalesce_is_lazy_and_returns_left_when_present(self):
        src = ('func boom() -> str\n    error("no")\nend\n'
               'let a: str? = "x"\nprint(a ?? boom())\nlet b: str? = none\nprint(b ?? "d")')
        self.assertEqual(run(src).split(), ["x", "d"])

    def test_narrowed_optional_runs(self):
        src = ('func f(a: int?) -> int\n    if a == none\n        return 0\n    end\n    return a + 1\nend\n'
               'print(f(none))\nprint(f(4))')
        self.assertEqual(run(src).split(), ["0", "5"])

    def test_inferred_function_runs(self):
        src = ('func fact(n: int)\n    if n <= 1\n        return 1\n    end\n    return n * fact(n - 1)\nend\n'
               'print(fact(10))')
        self.assertEqual(run(src).strip(), "3628800")


if __name__ == "__main__":
    unittest.main()
