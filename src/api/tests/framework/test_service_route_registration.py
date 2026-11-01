"""Service route groups are registered explicitly, not by the plugin scan."""

import ast
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2] / "flaskr" / "service"


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ""


def test_service_modules_do_not_use_inject() -> None:
    # The startup scan imports every service module and runs @inject functions in
    # directory order, swallowing errors per package; route groups belong in
    # flaskr.route.register_route instead.
    offenders = [
        f"{path.relative_to(SERVICE_ROOT)}:{node.lineno}"
        for path in sorted(SERVICE_ROOT.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_decorator_name(d) == "inject" for d in node.decorator_list)
    ]
    assert offenders == []
