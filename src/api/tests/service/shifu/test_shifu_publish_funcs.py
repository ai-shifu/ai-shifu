import sys
import types
from datetime import datetime
from decimal import Decimal

import pytest
from flask import Flask

from flaskr.dao import db
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
    ShifuCourseSlug,
)


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = types.ModuleType("litellm")
    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.completion = lambda *args, **kwargs: iter([])
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


class _FakeSpan:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.end_kwargs = {}

    def end(self, **kwargs):
        self.end_kwargs = kwargs


class _FakeTrace:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.updated = {}
        self.last_span = None

    def span(self, **kwargs):
        self.last_span = _FakeSpan(**kwargs)
        return self.last_span

    def update(self, **kwargs):
        self.updated = kwargs


class _FakeLangfuseClient:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        trace = _FakeTrace(**kwargs)
        self.traces.append(trace)
        return trace


def test_get_summary_updates_trace_and_span_output(monkeypatch):
    from flaskr.service.shifu import shifu_publish_funcs as module

    fake_langfuse = _FakeLangfuseClient()
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
    assert trace.last_span is not None
    assert trace.last_span.kwargs["input"] == "Summarize this lesson"
    assert trace.last_span.end_kwargs["output"] == "summary result"
    assert trace.updated["output"] == "summary result"


def test_run_summary_downgrades_shutdown_race_to_warning(monkeypatch):
    from unittest.mock import MagicMock
    from flaskr.service.shifu import shifu_publish_funcs as module

    monkeypatch.setattr(module, "apply_shifu_context_snapshot", lambda *_a, **_k: None)

    def _raise_shutdown(*_a, **_k):
        raise RuntimeError(
            "litellm.MidStreamFallbackError: APIConnectionError: OpenAIException - "
            "cannot schedule new futures after shutdown"
        )

    monkeypatch.setattr(module, "get_shifu_summary", _raise_shutdown)

    app = Flask("shifu-summary-shutdown")
    warning_mock = MagicMock()
    error_mock = MagicMock()
    monkeypatch.setattr(app.logger, "warning", warning_mock)
    monkeypatch.setattr(app.logger, "error", error_mock)

    module._run_summary_with_error_handling(app, "shifu-1")

    warning_mock.assert_called_once()
    error_mock.assert_not_called()


def test_run_summary_logs_error_for_other_failures(monkeypatch):
    from unittest.mock import MagicMock
    from flaskr.service.shifu import shifu_publish_funcs as module

    monkeypatch.setattr(module, "apply_shifu_context_snapshot", lambda *_a, **_k: None)

    def _raise_other(*_a, **_k):
        raise ValueError("boom")

    monkeypatch.setattr(module, "get_shifu_summary", _raise_other)

    app = Flask("shifu-summary-error")
    warning_mock = MagicMock()
    error_mock = MagicMock()
    monkeypatch.setattr(app.logger, "warning", warning_mock)
    monkeypatch.setattr(app.logger, "error", error_mock)

    module._run_summary_with_error_handling(app, "shifu-1")

    error_mock.assert_called_once()
    warning_mock.assert_not_called()


def test_publish_shifu_draft_preserves_outline_updated_at(app, monkeypatch):
    from flaskr.service.shifu import shifu_publish_funcs as module

    monkeypatch.setattr(module, "_run_summary_with_error_handling", lambda *args: None)

    draft_updated_at = datetime(2026, 6, 30, 10, 0, 0)
    with app.app_context():
        draft = DraftShifu(
            shifu_bid="publish-preserve-outline-updated-at",
            title="Draft",
            description="Desc",
            keywords="a,b",
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

    published_url = module.publish_shifu_draft(
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
        slug = ShifuCourseSlug.query.filter_by(
            shifu_bid="publish-preserve-outline-updated-at",
            is_current=1,
        ).one()

    assert published_outline is not None
    assert published_outline.updated_at == draft_updated_at
    assert published_url == f"https://example.com/c/{slug.slug}"


def test_rename_and_republish_preserve_the_original_slug(app, monkeypatch):
    from flaskr.service.shifu import shifu_draft_funcs, shifu_publish_funcs

    course_bid = "rename-republish-slug-course"
    owner_bid = "rename-republish-owner"
    original_slug = "original-rename-course-link"

    def fail_slug_regeneration(*_args, **_kwargs):
        pytest.fail("rename and republish must not regenerate the slug")

    monkeypatch.setattr(
        shifu_publish_funcs,
        "_run_summary_with_error_handling",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        shifu_draft_funcs,
        "check_text_with_risk_control",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        shifu_draft_funcs,
        "shifu_permission_verification",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.slug.prepare_course_slug",
        fail_slug_regeneration,
    )

    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=course_bid,
                    title="Original course title",
                    description="Description",
                    price=Decimal("0.50"),
                    created_user_bid=owner_bid,
                    updated_user_bid=owner_bid,
                ),
                DraftOutlineItem(
                    outline_item_bid="rename-republish-lesson",
                    shifu_bid=course_bid,
                    title="Lesson",
                    position="1",
                    type=401,
                    hidden=0,
                    content="# Lesson",
                    created_user_bid=owner_bid,
                    updated_user_bid=owner_bid,
                ),
                ShifuCourseSlug(
                    shifu_bid=course_bid,
                    slug=original_slug,
                    version=1,
                    is_current=1,
                    generation_source="llm",
                ),
            ]
        )
        db.session.commit()

    renamed = shifu_draft_funcs.save_shifu_draft_info(
        app,
        user_id=owner_bid,
        shifu_id=course_bid,
        shifu_name="Renamed course title",
        shifu_description=None,
        shifu_avatar=None,
        shifu_keywords=None,
        shifu_model=None,
        shifu_temperature=None,
        shifu_price=None,
        shifu_system_prompt=None,
        base_url="https://example.com",
    )
    first_url = shifu_publish_funcs.publish_shifu_draft(
        app,
        user_id=owner_bid,
        shifu_id=course_bid,
        base_url="https://example.com",
        sync_summary=True,
    )
    second_url = shifu_publish_funcs.publish_shifu_draft(
        app,
        user_id=owner_bid,
        shifu_id=course_bid,
        base_url="https://example.com",
        sync_summary=True,
    )

    with app.app_context():
        slug_bindings = ShifuCourseSlug.query.filter_by(shifu_bid=course_bid).all()
        current_publish = PublishedShifu.query.filter_by(
            shifu_bid=course_bid,
            deleted=0,
        ).one()
        published_versions = PublishedShifu.query.filter_by(shifu_bid=course_bid).all()

        assert renamed.slug == original_slug
        assert renamed.url == f"https://example.com/c/{original_slug}"
        assert first_url == f"https://example.com/c/{original_slug}"
        assert second_url == first_url
        assert current_publish.title == "Renamed course title"
        assert len(published_versions) == 2
        assert [(binding.slug, binding.is_current) for binding in slug_bindings] == [
            (original_slug, 1)
        ]
