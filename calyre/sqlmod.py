"""
`sql`: one database API for Calyre, with SQLite as the first engine.

    use sql
    let db = sql.open("sqlite:app.db")            # or "sqlite::memory:"
    db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    db.execute("INSERT INTO users (name) VALUES (?)", ["Ana"])
    for row in db.query("SELECT id, name FROM users WHERE name = ?", ["Ana"])
        print(row["name"])
    end

Design (see docs/SPEC.md):
* The engine is chosen by the URL scheme. Only `sqlite:` exists; `calyre:` is reserved for a future
  native engine and is reported as "not implemented yet". Code written against `Database` will not
  have to change when it arrives.
* SQLite is a database that *implements* SQL; this module is an interface to it, not a SQL engine.
* Values are only ever passed as `?` parameters. The linter warns about queries built by joining text.
* Rows are `map<str, any>`; NULL is `none`; BLOB values are not supported yet (an error, never silent).
* Autocommit unless you call begin(); begin / commit / rollback are explicit.
* Foreign keys are enforced (PRAGMA foreign_keys = ON).
"""

import sqlite3

from .methods import _err
from .types import ANY, NONE_T

ENGINES = ("sqlite",)
RESERVED_ENGINES = ("calyre",)
ROWS = ("list", ("map", "str", ANY))
OPT_ROW = ("optional", ("map", "str", ANY))


def _shorten(query, n=80):
    q = " ".join(query.split())
    return q if len(q) <= n else q[:n - 3] + "..."


class Database:
    """A connection. Created by sql.open(); not constructible from Calyre code."""

    native_type = "sql.Database"

    def __init__(self, url, conn):
        self.url, self.conn, self.closed = url, conn, False

    def __repr__(self):
        return f"<sql.Database {self.url}{' (closed)' if self.closed else ''}>"

    def _live(self, op):
        if self.closed:
            raise _err(f"sql: cannot {op}: the database is closed")
        return self.conn

    # ---- parameters and rows
    @staticmethod
    def _params(params):
        if params is None:
            return ()
        if not isinstance(params, list):
            raise _err("sql: parameters must be a list, e.g. [name, age]")
        out = []
        for i, p in enumerate(params, 1):
            if p is None or isinstance(p, (str, float)):
                out.append(p)
            elif isinstance(p, bool):
                out.append(int(p))
            elif isinstance(p, int):
                if not -(2 ** 63) <= p < 2 ** 63:
                    raise _err(f"sql: parameter {i} is too large for the database (64-bit integers only)")
                out.append(p)
            else:
                raise _err(f"sql: parameter {i} has a type the database cannot store "
                           f"(use int, float, str, bool or none)")
        return tuple(out)

    def _run(self, query, params, op):
        conn = self._live(op)
        if not isinstance(query, str) or not query.strip():
            raise _err(f"sql: {op}: the query must be a non-empty text")
        try:
            return conn.execute(query, self._params(params))
        except sqlite3.Error as e:
            hint = ""
            if "You can only execute one statement" in str(e):
                hint = " (run one statement per call)"
            raise _err(f"sql: {e}{hint} - in: {_shorten(query)}") from e
        except OverflowError as e:
            raise _err(f"sql: a value is too large for the database - in: {_shorten(query)}") from e

    @staticmethod
    def _rows(cursor):
        if cursor.description is None:
            return []
        names = [d[0] for d in cursor.description]
        dup = next((n for n in names if names.count(n) > 1), None)
        if dup is not None:
            raise _err(f"sql: the result has two columns named '{dup}'; rename one with AS")
        rows = []
        for raw in cursor.fetchall():
            row = {}
            for name, value in zip(names, raw):
                if isinstance(value, (bytes, bytearray, memoryview)):
                    raise _err(f"sql: column '{name}' holds a BLOB, which Calyre does not support yet")
                row[name] = value
            rows.append(row)
        return rows

    # ---- methods
    def execute(self, query, params=None):
        cur = self._run(query, params, "execute")
        return max(cur.rowcount, 0)

    def query(self, query, params=None):
        return self._rows(self._run(query, params, "query"))

    def query_one(self, query, params=None):
        rows = self.query(query, params)
        return rows[0] if rows else None

    def last_insert_id(self):
        return self._live("read the last insert id").execute("SELECT last_insert_rowid()").fetchone()[0]

    def begin(self):
        self._run("BEGIN", None, "begin")

    def commit(self):
        self._run("COMMIT", None, "commit")

    def rollback(self):
        self._run("ROLLBACK", None, "rollback")

    def in_transaction(self):
        return self._live("check the transaction").in_transaction

    def close(self):
        if not self.closed:
            self.conn.close()
            self.closed = True


class NativeTypeMarker:
    """`sql.Database` as a name: usable in type annotations, not as a constructor."""

    native_type_name = "sql.Database"

    def __repr__(self):
        return "<native type sql.Database>"


def open_database(url):
    if not isinstance(url, str) or ":" not in url:
        raise _err("sql.open: expected a URL like \"sqlite:app.db\" or \"sqlite::memory:\"")
    engine, _, target = url.partition(":")
    if engine in RESERVED_ENGINES:
        raise _err(f"sql.open: the '{engine}' engine is planned but not implemented yet "
                   f"(available: {', '.join(ENGINES)})")
    if engine not in ENGINES:
        raise _err(f"sql.open: unknown engine '{engine}' (available: {', '.join(ENGINES)})")
    if target == "":
        raise _err("sql.open: the URL needs a file name or ':memory:', e.g. \"sqlite:app.db\"")
    conn = None
    try:
        conn = sqlite3.connect(target, isolation_level=None)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
    except sqlite3.Error as e:
        if conn is not None:
            conn.close()
        raise _err(f"sql.open: cannot open '{target}': {e}") from e
    return Database(url, conn)

# (params, return type, implementation, minimum number of arguments)
DATABASE_METHODS = {
    "execute": (["str", ("list", ANY)], "int", Database.execute, 1),
    "query": (["str", ("list", ANY)], ROWS, Database.query, 1),
    "query_one": (["str", ("list", ANY)], OPT_ROW, Database.query_one, 1),
    "last_insert_id": ([], "int", Database.last_insert_id, 0),
    "begin": ([], NONE_T, Database.begin, 0),
    "commit": ([], NONE_T, Database.commit, 0),
    "rollback": ([], NONE_T, Database.rollback, 0),
    "in_transaction": ([], "bool", Database.in_transaction, 0),
    "close": ([], NONE_T, Database.close, 0),
}

NATIVE_METHODS = {"sql.Database": DATABASE_METHODS}
