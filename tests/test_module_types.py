"""Static analysis across modules, and stdlib signatures."""
import unittest
from tests.helpers import errors, warnings, analyze, project, run

SHAPES = '''
struct Point
    x: int
    y: int
end

func make(x: int, y: int) -> Point
    return Point(x: x, y: y)
end

func norm1(p: Point) -> int
    return p.x + p.y
end

let ORIGIN = Point(x: 0, y: 0)

func _hidden() -> int
    return 1
end

func untyped(n: int)
    return n * 2
end
'''


class TestModuleTypes(unittest.TestCase):
    def test_member_call_is_typed(self):
        with project({"shapes.cly": SHAPES}) as d:
            self.assertEqual(errors('use shapes\nlet p: shapes.Point = shapes.make(1, 2)', d), [])
            self.assertTrue(errors('use shapes\nlet s: str = shapes.make(1, 2).x', d))

    def test_wrong_argument_type_across_modules(self):
        with project({"shapes.cly": SHAPES}) as d:
            e = errors('use shapes\nshapes.make(1, "two")', d)
            self.assertEqual(len(e), 1)
            self.assertIn("argument 2", e[0])

    def test_struct_from_module_can_be_built_and_checked(self):
        with project({"shapes.cly": SHAPES}) as d:
            self.assertEqual(errors('use shapes\nlet p = shapes.Point(x: 1, y: 2)\nprint(shapes.norm1(p))', d), [])
            self.assertTrue(errors('use shapes\nlet p = shapes.Point(x: 1, y: "no")', d))
            self.assertTrue(errors('use shapes\nlet p = shapes.Point(x: 1)', d))

    def test_alias_keeps_type_identity(self):
        with project({"shapes.cly": SHAPES}) as d:
            src = 'use shapes\nuse shapes as s2\nlet p: shapes.Point = s2.make(1, 2)'
            self.assertEqual(errors(src, d), [])

    def test_inferred_return_type_crosses_modules(self):
        with project({"shapes.cly": SHAPES}) as d:
            self.assertTrue(errors('use shapes\nlet s: str = shapes.untyped(1)', d))
            self.assertEqual(errors('use shapes\nlet n: int = shapes.untyped(1)', d), [])

    def test_exported_constant_is_typed(self):
        with project({"shapes.cly": SHAPES}) as d:
            self.assertEqual(errors('use shapes\nlet o: shapes.Point = shapes.ORIGIN', d), [])
            self.assertTrue(errors('use shapes\nlet o: int = shapes.ORIGIN', d))

    def test_private_member_is_rejected_statically(self):
        with project({"shapes.cly": SHAPES}) as d:
            e = errors('use shapes\nshapes._hidden()', d)
            self.assertEqual(len(e), 1)
            self.assertIn("private", e[0])

    def test_missing_member_has_suggestion(self):
        with project({"shapes.cly": SHAPES}) as d:
            diag = analyze('use shapes\nshapes.mak(1, 2)', d)[0][0]
            self.assertIn("make", diag.hint)

    def test_unknown_qualified_type(self):
        with project({"shapes.cly": SHAPES}) as d:
            self.assertTrue(errors('use shapes\nlet p: shapes.Nope = 1', d))
            self.assertTrue(errors('let p: shapes.Point = 1', d))

    def test_missing_module_suggests_stdlib_name(self):
        diag = analyze('use mth')[0][0]
        self.assertIn("math", diag.hint)

    def test_module_with_type_error_is_reported_at_the_import(self):
        with project({"bad.cly": 'let x: int = "oops"'}) as d:
            diags = analyze('use bad\nprint(1)', d)[0]
            self.assertEqual(len(diags), 1)
            self.assertEqual(diags[0].line, 1)
            self.assertIn("bad.cly:1", diags[0].message)

    def test_module_with_syntax_error(self):
        with project({"bad.cly": 'func f(\n'}) as d:
            self.assertTrue(errors('use bad', d))

    def test_circular_import_is_static(self):
        with project({"a.cly": "use b\n", "b.cly": "use a\n"}) as d:
            self.assertTrue(any("circular" in m for m in errors("use a", d)))

    def test_nested_module_path(self):
        with project({"lib/util.cly": 'func one() -> int\n    return 1\nend'}) as d:
            self.assertEqual(errors('use lib.util\nlet n: int = util.one()', d), [])

    def test_transitive_struct_types(self):
        files = {
            "geo.cly": 'struct P\n    x: int\nend\nfunc mk() -> P\n    return P(x: 1)\nend',
            "mid.cly": 'use geo\nfunc relay() -> geo.P\n    return geo.mk()\nend',
        }
        with project(files) as d:
            self.assertEqual(errors('use mid\nlet v = mid.relay()\nprint(v.x + 1)', d), [])
            self.assertTrue(errors('use mid\nlet v = mid.relay()\nlet s: str = v.x', d))

    def test_runtime_matches_static_typing(self):
        with project({"shapes.cly": SHAPES}) as d:
            out = run('use shapes\nlet p = shapes.make(3, 4)\nprint(shapes.norm1(p))', d)
            self.assertEqual(out.strip(), "7")


class TestStdlibSignatures(unittest.TestCase):
    def test_stdlib_calls_are_typed(self):
        self.assertTrue(errors('use math\nlet s: str = math.sqrt(4.0)'))
        self.assertTrue(errors('use text\ntext.upper(5)'))
        self.assertTrue(errors('use fs\nfs.write("a", 5)'))
        self.assertEqual(errors('use math\nlet r: float = math.sqrt(16)'), [])  # int accepted: number

    def test_unknown_stdlib_member(self):
        d = analyze('use math\nmath.sqroot(4.0)')[0][0]
        self.assertIn("sqrt", d.hint)

    def test_python_bridge_is_dynamic_on_purpose(self):
        self.assertEqual(errors('use python\nlet a: str = python.call("math", "sqrt", 4.0)\nlet b: int = python.call("math", "sqrt", 4.0)'), [])

    def test_signature_table_matches_runtime(self):
        from calyre.stdlib import STDLIB_MODULES
        from calyre.stdlib_types import STDLIB_SIGNATURES
        self.assertEqual(set(STDLIB_MODULES), set(STDLIB_SIGNATURES))
        for name, factory in STDLIB_MODULES.items():
            self.assertEqual(set(factory().members), set(STDLIB_SIGNATURES[name]), name)

    def test_builtin_table_matches_runtime(self):
        from calyre.interpreter import BUILTINS
        from calyre.stdlib_types import BUILTIN_SPECS
        self.assertEqual(set(BUILTINS), set(BUILTIN_SPECS))


if __name__ == "__main__":
    unittest.main()
