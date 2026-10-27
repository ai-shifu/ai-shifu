"""Keep follow-up settings and prompts on the publication a request binds to."""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flaskr.api.llm import markdownflow_model, model_selection
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import handle_input_ask
from flaskr.service.learn.ask import follow_up_run
from flaskr.service.learn.ask_provider_adapters import (
    AskProviderError,
    AskProviderRuntime,
    AskProviderTimeoutError,
)
from flaskr.service.learn.utils_v2 import get_follow_up_info_v2
from flaskr.service.shifu import shifu_publish_funcs
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, PublishedShifu
from flaskr.service.shifu.shifu_struct_manager import get_shifu_struct
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query

from tests.service.learn import published_course as revision
from tests.service.learn.agent.test_gateway_model import FakeChunk

runtime_dependencies = revision.runtime_dependencies


@pytest.fixture
def follow_up_dependencies(
    monkeypatch: pytest.MonkeyPatch, runtime_dependencies: object
) -> SimpleNamespace:
    _ = runtime_dependencies
    calls = SimpleNamespace(guardrails=[], providers=[], llm=[])

    def guardrail(*args: object) -> list:
        calls.guardrails.append(args[8])
        return []

    def fake_chat(*_args: object, **kwargs: object) -> object:
        calls.llm.append(kwargs)
        yield SimpleNamespace(result="Follow-up answer")

    def fake_provider(**kwargs: object) -> object:
        calls.providers.append(kwargs)
        # Exercise the same runtime factory used by retrieval providers, so
        # selected model, temperature and the assembled prompt reach the LLM.
        for response in kwargs["runtime"].llm_stream_factory():
            yield SimpleNamespace(content=response.result)

    def fake_gateway_chat(*_args: object, **kwargs: object) -> object:
        # 2.0 courses answer through the memory-aware gateway model.
        calls.llm.append(kwargs)
        yield FakeChunk(result="Follow-up answer", finish_reason="stop")

    monkeypatch.setattr(handle_input_ask, "_run_guardrail", guardrail)
    monkeypatch.setattr(handle_input_ask, "chat_llm", fake_chat)
    monkeypatch.setattr(markdownflow_model, "chat_llm", fake_gateway_chat)
    monkeypatch.setattr(handle_input_ask, "stream_ask_provider_response", fake_provider)
    monkeypatch.setattr(handle_input_ask, "AskProviderRuntime", AskProviderRuntime)
    monkeypatch.setattr(handle_input_ask, "AskProviderError", AskProviderError)
    monkeypatch.setattr(
        handle_input_ask, "AskProviderTimeoutError", AskProviderTimeoutError
    )
    monkeypatch.setattr(
        handle_input_ask,
        "stream_provider_with_langfuse",
        lambda **kwargs: kwargs["provider_stream"],
    )
    monkeypatch.setattr(
        handle_input_ask, "update_langfuse_trace", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        handle_input_ask, "update_langfuse_observation", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        model_selection,
        "get_configured_model_slots",
        lambda: [
            {"index": "1", "model": "configured-1"},
            {"index": "8", "model": "configured-8"},
        ],
    )
    monkeypatch.setattr(
        model_selection, "resolve_model_slot", lambda index: f"configured-{index}"
    )
    return calls


def _configure_follow_up(
    app: object, course: SimpleNamespace, *, label: str, model: str, temperature: str
) -> dict:
    provider_config = {
        "provider": "get_biji_knowledge" if label == "Old" else "dify",
        "mode": "provider_only" if label == "Old" else "provider_then_llm",
        "config": {"topic_id": label, "api_key": "test-key"},
    }
    with app.app_context(), unit_of_work():
        draft = DraftShifu.query.filter_by(shifu_bid=course.course_bid, deleted=0).one()
        draft.ask_llm = model
        draft.ask_llm_temperature = Decimal(temperature)
        draft.ask_llm_system_prompt = (
            f"{label} course follow-up prompt::{{shifu_system_message}}"
        )
        draft.ask_enabled_status = 5103 if label == "Old" else 5102
        draft.ask_provider_config = json.dumps(provider_config)
        outline = DraftOutlineItem.query.filter_by(
            outline_item_bid=course.outline_bid, deleted=0
        ).one()
        outline.llm_system_prompt = f"{label} lesson prompt"
        outline.ask_llm_system_prompt = (
            f"{label} lesson follow-up prompt::{{shifu_system_message}}"
        )
        outline.ask_enabled_status = 5103 if label == "Old" else 5102
    return provider_config


def _bound(app: object, course: SimpleNamespace, *, preview: bool = False) -> object:
    """Return the structure a request binds to, the way a follow-up resolves it."""
    return SimpleNamespace(
        _struct=get_shifu_struct(app, course.course_bid, preview),
        _shifu_model=DraftShifu if preview else PublishedShifu,
    )


def _ask(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    course: SimpleNamespace,
    *,
    preview: bool,
) -> list:
    monkeypatch.setattr(
        follow_up_run,
        "create_trace_with_root_span",
        lambda **_kwargs: (MagicMock(), None),
    )
    monkeypatch.setattr(follow_up_run, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(follow_up_run, "finalize_langfuse_trace", lambda **_k: None)
    monkeypatch.setattr(
        follow_up_run,
        "load_memory",
        lambda *_args, **_kwargs: SimpleNamespace(as_variables=dict),
    )
    monkeypatch.setattr(
        follow_up_run,
        "load_user_aggregate",
        lambda _bid: SimpleNamespace(
            user_id=course.user_bid, mobile="", email="learner@example.com"
        ),
    )
    return list(
        follow_up_run.follow_up_events(
            app,
            user_bid=course.user_bid,
            outline_bid=course.outline_bid,
            user_input={"input": "Explain this"},
            reload_generated_block_bid=None,
            reload_element_bid=None,
            listen=False,
            learning_mode="read",
            preview_mode=preview,
            stop_event=None,
        )
    )


def test_follow_up_preview_and_publication_use_their_own_bound_rows(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    follow_up_dependencies: SimpleNamespace,
) -> None:
    course = revision._seed_course(app)
    old_provider = _configure_follow_up(
        app, course, label="Old", model="1", temperature="0"
    )
    shifu_publish_funcs.publish_shifu_draft(
        app, course.user_bid, course.course_bid, "", sync_summary=True
    )
    draft_provider = _configure_follow_up(
        app, course, label="Draft", model="8", temperature="0.7"
    )
    with app.app_context():
        formal = _bound(app, course)
        preview = _bound(app, course, preview=True)
        for is_preview in (False, True):
            _ask(app, monkeypatch, course, preview=is_preview)
        formal_info, preview_info = follow_up_dependencies.guardrails
        assert formal_info.ask_model == "1"
        assert formal_info.model_args == {"temperature": Decimal(0)}
        assert formal_info.ask_provider_config == old_provider
        assert (
            formal_info.usage_metadata["model_selection_table"]
            == PublishedShifu.__tablename__
        )
        assert (
            formal_info.usage_metadata["model_selection_record_id"] == formal._struct.id
        )
        assert preview_info.ask_model == "8"
        assert preview_info.model_args == {"temperature": Decimal("0.7")}
        assert preview_info.ask_provider_config == draft_provider
        assert (
            preview_info.ask_prompt
            == "Draft lesson follow-up prompt::{shifu_system_message}"
        )
        assert (
            preview_info.usage_metadata["model_selection_table"]
            == DraftShifu.__tablename__
        )
        assert (
            preview_info.usage_metadata["model_selection_record_id"]
            == preview._struct.id
        )
        assert "Old lesson" in follow_up_dependencies.llm[0]["messages"][0]["content"]
        assert (
            "Draft lesson"
            not in follow_up_dependencies.llm[0]["messages"][0]["content"]
        )
        assert "Draft lesson" in follow_up_dependencies.llm[1]["messages"][0]["content"]
        assert (
            "Old lesson" not in follow_up_dependencies.llm[1]["messages"][0]["content"]
        )


@pytest.mark.parametrize(
    ("missing_part", "error_key"),
    [
        ("course", "server.shifu.shifuNotFound"),
        ("outline", "server.shifu.outlineItemNotFound"),
    ],
)
def test_missing_follow_up_bound_row_returns_business_error(
    app: object, runtime_dependencies: object, missing_part: str, error_key: str
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    with app.app_context():
        context = _bound(app, course)
        node = (
            context._struct if missing_part == "course" else context._struct.children[0]
        )
        node.id = -1
        with pytest.raises(AppError) as error:
            get_follow_up_info_v2(
                app, course.course_bid, course.outline_bid, "", struct=context._struct
            )
        assert error.value.code == ERROR_CODE[error_key]


@pytest.mark.parametrize("preview", [False, True])
def test_follow_up_does_not_revive_a_deleted_course(
    app: object, runtime_dependencies: object, preview: bool
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    with app.app_context():
        context = _bound(app, course, preview=preview)
        with unit_of_work():
            context._shifu_model.query.filter_by(shifu_bid=course.course_bid).update(
                {"deleted": 1}
            )
        with pytest.raises(AppError) as error:
            get_follow_up_info_v2(
                app,
                course.course_bid,
                course.outline_bid,
                "",
                preview,
                struct=context._struct,
            )
        assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]


def test_retired_follow_up_preview_does_not_use_latest_draft(
    app: object, runtime_dependencies: object
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    with app.app_context():
        preview = _bound(app, course, preview=True)
        with unit_of_work():
            DraftShifu.query.filter_by(id=preview._struct.id).update({"deleted": 1})
            db.session.add(DraftShifu(shifu_bid=course.course_bid, ask_llm="8"))
        with pytest.raises(AppError) as error:
            get_follow_up_info_v2(
                app,
                course.course_bid,
                course.outline_bid,
                "",
                is_preview=True,
                struct=preview._struct,
            )
        assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]


@pytest.mark.parametrize("mismatched_part", ["course", "outline"])
def test_follow_up_rejects_physical_row_from_another_course(
    app: object, runtime_dependencies: object, mismatched_part: str
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    other_course = revision._seed_course(app)
    with app.app_context():
        context = _bound(app, course)
        other = _bound(app, other_course)
        if mismatched_part == "course":
            context._struct.id = other._struct.id
            error_key = "server.shifu.shifuNotFound"
        else:
            context._struct.children[0].id = other._struct.children[0].id
            error_key = "server.shifu.outlineItemNotFound"
        with pytest.raises(AppError) as error:
            get_follow_up_info_v2(
                app, course.course_bid, course.outline_bid, "", struct=context._struct
            )
        assert error.value.code == ERROR_CODE[error_key]


def test_follow_up_configuration_database_error_propagates(
    app: object, monkeypatch: pytest.MonkeyPatch, runtime_dependencies: object
) -> None:
    _ = runtime_dependencies
    course = revision._seed_course(app)
    with app.app_context():
        context = _bound(app, course)
        failure = OperationalError("SELECT follow-up", {}, RuntimeError("DB failure"))

        def fail_query(_query: object) -> None:
            raise failure

        monkeypatch.setattr(Query, "first", fail_query)
        with pytest.raises(OperationalError) as error:
            get_follow_up_info_v2(
                app, course.course_bid, course.outline_bid, "", struct=context._struct
            )
        assert error.value is failure
