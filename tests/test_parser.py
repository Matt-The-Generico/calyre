import unittest
from calyre.lexer import tokenize
from calyre.calyre_parser import parse, ParseError
from calyre import ast_nodes as A


def _parse(src):
    return parse(tokenize(src))


class TestParser(unittest.TestCase):
    def test_let_with_and_without_type(self):
        prog = _parse("let x = 5\nlet y: int = 10")
        self.assertIsInstance(prog.statements[0], A.LetStmt)
        self.assertIsNone(prog.statements[0].type_ann)
        self.assertEqual(prog.statements[1].type_ann.name, "int")

    def test_func_decl(self):
        prog = _parse("func add(a: int, b: int) -> int\n    return a + b\nend")
        fn = prog.statements[0]
        self.assertIsInstance(fn, A.FuncDecl)
        self.assertEqual(fn.name, "add")
        self.assertEqual(len(fn.params), 2)
        self.assertEqual(fn.return_type.name, "int")

    def test_if_elif_else(self):
        src = "if a\n    x\nelif b\n    y\nelse\n    z\nend"
        prog = _parse(src)
        ifstmt = prog.statements[0]
        self.assertEqual(len(ifstmt.branches), 2)
        self.assertIsNotNone(ifstmt.else_block)

    def test_missing_end_is_parse_error(self):
        with self.assertRaises(ParseError):
            _parse("func f()\n    return 1\n")

    def test_operator_precedence(self):
        prog = _parse("let x = 1 + 2 * 3")
        value = prog.statements[0].value
        self.assertIsInstance(value, A.BinaryOp)
        self.assertEqual(value.op, "+")
        self.assertIsInstance(value.right, A.BinaryOp)
        self.assertEqual(value.right.op, "*")

    def test_list_and_map_literals(self):
        prog = _parse('let a = [1, 2, 3]\nlet b = { "x": 1, "y": 2 }')
        self.assertIsInstance(prog.statements[0].value, A.ListLiteral)
        self.assertIsInstance(prog.statements[1].value, A.MapLiteral)
        self.assertEqual(len(prog.statements[1].value.pairs), 2)

    def test_use_with_alias(self):
        prog = _parse("use math_utils as m")
        stmt = prog.statements[0]
        self.assertEqual(stmt.path, "math_utils")
        self.assertEqual(stmt.alias, "m")

    def test_use_without_alias(self):
        prog = _parse("use math_utils")
        stmt = prog.statements[0]
        self.assertIsNone(stmt.alias)

    def test_try_catch(self):
        prog = _parse("try\n    let x = 1\ncatch e\n    print(e)\nend")
        stmt = prog.statements[0]
        self.assertIsInstance(stmt, A.TryStmt)
        self.assertEqual(stmt.err_name, "e")

    def test_assert_with_and_without_message(self):
        prog = _parse('assert 1 == 1\nassert 1 == 1, "should hold"')
        self.assertIsNone(prog.statements[0].message)
        self.assertIsNotNone(prog.statements[1].message)

    def test_struct_decl(self):
        prog = _parse("struct Point\n    x: int\n    y: int\nend")
        stmt = prog.statements[0]
        self.assertIsInstance(stmt, A.StructDecl)
        self.assertEqual([f.name for f in stmt.fields], ["x", "y"])

    def test_match_case(self):
        prog = _parse("match x\ncase 1\n    a\ncase _\n    b\nend")
        stmt = prog.statements[0]
        self.assertEqual(len(stmt.cases), 2)
        self.assertIsNone(stmt.cases[1][0])  # wildcard

    def test_string_interpolation_produces_interp_string_node(self):
        prog = _parse('let g = "Hi {name}"')
        self.assertIsInstance(prog.statements[0].value, A.InterpString)

    def test_generic_type_annotation(self):
        prog = _parse("let xs: list<int> = [1, 2]")
        t = prog.statements[0].type_ann
        self.assertEqual(t.name, "list")
        self.assertEqual(t.params[0].name, "int")

    def test_optional_type_annotation(self):
        prog = _parse("func f(x: str?) -> int\n    return 1\nend")
        self.assertTrue(prog.statements[0].params[0].type_ann.optional)


if __name__ == "__main__":
    unittest.main()
