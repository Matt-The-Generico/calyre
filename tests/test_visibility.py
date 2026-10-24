"""`pub` visibility, `use ... from`, and migration compatibility."""
import unittest
from tests.helpers import errors, analyze, project, run

LEGACY = 'func shown() -> int\n    return 1\nend\nfunc _hidden() -> int\n    return 2\nend'
EXPLICIT = ('pub func shown() -> int\n    return helper()\nend\n'
            'func helper() -> int\n    return 2\nend\n'
            'pub struct Point\n    x: int\nend\npub let LIMIT = 10\nlet secret = 5')


class TestVisibility(unittest.TestCase):
    def test_legacy_module_exports_everything_without_underscore(self):
        with project({"m.cly": LEGACY}) as d:
            self.assertEqual(errors('use m\nprint(m.shown())', d), [])
            e = errors('use m\nprint(m._hidden())', d)
            self.assertIn("private", e[0])

    def test_explicit_mode_exports_only_pub(self):
        with project({"m.cly": EXPLICIT}) as d:
            self.assertEqual(errors('use m\nlet p = m.Point(x: m.shown())\nprint(m.LIMIT + p.x)', d), [])
            e = errors('use m\nprint(m.helper())', d)
            self.assertEqual(len(e), 1)
            self.assertIn("not public", e[0])
            self.assertTrue(errors('use m\nprint(m.secret)', d))

    def test_not_public_has_a_pub_hint(self):
        with project({"m.cly": EXPLICIT}) as d:
            self.assertIn("pub", analyze('use m\nm.helper()', d)[0][0].hint)

    def test_explicit_mode_at_runtime_matches_static(self):
        with project({"m.cly": EXPLICIT}) as d:
            self.assertEqual(run('use m\nprint(m.shown())', d).strip(), "2")
            from calyre.interpreter import CalyreRuntimeError
            with self.assertRaises(CalyreRuntimeError):
                run('use m\nprint(m.helper())', d, check=False)

    def test_private_type_in_annotation(self):
        files = {"m.cly": 'pub func f() -> int\n    return 1\nend\nstruct Hidden\n    x: int\nend'}
        with project(files) as d:
            self.assertTrue(any("not public" in m for m in errors('use m\nlet h: m.Hidden = 1', d)))

    def test_pub_only_at_top_level(self):
        self.assertTrue(errors('func f()\n    pub let x = 1\nend'))
        self.assertTrue(errors('if true\n    pub func g()\n        print(1)\n    end\nend'))

    def test_pub_is_not_reserved(self):
        self.assertEqual(run('let pub = 5\nprint(pub + 1)').strip(), "6")
        self.assertEqual(run('func pub(a: int) -> int\n    return a\nend\nprint(pub(2))').strip(), "2")

    def test_phase3_style_library_without_pub_still_works(self):
        # the shape of examples/modules_demo/math_utils.cly before `pub` existed (frozen copy)
        legacy = ('func square(x: float) -> float\n    return x * x\nend\n'
                  'func _internal_helper() -> int\n    return 0\nend\n')
        with project({"math_utils.cly": legacy, "main.cly": 'use math_utils\nprint(math_utils.square(3.0))'}) as d:
            import os
            from tests.helpers import cli
            code, out, err = cli("run", os.path.join(d, "main.cly"))
            self.assertEqual((code, out.strip()), (0, "9.0"), err)


class TestUseFrom(unittest.TestCase):
    def test_use_names_from_stdlib(self):
        self.assertEqual(run('use sqrt, floor from math\nprint(sqrt(16.0))\nprint(floor(2.5))').split(), ["4.0", "2"])

    def test_use_name_with_alias(self):
        self.assertEqual(run('use sqrt as root from math\nprint(root(9.0))').strip(), "3.0")
        self.assertEqual(run('use sqrt as root, floor from math\nprint(root(9.0) + 1.0)\nprint(floor(1.5))').split(), ["4.0", "1"])

    def test_use_from_is_typed(self):
        self.assertTrue(errors('use sqrt from math\nlet s: str = sqrt(4.0)'))
        self.assertTrue(errors('use nope from math'))
        self.assertIn("sqrt", analyze('use sqr from math')[0][0].hint)

    def test_use_from_local_module_and_struct_as_type(self):
        files = {"geo.cly": 'pub struct Point\n    x: int\nend\npub func make(x: int) -> Point\n    return Point(x: x)\nend'}
        with project(files) as d:
            self.assertEqual(run('use Point, make from geo\nlet p: Point = make(3)\nprint(p.x)', d).strip(), "3")

    def test_use_from_respects_visibility(self):
        files = {"geo.cly": 'pub func a() -> int\n    return 1\nend\nfunc b() -> int\n    return 2\nend'}
        with project(files) as d:
            self.assertTrue(errors('use b from geo', d))

    def test_from_is_still_a_valid_identifier(self):
        self.assertEqual(run('let from = 3\nprint(from)').strip(), "3")

    def test_plain_use_forms_unchanged(self):
        self.assertEqual(run('use math as m\nprint(m.floor(2.5))').strip(), "2")


if __name__ == "__main__":
    unittest.main()
