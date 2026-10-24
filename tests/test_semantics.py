"""Semantic analysis: scopes, declarations, returns, unknown types, optionals."""
import unittest
from tests.helpers import errors, warnings, analyze


class TestDeclarations(unittest.TestCase):
    def test_duplicate_let_same_scope(self):
        e = errors('let x = 1\nlet x = "a"')
        self.assertEqual(len(e), 1)
        self.assertIn("already declared", e[0])

    def test_shadowing_in_nested_scope_is_allowed(self):
        self.assertEqual(errors('let x = 1\nif true\n    let x = "a"\nend'), [])

    def test_duplicate_function(self):
        src = 'func f() -> int\n    return 1\nend\nfunc f() -> int\n    return 2\nend'
        self.assertTrue(any("already declared" in m for m in errors(src)))

    def test_duplicate_parameter(self):
        src = 'func f(a: int, a: int) -> int\n    return a\nend'
        self.assertTrue(any("two parameters" in m for m in errors(src)))

    def test_duplicate_struct_and_field(self):
        self.assertTrue(any("more than once" in m for m in errors(
            'struct P\n    x: int\nend\nstruct P\n    y: int\nend')))
        self.assertTrue(any("two fields" in m for m in errors('struct P\n    x: int\n    x: int\nend')))

    def test_redeclaring_a_loop_variable_in_body(self):
        self.assertTrue(errors('for i in range(3)\n    let i = 5\nend'))


class TestUnknownTypes(unittest.TestCase):
    def test_unknown_type_in_let(self):
        e = errors('let p: Pointt = 5')
        self.assertEqual(e, ["unknown type 'Pointt'"])

    def test_unknown_type_has_suggestion(self):
        d = analyze('struct Point\n    x: int\nend\nlet p: Pont = 1')[0][0]
        self.assertIn("Point", d.hint)

    def test_unknown_type_in_signature_and_field(self):
        self.assertEqual(len(errors('func g(a: Foo) -> Bar\n    return a\nend')), 2)
        self.assertEqual(len(errors('struct S\n    x: Nope\nend')), 1)

    def test_generic_arity_errors(self):
        self.assertTrue(errors('let a: list = []'))
        self.assertTrue(errors('let a: map<int> = {}'))
        self.assertTrue(errors('let a: int<str> = 1'))

    def test_explicit_any_is_allowed(self):
        self.assertEqual(errors('let a: any = 5\na = "now a string"'), [])

    def test_struct_declared_after_use(self):
        src = 'func f(p: P) -> int\n    return p.x\nend\nstruct P\n    x: int\nend'
        self.assertEqual(errors(src), [])


class TestReturns(unittest.TestCase):
    def test_missing_return_path(self):
        src = 'func f(a: int) -> int\n    if a > 0\n        return 1\n    end\nend'
        self.assertTrue(any("without returning" in m for m in errors(src)))

    def test_all_paths_return_if_else(self):
        src = 'func f(a: int) -> int\n    if a > 0\n        return 1\n    else\n        return 2\n    end\nend'
        self.assertEqual(errors(src), [])

    def test_all_paths_return_match_with_default(self):
        src = ('func f(a: int) -> str\n    match a\n        case 1\n            return "a"\n'
               '        case _\n            return "b"\n    end\nend')
        self.assertEqual(errors(src), [])

    def test_match_without_default_is_not_exhaustive(self):
        src = 'func f(a: int) -> str\n    match a\n        case 1\n            return "a"\n    end\nend'
        self.assertTrue(errors(src))

    def test_error_call_terminates_path(self):
        src = 'func f(a: int) -> int\n    if a > 0\n        return 1\n    end\n    error("bad")\nend'
        self.assertEqual(errors(src), [])

    def test_while_true_without_break_terminates(self):
        src = 'func f() -> int\n    while true\n        return 1\n    end\nend'
        self.assertEqual(errors(src), [])

    def test_optional_return_may_fall_through(self):
        self.assertEqual(errors('func f(a: int) -> int?\n    if a > 0\n        return 1\n    end\nend'), [])

    def test_return_type_mismatch(self):
        self.assertTrue(errors('func f() -> int\n    return "x"\nend'))

    def test_bare_return_in_valued_function(self):
        self.assertTrue(errors('func f() -> int\n    return\nend'))

    def test_inferred_return_type_is_used_by_callers(self):
        src = 'func double(n: int)\n    return n * 2\nend\nlet s: str = double(2)'
        self.assertTrue(errors(src))

    def test_inferred_return_of_recursive_function(self):
        src = ('func fact(n: int)\n    if n <= 1\n        return 1\n    end\n'
               '    return n * fact(n - 1)\nend\nlet x: int = fact(5)')
        self.assertEqual(errors(src), [])

    def test_inference_through_later_function(self):
        src = 'func a()\n    return b()\nend\nfunc b()\n    return 1\nend\nlet s: str = a()'
        self.assertTrue(errors(src))

    def test_function_without_value_returns_none(self):
        src = 'func hello()\n    print("hi")\nend\nlet x: int = hello()'
        self.assertTrue(errors(src))

    def test_mixed_inferred_returns_warn(self):
        src = 'func f(a: int)\n    if a > 0\n        return 1\n    end\n    return "no"\nend'
        self.assertEqual(errors(src), [])
        self.assertTrue(any("different types" in m for m in warnings(src)))

    def test_inferred_optional_when_falling_through(self):
        src = 'func f(a: int)\n    if a > 0\n        return 1\n    end\nend\nlet x: int = f(1)'
        self.assertTrue(errors(src))


class TestControlContext(unittest.TestCase):
    def test_break_continue_outside_loop(self):
        self.assertTrue(errors("break"))
        self.assertTrue(errors("continue"))

    def test_break_in_function_called_from_loop(self):
        src = 'func f()\n    break\nend\nwhile true\n    f()\nend'
        self.assertTrue(errors(src))

    def test_break_inside_loop_ok(self):
        self.assertEqual(errors('while true\n    break\nend'), [])

    def test_return_outside_function(self):
        self.assertTrue(errors("return 1"))


class TestOptionals(unittest.TestCase):
    def test_optional_not_usable_as_plain(self):
        self.assertTrue(errors('let a: int? = 5\nlet b: int = a'))
        self.assertTrue(errors('let a: int? = 5\nprint(a + 1)'))

    def test_narrowing_with_not_equal_none(self):
        self.assertEqual(errors('let a: int? = 5\nif a != none\n    print(a + 1)\nend'), [])

    def test_narrowing_else_branch(self):
        src = 'let a: int? = 5\nif a == none\n    print("none")\nelse\n    print(a + 1)\nend'
        self.assertEqual(errors(src), [])

    def test_early_exit_narrows_rest_of_function(self):
        src = 'func f(a: int?) -> int\n    if a == none\n        return 0\n    end\n    return a + 1\nend'
        self.assertEqual(errors(src), [])

    def test_narrowing_with_and(self):
        self.assertEqual(errors('let a: int? = 5\nif a != none and a > 3\n    print(a)\nend'), [])

    def test_narrowing_does_not_leak_out_of_branch(self):
        self.assertTrue(errors('let a: int? = 5\nif a != none\n    print(1)\nend\nprint(a + 1)'))

    def test_assignment_invalidates_narrowing(self):
        src = 'let a: int? = 5\nif a != none\n    a = none\n    print(a + 1)\nend'
        self.assertTrue(errors(src))

    def test_coalesce_unwraps(self):
        self.assertEqual(errors('let a: str? = none\nlet b: str = a ?? "guest"'), [])

    def test_coalesce_wrong_fallback_type(self):
        self.assertTrue(errors('let a: str? = none\nlet b = a ?? 5'))

    def test_coalesce_on_non_optional_warns(self):
        self.assertTrue(any("never none" in m for m in warnings('let a = 5\nlet b = a ?? 6')))

    def test_none_start_warns_and_stays_dynamic(self):
        src = 'let a = none\na = 5'
        self.assertEqual(errors(src), [])
        self.assertTrue(warnings(src))

    def test_member_access_on_optional_struct(self):
        src = 'struct P\n    x: int\nend\nfunc f(p: P?) -> int\n    return p.x\nend'
        self.assertTrue(errors(src))


class TestCollectionsAndStructs(unittest.TestCase):
    def test_mixed_list_is_error(self):
        self.assertTrue(errors('let a = [1, "x"]'))

    def test_list_with_none_becomes_optional(self):
        self.assertEqual(errors('let a: list<int?> = [1, none]'), [])

    def test_mixed_map_values_error(self):
        self.assertTrue(errors('let m = {"a": 1, "b": "x"}'))

    def test_list_element_assignment_checked(self):
        self.assertTrue(errors('let a: list<int> = [1]\na[0] = "x"'))

    def test_map_key_and_value_checked(self):
        self.assertTrue(errors('let m: map<str, int> = {"a": 1}\nm[1] = 2'))
        self.assertTrue(errors('let m: map<str, int> = {"a": 1}\nm["b"] = "x"'))

    def test_index_must_be_int(self):
        self.assertTrue(errors('let a = [1, 2]\nprint(a["x"])'))

    def test_empty_collection_without_annotation_warns(self):
        self.assertTrue(warnings('let a = []'))
        self.assertEqual(warnings('let a: list<int> = []'), [])

    def test_struct_field_assignment_checked(self):
        src = 'struct P\n    x: int\nend\nlet p = P(x: 1)\np.x = "s"'
        self.assertTrue(errors(src))

    def test_struct_unknown_field_suggestion(self):
        src = 'struct P\n    name: str\nend\nlet p = P(name: "a")\nprint(p.nam)'
        d = analyze(src)[0][0]
        self.assertIn("name", d.hint)

    def test_loop_over_non_iterable(self):
        self.assertTrue(errors('for i in 5\n    print(i)\nend'))

    def test_loop_variable_gets_element_type(self):
        self.assertEqual(errors('for s in ["a"]\n    let n: int = len(s)\nend'), [])
        self.assertTrue(errors('for s in ["a"]\n    let n: int = s\nend'))


class TestOperators(unittest.TestCase):
    def test_division_always_float(self):
        self.assertEqual(errors('let a: float = 7 / 2'), [])
        self.assertTrue(errors('let a: int = 7 / 2'))

    def test_int_float_mixing(self):
        self.assertTrue(errors('print(1 + 1.5)'))
        self.assertTrue(errors('print(1 < 1.5)'))

    def test_str_plus_int_hint(self):
        d = analyze('print("a" + 1)')[0][0]
        self.assertIn("interpolation", d.hint)

    def test_impossible_equality_warns(self):
        self.assertTrue(warnings('print(1 == "a")'))

    def test_match_case_type_mismatch(self):
        self.assertTrue(errors('match 1\n    case "a"\n        print(1)\nend'))

    def test_calling_non_function(self):
        self.assertTrue(errors('let a = 5\na()'))

    def test_named_args_only_for_structs(self):
        self.assertTrue(errors('func f(a: int) -> int\n    return a\nend\nf(a: 1)'))

    def test_assign_to_function_name(self):
        self.assertTrue(errors('func f() -> int\n    return 1\nend\nf = 2'))

    def test_builtin_arity_static(self):
        self.assertTrue(errors('print(len(1, 2))'))
        self.assertTrue(errors('print(len(5))'))

    def test_undefined_name_suggestion(self):
        d = analyze('let counter = 1\nprint(countr)')[0][0]
        self.assertIn("counter", d.hint)

    def test_one_mistake_gives_one_error(self):
        # `unknown` suppresses cascades
        self.assertEqual(len(errors('let a = nope + 1\nlet b = a * 2')), 1)

    def test_diagnostics_are_ordered_by_line(self):
        d = analyze('let a: int = "x"\nlet b: str = 1\nlet c: bool = 2')[0]
        self.assertEqual([x.line for x in d], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()


class TestColumns(unittest.TestCase):
    def pos(self, src):
        d = analyze(src)[0][0]
        return d.line, d.col

    def test_mismatch_points_at_the_value(self):
        self.assertEqual(self.pos('let x: int = "no"'), (1, 14))

    def test_argument_error_points_at_the_argument(self):
        self.assertEqual(self.pos('func f(a: int) -> int\n    return a\nend\nf("x")'), (4, 3))

    def test_return_mismatch_points_at_the_returned_value(self):
        self.assertEqual(self.pos('func f() -> int\n    return "x"\nend'), (2, 12))

    def test_unknown_name_and_field_columns(self):
        self.assertEqual(self.pos('let a = 1\nprint(b)'), (2, 7))
        self.assertEqual(self.pos('struct P\n    x: int\nend\nlet p = P(x: 1)\nprint(p.y)'), (5, 9))

    def test_binary_operator_error_starts_at_the_left_operand(self):
        self.assertEqual(self.pos('let a = 1\nlet b = a + "x"'), (2, 9))

    def test_columns_count_characters_after_multibyte_text(self):
        self.assertEqual(self.pos('let s = "日本"\nlet q: int = s'), (2, 14))

    def test_warning_has_position_too(self):
        d = analyze('let xs = []')[1][0]
        self.assertEqual((d.line, d.col), (1, 1))


class TestAssertNarrowing(unittest.TestCase):
    def test_assert_not_none_narrows_the_rest_of_the_block(self):
        src = 'func f(x: int?) -> int\n    assert x != none\n    return x + 1\nend'
        self.assertEqual(errors(src), [])

    def test_assert_with_and_and_message(self):
        src = 'func f(x: int?, y: str?) -> int\n    assert x != none and y != none, "both needed"\n    return x + len(y)\nend'
        self.assertEqual(errors(src), [])

    def test_assert_does_not_narrow_when_it_cannot_know(self):
        self.assertTrue(errors('func f(x: int?) -> int\n    assert x == none\n    return x + 1\nend'))
        self.assertTrue(errors('func f(x: int?, y: int?) -> int\n    assert x != none or y != none\n    return x + 1\nend'))

    def test_narrowing_from_assert_stays_in_its_block(self):
        src = 'func f(x: int?, ok: bool) -> int\n    if ok\n        assert x != none\n    end\n    return x + 1\nend'
        self.assertTrue(errors(src))

    def test_assert_narrowing_runs(self):
        from tests.helpers import run
        self.assertEqual(run('func f(x: int?) -> int\n    assert x != none\n    return x + 1\nend\nprint(f(4))').strip(), "5")
