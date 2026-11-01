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


def test_service_routes_exist_before_plugins_load(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Plugins may wrap service view functions while they load, so the service
    # route groups must already be registered by then.
    import app as app_module
    from flaskr.framework.plugin import load_plugin

    seen: dict[str, bool] = {}
    original = load_plugin.load_plugins_from_dir

    def _record(
        flask_app: Flask, plugins_dir: str, plugin_manager: object = None
    ) -> object:
        if plugin_manager is not None:
            seen["shifu"] = "get_shifu_list_api" in flask_app.view_functions
            seen["learn"] = any(
                rule.rule.startswith("/api/learn")
                for rule in flask_app.url_map.iter_rules()
            )
        return original(flask_app, plugins_dir, plugin_manager)

    monkeypatch.setattr(load_plugin, "load_plugins_from_dir", _record)
    # create_app caches its app; build a fresh one in the fixture's environment.
    monkeypatch.setattr(app_module._application_state, "app", None)
    assert app_module.create_app() is not app
    assert seen == {"shifu": True, "learn": True}
