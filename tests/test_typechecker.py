import unittest
from calyre.lexer import tokenize
from calyre.calyre_parser import parse
from calyre import typechecker


def _errors(src):
    prog = parse(tokenize(src))
    return typechecker.check(prog)


class TestTypeChecker(unittest.TestCase):
    def test_valid_program_has_no_errors(self):
        errs = _errors('let x: int = 10\nprint(x)')
        self.assertEqual(errs, [])

    def test_reassign_wrong_type_declared(self):
        errs = _errors('let x: int = 10\nx = "hello"')
        self.assertEqual(len(errs), 1)
        self.assertIn("int", errs[0].message)

    def test_add_int_and_str_rejected(self):
        errs = _errors('let x: int = 10\nlet y: str = "hello"\nprint(x + y)')
        self.assertEqual(len(errs), 1)
        self.assertIn("+", errs[0].message)

    def test_inferred_type_still_checked_on_reassignment(self):
        errs = _errors('let x = 10\nx = "hello"')
        self.assertEqual(len(errs), 1)

    def test_int_float_mixing_rejected(self):
        errs = _errors('let x: float = 1.0\nlet y: int = 2\nprint(x + y)')
        self.assertTrue(any("int and float" in e.message for e in errs))

    def test_undefined_variable_flagged(self):
        errs = _errors('print(does_not_exist)')
        self.assertEqual(len(errs), 1)
        self.assertIn("not defined", errs[0].message)

    def test_function_signature_checked(self):
        src = '''
func add(a: int, b: int) -> int
    return a + b
end
add(1, "two")
'''
        errs = _errors(src)
        self.assertTrue(any("argument" in e.message for e in errs))

    def test_function_return_type_checked(self):
        src = '''
func broken() -> int
    return "not an int"
end
'''
        errs = _errors(src)
        self.assertTrue(any("return" in e.message for e in errs))

    def test_forward_reference_to_function_allowed(self):
        src = '''
func main()
    print(helper())
end
func helper() -> int
    return 1
end
'''
        errs = _errors(src)
        self.assertEqual(errs, [])

    def test_struct_field_types_checked(self):
        src = '''
struct Point
    x: int
    y: int
end
let p = Point(x: 1, y: "oops")
'''
        errs = _errors(src)
        self.assertTrue(any("field" in e.message for e in errs))

    def test_struct_missing_field(self):
        src = '''
struct Point
    x: int
    y: int
end
let p = Point(x: 1)
'''
        errs = _errors(src)
        self.assertTrue(any("missing field" in e.message for e in errs))

    def test_optional_allows_none(self):
        src = 'func maybe() -> str?\n    return none\nend'
        errs = _errors(src)
        self.assertEqual(errs, [])

    def test_non_optional_rejects_none(self):
        errs = _errors('let x: int = none')
        self.assertEqual(len(errs), 1)

    def test_for_loop_variable_typed_from_list(self):
        src = '''
let xs: list<int> = [1, 2, 3]
for n in xs
    let doubled: int = n * 2
end
'''
        errs = _errors(src)
        self.assertEqual(errs, [])

    def test_module_member_calls_are_lenient(self):
        # cross-module type info isn't tracked in this phase — should not error
        src = '''
use math_utils
print(math_utils.square(5.0))
'''
        errs = _errors(src)
        self.assertEqual(errs, [])

    def test_list_type_mismatch_via_index(self):
        src = '''
let xs: list<str> = ["a", "b"]
let n: int = xs[0]
'''
        errs = _errors(src)
        self.assertEqual(len(errs), 1)


if __name__ == "__main__":
    unittest.main()
