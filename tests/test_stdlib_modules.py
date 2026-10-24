"""json, path, system and the extended fs module."""
import os
import sys
import unittest

from calyre.interpreter import CalyreRuntimeError
from tests.helpers import cli, errors, project, run


def out(src, **k):
    return run(src, **k).splitlines()


def fails(src, text):
    with unittest.TestCase().assertRaises(CalyreRuntimeError) as ctx:
        run(src)
    assert text in str(ctx.exception), str(ctx.exception)


class TestJson(unittest.TestCase):
    DOC = '"""{"a": 1, "b": [1.5, true, null, "x"], "c": {"d": 2}}"""'

    def test_parse_values(self):
        src = ('use json\nlet d = json.parse(' + self.DOC + ')\n'
               'print(d["a"])\nprint(d["b"])\nprint(d["c"]["d"])\nprint(d.get("zzz") ?? "missing")')
        self.assertEqual(out(src), ["1", '[1.5, true, none, "x"]', "2", "missing"])

    def test_numbers_keep_their_kind(self):
        self.assertEqual(out('use json\nprint(json.parse("1"))\nprint(json.parse("1.0"))\nprint(json.parse("1e3"))'),
                         ["1", "1.0", "1000.0"])
        self.assertEqual(out('use json\nprint(json.parse("123456789012345678901234567890"))'),
                         ["123456789012345678901234567890"])

    def test_unicode_and_escapes(self):
        src = r'''use json
print(json.parse("\"caf\\u00e9\""))'''
        self.assertEqual(run(src).strip(), "café")
        src = r'''use json
print(json.parse("""["a\nb"]""")[0].split("\n"))'''
        self.assertEqual(run(src).strip(), '["a", "b"]')

    def test_invalid_json_errors_say_where(self):
        for bad in ('{"a": }', '[1, 2', '', '{"a": 1} trailing', "{'a': 1}"):
            with self.assertRaises(CalyreRuntimeError) as ctx:
                run('use json\njson.parse("""' + bad + '""")')
            self.assertIn("json.parse: invalid JSON at line", str(ctx.exception), bad)

    def test_error_position_is_reported(self):
        with self.assertRaises(CalyreRuntimeError) as ctx:
            run('use json\njson.parse("""{\n  "a": ,\n}""")')
        self.assertIn("line 2, column 8", str(ctx.exception))

    def test_nan_and_infinity_are_rejected(self):
        for c in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(CalyreRuntimeError):
                run(f'use json\njson.parse("{c}")')

    def test_too_deep_is_an_error_not_a_crash(self):
        with self.assertRaises(CalyreRuntimeError) as ctx:
            run('use json\njson.parse("[".repeat(100000) + "]".repeat(100000))')
        self.assertIn("nested too deeply", str(ctx.exception))

    def test_stringify_and_pretty(self):
        self.assertEqual(out('use json\nprint(json.stringify({"a": [1, 2.5, true, none, "x"]}))'),
                         ['{"a":[1,2.5,true,null,"x"]}'])
        self.assertEqual(run('use json\nprint(json.pretty({"a": [1], "b": {}}))'),
                         '{\n  "a": [\n    1\n  ],\n  "b": {}\n}\n')

    def test_structs_become_objects(self):
        src = ('use json\nstruct User\n    name: str\n    tags: list<str>\n    boss: User?\nend\n'
               'print(json.stringify(User(name: "Ana", tags: ["a"], boss: none)))')
        self.assertEqual(out(src), ['{"name":"Ana","tags":["a"],"boss":null}'])

    def test_non_ascii_is_kept(self):
        self.assertEqual(run('use json\nprint(json.stringify("日本語 é"))').strip(), '"日本語 é"')

    def test_roundtrip(self):
        src = ('use json\nlet text = json.stringify({"n": [1, {"k": "v"}], "f": 0.5})\n'
               'print(json.stringify(json.parse(text)) == text)')
        self.assertEqual(out(src), ["true"])

    def test_stringify_errors_name_the_offending_part(self):
        fails('use json\njson.stringify({1: "a"})', "map key that is not a text")
        fails('use json\nlet x: any = print\njson.stringify(x)', "cannot be turned into JSON")
        fails('use json\nlet x: any = [1, print]\njson.stringify(x)', "value[1]")

    def test_infinity_and_nan_cannot_be_stringified(self):
        huge = "1" + "0" * 400 + ".0"                      # a float literal too big for a float: inf
        fails(f'use json\njson.stringify({huge})', "which JSON cannot represent")
        fails(f'use json\nlet big = {huge}\njson.stringify(big - big)', "which JSON cannot represent")

    def test_mixed_literals_are_fine_where_any_is_expected(self):
        # a heterogeneous literal is accepted as the `any` argument ...
        self.assertEqual(errors('use json\njson.stringify([1, "a", {"k": [true, none]}])'), [])
        # ... but not where a typed list is expected
        self.assertTrue(errors('func f(xs: list<int>)\n    print(1)\nend\nf([1, "a"])'))
        self.assertEqual(errors('func f(x: any)\n    print(1)\nend\nf([1, "a"])'), [])

    def test_typing(self):
        self.assertEqual(errors('use json\nlet d = json.parse("1")\nlet n: int = d\nlet s: str = d'), [])   # any
        self.assertTrue(errors('use json\njson.parse(5)'))
        self.assertTrue(errors('use json\nlet n: int = json.stringify([1])'))
        self.assertEqual(errors('use json\nlet s: str = json.stringify(json.parse("[1]"))'), [])


class TestPath(unittest.TestCase):
    def check(self, expr, want):
        self.assertEqual(run(f'use path\nprint({expr})').rstrip("\n"), want, expr)

    def test_join(self):
        for expr, want in [('path.join("a", "b")', "a/b"), ('path.join("a/", "b")', "a/b"), ('path.join("", "b")', "b"),
                           ('path.join("a", "/abs")', "/abs"), ('path.join("a", "C:/x")', "C:/x"),
                           ('path.join("a\\\\b", "c\\\\d")', "a/b/c/d"), ('path.join("/", "x")', "/x"),
                           ('path.join_all(["a", "b", "c.txt"])', "a/b/c.txt"), ('path.join_all([])', "")]:
            self.check(expr, want)

    def test_basename_dirname(self):
        for expr, want in [('path.basename("a/b/c.txt")', "c.txt"), ('path.basename("a/b/")', "b"), ('path.basename("c")', "c"),
                           ('path.basename("/")', ""), ('path.basename("")', ""),
                           ('path.dirname("a/b/c.txt")', "a/b"), ('path.dirname("c.txt")', ""), ('path.dirname("/c")', "/"),
                           ('path.dirname("a/b/")', "a"), ('path.dirname("a\\\\b")', "a")]:
            self.check(expr, want)

    def test_stem_and_extension(self):
        for expr, want in [('path.stem("a/b.txt")', "b"), ('path.extension("a/b.txt")', ".txt"),
                           ('path.extension("a.tar.gz")', ".gz"), ('path.stem("a.tar.gz")', "a.tar"),
                           ('path.extension(".bashrc")', ""), ('path.stem(".bashrc")', ".bashrc"),
                           ('path.extension("noext")', ""), ('path.extension("a.b/c")', "")]:
            self.check(expr, want)

    def test_with_extension(self):
        for expr, want in [('path.with_extension("a/b.txt", ".md")', "a/b.md"), ('path.with_extension("b", ".md")', "b.md"),
                           ('path.with_extension("a/b.txt", "")', "a/b")]:
            self.check(expr, want)
        for bad in ('"md"', '"."', '"./x"'):
            fails(f'use path\npath.with_extension("a.txt", {bad})', "extension")

    def test_normalize(self):
        for expr, want in [('path.normalize("a/./b/../c")', "a/c"), ('path.normalize("")', "."), ('path.normalize("../x")', "../x"),
                           ('path.normalize("a\\\\b\\\\..\\\\c")', "a/c"), ('path.normalize("/a/../..")', "/")]:
            self.check(expr, want)

    def test_parts_and_absoluteness(self):
        self.check('path.parts("a/b/c")', '["a", "b", "c"]')
        self.check('path.parts("/a/./b")', '["/", "a", "b"]')
        for expr, want in [('path.is_absolute("/x")', "true"), ('path.is_absolute("C:/x")', "true"),
                           ('path.is_absolute("C:\\\\x")', "true"), ('path.is_absolute("x/y")', "false"),
                           ('path.is_absolute("")', "false")]:
            self.check(expr, want)

    def test_relative_to(self):
        self.check('path.relative_to("a/b/c", "a")', "b/c")
        self.check('path.relative_to("/x/y", "/x/z")', "../y")
        fails('use path\npath.relative_to("/a", "b")', "both paths")

    def test_absolute_uses_slashes_and_the_working_directory(self):
        got = run('use path\nprint(path.absolute("x/y"))').strip()
        self.assertNotIn("\\", got)
        self.assertTrue(got.endswith("/x/y"))

    def test_results_do_not_depend_on_the_operating_system(self):
        # the functions are pure text functions: same input, same output everywhere
        self.check('path.join("dir", "file.txt")', "dir/file.txt")

    def test_typing(self):
        self.assertTrue(errors('use path\nlet n: int = path.join("a", "b")'))
        self.assertTrue(errors('use path\npath.join("a")'))
        self.assertEqual(errors('use path\nlet p: list<str> = path.parts("a/b")'), [])


class TestFsExtended(unittest.TestCase):
    def test_write_read_append_and_exact_bytes(self):
        with project({}) as d:
            f = os.path.join(d, "t.txt").replace("\\", "/")
            src = (f'use fs\nfs.write("{f}", "a\\nb\\n")\nfs.append("{f}", "c")\nprint(fs.read("{f}") == "a\\nb\\nc")\n'
                   f'print(fs.size("{f}"))\nprint(fs.is_file("{f}"))\nprint(fs.is_dir("{f}"))')
            self.assertEqual(out(src), ["true", "5", "true", "false"])
            self.assertEqual(open(f, "rb").read(), b"a\nb\nc")           # never \r\n, on any platform

    def test_reading_translates_crlf(self):
        with project({}) as d:
            f = os.path.join(d, "w.txt")
            with open(f, "wb") as fh:
                fh.write(b"one\r\ntwo\r\n")
            self.assertEqual(out(f'use fs\nprint(fs.read("{f}".replace("\\\\", "/")) == "one\\ntwo\\n")'.replace(
                '.replace("\\\\", "/")', "")), ["true"]) if os.name != "nt" else None

    def test_remove_and_remove_dir_are_deliberately_limited(self):
        with project({"d/x.txt": "x", "e/.keep": ""}) as d:
            p = lambda *a: os.path.join(d, *a).replace("\\", "/")
            fails(f'use fs\nfs.remove("{p("d")}")', "only deletes files")
            fails(f'use fs\nfs.remove_dir("{p("d")}")', "never deletes folders recursively")
            run(f'use fs\nfs.remove("{p("d", "x.txt")}")\nfs.remove_dir("{p("d")}")')
            self.assertFalse(os.path.exists(p("d")))
            fails(f'use fs\nfs.remove("{p("nope.txt")}")', "no such file")

    def test_rename_never_overwrites(self):
        with project({"a.txt": "A", "b.txt": "B"}) as d:
            p = lambda n: os.path.join(d, n).replace("\\", "/")
            fails(f'use fs\nfs.rename("{p("a.txt")}", "{p("b.txt")}")', "already exists")
            run(f'use fs\nfs.rename("{p("a.txt")}", "{p("c.txt")}")')
            self.assertEqual(open(p("c.txt")).read(), "A")
            self.assertEqual(open(p("b.txt")).read(), "B")

    def test_error_messages_are_readable(self):
        with project({"dir/x": "", "bad.bin": ""}) as d:
            p = lambda n: os.path.join(d, n).replace("\\", "/")
            with open(p("bad.bin"), "wb") as fh:
                fh.write(b"\xff\xfe\xfa")
            fails(f'use fs\nfs.read("{p("missing.txt")}")', "no such file or folder")
            fails(f'use fs\nfs.read("{p("dir")}")', "it is a folder, not a file")
            fails(f'use fs\nfs.read("{p("bad.bin")}")', "not valid UTF-8")
            fails(f'use fs\nfs.write("{p("nodir/x.txt")}", "x")', "folder does not exist")
            fails(f'use fs\nfs.list_dir("{p("bad.bin")}")', "it is a file, not a folder")
            fails(f'use fs\nfs.make_dir("{p("bad.bin")}")', "bad.bin")
            fails(f'use fs\nfs.size("{p("nope")}")', "no such file")

    def test_typing(self):
        self.assertTrue(errors('use fs\nlet n: str = fs.size("x")'))
        self.assertTrue(errors('use fs\nfs.append("a", 1)'))
        self.assertEqual(errors('use fs\nlet b: bool = fs.is_dir("x")'), [])

    def test_catchable(self):
        self.assertEqual(out('use fs\ntry\n    fs.read("/definitely/not/here")\ncatch e\n    print("caught")\nend'), ["caught"])


class TestSystem(unittest.TestCase):
    def test_args_reach_the_program(self):
        with project({"a.cly": 'use system\nprint(system.args())\nprint(len(system.args()))'}) as d:
            code, o, err = cli("run", os.path.join(d, "a.cly"), "one", "--flag", "two words")
            self.assertEqual((code, o.splitlines()), (0, ['["one", "--flag", "two words"]', "3"]), err)
            self.assertEqual(cli("run", os.path.join(d, "a.cly"))[1].splitlines()[0], "[]")

    def test_env_is_optional(self):
        os.environ["CALYRE_TEST_VAR"] = "hello"
        try:
            self.assertEqual(out('use system\nprint(system.env("CALYRE_TEST_VAR") ?? "none")'), ["hello"])
        finally:
            del os.environ["CALYRE_TEST_VAR"]
        self.assertEqual(out('use system\nprint(system.env("CALYRE_SURELY_NOT_SET") ?? "default")'), ["default"])
        self.assertTrue(errors('use system\nlet s: str = system.env("X")'))
        self.assertEqual(errors('use system\nlet s: str = system.env("X") ?? ""'), [])

    def test_platform_and_cwd(self):
        self.assertIn(run('use system\nprint(system.platform())').strip(), ("windows", "linux", "macos") + (sys.platform,))
        self.assertNotIn("\\", run('use system\nprint(system.cwd())'))

    def test_exit_code_and_flushed_output(self):
        with project({"a.cly": 'use system\nprint("before")\nsystem.exit(3)\nprint("after")'}) as d:
            code, o, _ = cli("run", os.path.join(d, "a.cly"))
            self.assertEqual((code, o.strip()), (3, "before"))

    def test_exit_is_not_caught_by_try(self):
        with project({"a.cly": 'use system\ntry\n    system.exit(4)\ncatch e\n    print("caught")\nend'}) as d:
            code, o, _ = cli("run", os.path.join(d, "a.cly"))
            self.assertEqual((code, o.strip()), (4, ""))

    def test_invalid_exit_codes(self):
        for bad in ("256", "-1"):
            fails(f'use system\nsystem.exit({bad})', "0 to 255")

    def test_exit_inside_a_test_fails_that_test_only(self):
        files = {"test_a.cly": 'use system\nfunc test_exits()\n    system.exit(9)\nend\nfunc test_fine()\n    assert true\nend'}
        with project(files) as d:
            code, o, _ = cli("test", d)
            self.assertEqual(code, 1)
            self.assertIn("1 passed, 1 failed", o)
            self.assertIn("system.exit(9)", o)


if __name__ == "__main__":
    unittest.main()
