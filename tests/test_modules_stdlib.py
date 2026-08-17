import io
import os
import contextlib
import tempfile
import unittest

from calyre.lexer import tokenize
from calyre.calyre_parser import parse
from calyre.interpreter import interpret, CalyreRuntimeError


def run_in_dir(main_src, files, base_dir):
    for name, content in files.items():
        with open(os.path.join(base_dir, name), "w", encoding="utf-8") as f:
            f.write(content)
    prog = parse(tokenize(main_src))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        interpret(prog, base_dir=base_dir)
    return buf.getvalue()


class TestModules(unittest.TestCase):
    def test_local_module_use_and_call(self):
        with tempfile.TemporaryDirectory() as d:
            out = run_in_dir(
                'use math_utils\nprint(math_utils.square(4.0))',
                {"math_utils.cly": 'func square(x: float) -> float\n    return x * x\nend'},
                d,
            )
            self.assertEqual(out.strip(), "16.0")

    def test_local_module_alias(self):
        with tempfile.TemporaryDirectory() as d:
            out = run_in_dir(
                'use math_utils as m\nprint(m.square(3.0))',
                {"math_utils.cly": 'func square(x: float) -> float\n    return x * x\nend'},
                d,
            )
            self.assertEqual(out.strip(), "9.0")

    def test_missing_module_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CalyreRuntimeError) as ctx:
                run_in_dir('use does_not_exist\nprint(1)', {}, d)
            self.assertIn("does_not_exist", str(ctx.exception))

    def test_private_names_not_exported(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CalyreRuntimeError):
                run_in_dir(
                    'use helpers\nprint(helpers._secret())',
                    {"helpers.cly": 'func _secret() -> int\n    return 42\nend'},
                    d,
                )

    def test_circular_import_detected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(CalyreRuntimeError) as ctx:
                run_in_dir(
                    'use a\nprint(1)',
                    {
                        "a.cly": "use b\n",
                        "b.cly": "use a\n",
                    },
                    d,
                )
            self.assertIn("circular", str(ctx.exception).lower())


class TestStdlib(unittest.TestCase):
    def _run(self, src):
        prog = parse(tokenize(src))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            interpret(prog)
        return buf.getvalue()

    def test_math_module(self):
        out = self._run('use math\nprint(math.sqrt(16.0))\nprint(math.floor(3.7))\nprint(math.abs(-5))')
        self.assertEqual(out.splitlines(), ["4.0", "3", "5"])

    def test_math_sqrt_negative_raises(self):
        with self.assertRaises(CalyreRuntimeError):
            self._run('use math\nprint(math.sqrt(-1.0))')

    def test_text_module(self):
        src = '''
use text
print(text.upper("abc"))
print(text.lower("ABC"))
print(text.trim("  hi  "))
print(text.contains("hello world", "world"))
print(text.join(["a", "b", "c"], "-"))
'''
        out = self._run(src)
        self.assertEqual(out.splitlines(), ["ABC", "abc", "hi", "true", "a-b-c"])

    def test_random_module_bounds(self):
        src = '''
use random
let n = random.int(1, 1)
print(n)
'''
        out = self._run(src)
        self.assertEqual(out.strip(), "1")

    def test_fs_module_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.txt").replace("\\", "/")
            src = f'''
use fs
fs.write("{path}", "hello file")
print(fs.exists("{path}"))
print(fs.read("{path}"))
'''
            out = self._run(src)
            self.assertEqual(out.splitlines(), ["true", "hello file"])

    def test_python_bridge_allowed_module(self):
        out = self._run('use python\nprint(python.call("math", "sqrt", 25.0))')
        self.assertEqual(out.strip(), "5.0")

    def test_python_bridge_blocks_non_whitelisted_module(self):
        with self.assertRaises(CalyreRuntimeError):
            self._run('use python\nprint(python.call("os", "system", "echo hi"))')


if __name__ == "__main__":
    unittest.main()
