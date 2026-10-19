"""calyre.toml path dependencies are actually resolved by `use`."""
import os
import unittest
from tests.helpers import cli, project, errors, run

LIB = 'func hello(name: str) -> str\n    return "hi {name}"\nend'
MANIFEST = '[project]\nname = "app"\nversion = "0.1.0"\n\n[dependencies]\nmylib = {{ path = "{p}" }}\n'


class TestDependencies(unittest.TestCase):
    def files(self, entry="mylib.cly"):
        return {"app/calyre.toml": MANIFEST.format(p="../lib"), "app/main.cly": 'use mylib\nprint(mylib.hello("x"))',
                f"lib/{entry}": LIB}

    def test_dependency_is_resolved_and_typed(self):
        with project(self.files()) as d:
            app = os.path.join(d, "app")
            self.assertEqual(len(errors('use mylib\nlet n: int = mylib.hello("a")', app)), 1)
            self.assertEqual(errors('use mylib\nlet n: str = mylib.hello("a")', app), [])

    def test_dependency_runs_end_to_end(self):
        with project(self.files()) as d:
            code, out, err = cli("run", os.path.join(d, "app", "main.cly"))
            self.assertEqual((code, out.strip()), (0, "hi x"), err)

    def test_submodule_of_dependency(self):
        files = self.files()
        files["lib/extra.cly"] = 'func one() -> int\n    return 1\nend'
        files["app/main.cly"] = 'use mylib.extra\nprint(extra.one())'
        with project(files) as d:
            code, out, err = cli("run", os.path.join(d, "app", "main.cly"))
            self.assertEqual((code, out.strip()), (0, "1"), err)

    def test_local_file_shadows_dependency(self):
        files = self.files()
        files["app/mylib.cly"] = 'func hello(name: str) -> str\n    return "local"\nend'
        with project(files) as d:
            code, out, _ = cli("run", os.path.join(d, "app", "main.cly"))
            self.assertEqual(out.strip(), "local")

    def test_missing_dependency_entry_file(self):
        files = self.files(entry="other.cly")
        with project(files) as d:
            code, _, err = cli("run", os.path.join(d, "app", "main.cly"))
            self.assertEqual(code, 1)
            self.assertIn("cannot find module 'mylib'", err)

    def test_add_then_use_full_flow(self):
        files = {"lib/mylib.cly": LIB}
        with project(files) as d:
            app = os.path.join(d, "app")
            self.assertEqual(cli("init", app)[0], 0)
            self.assertEqual(cli("add", "mylib", "--path", "../lib", cwd=app)[0], 0)
            with open(os.path.join(app, "main.cly"), "w") as f:
                f.write('use mylib\nprint(mylib.hello("flow"))')
            code, out, err = cli("run", "main.cly", cwd=app)
            self.assertEqual((code, out.strip()), (0, "hi flow"), err)


if __name__ == "__main__":
    unittest.main()
