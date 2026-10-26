"""Keep a learning run on its publication across a republish and block commit."""

from __future__ import annotations

import threading
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import context_v2
from flaskr.service.learn.context_v2 import RunScriptContextV2, RunType
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from flaskr.service.shifu import shifu_publish_funcs
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.shifu_struct_manager import (
    get_shifu_outline_tree,
    get_shifu_struct,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query

OLD_DOCUMENT = "Old first block\n\n---\n\nOld second block\n\n---\n\n?[Continue]"
NEW_DOCUMENT = "New first block\n\n---\n\nNew second block\n\n---\n\n?[Continue]"


@pytest.fixture
def runtime_dependencies(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls = []
    monkeypatch.setattr(
        shifu_publish_funcs, "_run_summary_with_error_handling", lambda *_args: None
    )
    monkeypatch.setattr(
        context_v2, "create_trace_with_root_span", lambda **_kwargs: (None, None)
    )
    monkeypatch.setattr(context_v2, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(
        context_v2,
        "load_memory",
        lambda *_args, **_kwargs: SimpleNamespace(as_variables=dict),
    )
    monkeypatch.setattr(
        context_v2, "get_profile_item_definition_list", lambda *_args: []
    )

    def fake_chat_llm(*_args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        yield SimpleNamespace(result="Generated test content")

    monkeypatch.setattr(context_v2, "chat_llm", fake_chat_llm)
    return calls


def _seed_course(
    app: object,
    *,
    model: str = "1",
    temperature: Decimal = Decimal(0),
    outline_prompt: str = "Old lesson prompt",
) -> SimpleNamespace:
    course_bid, outline_bid, user_bid = (uuid4().hex for _index in range(3))
    with app.app_context(), unit_of_work():
        draft = DraftShifu(
            shifu_bid=course_bid,
            title="Revision test course",
            llm=model,
            llm_temperature=temperature,
            llm_system_prompt="Old course prompt",
        )
        outline = DraftOutlineItem(
            shifu_bid=course_bid,
            outline_item_bid=outline_bid,
            title="Revision test lesson",
            position="01",
            type=401,
            content=OLD_DOCUMENT,
            llm_system_prompt=outline_prompt,
        )
        db.session.add_all([draft, outline])
        db.session.flush()
        draft_struct = HistoryItem(
            bid=course_bid,
            id=draft.id,
            type="shifu",
            children=[
                HistoryItem(
                    bid=outline_bid,
                    id=outline.id,
                    type="outline",
                    children=[],
                    child_count=3,
                )
            ],
        )
        db.session.add(
            LogDraftStruct(
                struct_bid=uuid4().hex,
                shifu_bid=course_bid,
                struct=draft_struct.to_json(),
            )
        )
    shifu_publish_funcs.publish_shifu_draft(
        app, user_bid, course_bid, "", sync_summary=True
    )
    return SimpleNamespace(
        course_bid=course_bid, outline_bid=outline_bid, user_bid=user_bid
    )


def _make_context(
    app: object, course: SimpleNamespace, *, preview: bool = False
) -> object:
    struct = get_shifu_struct(app, course.course_bid, preview)
    info = get_shifu_outline_tree(app, course.course_bid, preview)
    context = RunScriptContextV2(
        app=app,
        shifu_info=info,
        struct=struct,
        outline_item_info=info.outline_items[0],
        user_info=SimpleNamespace(
            user_id=course.user_bid, mobile="", email="test@example.com"
        ),
        is_paid=True,
        preview_mode=preview,
    )
    context._input_type = ""
    context._input = ""
    context._run_type = RunType.OUTPUT
    return context


@pytest.mark.parametrize("model", ["1", ""])
@pytest.mark.parametrize("temperature", [Decimal(0), Decimal("0.65")])
def test_published_settings_preserve_model_selection_and_temperature(
    app: object,
    runtime_dependencies: object,
    model: str,
    temperature: Decimal,
) -> None:
    _ = runtime_dependencies
    course = _seed_course(app, model=model, temperature=temperature)
    with app.app_context():
        context = _make_context(app, course)
        settings = context.get_llm_settings(course.outline_bid)
        assert settings.model == model
        assert settings.temperature == float(temperature)
        assert (
            settings.usage_metadata["model_selection_record_id"] == context._struct.id
        )
        assert (
            settings.usage_metadata["model_selection_table"]
            == PublishedShifu.__tablename__
        )
        assert settings.usage_metadata["model_index"] == "1"
        assert settings.usage_metadata["model_selection_fallback"] is (model == "")
        assert settings.usage_metadata["model_selection_fallback_reason"] == (
            "missing_selection" if model == "" else None
        )


@pytest.mark.parametrize("outline_prompt", ["Old lesson prompt", ""])
def test_republish_between_run_resolution_and_block_commit_keeps_old_revision(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    runtime_dependencies: list[dict],
    outline_prompt: str,
) -> None:
    course = _seed_course(app, outline_prompt=outline_prompt)
    with app.app_context(), unit_of_work():
        draft = DraftShifu.query.filter_by(shifu_bid=course.course_bid, deleted=0).one()
        draft.llm = "8"
        draft.llm_temperature = Decimal("0.95")
        draft.llm_system_prompt = "New course prompt"
        outline = DraftOutlineItem.query.filter_by(
            outline_item_bid=course.outline_bid, deleted=0
        ).one()
        outline.content = NEW_DOCUMENT
        outline.llm_system_prompt = "New lesson prompt"
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

    original_init_generated_block = context_v2.init_generated_block
    publisher_errors = []
    publisher_sessions = []
    publication = {"done": False}

    def publish() -> None:
        try:
            with app.app_context():
                publisher_sessions.append(db.session())
                shifu_publish_funcs.publish_shifu_draft(
                    app, course.user_bid, course.course_bid, "", sync_summary=True
                )
        except Exception as exc:
            publisher_errors.append(exc)

    def publish_before_staging(*args: object, **kwargs: object) -> object:
        if not publication["done"]:
            # run_inner has read this block's body, config and prompt. Publish
            # on a separate session before SQLite's single-writer staged INSERT;
            # leave the real streaming and block-finalize commit untouched.
            publication["done"] = True
            thread = threading.Thread(target=publish)
            thread.start()
            thread.join(timeout=10)
            assert not thread.is_alive()
            assert not publisher_errors
        return original_init_generated_block(*args, **kwargs)

    monkeypatch.setattr(context_v2, "init_generated_block", publish_before_staging)
    with app.app_context():
        context = _make_context(app, course)
        retained_struct = context._struct
        run_session = db.session()
        expected_prompt = outline_prompt or "Old course prompt"
        first_events = list(context.run_inner(app))
        assert publication["done"]
        assert publisher_sessions[0] is not run_session
        assert any(event.type == GeneratedType.CONTENT for event in first_events)
        assert any(event.type == GeneratedType.BREAK for event in first_events)
        assert context._current_attend.block_position == 1
        assert PublishedShifu.query.filter_by(id=retained_struct.id).one().deleted == 1

        # A different reader sees the real recorder commit before continuation.
        with app.app_context():
            progress = LearnProgressRecord.query.filter_by(
                user_bid=course.user_bid
            ).one()
            first_block = LearnGeneratedBlock.query.filter_by(
                user_bid=course.user_bid, position=0
            ).one()
            assert progress.block_position == 1
            assert first_block.generated_content == "Generated test content"
            assert first_block.block_content_conf == "Old first block"

        second_events = list(context.run_inner(app))
        assert any(event.type == GeneratedType.CONTENT for event in second_events)
        assert context._struct is retained_struct
        assert context._current_attend.block_position == 2
        assert context.get_system_prompt(course.outline_bid) == expected_prompt
        second_block = LearnGeneratedBlock.query.filter_by(
            user_bid=course.user_bid, position=1
        ).one()
        assert second_block.block_content_conf == "Old second block"
        assert len(runtime_dependencies) == 2
        for call in runtime_dependencies:
            assert call["model"] == "1"
            assert call["temperature"] == 0
            assert (
                call["usage_metadata"]["model_selection_record_id"]
                == retained_struct.id
            )
            assert expected_prompt in call["messages"][0]["content"]
            assert "New lesson prompt" not in call["messages"][0]["content"]

        latest = _make_context(app, course)
        assert latest._struct.id != retained_struct.id
        assert latest.get_llm_settings(course.outline_bid).model == "8"
        assert latest.get_llm_settings(course.outline_bid).temperature == 0.95
        assert latest.get_system_prompt(course.outline_bid) == "New lesson prompt"


def test_missing_bound_course_config_raises_business_error(
    app: object, runtime_dependencies: object
) -> None:
    _ = runtime_dependencies
    course = _seed_course(app)
    with app.app_context():
        context = _make_context(app, course)
        context._struct.id = -1
        with pytest.raises(AppError) as error:
            context.get_llm_settings(course.outline_bid)
        assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
        with pytest.raises(AppError) as prompt_error:
            context.get_system_prompt(course.outline_bid)
        assert prompt_error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]


def test_preview_and_published_run_read_distinct_sources(
    app: object, runtime_dependencies: object
) -> None:
    _ = runtime_dependencies
    course = _seed_course(app)
    with app.app_context(), unit_of_work():
        draft = DraftShifu.query.filter_by(shifu_bid=course.course_bid, deleted=0).one()
        draft.llm = "8"
        draft.llm_temperature = Decimal("0.75")
        draft.llm_system_prompt = "Draft course prompt"
        outline = DraftOutlineItem.query.filter_by(
            outline_item_bid=course.outline_bid, deleted=0
        ).one()
        outline.content = NEW_DOCUMENT
        outline.llm_system_prompt = "Draft lesson prompt"

    with app.app_context():
        preview = _make_context(app, course, preview=True)
        published = _make_context(app, course)
        preview_settings = preview.get_llm_settings(course.outline_bid)
        published_settings = published.get_llm_settings(course.outline_bid)
        assert preview_settings.model == "8"
        assert preview_settings.temperature == 0.75
        assert (
            preview_settings.usage_metadata["model_selection_table"]
            == DraftShifu.__tablename__
        )
        assert preview.get_system_prompt(course.outline_bid) == "Draft lesson prompt"
        assert published_settings.model == "1"
        assert published_settings.temperature == 0
        assert (
            published_settings.usage_metadata["model_selection_table"]
            == PublishedShifu.__tablename__
        )
        assert published.get_system_prompt(course.outline_bid) == "Old lesson prompt"
        attend = SimpleNamespace(outline_item_bid=course.outline_bid, block_position=0)
        assert preview._get_run_script_info(attend).mdflow == NEW_DOCUMENT
        assert published._get_run_script_info(attend).mdflow == OLD_DOCUMENT


@pytest.mark.parametrize("preview", [False, True])
def test_deleted_course_is_not_revived_from_bound_structure(
    app: object, runtime_dependencies: object, preview: bool
) -> None:
    _ = runtime_dependencies
    course = _seed_course(app)
    with app.app_context():
        context = _make_context(app, course, preview=preview)
        with unit_of_work():
            context._shifu_model.query.filter_by(shifu_bid=course.course_bid).update(
                {"deleted": 1}
            )
        with pytest.raises(AppError) as error:
            context.get_llm_settings(course.outline_bid)
        assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
        with pytest.raises(AppError) as prompt_error:
            context.get_system_prompt(course.outline_bid)
        assert prompt_error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
        if not preview:
            attend = SimpleNamespace(
                outline_item_bid=course.outline_bid, block_position=0
            )
            with pytest.raises(AppError) as body_error:
                context._get_run_script_info(attend)
            assert body_error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]


def test_retired_draft_config_is_not_replaced_by_latest_draft_or_publication(
    app: object, runtime_dependencies: object
) -> None:
    _ = runtime_dependencies
    course = _seed_course(app)
    with app.app_context():
        preview = _make_context(app, course, preview=True)
        with unit_of_work():
            DraftShifu.query.filter_by(id=preview._struct.id).update({"deleted": 1})
            db.session.add(
                DraftShifu(
                    shifu_bid=course.course_bid,
                    title="Replacement draft",
                    llm="8",
                    llm_temperature=Decimal("0.85"),
                )
            )
        with pytest.raises(AppError) as error:
            preview.get_llm_settings(course.outline_bid)
        assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]


def test_missing_bound_body_does_not_fall_back_to_latest_outline(
    app: object, runtime_dependencies: object
) -> None:
    _ = runtime_dependencies
    course = _seed_course(app)
    with app.app_context():
        context = _make_context(app, course)
        context._current_outline_item.id = -1
        attend = SimpleNamespace(outline_item_bid=course.outline_bid, block_position=0)
        with pytest.raises(AppError) as error:
            context._get_run_script_info(attend)
        assert error.value.code == ERROR_CODE["server.shifu.outlineItemNotFound"]
        with pytest.raises(AppError) as prompt_error:
            context.get_system_prompt(course.outline_bid)
        assert prompt_error.value.code == ERROR_CODE["server.shifu.outlineItemNotFound"]


def test_bound_outline_identity_mismatch_does_not_fall_back(
    app: object, runtime_dependencies: object
) -> None:
    _ = runtime_dependencies
    course = _seed_course(app)
    other_course = _seed_course(app)
    other_struct = get_shifu_struct(app, other_course.course_bid)
    with app.app_context():
        context = _make_context(app, course)
        context._current_outline_item.id = other_struct.children[0].id
        attend = SimpleNamespace(outline_item_bid=course.outline_bid, block_position=0)
        with pytest.raises(AppError) as error:
            context._get_run_script_info(attend)
        assert error.value.code == ERROR_CODE["server.shifu.outlineItemNotFound"]


def test_database_error_from_config_query_is_not_swallowed(
    app: object, monkeypatch: pytest.MonkeyPatch, runtime_dependencies: object
) -> None:
    _ = runtime_dependencies
    course = _seed_course(app)
    with app.app_context():
        context = _make_context(app, course)
        failure = OperationalError(
            "SELECT revision", {}, RuntimeError("test database failure")
        )

        def fail_query(_query: object) -> None:
            raise failure

        monkeypatch.setattr(Query, "first", fail_query)
        with pytest.raises(OperationalError) as error:
            context.get_llm_settings(course.outline_bid)
        assert error.value is failure
