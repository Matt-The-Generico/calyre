"""
Which names a module exports.

* Explicit mode: if a module declares anything with `pub`, exactly the `pub`
  declarations are exported.
* Legacy mode (no `pub` anywhere): every top-level name that does not start with
  `_` is exported — the rule of earlier versions, kept so existing libraries
  keep working unchanged. Migration = add `pub` to what you want to export.

Shared by the type checker and the interpreter so they cannot disagree.
"""

from . import ast_nodes as A


def exported_names(program, defined):
    """Return (exported_names, explicit_mode). `defined` = names bound at module top level."""
    pub = {s.name for s in program.statements
           if isinstance(s, (A.FuncDecl, A.StructDecl, A.LetStmt)) and s.public}
    if pub:
        return {n for n in defined if n in pub}, True
    return {n for n in defined if not n.startswith("_")}, False
