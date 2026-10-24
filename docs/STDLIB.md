# Standard library reference

Everything here is covered by tests: a test fails if a function, method or builtin exists but is missing from this page, and every
`calyre` example is run by the test suite. Signatures use Calyre types; `any` means the function deliberately works on dynamic data.

Two ways to call things:

* **Methods** of the built-in types (`list`, `map`, `str`): `items.append(x)`, `name.upper()`. This is the one way to operate on a value.
* **Modules** (`use math`): functions that are not "a method of a value". Import one with `use math`, `use math as m` or `use sqrt, floor from math`.

## Builtins (always available)

| Call | Result |
|------|--------|
| `print(a, b, ...)` | prints its arguments separated by spaces; returns `none` |
| `str(x)` | the text form of any value |
| `int(x)` | an `int` from a number or a text (error if the text is not a whole number) |
| `float(x)` | a `float` from a number or a text |
| `len(x)` | length of a text, list or map |
| `range(n)`, `range(a, b)`, `range(a, b, step)` | a `list<int>` |
| `input(prompt)` | reads a line of text (`prompt` optional) |
| `input_int(prompt)`, `input_float(prompt)`, `input_bool(prompt)` | reads and converts; invalid input is a catchable error |
| `error(message)` | raises a catchable runtime error |

```calyre run
for n in range(1, 4)
    print(str(n * n) + "!")
end
print(len("héllo"), len([1, 2]), len({"a": 1}))
print(int("42") + 1, float("2.5") * 2.0)
```

```output
1!
4!
9!
5 2 1
43 5.0
```

## Methods of `list<T>`

Lists are mutable and shared by reference; `copy()` is shallow.

| Method | Result |
|--------|--------|
| `xs.append(x)` | adds `x` at the end |
| `xs.insert(i, x)` | inserts before position `i` (`0..len`); error if out of range |
| `xs.pop()` | removes and returns the last element; error if empty |
| `xs.remove_at(i)` | removes and returns the element at `i` (negative counts from the end) |
| `xs.remove(x)` | removes the first element equal to `x`; `true` if one was found |
| `xs.contains(x)` | `bool` |
| `xs.index_of(x)` | `int?`: position of the first match or `none` |
| `xs.clear()` | empties the list |
| `xs.copy()` | a shallow copy, `list<T>` |
| `xs.extend(other)` | appends every element of another `list<T>` |
| `xs.reverse()` | reverses in place |
| `xs.sort()` | sorts in place (elements must be `int`, `float` or `str`) |
| `xs.slice(a, b)` | a new list with positions `a` up to (not including) `b`; out-of-range ends are clamped |

Use `len(xs)` for the length.

```calyre run
let xs = [3, 1, 2]
xs.append(5)
xs.insert(0, 9)
print(xs)
print(xs.pop(), xs.remove(1), xs.remove(42), xs.contains(2))
xs.sort()
print(xs, xs.index_of(3) ?? -1, xs.slice(1, 3))
let ys = xs.copy()
ys.reverse()
print(xs, ys)
```

```output
[9, 3, 1, 2, 5]
5 true false true
[2, 3, 9] 1 [3, 9]
[2, 3, 9] [9, 3, 2]
```

## Methods of `map<K, V>`

| Method | Result |
|--------|--------|
| `m.has(k)` | `bool` |
| `m.get(k)` | `V?`: the value, or `none` if the key is missing |
| `m.remove(k)` | removes the key; `true` if it existed |
| `m.keys()` | `list<K>` in insertion order |
| `m.values()` | `list<V>` |
| `m.clear()` | empties the map |
| `m.copy()` | a shallow copy |

`m[k]` reads a key (error if missing), `m[k] = v` sets it, `for k in m` visits the keys.

```calyre run
let stock = {"apples": 3, "pears": 0}
stock["plums"] = 7
print(stock.keys(), stock.values())
print(stock.has("pears"), stock.get("kiwi") ?? 0, stock.remove("pears"), len(stock))
```

```output
["apples", "pears", "plums"] [3, 0, 7]
true 0 true 2
```

## Methods of `str`

Texts are immutable Unicode; every method returns a new text. Positions count characters, not bytes.

| Method | Result |
|--------|--------|
| `s.upper()`, `s.lower()` | case conversion (`"straße".upper()` is `"STRASSE"`) |
| `s.trim()` | removes whitespace at both ends |
| `s.contains(t)`, `s.starts_with(t)`, `s.ends_with(t)` | `bool` |
| `s.replace(old, new)` | replaces every occurrence (`old` must not be empty) |
| `s.split(sep)` | `list<str>` (`sep` must not be empty) |
| `s.index_of(t)` | `int?` position of the first match or `none` |
| `s.slice(a, b)` | the characters from `a` up to (not including) `b` |
| `s.repeat(n)` | the text `n` times (`n >= 0`) |

```calyre run
let line = "  name=Ana;age=30 "
let parts = line.trim().split(";")
print(parts)
print(parts[0].replace("name=", "").upper(), parts[1].index_of("=") ?? -1)
print("ab".repeat(3), "日本語".slice(1, 3), "x,y".contains(","))
```

```output
["name=Ana", "age=30"]
ANA 3
ababab 本語 true
```

The older `text` module (`text.upper(s)`, ...) still works for compatibility and is frozen: no new functions will be added to it.

## `math`

| Function | Notes |
|----------|-------|
| `math.sqrt(x)` | `float`; error for negative numbers |
| `math.floor(x)`, `math.ceil(x)`, `math.round(x)` | `int` |
| `math.abs(x)` | same kind as `x` (`int` → `int`, `float` → `float`) |
| `math.min(a, b)`, `math.max(a, b)` | both arguments must be the same kind |
| `math.pow(x, y)` | always `float`; error for `0` to a negative power or a negative base with a fractional exponent |
| `math.floor_div(a, b)` | integer division of two `int`s |
| `math.pi`, `math.e` | constants |

```calyre run
use math
let smallest: int = math.min(4, 9)
let distance: float = math.sqrt(math.pow(3, 2) + math.pow(4, 2))
print(smallest, distance, math.floor_div(7, 2), math.abs(-2.5))
```

```output
4 5.0 3 2.5
```

## `random`

`random.int(a, b)` (both ends included), `random.float(a, b)`, `random.choice(items)` (returns an element of the list; error if empty).

```calyre
use random
let roll: int = random.int(1, 6)
let pick: str = random.choice(["red", "green"])
```

## `time`

`time.now()` returns seconds since 1970 as a `float`; `time.sleep(seconds)` pauses.

```calyre
use time
let started: float = time.now()
time.sleep(0.01)
let elapsed: float = time.now() - started
```

## `text` (legacy)

`text.upper`, `text.lower`, `text.trim`, `text.split`, `text.join`, `text.replace`, `text.contains`, `text.starts_with`,
`text.ends_with`, `text.repeat`. Prefer the methods above, except `text.join(items, sep)`, which joins a list with a separator:

```calyre run
use text
print(text.join([1, 2, 3], "-"), text.join(["a", "b"], ""))
```

```output
1-2-3 ab
```

## `fs` (everything that touches the disk)

Text is UTF-8. Reading turns `\r\n` into `\n`; writing never converts, so a file written on Windows and on Linux is identical.
Paths may use `/` everywhere. Errors say what is wrong (`no such file or folder`, `permission denied`, `not valid UTF-8 text`, ...).

| Function | Notes |
|----------|-------|
| `fs.read(path)` | the whole file as text |
| `fs.write(path, text)` | creates or replaces the file; the folder must exist |
| `fs.append(path, text)` | adds to the end (creates the file) |
| `fs.exists(path)`, `fs.is_file(path)`, `fs.is_dir(path)` | `bool` |
| `fs.size(path)` | size in bytes |
| `fs.list_dir(path)` | sorted names |
| `fs.make_dir(path)` | creates the folder and parents (already existing is fine) |
| `fs.remove(path)` | deletes a **file** (never a folder) |
| `fs.remove_dir(path)` | deletes an **empty** folder (Calyre never deletes folders recursively) |
| `fs.rename(from, to)` | refuses to overwrite an existing destination (so it behaves the same on every OS) |

```calyre
use fs
fs.make_dir("notes")
fs.write("notes/today.txt", "buy milk\n")
fs.append("notes/today.txt", "call Ana\n")
let lines = fs.read("notes/today.txt").trim().split("\n")
fs.remove("notes/today.txt")
fs.remove_dir("notes")
```

## `path` (pure text, no disk access)

Calyre paths always use `/`; a `\` in the input is accepted and treated as `/`, so results are identical on every OS.

| Function | Example |
|----------|---------|
| `path.join(a, b)` | `"a/b"`; an absolute `b` wins |
| `path.join_all(parts)` | `join_all(["a", "b", "c.txt"])` → `"a/b/c.txt"` |
| `path.basename(p)`, `path.dirname(p)` | `"c.txt"`, `"a/b"` for `"a/b/c.txt"` |
| `path.stem(p)`, `path.extension(p)` | `"c"`, `".txt"` (dotfiles and names without a dot have no extension) |
| `path.with_extension(p, ext)` | `with_extension("a/b.txt", ".md")` → `"a/b.md"`; `ext` is `""` or like `".md"` |
| `path.normalize(p)` | collapses `.` and `..` |
| `path.parts(p)` | `["/", "a", "b"]` for `"/a/b"` |
| `path.is_absolute(p)` | `/x`, `C:/x` and `C:\x` are absolute on every OS |
| `path.relative_to(p, start)` | both absolute or both relative |
| `path.absolute(p)` | relative to the working directory, with `/` separators |

```calyre run
use path
let file = path.join("reports", "2024/summary.final.txt")
print(file, path.basename(file), path.stem(file), path.extension(file))
print(path.with_extension(file, ".md"), path.dirname(file))
print(path.normalize("a/./b/../c"), path.is_absolute("C:\\data"), path.parts("/a/b"))
```

```output
reports/2024/summary.final.txt summary.final.txt summary.final .txt
reports/2024/summary.final.md reports/2024
a/c true ["/", "a", "b"]
```

## `json`

* `json.parse(text)` → `any`: objects become `map<str, any>`, arrays `list<any>`, numbers `int` or `float`, `null` is `none`.
  Invalid JSON, `NaN`/`Infinity` and absurdly deep nesting are catchable errors that name the line and column.
* `json.stringify(value)` / `json.pretty(value)` (2-space indent) → `str`. Lists, maps with text keys, texts, numbers, bools, `none`
  and **structs** (as objects) are accepted; anything else, `NaN` and infinities are errors that name the offending part.

JSON is dynamic data, so these are the places where `any` is the honest type. Triple-quoted texts make JSON literals easy to write.

```calyre run
use json
let doc = json.parse("""{"name": "Ana", "langs": ["pt", "en"], "age": 30}""")
print(doc["name"], doc["langs"][1], doc["age"] + 1)
print(json.stringify({"ok": true, "items": [1, 2.5, none]}))

struct Point
    x: int
    y: int
end
print(json.stringify(Point(x: 1, y: 2)))
```

```output
Ana en 31
{"ok":true,"items":[1,2.5,null]}
{"x":1,"y":2}
```

## `system`

| Function | Notes |
|----------|-------|
| `system.args()` | `list<str>`: what follows the file in `calyre run file.cly a b` |
| `system.env(name)` | `str?`: the environment variable or `none` |
| `system.platform()` | `"windows"`, `"linux"` or `"macos"` |
| `system.cwd()` | the working directory, with `/` separators |
| `system.exit(code)` | ends the program now with `code` (0 to 255); `try/catch` does not intercept it |

```calyre
use system
let home: str = system.env("HOME") ?? "(unknown)"
if len(system.args()) == 0
    print("usage: calyre run tool.cly <file>")
    system.exit(2)
end
```

## `sql`

One database API with SQLite as the first engine (Python's `sqlite3`, nothing to install). `sql.open(url)` picks the engine by the
URL scheme: `sqlite:app.db`, `sqlite::memory:`. `calyre:` is reserved for a future native engine and reports "not implemented yet";
code written against `sql.Database` will not have to change. SQLite *implements* SQL; this module is an interface to it.

| Function / method | Notes |
|-------------------|-------|
| `sql.open(url)` | a `sql.Database` |
| `sql.engines()` | `["sqlite"]` |
| `db.execute(query, params)` | runs a statement, returns the number of affected rows (`params` optional) |
| `db.query(query, params)` | `list<map<str, any>>`, one map per row, column name → value (`NULL` is `none`) |
| `db.query_one(query, params)` | the first row or `none` |
| `db.last_insert_id()` | the id of the last inserted row |
| `db.begin()`, `db.commit()`, `db.rollback()` | explicit transactions (otherwise every statement commits by itself) |
| `db.in_transaction()` | `bool` |
| `db.close()` | closes the connection; uncommitted work is discarded; closing twice is fine |

Rules: values go in as `?` **parameters** (a list of int, float, str, bool or none), never joined into the query text; `calyre lint`
warns about queries built with `+` or `{interpolation}` (`sql-injection-risk`). One statement per call. Foreign keys are enforced.
`BLOB` columns are not supported yet (an error, never silent). Error messages show the query but never the parameter values.

```calyre run
use sql
let db = sql.open("sqlite::memory:")
db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")

db.begin()
try
    db.execute("INSERT INTO users (name) VALUES (?)", ["Ana"])
    db.execute("INSERT INTO users (name) VALUES (?)", ["Bruno"])
    db.commit()
catch e
    db.rollback()
    error(e.message)
end

for row in db.query("SELECT id, name FROM users ORDER BY id")
    print("{row["id"]}: {row["name"]}")
end
let missing = db.query_one("SELECT name FROM users WHERE id = ?", [99])
print(missing == none)
db.close()
```

```output
1: Ana
2: Bruno
true
```

## `python` (restricted bridge)

`python.call("math", "sqrt", 16.0)`: see the language reference, section 10. Only a short list of standard Python modules is allowed.

## What is not here yet

`datetime`, `regex`, `process`, `http`, `log` and a `collections` module are planned (see [ROADMAP.md](ROADMAP.md)).
`http` will use the Python standard library, with timeouts and no silent network errors, and will work with `json`.
