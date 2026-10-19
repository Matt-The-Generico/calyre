"""End-to-end tests of the real `calyre` command (subprocess, real exit codes)."""
import os
import unittest
from tests.helpers import cli, project, ROOT

EX = os.path.join(ROOT, "examples")


class TestCli(unittest.TestCase):
    def test_version(self):
        code, out, _ = cli("version")
        self.assertEqual(code, 0)
        self.assertIn("calyre", out)

    def test_run_hello(self):
        code, out, _ = cli("run", os.path.join(EX, "hello.cly"))
        self.assertEqual((code, out.strip()), (0, "Olá, mundo!"))

    def test_type_error_blocks_execution(self):
        with project({"a.cly": 'print("should not print")\nlet x: int = "no"'}) as d:
            code, out, err = cli("run", os.path.join(d, "a.cly"))
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("a.cly:2: error:", err)
            self.assertIn("nothing was run", err)

    def test_diagnostic_format_is_file_line_severity(self):
        with project({"a.cly": 'let x = 1\nlet x = 2'}) as d:
            _, _, err = cli("check", os.path.join(d, "a.cly"))
            self.assertRegex(err, r"a\.cly:2: error: 'x' is already declared")

    def test_check_warnings_do_not_fail(self):
        with project({"a.cly": 'let xs = []'}) as d:
            code, out, err = cli("check", os.path.join(d, "a.cly"))
            self.assertEqual(code, 0)
            self.assertIn("warning", err)
            self.assertIn("1 warning", out)

    def test_run_with_warnings_still_runs(self):
        with project({"a.cly": 'let xs = []\nprint("ran")'}) as d:
            code, out, err = cli("run", os.path.join(d, "a.cly"))
            self.assertEqual((code, out.strip()), (0, "ran"))
            self.assertIn("warning", err)

    def test_syntax_error_exit_code(self):
        with project({"a.cly": 'func f(\n'}) as d:
            code, _, err = cli("run", os.path.join(d, "a.cly"))
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", err)

    def test_runtime_error_exit_code_and_no_traceback(self):
        with project({"a.cly": 'print(1 / 0)'}) as d:
            code, _, err = cli("run", os.path.join(d, "a.cly"))
            self.assertEqual(code, 1)
            self.assertNotIn("Traceback", err)

    def test_missing_file(self):
        code, _, err = cli("run", "/nonexistent/file.cly")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    def test_unknown_command(self):
        code, _, err = cli("frobnicate")
        self.assertEqual(code, 1)
        self.assertIn("unknown command", err)

    def test_module_project_runs_from_other_cwd(self):
        files = {"main.cly": 'use util\nprint(util.one())', "util.cly": 'func one() -> int\n    return 1\nend'}
        with project(files) as d:
            code, out, _ = cli("run", os.path.join(d, "main.cly"), cwd="/")
            self.assertEqual((code, out.strip()), (0, "1"))

    def test_init_then_run(self):
        with project({}) as d:
            target = os.path.join(d, "proj")
            code, _, _ = cli("init", target)
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(os.path.join(target, "calyre.toml")))
            code, out, _ = cli("run", os.path.join(target, "main.cly"))
            self.assertEqual(code, 0)
            self.assertIn("Hello", out)
            code, _, err = cli("init", target)           # refuses to overwrite
            self.assertEqual(code, 1)

    def test_add_remove_list_local_dependency(self):
        with project({}) as d:
            cli("init", d + "/p")
            p = d + "/p"
            self.assertEqual(cli("add", "lib", "--path", "../lib", cwd=p)[0], 0)
            self.assertIn("lib", cli("list", cwd=p)[1])
            self.assertEqual(cli("remove", "lib", cwd=p)[0], 0)
            self.assertIn("no dependencies", cli("list", cwd=p)[1])
            self.assertEqual(cli("remove", "lib", cwd=p)[0], 1)

    def test_add_without_path_is_refused(self):
        with project({}) as d:
            cli("init", d + "/p")
            code, _, err = cli("add", "lib", cwd=d + "/p")
            self.assertEqual(code, 1)
            self.assertIn("local", err)

    def test_repl_session_survives_errors(self):
        code, out, _ = cli(stdin='let x = 10\nprint(x + "a")\nprint(x + 5)\nexit\n')
        self.assertEqual(code, 0)
        self.assertIn("15", out)
        self.assertIn("Error", out)

    def test_repl_multiline_function(self):
        code, out, _ = cli(stdin='func d(x: int) -> int\n    return x * 2\nend\nd(21)\nexit\n')
        self.assertIn("42", out)

    def test_repl_failed_input_leaves_no_ghost_declaration(self):
        _, out, _ = cli(stdin='let y: int = "a"\nprint(y)\nexit\n')
        self.assertEqual(out.count("Error"), 2)   # the 2nd error is "'y' is not defined"

    def test_runtime_error_in_module_names_the_module_file(self):
        files = {"main.cly": 'use util\nprint(util.boom())',
                 "util.cly": 'func boom() -> float\n    return 1 / 0\nend'}
        with project(files) as d:
            code, _, err = cli("run", os.path.join(d, "main.cly"))
            self.assertEqual(code, 1)
            self.assertIn("util.cly:2: runtime error: division by zero", err)

    def test_runtime_error_format_in_main_file(self):
        with project({"a.cly": 'let a = 1\nprint(a / 0)'}) as d:
            _, _, err = cli("run", os.path.join(d, "a.cly"))
            self.assertRegex(err, r"a\.cly:2: runtime error: division by zero")

    def test_examples_all_check_and_run(self):
        for rel in ("hello.cly", "demo.cly", os.path.join("modules_demo", "main.cly")):
            code, _, err = cli("run", os.path.join(EX, rel))
            self.assertEqual(code, 0, f"{rel}: {err}")


if __name__ == "__main__":
    unittest.main()
