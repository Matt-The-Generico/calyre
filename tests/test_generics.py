"""Generic functions and structs: declaration, inference, instantiation, diagnostics."""
import unittest
from tests.helpers import errors, warnings, analyze, run, project

IDENT = 'func identity<T>(value: T) -> T\n    return value\nend\n'


class TestGenericFunctions(unittest.TestCase):
    def test_identity_infers_each_type(self):
        src = IDENT + 'let a: int = identity(1)\nlet b: str = identity("x")\nlet c: list<int> = identity([1, 2])'
        self.assertEqual(errors(src), [])

    def test_result_type_follows_argument(self):
        self.assertTrue(errors(IDENT + 'let a: str = identity(1)'))
        self.assertEqual(len(errors(IDENT + 'let a: int = identity("x")')), 1)

    def test_runs_unchanged(self):
        self.assertEqual(run(IDENT + 'print(identity(5))\nprint(identity("hi"))').split(), ["5", "hi"])

    def test_two_parameters_same_variable_must_agree(self):
        src = 'func pick<T>(a: T, b: T) -> T\n    return a\nend\n'
        self.assertEqual(errors(src + 'let x: int = pick(1, 2)'), [])
        e = errors(src + 'let x = pick(1, "two")')
        self.assertEqual(len(e), 1)
        self.assertIn("argument 2", e[0])

    def test_two_type_parameters(self):
        src = 'func first<A, B>(a: A, b: B) -> A\n    return a\nend\n'
        self.assertEqual(errors(src + 'let x: int = first(1, "s")\nlet y: str = first("s", 2.5)'), [])

    def test_inference_through_collections(self):
        src = 'func head<T>(xs: list<T>) -> T\n    return xs[0]\nend\n'
        self.assertEqual(errors(src + 'let a: int = head([1, 2, 3])\nlet b: str = head(["a"])'), [])
        self.assertTrue(errors(src + 'let a: str = head([1, 2])'))
        self.assertTrue(errors(src + 'head(5)'))

    def test_inference_through_map_and_optional(self):
        src = ('func values_of<K, V>(m: map<K, V>) -> V?\n    return none\nend\n'
               'let r: int? = values_of({"a": 1})')
        self.assertEqual(errors(src), [])

    def test_cannot_infer_from_empty_list(self):
        e = errors('func head<T>(xs: list<T>) -> T\n    return xs[0]\nend\nhead([])')
        self.assertEqual(len(e), 1)
        self.assertIn("cannot infer", e[0])

    def test_unused_type_parameter_is_rejected(self):
        self.assertTrue(any("never be inferred" in m for m in errors('func f<T>() -> int\n    return 1\nend')))

    def test_type_parameter_is_opaque_inside_the_body(self):
        self.assertTrue(errors('func add<T>(a: T, b: T) -> T\n    return a + b\nend'))
        self.assertTrue(errors('func f<T>(a: T) -> int\n    return a\nend'))
        self.assertTrue(errors('func f<T>(a: T) -> T\n    return 1\nend'))

    def test_type_parameter_can_be_used_for_locals_and_equality(self):
        src = ('func same<T>(a: T, b: T) -> bool\n    let copy: T = a\n    return copy == b\nend\n'
               'print(same(1, 1))')
        self.assertEqual(errors(src), [])

    def test_generic_calling_generic(self):
        src = IDENT + 'func twice<T>(v: T) -> T\n    return identity(identity(v))\nend\nlet n: int = twice(3)'
        self.assertEqual(errors(src), [])

    def test_recursive_generic_function(self):
        src = ('func last<T>(xs: list<T>) -> T\n    if len(xs) == 1\n        return xs[0]\n    end\n'
               '    return last(xs.slice(1, len(xs)))\nend\nlet z: str = last(["a", "b"])')
        self.assertEqual(errors(src), [])

    def test_inferred_return_type_of_generic(self):
        src = 'func wrap<T>(v: T)\n    return [v]\nend\nlet a: list<int> = wrap(1)'
        self.assertEqual(errors(src), [])
        self.assertTrue(errors('func wrap<T>(v: T)\n    return [v]\nend\nlet a: list<str> = wrap(1)'))

    def test_wrong_arity_and_named_arguments(self):
        self.assertTrue(errors(IDENT + 'identity(1, 2)'))
        self.assertTrue(errors(IDENT + 'identity(value: 1)'))

    def test_any_argument_gives_any_result(self):
        self.assertEqual(errors(IDENT + 'let a: any = 1\nlet s: str = identity(a)'), [])

    def test_duplicate_type_parameter_is_a_syntax_error(self):
        from calyre.lexer import tokenize
        from calyre.calyre_parser import parse, ParseError
        with self.assertRaises(ParseError):
            parse(tokenize('func f<T, T>(a: T) -> T\n    return a\nend'))

    def test_type_parameter_with_arguments_is_rejected(self):
        self.assertTrue(errors('func f<T>(a: T<int>) -> int\n    return 1\nend'))


class TestGenericStructs(unittest.TestCase):
    BOX = 'struct Box<T>\n    value: T\nend\n'

    def test_construct_infers_type_argument(self):
        self.assertEqual(errors(self.BOX + 'let b: Box<int> = Box(value: 1)\nlet n: int = b.value'), [])
        self.assertTrue(errors(self.BOX + 'let b: Box<str> = Box(value: 1)'))

    def test_field_access_substitutes(self):
        self.assertTrue(errors(self.BOX + 'let b = Box(value: "s")\nlet n: int = b.value'))
        self.assertEqual(errors(self.BOX + 'let b = Box(value: "s")\nlet n: str = b.value'), [])

    def test_field_assignment_checked_with_substitution(self):
        self.assertTrue(errors(self.BOX + 'let b = Box(value: 1)\nb.value = "x"'))
        self.assertEqual(errors(self.BOX + 'let b = Box(value: 1)\nb.value = 2'), [])

    def test_generic_struct_in_signatures(self):
        src = (self.BOX + 'func unwrap<T>(b: Box<T>) -> T\n    return b.value\nend\n'
               'let n: int = unwrap(Box(value: 4))\nlet s: str = unwrap(Box(value: "a"))')
        self.assertEqual(errors(src), [])
        self.assertTrue(errors(self.BOX + 'func f(b: Box<int>) -> int\n    return b.value\nend\nf(Box(value: "x"))'))

    def test_missing_or_extra_type_arguments(self):
        self.assertTrue(errors(self.BOX + 'let b: Box = Box(value: 1)'))
        self.assertTrue(errors(self.BOX + 'let b: Box<int, str> = Box(value: 1)'))
        self.assertTrue(errors('struct P\n    x: int\nend\nlet p: P<int> = P(x: 1)'))

    def test_two_parameters(self):
        src = ('struct Pair<A, B>\n    left: A\n    right: B\nend\n'
               'let p = Pair(left: 1, right: "r")\nlet a: int = p.left\nlet b: str = p.right')
        self.assertEqual(errors(src), [])

    def test_nested_generic_types(self):
        src = (self.BOX + 'let b: Box<list<int>> = Box(value: [1])\nlet xs: list<int> = b.value')
        self.assertEqual(errors(src), [])

    def test_recursive_generic_struct_with_optional(self):
        src = ('struct Node<T>\n    value: T\n    next: Node<T>?\nend\n'
               'let n = Node(value: 1, next: none)\nlet m: Node<int> = Node(value: 2, next: n)')
        self.assertEqual(errors(src), [])

    def test_generic_struct_runs(self):
        out = run(self.BOX + 'let b = Box(value: 41)\nb.value = b.value + 1\nprint(b.value)')
        self.assertEqual(out.strip(), "42")

    def test_cannot_infer_from_none(self):
        self.assertTrue(errors(self.BOX + 'let b = Box(value: [])'))

    def test_generics_across_modules(self):
        files = {"box.cly": ('pub struct Box<T>\n    value: T\nend\n'
                             'pub func wrap<T>(v: T) -> Box<T>\n    return Box(value: v)\nend')}
        with project(files) as d:
            self.assertEqual(errors('use box\nlet b = box.wrap(3)\nlet n: int = b.value', d), [])
            self.assertTrue(errors('use box\nlet b = box.wrap(3)\nlet s: str = b.value', d))
            self.assertEqual(errors('use box\nlet b: box.Box<int> = box.wrap(3)', d), [])
            self.assertEqual(run('use box\nprint(box.wrap(7).value)', d).strip(), "7")


if __name__ == "__main__":
    unittest.main()
