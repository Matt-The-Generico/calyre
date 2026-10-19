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
import tomllib


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
