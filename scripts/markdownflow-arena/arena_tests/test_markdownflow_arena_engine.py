"""Verify model resolution, isolated rendering, and honest completion outcomes."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flaskr.api.llm import chat_llm as production_chat_llm

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from markdownflow_arena_lib import engine  # noqa: E402
from markdownflow_arena_lib.observe import chat_llm as real_chat_llm  # noqa: E402
from markdownflow_arena_lib.source import case_input_hash  # noqa: E402
from markdownflow_arena_lib.state import ArenaError  # noqa: E402


def _case() -> dict:
    case = {
        "case_id": "case-1",
        "owner_user_bid": "owner",
        "source": {"shifu_bid": "course", "outline_bid": "lesson"},
        "document": "Explain a vector and create a visual example.",
        "document_prompt": "Teach clearly.",
        "variables": {"language": "zh-CN", "sys_user_language": "zh-CN"},
        "context": [],
        "user_input": None,
        "output_language": "zh-CN",
        "use_learner_language": False,
        "block_index": 0,
        "temperature": 0.3,
    }
    case["input_hash"] = case_input_hash(case)
    return case


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> dict:
    runtime = engine._runtime()
    runtime.update(
        {
            "create_trace": MagicMock(return_value=(MagicMock(), MagicMock())),
            "finalize_trace": MagicMock(),
            "langfuse_client": MagicMock(),
            "get_language": lambda: "en-US",
            "set_language": MagicMock(),
        }
    )
    monkeypatch.setattr(engine, "_runtime", lambda: runtime)
    return runtime


def test_resolves_unique_exact_suffix_and_preserves_provider_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        engine,
        "_model_catalog",
        lambda _app: [
            {"model": "qwen/deepseek-v4-flash-0731", "display_name": "DeepSeek"},
            {"model": "gemini-3.8-flash", "display_name": "Gemini"},
        ],
    )
    models = engine.resolve_models(
        Flask(__name__), ["deepseek-v4-flash-0731", "gemini-3.8-flash"]
    )
    assert models == [
        {
            "requested": "deepseek-v4-flash-0731",
            "model": "qwen/deepseek-v4-flash-0731",
            "display_name": "DeepSeek",
        },
        {
            "requested": "gemini-3.8-flash",
            "model": "gemini-3.8-flash",
            "display_name": "Gemini",
        },
    ]


@pytest.mark.parametrize(
    "requested",
    [
        ["gemini-3.8-flash"],
        ["deepseek-v4-flash"],
        ["qwen/deepseek-v4-flash", "qwen/deepseek-v4-flash"],
    ],
)
def test_missing_ambiguous_and_duplicate_models_fail_without_fallback(
    monkeypatch: pytest.MonkeyPatch, requested: list[str]
) -> None:
    monkeypatch.setattr(
        engine,
        "_model_catalog",
        lambda _app: [
            {"model": "qwen/deepseek-v4-flash"},
            {"model": "silicon/deepseek-v4-flash"},
            {"model": "gemini-3.7-flash"},
        ],
    )
    with pytest.raises(ArenaError, match=r"unavailable|ambiguous|distinct"):
        engine.resolve_models(Flask(__name__), requested)


@pytest.mark.parametrize(
    ("finish_reason", "partial", "expected"),
    [
        ("stop", False, "complete"),
        ("length", False, "truncated"),
        ("stop", True, "truncated"),
        (None, False, "generation_failed"),
        ("content_filter", False, "generation_failed"),
    ],
)
def test_generation_classifies_terminal_metadata_and_renders_with_real_adapter(
    runtime: dict,
    monkeypatch: pytest.MonkeyPatch,
    finish_reason: str | None,
    partial: bool,
    expected: str,
) -> None:
    del runtime

    def complete(*_args: object, **kwargs: object) -> object:
        yield SimpleNamespace(result="A vector has a direction and a magnitude.")
        kwargs["completion_observer"](
            {
                "finish_reason": finish_reason,
                "partial_response": partial,
                "usage": {"input": 10, "output": 9, "total": 19},
            }
        )

    monkeypatch.setattr(engine, "_chat_llm", complete)
    result = engine.generate_case(Flask(__name__), _case(), {"model": "test-model"})
    assert result["status"] == expected, result["metadata"].get("error_class")
    assert result["content"] == "A vector has a direction and a magnitude."
    assert result["elements"]
    assert result["elements"][0]["element_type"] == "text"
    assert result["metadata"]["requests"][0]["usage"]["total"] == 19


def test_cross_model_requests_share_frozen_messages_without_preview_state(
    runtime: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.learn import context_v2

    forbidden = MagicMock(
        side_effect=AssertionError("Preview state must not be touched")
    )
    monkeypatch.setattr(context_v2, "_PreviewContextStore", forbidden)
    monkeypatch.setattr(context_v2, "get_user_profiles", forbidden)
    requests = []

    def complete(*_args: object, **kwargs: object) -> object:
        requests.append(copy.deepcopy(kwargs["messages"]))
        yield SimpleNamespace(result="A frozen explanation.")
        kwargs["completion_observer"](
            {"finish_reason": "stop", "partial_response": False}
        )

    monkeypatch.setattr(engine, "_chat_llm", complete)
    case = _case()
    original = copy.deepcopy(case)
    a = engine.generate_case(Flask(__name__), case, {"model": "A"})
    b = engine.generate_case(Flask(__name__), case, {"model": "B"})
    assert a["status"] == b["status"] == "complete"
    assert requests[0] == requests[1]
    assert (
        a["metadata"]["requests"][0]["messages_hash"]
        == b["metadata"]["requests"][0]["messages_hash"]
    )
    assert a["metadata"]["run_id"] != b["metadata"]["run_id"]
    assert case == original
    forbidden.assert_not_called()
    assert runtime["set_language"].call_args.args == ("en-US",)


@pytest.mark.parametrize("locale", ["zh-CN", "en-US", "fr-FR", "ar-SA", "th-TH"])
@pytest.mark.parametrize("finish_reason", ["stop", "length", None])
def test_generated_metadata_preserves_frozen_rendering_locale(
    runtime: dict,
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    finish_reason: str | None,
) -> None:
    def complete(*_args: object, **kwargs: object) -> object:
        yield SimpleNamespace(result="A localized teaching explanation.")
        kwargs["completion_observer"]({"finish_reason": finish_reason})

    monkeypatch.setattr(engine, "_chat_llm", complete)
    case = _case()
    case["output_language"] = locale
    case["variables"].update({"language": locale, "sys_user_language": locale})
    case["input_hash"] = case_input_hash(case)
    result = engine.generate_case(Flask(__name__), case, {"model": "test-model"})
    assert result["metadata"]["locale"] == locale
    assert (
        result["status"]
        == {
            "stop": "complete",
            "length": "truncated",
            None: "generation_failed",
        }[finish_reason]
    )
    assert runtime["set_language"].call_args.args == ("en-US",)


def test_stream_failure_preserves_partial_private_output_and_omits_raw_error(
    runtime: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    del runtime

    def fail(*_args: object, **_kwargs: object) -> object:
        yield SimpleNamespace(result="Partial explanation")
        message = "secret provider token in raw error"
        raise RuntimeError(message)

    monkeypatch.setattr(engine, "_chat_llm", fail)
    result = engine.generate_case(Flask(__name__), _case(), {"model": "A"})
    assert result["status"] == "generation_failed"
    assert result["content"] == "Partial explanation"
    assert result["metadata"]["error_class"] == "RuntimeError"
    assert "secret provider token" not in json.dumps(result)


def test_tampered_inputs_fail_before_runtime_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = MagicMock()
    monkeypatch.setattr(engine, "_runtime", runtime)
    case = _case()
    case["temperature"] = 1.5
    with pytest.raises(ArenaError, match="hash"):
        engine.generate_case(Flask(__name__), case, {"model": "A"})
    runtime.assert_not_called()


def test_html_and_text_elements_survive_real_markdownflow_stream(
    runtime: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    del runtime

    def complete(*_args: object, **kwargs: object) -> object:
        yield SimpleNamespace(
            result="<!DOCTYPE html><html><body><h1>A visual slide</h1></body></html>\n\nA teaching note."
        )
        kwargs["completion_observer"](
            {"finish_reason": "stop", "partial_response": False}
        )

    monkeypatch.setattr(engine, "_chat_llm", complete)
    result = engine.generate_case(Flask(__name__), _case(), {"model": "A"})
    assert result["status"] == "complete", result["metadata"]
    assert {item["element_type"] for item in result["elements"]} == {"html", "text"}


def test_shared_observer_captures_finish_only_chunk_without_provider_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.api import llm

    # The backend fixture replaces paid calls; this test deliberately exercises
    # the real production wrapper with a deterministic provider stream.
    production_call = MagicMock(wraps=production_chat_llm)
    monkeypatch.setattr(llm, "chat_llm", production_call)

    chunks = [
        SimpleNamespace(
            id="1",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="Output"), finish_reason=None
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            id="1",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None), finish_reason="length"
                )
            ],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=3, total_tokens=7),
        ),
    ]
    monkeypatch.setattr(
        llm,
        "get_litellm_params_and_model",
        lambda _model: (
            {"api_key": "private-key", "api_base": "private-base"},
            "actual-model",
            "openai",
        ),
    )
    monkeypatch.setattr(
        llm,
        "_prepare_litellm_request_kwargs",
        lambda _provider, _model, _params, kwargs: {
            **kwargs,
            "max_tokens": 3,
            "api_key": "private-key",
        },
    )
    monkeypatch.setattr(
        llm, "_iter_stream_with_precontent_retry", lambda *_args: iter(chunks)
    )
    monkeypatch.setattr(llm, "record_llm_usage", MagicMock())
    original_iterator = llm._iter_stream_with_precontent_retry
    original_resolver = llm.get_litellm_params_and_model
    span = MagicMock()
    observed = []
    with Flask(__name__).app_context():
        responses = list(
            real_chat_llm(
                Flask(__name__),
                "owner",
                span,
                "requested-model",
                [{"role": "user", "content": "private prompt"}],
                completion_observer=observed.append,
            )
        )
    assert responses[0].result == "Output"
    production_call.assert_called_once()
    assert "completion_observer" not in production_call.call_args.kwargs
    assert llm._iter_stream_with_precontent_retry is original_iterator
    assert llm.get_litellm_params_and_model is original_resolver
    assert observed[0]["finish_reason"] == "length"
    assert observed[0]["provider_model"] == "actual-model"
    assert observed[0]["usage"] == {"input": 4, "output": 3, "total": 7}
    assert observed[0]["parameters"] == {"max_tokens": 3}
    assert not any(
        secret in json.dumps(observed)
        for secret in ("private-key", "private-base", "private prompt")
    )


def test_trace_finalization_failure_preserves_successful_paid_output(
    runtime: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime["finalize_trace"].side_effect = RuntimeError("private tracing error")

    def complete(*_args: object, **kwargs: object) -> object:
        yield SimpleNamespace(result="The complete teaching output.")
        kwargs["completion_observer"](
            {"finish_reason": "stop", "partial_response": False}
        )

    monkeypatch.setattr(engine, "_chat_llm", complete)
    result = engine.generate_case(Flask(__name__), _case(), {"model": "A"})
    assert result["status"] == "complete"
    assert result["elements"]
    assert result["content"] == "The complete teaching output."
    assert result["metadata"]["tracing_failure"] is True
    assert "private tracing error" not in json.dumps(result)
    assert runtime["set_language"].call_args.args == ("en-US",)


def test_completion_observer_failure_does_not_change_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.api import llm

    monkeypatch.setattr(llm, "chat_llm", production_chat_llm)

    chunks = [
        SimpleNamespace(
            id="1",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="Output"), finish_reason="stop"
                )
            ],
            usage=None,
        )
    ]
    monkeypatch.setattr(
        llm,
        "get_litellm_params_and_model",
        lambda _model: ({"api_key": "test"}, "actual", "openai"),
    )
    monkeypatch.setattr(
        llm,
        "_prepare_litellm_request_kwargs",
        lambda _provider, _model, _params, kwargs: kwargs,
    )
    monkeypatch.setattr(
        llm, "_iter_stream_with_precontent_retry", lambda *_args: iter(chunks)
    )
    record = MagicMock()
    monkeypatch.setattr(llm, "record_llm_usage", record)
    observer = MagicMock(side_effect=RuntimeError("observer failure"))
    with Flask(__name__).app_context():
        responses = list(
            real_chat_llm(
                Flask(__name__),
                "owner",
                MagicMock(),
                "requested",
                [],
                completion_observer=observer,
            )
        )
    assert responses[0].result == "Output"
    record.assert_called_once()


@pytest.mark.parametrize("termination", ["failure", "close"])
def test_manual_observation_restores_production_functions_on_interruption(
    monkeypatch: pytest.MonkeyPatch, termination: str
) -> None:
    from flaskr.api import llm

    resolver = MagicMock(return_value=({"api_key": "test"}, "actual", "openai"))

    def interrupted(*_args: object) -> object:
        yield SimpleNamespace(
            id="1",
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="Output"), finish_reason=None
                )
            ],
            usage=None,
        )
        message = "Synthetic interrupted provider stream"
        raise RuntimeError(message)

    monkeypatch.setattr(llm, "chat_llm", production_chat_llm)
    monkeypatch.setattr(llm, "get_litellm_params_and_model", resolver)
    monkeypatch.setattr(llm, "_iter_stream_with_precontent_retry", interrupted)
    monkeypatch.setattr(
        llm, "_prepare_litellm_request_kwargs", lambda _p, _m, _c, values: values
    )
    observed = []
    app = Flask(__name__)
    with app.app_context():
        stream = real_chat_llm(
            app,
            "owner",
            MagicMock(),
            "requested",
            [],
            completion_observer=observed.append,
        )
        assert next(stream).result == "Output"
        if termination == "failure":
            with pytest.raises(RuntimeError, match="Synthetic interrupted"):
                list(stream)
        else:
            stream.close()
    assert llm.chat_llm is production_chat_llm
    assert llm.get_litellm_params_and_model is resolver
    assert llm._iter_stream_with_precontent_retry is interrupted
    assert len(observed) == 1
    assert engine._completion_status(observed) == "generation_failed"


def test_model_resolution_preserves_configured_glm_case_and_full_provider_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        engine, "_model_catalog", lambda _app: [{"model": "qwen/ZHIPU/GLM-5.3-Flash"}]
    )
    assert (
        engine.resolve_models(Flask(__name__), ["glm-5.3-flash"])[0]["model"]
        == "qwen/ZHIPU/GLM-5.3-Flash"
    )
    monkeypatch.setattr(
        engine,
        "_model_catalog",
        lambda _app: [
            {"model": "qwen/ZHIPU/GLM-5.3-Flash"},
            {"model": "ernie/glm-5.3-flash"},
        ],
    )
    with pytest.raises(ArenaError, match="ambiguous"):
        engine.resolve_models(Flask(__name__), ["glm-5.3-flash"])
