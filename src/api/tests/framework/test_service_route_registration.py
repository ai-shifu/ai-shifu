"""Service route groups are registered explicitly, not by the plugin scan."""

import ast
from pathlib import Path

import pytest
from flask import Flask

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


def test_service_routes_are_registered_before_plugins_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Plugins may wrap service view functions while they load, so the service
    # route groups must already be registered by then.
    import app as app_module
    from flaskr import route
    from flaskr.framework.plugin import load_plugin

    calls: list[str] = []
    monkeypatch.setattr(
        load_plugin,
        "load_plugins_from_dir",
        lambda _app, plugins_dir, _plugin_manager=None: calls.append(
            f"load {Path(plugins_dir).name}"
        ),
    )
    monkeypatch.setattr(
        route, "register_service_routes", lambda _app: calls.append("routes")
    )

    app_module.load_services_and_plugins(Flask(__name__), plugin_manager=object())

    assert calls == ["load service", "routes", "load plugins"]
