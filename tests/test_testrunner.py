"""`calyre test`."""
import os
import unittest
from tests.helpers import cli, project

GOOD = ('func add(a: int, b: int) -> int\n    return a + b\nend\n\n'
        'func test_add()\n    assert add(1, 2) == 3\nend\n\nfunc test_add_negative()\n    assert add(-1, -2) == -3\nend\n')
BAD = ('func test_ok()\n    assert 1 == 1\nend\n\n'
       'func test_fails()\n    print("noisy debug")\n    assert 1 + 1 == 3\nend\n\n'
       'func test_raises()\n    error("boom")\nend\n')


class TestTestRunner(unittest.TestCase):
    def test_all_pass(self):
        with project({"a_test.cly": GOOD}) as d:
            code, out, _ = cli("test", d)
            self.assertEqual(code, 0)
            self.assertIn("2 passed, 0 failed", out)

    def test_failures_exit_1_and_are_explained(self):
        with project({"test_x.cly": BAD}) as d:
            code, out, _ = cli("test", d)
            self.assertEqual(code, 1)
            self.assertIn("1 passed, 2 failed", out)
            self.assertIn("test_x.cly::test_fails", out)
            self.assertIn("assertion failed: 1 + 1 == 3", out)
            self.assertIn("test_x.cly:7:", out)                      # the assert's line
            self.assertIn("noisy debug", out)                        # captured output of the failing test
            self.assertIn("test_x.cly:11: boom", out)                # error() has a line too

    def test_output_of_passing_tests_is_hidden(self):
        with project({"test_p.cly": 'func test_p()\n    print("should be hidden")\nend\n'}) as d:
            self.assertNotIn("should be hidden", cli("test", d)[1])

    def test_verbose_lists_passing_tests(self):
        with project({"a_test.cly": GOOD}) as d:
            self.assertIn("PASS", cli("test", "-v", d)[1])

    def test_filter_by_name(self):
        with project({"test_x.cly": BAD}) as d:
            code, out, _ = cli("test", "-k", "ok", d)
            self.assertEqual((code, "1 passed, 0 failed" in out), (0, True))
            self.assertEqual(cli("test", "-k")[0], 1)

    def test_only_test_files_and_functions_are_collected(self):
        files = {"util.cly": 'func test_not_collected()\n    error("never runs")\nend',
                 "sub/test_deep.cly": 'func test_deep()\n    assert true\nend\nfunc helper()\n    error("no")\nend'}
        with project(files) as d:
            code, out, _ = cli("test", d)
            self.assertEqual((code, "1 passed, 0 failed" in out), (0, True))

    def test_no_tests_is_an_error(self):
        with project({"util.cly": "let a = 1"}) as d:
            code, _, err = cli("test", d)
            self.assertEqual(code, 1)
            self.assertIn("no tests found", err)

    def test_compile_errors_fail_the_file_without_running_it(self):
        with project({"test_bad.cly": 'print("ran?")\nfunc test_a()\n    let x: int = "s"\nend'}) as d:
            code, out, _ = cli("test", d)
            self.assertEqual(code, 1)
            self.assertIn("does not compile", out)
            self.assertNotIn("ran?", out)

    def test_syntax_error_fails_the_file(self):
        with project({"test_bad.cly": "func test_a(\n"}) as d:
            code, out, _ = cli("test", d)
            self.assertEqual(code, 1)
            self.assertIn("syntax error", out)

    def test_other_files_still_run_when_one_is_broken(self):
        with project({"test_bad.cly": "func test_a(\n", "test_ok.cly": 'func test_b()\n    assert true\nend'}) as d:
            self.assertIn("1 passed, 1 failed", cli("test", d)[1])

    def test_tests_can_use_modules_next_to_them(self):
        files = {"lib.cly": 'pub func double(n: int) -> int\n    return n * 2\nend',
                 "test_lib.cly": 'use lib\nfunc test_double()\n    assert lib.double(4) == 8\nend'}
        with project(files) as d:
            self.assertEqual(cli("test", d)[0], 0)

    def test_tests_do_not_share_failures(self):
        src = ('let counter = 0\nfunc test_a()\n    counter = counter + 1\n    error("x")\nend\n'
               'func test_b()\n    assert counter == 1\nend')
        with project({"test_s.cly": src}) as d:
            self.assertIn("1 passed, 1 failed", cli("test", d)[1])

    def test_parameters_are_rejected(self):
        with project({"test_p.cly": 'func test_p(a: int)\n    assert true\nend'}) as d:
            code, out, _ = cli("test", d)
            self.assertEqual(code, 1)
            self.assertIn("must not take parameters", out)

    def test_runtime_error_in_a_module_names_the_module(self):
        files = {"lib.cly": 'pub func boom() -> float\n    return 1 / 0\nend',
                 "test_l.cly": 'use lib\nfunc test_l()\n    lib.boom()\nend'}
        with project(files) as d:
            self.assertIn("lib.cly:2", cli("test", d)[1])

    def test_unknown_option(self):
        self.assertEqual(cli("test", "--bogus")[0], 1)


if __name__ == "__main__":
    unittest.main()
