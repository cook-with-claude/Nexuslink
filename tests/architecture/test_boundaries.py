"""AST architecture boundary checks (ADR 0001, Part B).

Enforces the invariants import-linter cannot express, by parsing the source:
  * no SQL execution (.execute/.executemany/.executescript) in any app/*/routes.py
  * no commit()/rollback() in any app/*/repo.py
  * no `flask` import in any app/*/repo.py
  * tools reach frozen Phase 1 only through app.infra.phase1

The scanners are generic over app/*/routes.py and app/*/repo.py, so every domain
package added by the reorg (and later) is covered automatically.
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
TOOLS = APP.parent / "tools"
_IDENTITY = APP / "api" / "identity.py"

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


def test_tools_reach_phase1_only_through_infra_seam():
    offenders = []
    for path in sorted(TOOLS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in {"detection", "loader"} or module.startswith("phase1_cdr"):
                    offenders.append(f"{path.name}:{node.lineno} {module}")
            elif isinstance(node, ast.Import):
                for name in node.names:
                    if name.name in {"detection", "loader"} or name.name.startswith("phase1_cdr"):
                        offenders.append(f"{path.name}:{node.lineno} {name.name}")
    assert not offenders, f"tools must reach Phase 1 via app.infra.phase1: {offenders}"


def test_identity_context_is_data_free():
    """The SUPPORT per-session identity context (app/api/identity.py) must never
    touch the DB: no SQL execution, and no app.* import at all (it is a leaf that
    reads only flask.session). DB-backed identity/role accessors are authz-tier
    (arrive with multi-account), not here -- a SUPPORT DB read inverts the layer
    rule (ADR 0001; ADR 0003; spec Codex #3)."""
    tree = ast.parse(_IDENTITY.read_text(encoding="utf-8"))

    sql = [n.lineno for n in ast.walk(tree)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr in _SQL_CALLS]
    assert not sql, f"identity.py must issue no SQL: lines {sql}"

    app_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "app":
            app_imports.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            app_imports += [(node.lineno, n.name) for n in node.names
                            if n.name.split(".")[0] == "app"]
    assert not app_imports, f"identity.py must not import app.* (data-free leaf): {app_imports}"
