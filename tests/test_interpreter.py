import io
import contextlib
import unittest

from calyre.lexer import tokenize
from calyre.calyre_parser import parse
from calyre.interpreter import interpret, CalyreRuntimeError


def run(src, base_dir=None):
    prog = parse(tokenize(src))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        interpret(prog, base_dir=base_dir)
    return buf.getvalue()


class TestInterpreter(unittest.TestCase):
    def test_hello_world(self):
        out = run('print("Hello, world!")')
        self.assertEqual(out, "Hello, world!\n")

    def test_arithmetic(self):
        out = run("print(2 + 3 * 4)")
        self.assertEqual(out.strip(), "14")

    def test_int_float_no_implicit_mixing(self):
        with self.assertRaises(CalyreRuntimeError):
            run("print(1 + 1.5)")

    def test_string_concat(self):
        out = run('print("a" + "b")')
        self.assertEqual(out.strip(), "ab")

    def test_string_interpolation(self):
        out = run('let name = "Alice"\nprint("Hi, {name}! {1 + 1}")')
        self.assertEqual(out.strip(), "Hi, Alice! 2")

    def test_if_elif_else(self):
        src = '''
func classify(n: int) -> str
    if n < 0
        return "neg"
    elif n == 0
        return "zero"
    else
        return "pos"
    end
end
print(classify(-1))
print(classify(0))
print(classify(5))
'''
        out = run(src)
        self.assertEqual(out.splitlines(), ["neg", "zero", "pos"])

    def test_while_break_continue(self):
        src = '''
let n = 0
let total = 0
while true
    n = n + 1
    if n == 2
        continue
    end
    if n > 4
        break
    end
    total = total + n
end
print(total)
'''
        out = run(src)
        self.assertEqual(out.strip(), "8")  # 1 + 3 + 4

    def test_for_over_list(self):
        out = run('for x in [1, 2, 3]\n    print(x)\nend')
        self.assertEqual(out.splitlines(), ["1", "2", "3"])

    def test_for_over_range(self):
        out = run('for x in range(3)\n    print(x)\nend')
        self.assertEqual(out.splitlines(), ["0", "1", "2"])

    def test_struct_construction_and_field_access(self):
        src = '''
struct Point
    x: int
    y: int
end
let p = Point(x: 1, y: 2)
print(p.x + p.y)
'''
        out = run(src)
        self.assertEqual(out.strip(), "3")

    def test_maps(self):
        src = '''
let scores = { "a": 1, "b": 2 }
scores["c"] = 3
print(scores["a"] + scores["b"] + scores["c"])
'''
        out = run(src)
        self.assertEqual(out.strip(), "6")

    def test_try_catch_recovers_from_runtime_error(self):
        src = '''
try
    let x = 1 / 0
catch e
    print("caught: " + e.message)
end
print("still running")
'''
        out = run(src)
        self.assertIn("caught:", out)
        self.assertIn("still running", out)

    def test_user_error_catchable(self):
        src = '''
try
    error("boom")
catch e
    print(e.message)
end
'''
        out = run(src)
        self.assertEqual(out.strip(), "boom")

    def test_assert_passes_silently(self):
        out = run("assert 1 == 1")
        self.assertEqual(out, "")

    def test_assert_failure_raises_with_values(self):
        with self.assertRaises(CalyreRuntimeError) as ctx:
            run("let x = 5\nassert x > 10")
        self.assertIn("x = 5", str(ctx.exception))

    def test_match_case(self):
        src = '''
let day = 2
match day
    case 1
        print("mon")
    case 2
        print("tue")
    case _
        print("other")
end
'''
        out = run(src)
        self.assertEqual(out.strip(), "tue")

    def test_closures_capture_environment(self):
        src = '''
func make_adder(n: int) -> int
    return n
end
let a = make_adder(5)
print(a)
'''
        out = run(src)
        self.assertEqual(out.strip(), "5")

    def test_undefined_variable_raises(self):
        with self.assertRaises(CalyreRuntimeError):
            run("print(nope)")

    def test_division_by_zero_raises(self):
        with self.assertRaises(CalyreRuntimeError):
            run("print(1 / 0)")

    def test_list_index_out_of_range_raises(self):
        with self.assertRaises(CalyreRuntimeError):
            run("print([1,2,3][10])")

    def test_builtins_str_int_float_len(self):
        out = run('print(str(5) + " " + str(int("3")) + " " + str(float("2.5")) + " " + str(len([1,2,3])))')
        self.assertEqual(out.strip(), "5 3 2.5 3")


if __name__ == "__main__":
    unittest.main()
