from __future__ import annotations

import ast
from pathlib import Path


_ROUTES_PATH = Path(__file__).resolve().parents[3] / "flaskr/service/learn/routes.py"


def test_every_shifu_learning_route_resolves_public_identifier_first() -> None:
    module = ast.parse(_ROUTES_PATH.read_text(encoding="utf-8"))
    register = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_learn_routes"
    )

    shifu_route_names = []
    for node in register.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        route_decorators = [
            decorator
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
        ]
        if not route_decorators:
            continue
        if not any(
            "/shifu/" in ast.unparse(decorator.args[0])
            for decorator in route_decorators
            if decorator.args
        ):
            continue

        shifu_route_names.append(node.name)
        assert any(
            isinstance(decorator, ast.Name)
            and decorator.id == "_with_resolved_shifu_identifier"
            for decorator in node.decorator_list
        ), f"{node.name} must resolve the public identifier before handling"

    assert len(shifu_route_names) == 13
