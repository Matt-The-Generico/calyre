"""
Module resolution, shared by the type checker and the interpreter so they can
never disagree about which file `use name` refers to.

Order for `use a.b`:
  1. relative to the importing file's folder:   <dir>/a/b.cly
  2. a dependency declared in the nearest calyre.toml (walking up from the
     importing file). For `use dep` the entry file is <dep path>/dep.cly;
     for `use dep.sub` it is <dep path>/sub.cly.
Local files win, so a project can always shadow a dependency deliberately.
"""

import os
import re
import tomllib

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:/")


def find_manifest(start_dir):
    d = os.path.abspath(start_dir)
    while True:
        candidate = os.path.join(d, "calyre.toml")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_dependencies(manifest_path):
    try:
        with open(manifest_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    deps = data.get("dependencies", {})
    return deps if isinstance(deps, dict) else {}


def path_candidate(spec, base_dir):
    """Where `use "spec"` points: `\\` counts as `/` on every platform, `.cly` is added when missing,
    relative paths are relative to the importing file's folder (never the working directory)."""
    p = spec.replace("\\", "/")
    if not p.endswith(".cly"):
        if "." in p.rsplit("/", 1)[-1] and not p.endswith("."):
            raise ValueError(f"only .cly files can be imported, not '{spec}'")
        p += ".cly"
    if p.startswith("/") or _WINDOWS_DRIVE.match(p):
        return os.path.normpath(p) if os.path.isabs(p) else p      # a drive path is only absolute on Windows
    return os.path.normpath(os.path.join(base_dir, p))


def resolve_import(spec, base_dir, by_path):
    """Canonical (symlink-free) file for a `use`, or None. Name imports and path imports of the
    same file yield the same string, so a module is loaded once however it is imported."""
    if by_path:
        try:
            cand = path_candidate(spec, base_dir)
        except ValueError:
            return None
        found = cand if os.path.isfile(cand) else None
    else:
        found = resolve(spec, base_dir)
    return os.path.realpath(found) if found else None


def describe_lookup(spec, base_dir, by_path):
    """Human text for 'where did the resolver look' (used in error hints)."""
    if by_path:
        try:
            return (f"looked for {path_candidate(spec, base_dir)} "
                    f"(paths are relative to the file that contains the `use`, not to the current folder)")
        except ValueError as e:
            return str(e)
    first = spec.split(".")[0]
    return (f"looked for {os.path.join(base_dir, *spec.split('.'))}.cly and for a dependency "
            f"named '{first}' in calyre.toml")


def resolve(path, base_dir):
    """Return the absolute .cly file for `use path`, or None."""
    parts = path.split(".")
    local = os.path.normpath(os.path.join(base_dir, *parts) + ".cly")
    if os.path.isfile(local):
        return local
    manifest = find_manifest(base_dir)
    if manifest:
        spec = load_dependencies(manifest).get(parts[0])
        if isinstance(spec, dict) and "path" in spec:
            root = os.path.normpath(os.path.join(os.path.dirname(manifest), spec["path"]))
            rest = parts[1:] or [parts[0]]
            candidate = os.path.normpath(os.path.join(root, *rest) + ".cly")
            if os.path.isfile(candidate):
                return candidate
    return None


def local_candidates(base_dir):
    """Module names a user could mean (for 'did you mean' hints)."""
    names = []
    if os.path.isdir(base_dir):
        names += [f[:-4] for f in os.listdir(base_dir) if f.endswith(".cly")]
    manifest = find_manifest(base_dir)
    if manifest:
        names += list(load_dependencies(manifest))
    return names
