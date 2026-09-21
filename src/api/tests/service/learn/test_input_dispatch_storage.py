"""Resolve persisted interaction prompts before accepting or replaying learner input."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn import context_v2 as runtime
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.metering import UsageContext
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from flaskr.service.shifu.consts import BLOCK_TYPE_MDINTERACTION_VALUE

from .test_context_interaction_phases import _consume


@pytest.fixture
def dispatch(app: object, monkeypatch: pytest.MonkeyPatch) -> object:
    key = uuid.uuid4().hex
    with app.app_context():
        context = runtime.RunScriptContextV2.__new__(runtime.RunScriptContextV2)
        context.app = app
        context._user_info = SimpleNamespace(user_id=key, mobile="", email="")
        context._outline_item_info = SimpleNamespace(
            bid=key, shifu_bid=key, title="Lesson"
        )
        context._current_attend = LearnProgressRecord(
            progress_record_bid=key,
            user_bid=key,
            shifu_bid=key,
            outline_item_bid=key,
            block_position=0,
            status=LEARN_STATUS_IN_PROGRESS,
        )
        with unit_of_work():
            db.session.add(context._current_attend)
        context._run_type = runtime.RunType.INPUT
        context._can_continue = True
        context._is_paid = True
        context._input = {"input": ["Go"]}
        context._trace_args = {"metadata": {}}
        context._trace_root_span = None
        context.append_langfuse_output = Mock()
        context._maybe_emit_feedback_after_access_gate = Mock(return_value=iter([]))
        state = runtime._RunStepState(
            run_script_info=runtime.RunScriptInfo(
                context._current_attend, key, 0, "?[Go]"
            ),
            llm_settings=LLMSettings(model="1", temperature=0.2),
            system_prompt=None,
            usage_context=UsageContext(user_bid=key, shifu_bid=key),
            llm_provider=Mock(),
            mdflow_context=Mock(),
            block_list=[object(), object()],
            user_profile={},
            message_list=[],
            variable_definition_key_id_map={},
            block=SimpleNamespace(
                content="?[Go]", index=0, block_type=runtime.BlockType.INTERACTION
            ),
        )
        rendered = SimpleNamespace(
            content="Translated prompt", metadata={}, variables={}
        )
        validated = SimpleNamespace(
            content="",
            metadata={"interaction_type": "non_assignment_button", "answer": ["go"]},
            variables={},
        )
        state.mdflow_context.process.side_effect = lambda **kwargs: (
            validated if "user_input" in kwargs else rendered
        )
        moderation = Mock(side_effect=lambda *_args, **_kwargs: iter([None]))
        monkeypatch.setattr(runtime, "check_text_with_llm_response", moderation)
        yield SimpleNamespace(
            app=app,
            key=key,
            context=context,
            state=state,
            moderation=moderation,
            validated=validated,
        )
        with unit_of_work():
            LearnGeneratedBlock.query.filter_by(shifu_bid=key).delete()
            LearnProgressRecord.query.filter_by(shifu_bid=key).delete()


def _block(dispatch: object, **overrides: object) -> LearnGeneratedBlock:
    fields = {
        "generated_block_bid": uuid.uuid4().hex,
        "progress_record_bid": dispatch.key,
        "outline_item_bid": dispatch.key,
        "user_bid": dispatch.key,
        "shifu_bid": dispatch.key,
        "type": BLOCK_TYPE_MDINTERACTION_VALUE,
        "position": 0,
        "status": 1,
        "deleted": 0,
        "generated_content": "",
        "block_content_conf": "Cached prompt",
        "role": ROLE_TEACHER,
    }
    fields.update(overrides)
    row = LearnGeneratedBlock(**fields)
    with unit_of_work():
        db.session.add(row)
    return row


def test_first_interaction_arrival_persists_prompt_and_pauses_without_consuming_input(
    dispatch: object,
) -> None:
    events, stop = _consume(
        dispatch.context._phase_process_input(dispatch.app, dispatch.state)
    )
    assert stop is True
    assert [event.type for event in events] == [GeneratedType.INTERACTION]
    assert events[0].content == "Translated prompt"
    db.session.expire_all()
    block = LearnGeneratedBlock.query.filter_by(shifu_bid=dispatch.key).one()
    assert block.generated_block_bid == events[0].generated_block_bid
    assert block.generated_content == ""
    assert block.role == ROLE_TEACHER
    assert dispatch.context._current_attend.block_position == 0
    assert dispatch.context._can_continue is False
    dispatch.moderation.assert_not_called()


@pytest.mark.parametrize(
    "distractor",
    ["user", "progress", "outline", "status", "position", "type", "deleted"],
)
def test_submitted_input_uses_latest_active_interaction_in_its_own_scope(
    dispatch: object,
    distractor: str,
) -> None:
    expected = _block(dispatch)
    mismatch = {
        "user": {"user_bid": "other"},
        "progress": {"progress_record_bid": "other"},
        "outline": {"outline_item_bid": "other"},
        "status": {"status": 0},
        "position": {"position": 1},
        "type": {"type": 0},
        "deleted": {"deleted": 1},
    }[distractor]
    excluded = _block(dispatch, **mismatch)
    expected_bid, excluded_bid = (
        expected.generated_block_bid,
        excluded.generated_block_bid,
    )
    events, stop = _consume(
        dispatch.context._phase_process_input(dispatch.app, dispatch.state)
    )
    assert events == []
    assert stop is True
    db.session.expire_all()
    expected = LearnGeneratedBlock.query.filter_by(
        generated_block_bid=expected_bid
    ).one()
    excluded = LearnGeneratedBlock.query.filter_by(
        generated_block_bid=excluded_bid
    ).one()
    assert expected.generated_content == "go"
    assert expected.role == ROLE_STUDENT
    assert excluded.generated_content == ""
    assert excluded.role == ROLE_TEACHER
    assert dispatch.context._current_attend.block_position == 1
    assert dispatch.context._run_type == runtime.RunType.OUTPUT
    assert (
        dispatch.moderation.call_args.kwargs["usage_context"].generated_block_bid
        == expected_bid
    )


def test_moderation_rejection_keeps_cursor_and_replays_question(
    dispatch: object,
) -> None:
    _block(dispatch)
    dispatch.moderation.side_effect = lambda *_a, **_kw: iter(
        ["Please try another answer"]
    )
    events, stop = _consume(
        dispatch.context._phase_process_input(dispatch.app, dispatch.state)
    )
    assert stop is True
    assert [event.type for event in events] == [
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
        GeneratedType.INTERACTION,
    ]
    assert events[0].content == "Please try another answer"
    assert events[-1].content == "Translated prompt"
    assert dispatch.context._current_attend.block_position == 0
    assert dispatch.context._can_continue is False
    db.session.expire_all()
    block = LearnGeneratedBlock.query.filter_by(
        generated_block_bid=events[-1].generated_block_bid
    ).one()
    assert block.generated_content == ""


def test_validation_failure_replays_error_and_keeps_completion_tail(
    dispatch: object,
) -> None:
    _block(dispatch)
    dispatch.validated.metadata = {}
    dispatch.validated.content = "Choose an available option"
    events, stop = _consume(
        dispatch.context._phase_process_input(dispatch.app, dispatch.state)
    )
    assert stop is False
    assert [event.type for event in events] == [
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
        GeneratedType.INTERACTION,
    ]
    assert events[0].content == "Choose an available option"
    assert dispatch.context._current_attend.block_position == 0
    db.session.expire_all()
    error = LearnGeneratedBlock.query.filter_by(
        generated_block_bid=events[0].generated_block_bid
    ).one()
    assert error.generated_content == "Choose an available option"


def test_noninteraction_input_realigns_to_pending_prompt_without_recording_answer(
    dispatch: object,
) -> None:
    pending = _block(dispatch, position=1)
    dispatch.state.block.block_type = runtime.BlockType.CONTENT
    dispatch.state.has_effective_input = True
    events, stop = _consume(
        dispatch.context._phase_process_input(dispatch.app, dispatch.state)
    )
    assert (events, stop) == ([], True)
    assert dispatch.context._current_attend.block_position == 1
    assert dispatch.context._run_type == runtime.RunType.INPUT
    assert pending.generated_content == ""
    dispatch.moderation.assert_not_called()
