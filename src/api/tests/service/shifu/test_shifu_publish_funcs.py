"""Verify shifu publish funcs behavior."""

import json
import sys
import types
from datetime import datetime
from decimal import Decimal

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.learn.live_follow_up_config import GEMINI_LIVE_MODEL_ID
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = types.ModuleType("litellm")

    def get_model_info(*args: object, **kwargs: object) -> None:
        _ = args, kwargs
        message = "unknown model"
        raise ValueError(message)

    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.get_model_info = get_model_info
    litellm_stub.get_supported_openai_params = lambda **_kwargs: []
    litellm_stub.completion = lambda *_args, **_kwargs: iter([])
    sys.modules["litellm"] = litellm_stub


def _install_openai_responses_stub() -> None:
    if "openai.types.responses" in sys.modules:
        return

    responses_pkg = types.ModuleType("openai.types.responses")
    responses_pkg.__path__ = []
    response_mod = types.ModuleType("openai.types.responses.response")
    response_create_mod = types.ModuleType(
        "openai.types.responses.response_create_params"
    )
    response_function_mod = types.ModuleType(
        "openai.types.responses.response_function_tool_call"
    )
    response_text_mod = types.ModuleType(
        "openai.types.responses.response_text_config_param"
    )

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
    response_function_mod.ResponseFunctionToolCall = response_function_tool_call
    response_text_mod.ResponseTextConfigParam = response_text_config
    responses_pkg.ResponseFunctionToolCall = response_function_tool_call

    sys.modules["openai.types.responses"] = responses_pkg
    sys.modules["openai.types.responses.response"] = response_mod
    sys.modules["openai.types.responses.response_create_params"] = response_create_mod
    sys.modules["openai.types.responses.response_function_tool_call"] = (
        response_function_mod
    )
    sys.modules["openai.types.responses.response_text_config_param"] = response_text_mod


_install_litellm_stub()
_install_openai_responses_stub()


class _FakeObservation:
    """Mimics a Langfuse SDK v4 observation object."""

    def __init__(self, kind: str = "span", **kwargs: object) -> None:
        self.kind = kind
        self.kwargs = kwargs
        self.updates = []
        self.ended = False
        self.public = False
        self.trace_id = "f" * 32
        self.id = f"fake-{kind}-id"
        self.generations = []

    def start_observation(self, as_type: object = "span", **kwargs: object) -> object:
        child = _FakeObservation(as_type, **kwargs)
        if as_type == "generation":
            self.generations.append(child)
        return child

    def update(self, **kwargs: object) -> None:
        self.updates.append(kwargs)

    def set_trace_as_public(self) -> None:
        self.public = True

    def end(self) -> None:
        self.ended = True

    @property
    def end_kwargs(self) -> object:
        merged = {}
        for item in self.updates:
            merged.update(item)
        return merged


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.traces = []

    def start_observation(
        self,
        as_type: object = "span",
        trace_context: object = None,
        **kwargs: object,
    ) -> object:
        root = _FakeObservation(as_type, **kwargs)
        root.trace_context = trace_context or {}
        self.traces.append(root)
        return root


def test_make_ask_prompt_fills_content_and_keeps_runtime_placeholders() -> None:
    from flaskr.service.shifu import shifu_publish_funcs as module
    from flaskr.util.prompt_loader import load_prompt_template

    app = Flask("shifu-ask-prompt")
    template = load_prompt_template("ask")

    result = module._make_ask_prompt(
        app,
        template,
        learned_text="learned summary",
        unlearned_text="unlearned summary",
    )

    assert "learned summary" in result
    assert "unlearned summary" in result
    # Runtime placeholders survive publishing and are filled at ask time.
    assert "{shifu_system_message}" in result
    assert "{knowledge_rule}" in result
    assert "{knowledge_section}" in result
    # The knowledge section itself is rendered at ask time, not at publish.
    assert "<knowledge>" not in result


def test_get_summary_updates_trace_and_span_output(monkeypatch: object) -> None:
    from flaskr.api import langfuse as langfuse_module
    from flaskr.service.shifu import shifu_publish_funcs as module

    fake_langfuse = _FakeLangfuseClient()

    def create_trace_id(seed: object = None) -> object:
        del seed
        return "a" * 32

    monkeypatch.setattr(
        langfuse_module.Langfuse,
        "create_trace_id",
        create_trace_id,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "get_langfuse_client",
        lambda: fake_langfuse,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "invoke_llm",
        lambda *_args, **_kwargs: iter(
            [
                types.SimpleNamespace(result="summary "),
                types.SimpleNamespace(result="result"),
            ]
        ),
    )

    app = Flask("shifu-summary")
    summary = module._get_summary(
        app,
        prompt="Summarize this lesson",
        model_name="gpt-test",
        user_id="user-1",
        temperature=0.2,
    )

    assert summary == "summary result"
    assert len(fake_langfuse.traces) == 1
    trace = fake_langfuse.traces[0]
    assert trace.kwargs["name"] == "shifu_summary"
    assert trace.kwargs["input"] == "Summarize this lesson"
    # In SDK v4 the root observation carries the overall input/output.
    assert trace.end_kwargs["output"] == "summary result"
    assert trace.ended


def test_run_summary_downgrades_shutdown_race_to_warning(monkeypatch: object) -> None:
    from unittest.mock import MagicMock

    from flaskr.service.shifu import shifu_publish_funcs as module

    monkeypatch.setattr(module, "apply_shifu_context_snapshot", lambda *_a, **_k: None)

    def _raise_shutdown(*_a: object, **_k: object) -> None:
        message = (
            "litellm.MidStreamFallbackError: APIConnectionError: OpenAIException - "
            "cannot schedule new futures after shutdown"
        )
        raise RuntimeError(message)

    monkeypatch.setattr(module, "get_shifu_summary", _raise_shutdown)

    app = Flask("shifu-summary-shutdown")
    warning_mock = MagicMock()
    error_mock = MagicMock()
    monkeypatch.setattr(app.logger, "warning", warning_mock)
    monkeypatch.setattr(app.logger, "error", error_mock)

    module._run_summary_with_error_handling(app, "shifu-1")

    warning_mock.assert_called_once()
    error_mock.assert_not_called()


def test_run_summary_logs_error_for_other_failures(monkeypatch: object) -> None:
    from unittest.mock import MagicMock

    from flaskr.service.shifu import shifu_publish_funcs as module

    monkeypatch.setattr(module, "apply_shifu_context_snapshot", lambda *_a, **_k: None)

    def _raise_other(*_a: object, **_k: object) -> None:
        message = "boom"
        raise ValueError(message)

    monkeypatch.setattr(module, "get_shifu_summary", _raise_other)

    app = Flask("shifu-summary-error")
    warning_mock = MagicMock()
    error_mock = MagicMock()
    monkeypatch.setattr(app.logger, "warning", warning_mock)
    monkeypatch.setattr(app.logger, "error", error_mock)

    module._run_summary_with_error_handling(app, "shifu-1")

    error_mock.assert_called_once()
    warning_mock.assert_not_called()


def test_publish_shifu_draft_preserves_outline_updated_at(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.shifu import shifu_publish_funcs as module

    monkeypatch.setattr(module, "_run_summary_with_error_handling", lambda *_args: None)
    original_load_existing_outline_items = module.load_existing_outline_items
    outline_load_calls = []

    def _record_outline_load(*args: object, **kwargs: object) -> object:
        outline_load_calls.append((args, kwargs))
        return original_load_existing_outline_items(*args, **kwargs)

    monkeypatch.setattr(
        module,
        "load_existing_outline_items",
        _record_outline_load,
    )

    draft_updated_at = datetime(2026, 6, 30, 10, 0, 0)
    with app.app_context():
        draft = DraftShifu(
            shifu_bid="publish-preserve-outline-updated-at",
            title="Draft",
            description="Desc",
            keywords="a,b",
            tts_enabled=1,
            default_listen_mode_enabled=1,
        )
        outline = DraftOutlineItem(
            outline_item_bid="publish-preserve-outline-lesson",
            shifu_bid="publish-preserve-outline-updated-at",
            title="Lesson",
            position="1",
            type=401,
            hidden=0,
            content="# Lesson",
            updated_at=draft_updated_at,
        )
        db.session.add_all([draft, outline])
        db.session.commit()

    module.publish_shifu_draft(
        app,
        user_id="user-1",
        shifu_id="publish-preserve-outline-updated-at",
        base_url="https://example.com",
        sync_summary=True,
    )

    with app.app_context():
        published_outline = (
            PublishedOutlineItem.query.filter_by(
                shifu_bid="publish-preserve-outline-updated-at",
                outline_item_bid="publish-preserve-outline-lesson",
                deleted=0,
            )
            .order_by(PublishedOutlineItem.id.desc())
            .first()
        )
        published_shifu = (
            PublishedShifu.query.filter_by(
                shifu_bid="publish-preserve-outline-updated-at",
                deleted=0,
            )
            .order_by(PublishedShifu.id.desc())
            .first()
        )

    assert published_outline is not None
    assert published_outline.updated_at == draft_updated_at
    assert published_shifu is not None
    assert published_shifu.default_listen_mode_enabled == 1
    assert outline_load_calls == [
        (("publish-preserve-outline-updated-at",), {"include_content": True})
    ]


def test_publish_rejects_invalid_live_contract_before_retiring_current_version(
    app: object,
) -> None:
    from flaskr.service.shifu import shifu_publish_funcs as module

    shifu_bid = "publish-reject-invalid-live-contract"
    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=shifu_bid,
                    title="Invalid Live draft",
                    llm="gpt-main",
                    ask_llm=GEMINI_LIVE_MODEL_ID,
                    ask_provider_config=json.dumps(
                        {
                            "provider": "dify",
                            "mode": "provider_only",
                            "config": {"live_voice": "Kore"},
                        }
                    ),
                ),
                PublishedShifu(
                    shifu_bid=shifu_bid,
                    title="Current published course",
                    llm="gpt-main",
                    deleted=0,
                ),
            ]
        )
        db.session.commit()

    with pytest.raises(AppError):
        module.publish_shifu_draft(
            app,
            user_id="teacher-1",
            shifu_id=shifu_bid,
            base_url="https://example.com",
            sync_summary=True,
        )

    with app.app_context():
        current = PublishedShifu.query.filter_by(
            shifu_bid=shifu_bid,
            deleted=0,
        ).one()
        assert current.title == "Current published course"


def test_publish_live_follow_up_defaults_official_voice(
    app: object,
    monkeypatch: object,
) -> None:
    from flaskr.service.shifu import shifu_publish_funcs as module

    shifu_bid = "publish-live-default-voice"
    monkeypatch.setattr(module, "_run_summary_with_error_handling", lambda *_args: None)
    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=shifu_bid,
                    title="Valid Live draft",
                    llm="gpt-main",
                    llm_temperature=Decimal("0.4"),
                    ask_llm=GEMINI_LIVE_MODEL_ID,
                    ask_provider_config="{}",
                ),
                DraftOutlineItem(
                    outline_item_bid="publish-live-default-voice-lesson",
                    shifu_bid=shifu_bid,
                    title="Lesson",
                    position="1",
                    type=401,
                    hidden=0,
                    content="# Lesson",
                ),
            ]
        )
        db.session.commit()

    module.publish_shifu_draft(
        app,
        user_id="teacher-1",
        shifu_id=shifu_bid,
        base_url="https://example.com",
        sync_summary=True,
    )

    with app.app_context():
        published = PublishedShifu.query.filter_by(
            shifu_bid=shifu_bid,
            deleted=0,
        ).one()
        assert json.loads(published.ask_provider_config) == {
            "provider": "llm",
            "mode": "provider_only",
            "config": {"live_voice": "Kore"},
        }


def test_live_follow_up_never_drives_text_summary_generation(
    monkeypatch: object,
) -> None:
    from flaskr.service.shifu import shifu_publish_funcs as module

    captured: dict[str, object] = {}

    def get_summary(_app: object, **kwargs: object) -> str:
        captured.update(kwargs)
        return "summary"

    monkeypatch.setattr(module, "_get_summary", get_summary)
    section = types.SimpleNamespace(bid="lesson-1", title="Lesson")
    tree = types.SimpleNamespace(
        outline_items=[
            types.SimpleNamespace(
                bid="chapter-1",
                title="Chapter",
                children=[section],
            )
        ]
    )
    outline = types.SimpleNamespace(
        outline_item_bid="lesson-1",
        content="",
        summary="",
        ask_enabled_status=0,
    )
    shifu = types.SimpleNamespace(
        llm="gpt-main",
        llm_temperature=Decimal("0.4"),
        ask_llm=GEMINI_LIVE_MODEL_ID,
        ask_llm_temperature=Decimal("0.1"),
    )

    result = module._generate_summaries(
        Flask("live-summary-model-test"),
        tree,
        {"lesson-1": outline},
        "Summary: {all_script_content}",
        shifu,
    )

    assert captured["model_name"] == "gpt-main"
    assert captured["temperature"] == Decimal("0.4")
    assert result["lesson-1"]["content"] == "summary"
