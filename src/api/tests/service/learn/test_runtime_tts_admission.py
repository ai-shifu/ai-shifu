from __future__ import annotations

import ast
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[3]
_ROUTES_PATH = _API_ROOT / "flaskr/service/learn/routes.py"
_MODULE = ast.parse(_ROUTES_PATH.read_text(encoding="utf-8"))


def _find_register_learn_routes() -> ast.FunctionDef:
    for node in _MODULE.body:
        if isinstance(node, ast.FunctionDef) and node.name == "register_learn_routes":
            return node
    raise AssertionError("register_learn_routes not found")


def _find_nested_route(name: str) -> ast.FunctionDef:
    register_fn = _find_register_learn_routes()
    for node in register_fn.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found inside register_learn_routes")


def _collect_called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _find_call_by_name(node: ast.AST, name: str) -> ast.Call:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name) and func.id == name:
            return child
        if isinstance(func, ast.Attribute) and func.attr == name:
            return child
    raise AssertionError(f"{name} call not found")


def test_generated_block_tts_route_keeps_admission_but_skips_runtime_slot() -> None:
    route_fn = _find_nested_route("synthesize_generated_block_audio_api")
    called_names = _collect_called_names(route_fn)

    assert "_admit_creator_usage_for_shifu" in called_names
    assert "reserve_creator_runtime_slot" not in called_names
    assert "_stream_sse_response" in called_names
    assert "stream_generated_block_audio" in called_names


def test_preview_tts_route_keeps_admission_but_skips_runtime_slot() -> None:
    route_fn = _find_nested_route("synthesize_preview_tts_audio_api")
    called_names = _collect_called_names(route_fn)

    assert "_admit_creator_usage_for_shifu" in called_names
    assert "reserve_creator_runtime_slot" not in called_names
    assert "_stream_sse_response" in called_names
    assert "stream_preview_tts_audio" in called_names


def test_run_route_passes_admission_payload_to_run_script() -> None:
    route_fn = _find_nested_route("run_outline_item_api")
    called_names = _collect_called_names(route_fn)
    run_script_call = _find_call_by_name(route_fn, "run_script")

    assert "_admit_creator_usage_for_shifu" in called_names
    assert "reserve_creator_runtime_slot" not in called_names
    assert "_stream_passthrough_response" in called_names
    assert "run_script" in called_names
    assert any(
        keyword.arg == "runtime_admission_payload"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "admission_payload"
        for keyword in run_script_call.keywords
    )
