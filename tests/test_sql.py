"""The `sql` module (SQLite engine) and its integration with the type checker."""
import os
import unittest

from calyre.interpreter import CalyreRuntimeError
from tests.helpers import errors, analyze, project, run

SETUP = '''use sql
let db = sql.open("sqlite::memory:")
db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, age INTEGER)")
'''


def out(src):
    return run(SETUP + src).splitlines()


def fails(src, text, setup=True):
    with unittest.TestCase().assertRaises(CalyreRuntimeError) as ctx:
        run((SETUP if setup else "") + src)
    assert text in str(ctx.exception), str(ctx.exception)


class TestQueries(unittest.TestCase):
    def test_insert_query_and_rows_as_maps(self):
        src = ('db.execute("INSERT INTO users (name, age) VALUES (?, ?)", ["Ana", 30])\n'
               'db.execute("INSERT INTO users (name, age) VALUES (?, ?)", ["Bruno", none])\n'
               'for row in db.query("SELECT id, name, age FROM users ORDER BY id")\n'
               '    print("{row["id"]} {row["name"]} {row["age"] ?? "?"}")\nend')
        self.assertEqual(out(src), ["1 Ana 30", "2 Bruno ?"])

    def test_null_is_none_and_values_keep_their_kind(self):
        src = ('db.execute("CREATE TABLE t (i INTEGER, f REAL, s TEXT, n TEXT)")\n'
               'db.execute("INSERT INTO t VALUES (?, ?, ?, ?)", [7, 2.5, "x", none])\n'
               'let r = db.query_one("SELECT * FROM t") ?? {}\nprint(r["i"] + 1)\nprint(r["f"] * 2.0)\nprint(r["n"] == none)')
        self.assertEqual(out(src), ["8", "5.0", "true"])

    def test_bool_parameters_are_stored_as_integers(self):
        self.assertEqual(out('db.execute("CREATE TABLE b (v INTEGER)")\ndb.execute("INSERT INTO b VALUES (?)", [true])\n'
                             'print((db.query_one("SELECT v FROM b") ?? {})["v"])'), ["1"])

    def test_execute_returns_affected_rows(self):
        src = ('db.execute("INSERT INTO users (name) VALUES (?)", ["a"])\ndb.execute("INSERT INTO users (name) VALUES (?)", ["b"])\n'
               'print(db.execute("UPDATE users SET age = 1"))\nprint(db.execute("DELETE FROM users WHERE id = ?", [99]))\n'
               'print(db.execute("DELETE FROM users"))')
        self.assertEqual(out(src), ["2", "0", "2"])

    def test_query_one_and_last_insert_id(self):
        src = ('db.execute("INSERT INTO users (name) VALUES (?)", ["a"])\nprint(db.last_insert_id())\n'
               'print(db.query_one("SELECT name FROM users WHERE id = ?", [1]) ?? {})\n'
               'print(db.query_one("SELECT name FROM users WHERE id = ?", [9]) == none)')
        self.assertEqual(out(src), ["1", '{"name": "a"}', "true"])

    def test_parameters_are_data_never_code(self):
        evil = "x'; DROP TABLE users; --"
        src = (f'db.execute("INSERT INTO users (name) VALUES (?)", [{evil!r}.replace("\'", "\'")])\n').replace(
            f"{evil!r}.replace(\"'\", \"'\")", '"x\'; DROP TABLE users; --"')
        src += 'print((db.query_one("SELECT name FROM users") ?? {})["name"])\nprint(len(db.query("SELECT * FROM users")))'
        self.assertEqual(out(src), ["x'; DROP TABLE users; --", "1"])

    def test_empty_result(self):
        self.assertEqual(out('print(db.query("SELECT * FROM users"))\nprint(len(db.query("SELECT * FROM users")))'), ["[]", "0"])

    def test_unicode_roundtrip(self):
        self.assertEqual(out('db.execute("INSERT INTO users (name) VALUES (?)", ["日本語 é"])\n'
                             'print((db.query_one("SELECT name FROM users") ?? {})["name"])'), ["日本語 é"])

    def test_rows_can_be_serialised_with_json(self):
        src = ('use json\ndb.execute("INSERT INTO users (name, age) VALUES (?, ?)", ["a", 1])\n'
               'print(json.stringify(db.query("SELECT name, age FROM users")))')
        self.assertEqual(out(src), ['[{"name":"a","age":1}]'])


class TestTransactionsAndErrors(unittest.TestCase):
    def test_commit_and_rollback(self):
        src = ('db.begin()\nprint(db.in_transaction())\ndb.execute("INSERT INTO users (name) VALUES (?)", ["kept"])\ndb.commit()\n'
               'db.begin()\ndb.execute("INSERT INTO users (name) VALUES (?)", ["gone"])\ndb.rollback()\n'
               'print(db.in_transaction())\nprint(len(db.query("SELECT * FROM users")))')
        self.assertEqual(out(src), ["true", "false", "1"])

    def test_rollback_on_error_pattern(self):
        src = ('db.execute("INSERT INTO users (name) VALUES (?)", ["dup"])\ndb.begin()\n'
               'try\n    db.execute("INSERT INTO users (name) VALUES (?)", ["fine"])\n'
               '    db.execute("INSERT INTO users (name) VALUES (?)", ["dup"])\n    db.commit()\n'
               'catch e\n    db.rollback()\n    print("rolled back")\nend\nprint(len(db.query("SELECT * FROM users")))')
        self.assertEqual(out(src), ["rolled back", "1"])

    def test_transaction_errors_are_explained(self):
        fails('db.commit()', "cannot commit")
        fails('db.begin()\ndb.begin()', "within a transaction")

    def test_constraint_errors_show_the_query_not_the_values(self):
        with self.assertRaises(CalyreRuntimeError) as ctx:
            run(SETUP + 'db.execute("INSERT INTO users (name) VALUES (?)", ["secret-value"])\n'
                        'db.execute("INSERT INTO users (name) VALUES (?)", ["secret-value"])')
        msg = str(ctx.exception)
        self.assertIn("UNIQUE", msg)
        self.assertIn("INSERT INTO users", msg)
        self.assertNotIn("secret-value", msg)

    def test_sql_errors_are_catchable(self):
        self.assertEqual(out('try\n    db.query("SELECT * FROM missing_table")\ncatch e\n    print(e.message.contains("no such table"))\nend'),
                         ["true"])

    def test_syntax_error_in_sql(self):
        fails('db.execute("SELEKT 1")', "syntax error")

    def test_one_statement_per_call(self):
        fails('db.execute("SELECT 1; SELECT 2")', "one statement per call")

    def test_foreign_keys_are_enforced(self):
        fails('db.execute("CREATE TABLE p (id INTEGER PRIMARY KEY)")\ndb.execute("CREATE TABLE c (pid INTEGER REFERENCES p(id))")\n'
              'db.execute("INSERT INTO c VALUES (?)", [5])', "FOREIGN KEY")

    def test_bad_parameters(self):
        fails('db.execute("INSERT INTO users (name) VALUES (?)", [[1]])', "parameter 1 has a type")
        fails('db.execute("INSERT INTO users (name, age) VALUES (?, ?)", ["a", 10000000000000000000])', "too large")
        fails('db.execute("INSERT INTO users (name) VALUES (?)", [])', "")      # wrong number of bindings
        fails('let p: any = {"a": 1}\ndb.execute("SELECT ?", p)', "parameters must be a list")
        fails('db.execute("   ")', "non-empty")

    def test_duplicate_column_names_and_blobs(self):
        fails('db.query("SELECT 1 AS a, 2 AS a")', "two columns named 'a'")
        fails('db.query("SELECT x\'0102\' AS data")', "BLOB")

    def test_closed_database(self):
        fails('db.close()\ndb.query("SELECT 1")', "database is closed")
        self.assertEqual(out('db.close()\ndb.close()\nprint("ok")'), ["ok"])


class TestOpening(unittest.TestCase):
    def test_engines_and_url_errors(self):
        self.assertEqual(run('use sql\nprint(sql.engines())').strip(), '["sqlite"]')
        fails('use sql\nsql.open("postgres:db")', "unknown engine 'postgres'", setup=False)
        fails('use sql\nsql.open("calyre:data")', "planned but not implemented", setup=False)
        fails('use sql\nsql.open("nocolon")', "expected a URL", setup=False)
        fails('use sql\nsql.open("sqlite:")', "needs a file name", setup=False)

    def test_file_database_persists_between_opens(self):
        with project({}) as d:
            f = os.path.join(d, "app.db").replace("\\", "/")
            run(f'use sql\nlet db = sql.open("sqlite:{f}")\ndb.execute("CREATE TABLE t (v INTEGER)")\n'
                f'db.execute("INSERT INTO t VALUES (?)", [42])\ndb.close()')
            self.assertEqual(run(f'use sql\nlet db = sql.open("sqlite:{f}")\nprint((db.query_one("SELECT v FROM t") ?? {{}})["v"])\ndb.close()').strip(), "42")

    def test_uncommitted_work_is_lost_on_close(self):
        with project({}) as d:
            f = os.path.join(d, "app.db").replace("\\", "/")
            run(f'use sql\nlet db = sql.open("sqlite:{f}")\ndb.execute("CREATE TABLE t (v INTEGER)")\ndb.begin()\n'
                f'db.execute("INSERT INTO t VALUES (1)")\ndb.close()')
            self.assertEqual(run(
                f'use sql\nlet db = sql.open("sqlite:{f}")\n'
                'print(len(db.query("SELECT * FROM t")))\ndb.close()'
            ).strip(), "0")

    def test_unopenable_files_are_clear_errors(self):
        with project({"junk.db": "this is not a database file at all, just text\n" * 20}) as d:
            fails(f'use sql\nsql.open("sqlite:{os.path.join(d, "junk.db").replace(chr(92), "/")}")', "cannot open", setup=False)
            fails(f'use sql\nsql.open("sqlite:{d.replace(chr(92), "/")}/no/such/dir/x.db")', "cannot open", setup=False)


class TestTyping(unittest.TestCase):
    def test_result_types(self):
        self.assertEqual(errors(SETUP + 'let n: int = db.execute("DELETE FROM users")\n'
                                        'let rows: list<map<str, any>> = db.query("SELECT 1")\n'
                                        'let one: map<str, any>? = db.query_one("SELECT 1")'), [])
        self.assertTrue(errors(SETUP + 'let s: str = db.execute("x")'))
        self.assertTrue(errors(SETUP + 'let one: map<str, any> = db.query_one("SELECT 1")'))   # optional

    def test_argument_checking(self):
        self.assertTrue(errors(SETUP + 'db.query(5)'))
        self.assertTrue(errors(SETUP + 'db.execute("x", "not a list")'))
        e = errors(SETUP + 'db.query()')
        self.assertIn("expects 1 to 2 argument(s), got 0", e[0])
        self.assertTrue(errors(SETUP + 'db.query("a", [1], [2])'))
        self.assertTrue(errors(SETUP + 'db.commit(1)'))

    def test_mixed_parameter_lists_are_fine(self):
        self.assertEqual(errors(SETUP + 'db.execute("x", ["a", 1, 2.5, true, none])'), [])

    def test_database_can_be_named_in_signatures(self):
        src = ('use sql\nfunc count(db: sql.Database) -> int\n    return len(db.query("SELECT 1"))\nend\n'
               'let db = sql.open("sqlite::memory:")\nlet n: int = count(db)')
        self.assertEqual(errors(src), [])
        self.assertTrue(errors(src + '\ncount(5)'))
        self.assertEqual(run(src + '\nprint(n)').strip(), "1")

    def test_database_cannot_be_constructed_or_given_fields(self):
        self.assertTrue(any("cannot be built directly" in m for m in errors('use sql\nlet d = sql.Database()')))
        self.assertTrue(errors(SETUP + 'print(db.name)'))

    def test_unknown_method_suggests(self):
        d = analyze(SETUP + 'db.exec("x")')[0][0]
        self.assertIn("execute", d.hint)
        self.assertIn("sql.Database has no method", d.message)

    def test_row_values_are_dynamic(self):
        self.assertEqual(errors(SETUP + 'let r = db.query_one("SELECT 1 AS a") ?? {}\nlet n: int = r["a"]\nlet s: str = r["a"]'), [])

    def test_printing_a_database(self):
        self.assertIn("sql.Database sqlite::memory:", run('use sql\nprint(sql.open("sqlite::memory:"))'))


if __name__ == "__main__":
    unittest.main()
