"""bootstrap is pure INFRA: no Flask, no domain, no storage (DB creation stays lazy)."""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "bootstrap.py"
FORBIDDEN_PREFIXES = ("flask", "app.auth", "app.api", "app.datasets", "app.targets",
                      "app.analysis", "app.audit", "app.infra.storage")


def _imported_names(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_bootstrap_imports_no_flask_domain_or_storage():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    offenders = [n for n in _imported_names(tree)
                 if any(n == p or n.startswith(p + ".") for p in FORBIDDEN_PREFIXES)]
    assert offenders == [], f"bootstrap must stay an INFRA leaf; forbidden imports: {offenders}"
