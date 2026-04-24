from __future__ import annotations

import ast
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = ModuleType("litellm")
    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.completion = lambda *args, **kwargs: iter([])
    sys.modules["litellm"] = litellm_stub


def _install_openai_responses_stub() -> None:
    if "openai.types.responses" in sys.modules:
        return

    responses_pkg = ModuleType("openai.types.responses")
    responses_pkg.__path__ = []
    response_mod = ModuleType("openai.types.responses.response")
    response_create_mod = ModuleType("openai.types.responses.response_create_params")
    response_function_mod = ModuleType(
        "openai.types.responses.response_function_tool_call"
    )
    response_text_mod = ModuleType("openai.types.responses.response_text_config_param")

    for name in [
        "IncompleteDetails",
        "Response",
        "ResponseOutputItem",
        "Tool",
        "ToolChoice",
    ]:
        setattr(response_mod, name, type(name, (), {}))

    for name in [
        "Reasoning",
        "ResponseIncludable",
        "ResponseInputParam",
        "ToolChoice",
        "ToolParam",
        "Text",
    ]:
        setattr(response_create_mod, name, type(name, (), {}))

    response_function_tool_call = type("ResponseFunctionToolCall", (), {})
    response_text_config = type("ResponseTextConfigParam", (), {})
    setattr(
        response_function_mod,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )
    setattr(
        response_text_mod,
        "ResponseTextConfigParam",
        response_text_config,
    )
    setattr(
        responses_pkg,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )

    sys.modules["openai.types.responses"] = responses_pkg
    sys.modules["openai.types.responses.response"] = response_mod
    sys.modules["openai.types.responses.response_create_params"] = response_create_mod
    sys.modules["openai.types.responses.response_function_tool_call"] = (
        response_function_mod
    )
    sys.modules["openai.types.responses.response_text_config_param"] = response_text_mod


_install_litellm_stub()
_install_openai_responses_stub()

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


def _mock_user(monkeypatch, user_id: str, *, is_creator: bool = False):
    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_creator=is_creator,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )
    return dummy_user


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
    assert all(
        keyword.arg != "runtime_admission_payload"
        for keyword in run_script_call.keywords
    )


def test_preview_route_skips_admission_and_runtime_slot_for_builtin_demo(
    monkeypatch, test_client, app
):
    _mock_user(monkeypatch, "user-preview")
    monkeypatch.setattr(
        "flaskr.service.learn.routes.is_builtin_demo_shifu",
        lambda _app, shifu_bid: shifu_bid == "builtin-demo-1",
    )
    monkeypatch.setattr(
        "flaskr.service.learn.routes.admit_creator_usage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("builtin demo should skip creator admission")
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.learn.context_v2.RunScriptPreviewContextV2.stream_preview",
        lambda self, **_kwargs: iter(
            [
                {
                    "type": "element",
                    "event_type": "element",
                    "content": "ok",
                }
            ]
        ),
    )

    resp = test_client.post(
        "/api/learn/shifu/builtin-demo-1/preview/outline-1",
        json={"content": "hello", "block_index": 0},
        headers={"Token": "test-token"},
    )
    body = resp.data.decode("utf-8")

    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert '"type": "element"' in body
    assert '"content": "ok"' in body


def test_run_route_skips_runtime_admission_payload_for_builtin_demo(
    monkeypatch, test_client
):
    _mock_user(monkeypatch, "user-run")

    monkeypatch.setattr(
        "flaskr.service.learn.routes.is_builtin_demo_shifu",
        lambda _app, shifu_bid: shifu_bid == "builtin-demo-1",
    )
    monkeypatch.setattr(
        "flaskr.service.learn.routes.admit_creator_usage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("builtin demo should skip creator admission")
        ),
    )

    def _fake_run_script(*_args, **kwargs):
        assert "runtime_admission_payload" not in kwargs
        yield 'data: {"type":"done","event_type":"done","content":""}\n\n'

    monkeypatch.setattr(
        "flaskr.service.learn.routes.run_script",
        _fake_run_script,
    )

    resp = test_client.put(
        "/api/learn/shifu/builtin-demo-1/run/outline-1",
        json={"input": "hello"},
        headers={"Token": "test-token"},
    )
    body = resp.data.decode("utf-8")

    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert '"event_type":"done"' in body
