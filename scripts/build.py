#!/usr/bin/env python3
"""
Build a standalone `calyre` executable for the machine you run this on, then smoke-test it.

    python scripts/build.py            # needs: pip install -r requirements-build.txt

Output (in dist/): calyre-<os>-<arch>[.exe] and calyre-<os>-<arch>[.exe].sha256

PyInstaller cannot cross-compile: a Windows .exe must be built on Windows, a macOS binary on
macOS, a Linux binary on Linux (CI builds all three, see .github/workflows/ci.yml). The smoke
test runs the *built executable*, never the Python sources, so it proves the artifact works
without Python's help.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def target_name():
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux" if sys.platform.startswith("linux") else sys.platform)
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"calyre-{system}-{arch}" + (".exe" if system == "windows" else "")


def build():
    try:
        import PyInstaller
    except ImportError:
        sys.exit("PyInstaller is not installed: pip install -r requirements-build.txt")
    print(f"python {platform.python_version()}  pyinstaller {PyInstaller.__version__}  {platform.platform()}")
    work = tempfile.mkdtemp(prefix="calyre-build-")
    try:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm",
                        "--name", "calyre", "--distpath", os.path.join(work, "out"),
                        "--workpath", os.path.join(work, "work"), "--specpath", work,
                        os.path.join(ROOT, "calyre_entry.py")], check=True, cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        built = os.path.join(work, "out", "calyre" + (".exe" if sys.platform == "win32" else ""))
        os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
        final = os.path.join(ROOT, "dist", target_name())
        shutil.copy2(built, final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    digest = hashlib.sha256(open(final, "rb").read()).hexdigest()
    with open(final + ".sha256", "w") as f:
        f.write(f"{digest}  {os.path.basename(final)}\n")
    print(f"built {final} ({os.path.getsize(final) / 1e6:.1f} MB)\nsha256 {digest}")
    return final


def smoke(exe):
    """Run the real executable through the main workflows; raise on the first deviation."""
    failures = []
    with tempfile.TemporaryDirectory() as d:
        def write(name, text):
            with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            return os.path.join(d, name)

        def run(*args, stdin=None):
            return subprocess.run([exe, *args], capture_output=True, text=True, input=stdin, cwd=d, timeout=120,
                                  encoding="utf-8")

        def expect(label, cond, detail=""):
            print(("ok   " if cond else "FAIL ") + label)
            if not cond:
                failures.append(f"{label}: {detail}")

        hello = write("hello.cly", 'use math\nprint("ok {math.floor(2.5)}")\n')
        r = run("version")
        expect("version", r.returncode == 0 and "calyre" in r.stdout, r.stderr)
        r = run("run", hello)
        expect("run a program", (r.returncode, r.stdout.strip()) == (0, "ok 2"), r.stdout + r.stderr)
        bad = write("bad.cly", 'let x: int = "no"\n')
        r = run("run", bad)
        expect("type errors stop execution", r.returncode == 1 and "bad.cly:1:14: error" in r.stderr, r.stderr)
        write("lib.cly", 'pub func twice(n: int) -> int\n    return n * 2\nend\n')
        main = write("main.cly", 'use "./lib.cly"\nprint(lib.twice(21))\n')
        r = run("run", main)
        expect("path imports", (r.returncode, r.stdout.strip()) == (0, "42"), r.stderr)
        r = run("fmt", "--check", main)
        expect("fmt --check", r.returncode == 0, r.stdout + r.stderr)
        write("test_lib.cly", 'use "./lib.cly"\nfunc test_twice()\n    assert lib.twice(2) == 4\nend\n')
        r = run("test", d)
        expect("test runner", r.returncode == 0 and "1 passed" in r.stdout, r.stdout + r.stderr)
        r = run("lint", main)
        expect("lint", r.returncode == 0, r.stdout + r.stderr)
        db = write("db.cly", 'use sql\nlet db = sql.open("sqlite::memory:")\ndb.execute("CREATE TABLE t (v INTEGER)")\n'
                             'db.execute("INSERT INTO t VALUES (?)", [7])\nprint((db.query_one("SELECT v FROM t") ?? {})["v"])\n')
        r = run("run", db)
        expect("sqlite works inside the executable", (r.returncode, r.stdout.strip()) == (0, "7"), r.stdout + r.stderr)
        js = write("js.cly", 'use json\nprint(json.stringify({"a": [1, 2]}))\n')
        r = run("run", js)
        expect("json", (r.returncode, r.stdout.strip()) == (0, '{"a":[1,2]}'), r.stdout + r.stderr)
        r = run(stdin="1 + 1\nlet x = 5\nx * 2\nexit\n")
        expect("repl", r.returncode == 0 and "2\n" in r.stdout and "10" in r.stdout, r.stdout + r.stderr)
        r = run("run", write("args.cly", 'use system\nprint(system.args())\n'), "a", "b")
        expect("program arguments", r.stdout.strip() == '["a", "b"]', r.stdout + r.stderr)
    if failures:
        sys.exit("smoke test failed:\n  " + "\n  ".join(failures))
    print("SMOKE OK")


if __name__ == "__main__":
    smoke(build())
