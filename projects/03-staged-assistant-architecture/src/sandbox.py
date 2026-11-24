"""Stage 2: runs analysis code written by a model, with prior validation.

WARNING: this is a teaching sketch, NOT a security boundary. It blocks the obvious (imports, private
attribute access, file writes, dangerous functions) and exposes only copies of the Gold data. It does
not limit time or memory. In production, run the generated code in an isolated process or container,
with limits.
"""
import ast
import builtins
from typing import Any

BLOCKED_NAMES = {"open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr",
                 "globals", "locals", "vars", "input", "breakpoint", "help", "dir", "type"}
BLOCKED_ATTRS = {"read_csv", "read_excel", "read_parquet", "read_pickle", "read_json", "read_sql",
                 "eval", "system", "popen"}
ALLOWED_TO = {"to_dict", "to_string", "to_list", "to_numpy", "to_frame"}
SAFE_BUILTINS = {n: getattr(builtins, n)
                 for n in ("len", "min", "max", "sum", "round", "sorted", "abs", "range", "list",
                           "dict", "enumerate", "zip", "float", "int", "str", "bool", "set", "tuple")}


class SandboxError(Exception):
    """Raised when generated code is rejected by validation or fails while running."""


def validate(code: str) -> ast.Module:
    """Parses `code` and rejects imports, global scope, blocked names and blocked attributes."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SandboxError(f"invalid code: {e.msg}") from e
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
            raise SandboxError("imports and global scope are not allowed")
        if isinstance(node, ast.Name) and (node.id in BLOCKED_NAMES or node.id.startswith("__")):
            raise SandboxError(f"blocked name: {node.id}")
        if isinstance(node, ast.Attribute):
            a = node.attr
            if a.startswith("_") or a in BLOCKED_ATTRS or (a.startswith("to_") and a not in ALLOWED_TO):
                raise SandboxError(f"blocked attribute: {a}")
    return tree


def run_sandboxed(code: str, tables: dict[str, Any]) -> Any:
    """Runs `code` with `tables` (copies of the Gold DataFrames) and returns the `result` variable."""
    tree = validate(code)
    scope: dict[str, Any] = dict(tables)
    scope["__builtins__"] = SAFE_BUILTINS
    try:
        exec(compile(tree, "<generated>", "exec"), scope)
    except Exception as e:
        raise SandboxError(f"execution failed: {type(e).__name__}: {e}") from e
    if "result" not in scope:
        raise SandboxError("the code did not define the 'result' variable")
    return scope["result"]
