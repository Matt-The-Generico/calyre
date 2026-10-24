"""Methods of list / map / str, generic stdlib signatures, and their runtime behaviour."""
import unittest
from tests.helpers import errors, analyze, run
from calyre.interpreter import CalyreRuntimeError


def out(src):
    return run(src).split()


class TestListMethods(unittest.TestCase):
    def test_append_and_len(self):
        self.assertEqual(out('let xs: list<int> = []\nxs.append(1)\nxs.append(2)\nprint(len(xs))\nprint(xs)'),
                         ["2", "[1,", "2]"])

    def test_append_type_is_checked(self):
        self.assertTrue(errors('let xs: list<int> = []\nxs.append("a")'))
        self.assertEqual(errors('let xs: list<int> = []\nxs.append(1)'), [])
        self.assertTrue(errors('let xs = [1, 2]\nxs.append(2.5)'))

    def test_append_to_optional_element_list(self):
        self.assertEqual(errors('let xs: list<int?> = []\nxs.append(none)\nxs.append(3)'), [])

    def test_pop_returns_element_type(self):
        self.assertEqual(errors('let xs = [1, 2]\nlet n: int = xs.pop()'), [])
        self.assertTrue(errors('let xs = [1, 2]\nlet s: str = xs.pop()'))
        self.assertEqual(out('let xs = [1, 2, 3]\nprint(xs.pop())\nprint(len(xs))'), ["3", "2"])

    def test_pop_empty_is_a_clear_error(self):
        with self.assertRaises(CalyreRuntimeError) as ctx:
            run('let xs: list<int> = []\nxs.pop()')
        self.assertIn("the list is empty", str(ctx.exception))

    def test_insert_and_remove_at(self):
        self.assertEqual(out('let xs = [1, 3]\nxs.insert(1, 2)\nprint(xs.remove_at(0))\nprint(xs)'),
                         ["1", "[2,", "3]"])
        with self.assertRaises(CalyreRuntimeError):
            run('let xs = [1]\nxs.insert(5, 1)')
        with self.assertRaises(CalyreRuntimeError) as ctx:
            run('let xs = [1]\nxs.remove_at(3)')
        self.assertIn("valid: -1 to 0", str(ctx.exception))

    def test_remove_and_contains_and_index_of(self):
        src = ('let xs = ["a", "b", "a"]\nprint(xs.contains("b"))\nprint(xs.remove("a"))\n'
               'print(xs.remove("z"))\nprint(xs.index_of("a") ?? -1)\nprint(xs.index_of("q") ?? -1)')
        self.assertEqual(out(src), ["true", "true", "false", "1", "-1"])

    def test_index_of_is_optional(self):
        self.assertTrue(errors('let xs = [1]\nlet i: int = xs.index_of(1)'))
        self.assertEqual(errors('let xs = [1]\nlet i: int? = xs.index_of(1)'), [])

    def test_contains_does_not_confuse_bool_and_int(self):
        self.assertEqual(out('let xs: list<any> = [1]\nprint(xs.contains(true))'), ["false"])

    def test_copy_extend_reverse_sort_slice(self):
        src = ('let xs = [3, 1, 2]\nlet ys = xs.copy()\nys.sort()\nprint(xs)\nprint(ys)\n'
               'xs.extend(ys)\nxs.reverse()\nprint(xs)\nprint(xs.slice(1, 3))\nprint(xs.slice(-2, 6))')
        self.assertEqual(" ".join(out(src)), "[3, 1, 2] [1, 2, 3] [3, 2, 1, 2, 1, 3] [2, 1] [1, 3]")

    def test_sort_needs_orderable_elements(self):
        self.assertEqual(errors('let xs = ["b", "a"]\nxs.sort()'), [])
        self.assertTrue(errors('let xs = [[1], [2]]\nxs.sort()'))
        self.assertTrue(errors('struct P\n    x: int\nend\nlet xs = [P(x: 1)]\nxs.sort()'))

    def test_sort_of_mixed_dynamic_values_is_a_runtime_error(self):
        with self.assertRaises(CalyreRuntimeError):
            run('let xs: list<any> = [1, "a"]\nxs.sort()')

    def test_lists_have_reference_semantics(self):
        self.assertEqual(out('let a = [1]\nlet b = a\nb.append(2)\nprint(len(a))'), ["2"])
        self.assertEqual(out('let a = [1]\nlet b = a.copy()\nb.append(2)\nprint(len(a))'), ["1"])

    def test_loop_visits_the_elements_present_at_its_start(self):
        src = 'let xs = [1, 2]\nfor x in xs\n    xs.append(x * 10)\nend\nprint(xs)'
        self.assertEqual(" ".join(out(src)), "[1, 2, 10, 20]")

    def test_unknown_method_has_a_suggestion(self):
        d = analyze('let xs = [1]\nxs.apend(2)')[0][0]
        self.assertIn("append", d.hint)
        self.assertIn("list<int> has no method", d.message)

    def test_wrong_method_arity_is_static(self):
        self.assertTrue(errors('let xs = [1]\nxs.append()'))
        self.assertTrue(errors('let xs = [1]\nxs.pop(1)'))

    def test_method_on_optional_list_is_rejected(self):
        self.assertTrue(errors('func f(xs: list<int>?) -> int\n    return xs.pop()\nend'))

    def test_method_on_literal_and_chain(self):
        self.assertEqual(out('print([3, 1].contains(1))'), ["true"])
        self.assertEqual(out('print("a,b".split(",").contains("b"))'), ["true"])

    def test_dynamic_receiver_checked_at_runtime(self):
        with self.assertRaises(CalyreRuntimeError):
            run('let a: any = [1]\na.nope()')


class TestMapMethods(unittest.TestCase):
    def test_has_get_remove_keys_values(self):
        src = ('let m = {"a": 1, "b": 2}\nprint(m.has("a"))\nprint(m.get("zz") ?? 0)\nprint(m.get("b") ?? 0)\n'
               'print(m.remove("a"))\nprint(m.remove("a"))\nprint(m.keys())\nprint(m.values())')
        self.assertEqual(" ".join(out(src)), 'true 0 2 true false ["b"] [2]')

    def test_get_is_optional_and_typed(self):
        self.assertTrue(errors('let m = {"a": 1}\nlet n: int = m.get("a")'))
        self.assertEqual(errors('let m = {"a": 1}\nlet n: int = m.get("a") ?? 0'), [])
        self.assertTrue(errors('let m = {"a": 1}\nm.get(5)'))

    def test_keys_values_types(self):
        self.assertEqual(errors('let m = {"a": 1}\nlet k: list<str> = m.keys()\nlet v: list<int> = m.values()'), [])

    def test_copy_and_clear(self):
        self.assertEqual(out('let m = {"a": 1}\nlet c = m.copy()\nm.clear()\nprint(len(m))\nprint(len(c))'), ["0", "1"])

    def test_iterate_keys_while_modifying(self):
        src = 'let m = {"a": 1, "b": 2}\nfor k in m\n    m.remove(k)\nend\nprint(len(m))'
        self.assertEqual(out(src), ["0"])


class TestStrMethods(unittest.TestCase):
    def test_basic(self):
        src = ('let s = "  Hello World  "\nprint(s.trim().upper())\nprint(s.lower().trim())\n'
               'print(s.contains("World"))\nprint(s.trim().starts_with("Hello"))\nprint(s.trim().ends_with("x"))\n'
               'print(s.replace("l", "L"))\nprint(s.trim().split(" "))\nprint(s.trim().index_of("W") ?? -1)\n'
               'print(s.trim().slice(0, 5))\nprint("ab".repeat(3))')
        self.assertEqual(run(src).splitlines(),
                         ["HELLO WORLD", "hello world", "true", "true", "false", "  HeLLo WorLd  ",
                          '["Hello", "World"]', "6", "Hello", "ababab"])

    def test_unicode(self):
        self.assertEqual(run('print("straße".upper())\nprint(len("日本語"))\nprint("日本語".slice(1, 3))').splitlines(),
                         ["STRASSE", "3", "本語"])

    def test_types(self):
        self.assertTrue(errors('let n: int = "a".upper()'))
        self.assertTrue(errors('"a".contains(1)'))
        self.assertEqual(errors('let parts: list<str> = "a b".split(" ")'), [])
        self.assertTrue(errors('let i: int = "abc".index_of("b")'))

    def test_empty_separator_and_pattern_are_errors(self):
        for src in ('"a".split("")', '"a".replace("", "x")', '"a".repeat(-1)'):
            with self.assertRaises(CalyreRuntimeError):
                run(src)

    def test_unknown_str_method(self):
        d = analyze('"a".uppper()')[0][0]
        self.assertIn("upper", d.hint)

    def test_text_module_still_works_for_compatibility(self):
        self.assertEqual(run('use text\nprint(text.upper("a"))').strip(), "A")


class TestGenericStdlib(unittest.TestCase):
    def test_abs_min_max_keep_the_numeric_kind(self):
        self.assertEqual(errors('use math\nlet a: int = math.abs(-3)\nlet b: float = math.abs(-3.5)'), [])
        self.assertTrue(errors('use math\nlet a: float = math.abs(-3)'))
        self.assertEqual(errors('use math\nlet a: int = math.min(1, 2)\nlet b: float = math.max(1.0, 2.0)'), [])

    def test_min_max_reject_mixed_kinds(self):
        e = errors('use math\nmath.min(1, 2.5)')
        self.assertEqual(len(e), 1)
        self.assertIn("argument 2", e[0])

    def test_numeric_functions_reject_non_numbers(self):
        self.assertTrue(errors('use math\nmath.abs("x")'))
        self.assertTrue(errors('use math\nmath.max("a", "b")'))

    def test_pow_is_always_float(self):
        self.assertEqual(errors('use math\nlet p: float = math.pow(2, 3)'), [])
        self.assertTrue(errors('use math\nlet p: int = math.pow(2, 3)'))
        self.assertEqual(out('use math\nprint(math.pow(2, 3))\nprint(math.pow(2, -1))'), ["8.0", "0.5"])
        for bad in ('use math\nmath.pow(0, -1)', 'use math\nmath.pow(-8, 0.5)'):
            with self.assertRaises(CalyreRuntimeError):
                run(bad)

    def test_random_choice_is_typed(self):
        self.assertEqual(errors('use random\nlet n: int = random.choice([1, 2])\nlet s: str = random.choice(["a"])'), [])
        self.assertTrue(errors('use random\nlet n: str = random.choice([1, 2])'))
        self.assertEqual(out('use random\nprint(random.choice([7]))'), ["7"])
        self.assertTrue(errors('use random\nrandom.choice(5)'))

    def test_text_join_accepts_any_list_but_not_non_lists(self):
        self.assertEqual(errors('use text\nlet s: str = text.join([1, 2], ",")\nlet t: str = text.join(["a"], ",")'), [])
        self.assertTrue(errors('use text\ntext.join("abc", ",")'))
        self.assertEqual(out('use text\nprint(text.join([1, 2], "-"))'), ["1-2"])

    def test_use_from_with_generic_function(self):
        self.assertEqual(errors('use abs from math\nlet n: int = abs(-2)'), [])
        self.assertTrue(errors('use abs from math\nlet n: str = abs(-2)'))


if __name__ == "__main__":
    unittest.main()
