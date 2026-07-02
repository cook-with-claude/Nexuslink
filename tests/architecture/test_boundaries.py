"""AST architecture boundary checks (ADR 0001, Part B).

Enforces the invariants import-linter cannot express, by parsing the source:
  * no SQL execution (.execute/.executemany/.executescript) in any app/*/routes.py
  * no commit()/rollback() in any app/*/repo.py
  * no `flask` import in any app/*/repo.py

The scanners are generic over app/*/routes.py and app/*/repo.py, so every domain
package added by the reorg (and later) is covered automatically.
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

_SQL_CALLS = {"execute", "executemany", "executescript"}
_TXN_CALLS = {"commit", "rollback"}


def _routes_files():
    # Every APPLICATION-layer module that handles requests, not just the domain
    # routes.py files: api/system.py and ui.py serve routes too and must obey the
    # same "no SQL outside repos" invariant.
    return sorted([*APP.glob("*/routes.py"), APP / "api" / "system.py", APP / "ui.py"])


def _repo_files():
    return sorted(APP.glob("*/repo.py"))


def _attr_calls(path):
    """Yield (lineno, attribute_name) for every `x.<attr>(...)` call in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            yield node.lineno, node.func.attr


def _is_flask_import(node):
    if isinstance(node, ast.Import):
        return any(n.name == "flask" or n.name.startswith("flask.") for n in node.names)
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        return mod == "flask" or mod.startswith("flask.")
    return False


def test_at_least_one_routes_and_repo_exist():
    # Guards against the scanners silently passing because a glob found nothing.
    assert _routes_files(), "expected at least one app/*/routes.py"
    assert _repo_files(), "expected at least one app/*/repo.py"


def test_no_sql_execution_in_routes():
    offenders = [
        f"{f.relative_to(APP)}:{lineno} .{attr}("
        for f in _routes_files()
        for lineno, attr in _attr_calls(f)
        if attr in _SQL_CALLS
    ]
    assert not offenders, f"SQL execution must live in repo.py, not routes: {offenders}"


def test_no_commit_or_rollback_in_repos():
    offenders = [
        f"{f.relative_to(APP)}:{lineno} .{attr}("
        for f in _repo_files()
        for lineno, attr in _attr_calls(f)
        if attr in _TXN_CALLS
    ]
    assert not offenders, f"repos never commit/rollback (the route owns the txn): {offenders}"


def test_no_flask_import_in_repos():
    offenders = []
    for f in _repo_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if _is_flask_import(node):
                offenders.append(f"{f.relative_to(APP)}:{node.lineno}")
    assert not offenders, f"repos must not import flask: {offenders}"
