"""Keep follow-up settings and prompts on the publication bound to a run."""

from __future__ import annotations

import json
import threading
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from flaskr.api.llm import model_selection
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import handle_input_ask
from flaskr.service.learn.ask_provider_adapters import (
    AskProviderError,
    AskProviderRuntime,
    AskProviderTimeoutError,
)
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.learn.utils_v2 import get_follow_up_info_v2
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from flaskr.service.shifu import shifu_publish_funcs
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, PublishedShifu
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query

from tests.service.learn import test_run_published_revision as revision

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

    monkeypatch.setattr(handle_input_ask, "_run_guardrail", guardrail)
    monkeypatch.setattr(handle_input_ask, "chat_llm", fake_chat)
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


def _ask(app: object, context: object) -> list:
    context._input = {"input": "Explain this"}
    context._trace = MagicMock()
    context._trace_root_span = None
    return list(context._phase_handle_ask_input(app, SimpleNamespace(block_position=1)))


@pytest.mark.parametrize("old_model", ["1", ""])
@pytest.mark.parametrize("outline_override", [True, False])
def test_republish_after_committed_block_keeps_follow_up_on_retained_revision(
    app: object,
    follow_up_dependencies: SimpleNamespace,
    old_model: str,
    outline_override: bool,
) -> None:
    course = revision._seed_course(app)
    old_provider = _configure_follow_up(
        app, course, label="Old", model=old_model, temperature="0"
    )
    if not outline_override:
        with app.app_context(), unit_of_work():
            DraftOutlineItem.query.filter_by(
                outline_item_bid=course.outline_bid, deleted=0
            ).one().ask_enabled_status = 5101
    shifu_publish_funcs.publish_shifu_draft(
        app, course.user_bid, course.course_bid, "", sync_summary=True
    )
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=uuid4().hex,
                shifu_bid=course.course_bid,
                outline_item_bid=course.outline_bid,
                user_bid=course.user_bid,
                status=LEARN_STATUS_IN_PROGRESS,
                block_position=0,
            )
        )

    with app.app_context():
        context = revision._make_context(app, course)
        retained_struct = context._struct
        events = list(context.run_inner(app))
        assert any(event.type == GeneratedType.BREAK for event in events)
        # An independent session sees the actual content-block commit.
        with app.app_context():
            block = LearnGeneratedBlock.query.filter_by(
                user_bid=course.user_bid, position=0
            ).one()
            assert block.generated_content == "Generated test content"
        new_provider = _configure_follow_up(
            app, course, label="New", model="8", temperature="0.8"
        )
        publisher_errors = []
        publisher_sessions = []

        def publish() -> None:
            try:
                with app.app_context():
                    publisher_sessions.append(db.session())
                    shifu_publish_funcs.publish_shifu_draft(
                        app, course.user_bid, course.course_bid, "", sync_summary=True
                    )
            except Exception as exc:
                publisher_errors.append(exc)

        run_session = db.session()
        publisher = threading.Thread(target=publish)
        publisher.start()
        publisher.join(timeout=10)
        assert not publisher.is_alive()
        assert not publisher_errors
        assert publisher_sessions[0] is not run_session
        assert PublishedShifu.query.filter_by(id=retained_struct.id).one().deleted == 1

        ask_events = _ask(app, context)
        assert any(event.type == GeneratedType.CONTENT for event in ask_events)
        info = follow_up_dependencies.guardrails[-1]
        assert info.ask_model == old_model
        assert info.model_args == {"temperature": Decimal(0)}
        old_prompt_source = "lesson" if outline_override else "course"
        expected_ask_prompt = f"Old {old_prompt_source} follow-up prompt::"
        assert info.ask_prompt == expected_ask_prompt + "{shifu_system_message}"
        assert info.ask_mode == 5103
        assert info.ask_provider_config == old_provider
        assert info.usage_metadata["model_selection_record_id"] == retained_struct.id
        provider_call = follow_up_dependencies.providers[-1]
        assert provider_call["provider_config"] == old_provider
        assert (
            "<course_prompt>\nOld lesson prompt\n</course_prompt>"
            in provider_call["messages"][0]["content"]
        )
        assert "New lesson prompt" not in provider_call["messages"][0]["content"]
        llm_call = follow_up_dependencies.llm[-1]
        assert llm_call["model"] == "configured-1"
        assert llm_call["temperature"] == 0
        assert (
            llm_call["usage_metadata"]["model_selection_record_id"]
            == retained_struct.id
        )
        assert llm_call["usage_metadata"]["model_selection_fallback"] is (
            old_model == ""
        )
        assert llm_call["messages"][0]["content"].startswith(expected_ask_prompt)
        assert (
            "<course_prompt>\nOld lesson prompt\n</course_prompt>"
            in llm_call["messages"][0]["content"]
        )
        assert "New lesson" not in llm_call["messages"][0]["content"]
        assert context._struct is retained_struct

        latest = revision._make_context(app, course)
        latest._current_attend = context._current_attend
        _ask(app, latest)
        latest_info = follow_up_dependencies.guardrails[-1]
        assert latest_info.ask_model == "8"
        assert latest_info.model_args == {"temperature": Decimal("0.8")}
        assert (
            latest_info.ask_prompt
            == "New lesson follow-up prompt::{shifu_system_message}"
        )
        assert latest_info.ask_mode == 5102
        assert latest_info.ask_provider_config == new_provider
        assert (
            latest_info.usage_metadata["model_selection_record_id"] == latest._struct.id
        )
        assert latest._struct.id != retained_struct.id
        assert follow_up_dependencies.llm[-1]["messages"][0]["content"].startswith(
            "New lesson follow-up prompt::"
        )
        assert (
            "<course_prompt>\nNew lesson prompt\n</course_prompt>"
            in follow_up_dependencies.llm[-1]["messages"][0]["content"]
        )

        direct_info = get_follow_up_info_v2(
            app, course.course_bid, course.outline_bid, ""
        )
        assert direct_info.ask_model == "8"
        assert (
            direct_info.usage_metadata["model_selection_record_id"] == latest._struct.id
        )


def test_follow_up_preview_and_publication_use_their_own_bound_rows(
    app: object, follow_up_dependencies: SimpleNamespace
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
        formal = revision._make_context(app, course)
        preview = revision._make_context(app, course, preview=True)
        for context in (formal, preview):
            context._current_attend = SimpleNamespace(progress_record_bid=uuid4().hex)
            _ask(app, context)
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
        context = revision._make_context(app, course)
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
        context = revision._make_context(app, course, preview=preview)
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
        preview = revision._make_context(app, course, preview=True)
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
        context = revision._make_context(app, course)
        other = revision._make_context(app, other_course)
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
        context = revision._make_context(app, course)
        failure = OperationalError("SELECT follow-up", {}, RuntimeError("DB failure"))

        def fail_query(_query: object) -> None:
            raise failure

        monkeypatch.setattr(Query, "first", fail_query)
        with pytest.raises(OperationalError) as error:
            get_follow_up_info_v2(
                app, course.course_bid, course.outline_bid, "", struct=context._struct
            )
        assert error.value is failure
