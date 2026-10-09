"""Edit draft answers through the real engine, adapter and guarded persistence path."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.learn.agent import lesson_entry, preview_history, preview_rewind
from flaskr.service.learn.agent.engine import ScriptBundle, Session
from flaskr.service.learn.agent.models import LearnAgentSession
from flaskr.service.learn.agent.session_store import (
    load_agent_session,
    save_agent_session,
)
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learn_funcs import reset_learn_record
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.service.learn.test_draft_classroom_history import (
    classroom as classroom,  # noqa: PLC0414 - pytest fixture re-export.
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from flask import Flask


def test_editing_an_old_draft_answer_replaces_only_its_future(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    published = Session(script=ScriptBundle(script="Published"), turn=7)
    save_agent_session(
        app, published, user_bid=identity, shifu_bid=identity, outline_item_bid=identity
    )
    run()
    original = history().elements
    run("Old choice")
    run("Discard this later answer")
    run("New choice", anchor=original[1].element_bid)
    elements = history().elements
    assert [e.element_type for e in elements] == [
        ElementType.TEXT,
        ElementType.INTERACTION,
        ElementType.TEXT,
        ElementType.INTERACTION,
    ]
    assert elements[0].element_bid == original[0].element_bid
    assert elements[1].element_bid == original[1].element_bid
    assert elements[1].payload.user_input == "New choice"
    assert "question 4" in elements[2].content
    session = load_agent_session(app, identity, identity, preview_mode=True)
    serialized = json.dumps(session.to_dict())
    assert "New choice" in serialized
    assert "Old choice" not in serialized
    assert "Discard this later answer" not in serialized
    assert load_agent_session(app, identity, identity).to_dict() == published.to_dict()
    with app.app_context():
        assert LearnProgressRecord.query.filter_by(user_bid=identity).count() == 0
        assert LearnGeneratedBlock.query.filter_by(user_bid=identity).count() == 0


def test_draft_content_regeneration_reuses_the_original_answer(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    run("Original answer")
    old = history()
    run(anchor=old.elements[2].element_bid)
    restored = history()
    assert restored.last_progress_updated_at == old.last_progress_updated_at
    assert restored.elements[0].element_bid == old.elements[0].element_bid
    assert restored.elements[1].payload.user_input == "Original answer"
    assert "question 3" in restored.elements[2].content
    assert "question 2" not in " ".join(e.content or "" for e in restored.elements)
    assert "Original answer" in json.dumps(
        load_agent_session(app, identity, identity, preview_mode=True).to_dict()
    )


def test_anchored_first_pending_answer_does_not_require_a_checkpoint(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    anchor = history().elements[1].element_bid
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        data = json.loads(row.session_data)
        data["ai_shifu_preview_presentation"].pop("turns", None)
        row.session_data = json.dumps(data)
    run("First answer", anchor=anchor)
    assert history().elements[1].payload.user_input == "First answer"


def test_missing_old_checkpoint_does_not_discard_existing_history(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, calls = classroom
    run()
    anchor = history().elements[1].element_bid
    run("Old answer")
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        data = json.loads(row.session_data)
        data["ai_shifu_preview_presentation"].pop("turns")
        row.session_data = json.dumps(data)
    before = history().model_dump()
    count = len(calls)
    with pytest.raises(AppError):
        run("New answer", anchor=anchor)
    assert len(calls) == count
    assert history().model_dump() == before


def test_reset_generation_anchor_cannot_rewind_a_new_draft(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, calls = classroom
    run()
    old_anchor = history().elements[1].element_bid
    reset_learn_record(app, identity, identity, identity, preview_mode=True)
    run()
    before = history().model_dump()
    count = len(calls)
    with pytest.raises(AppError):
        run("Stale answer", anchor=old_anchor)
    assert len(calls) == count
    assert history().model_dump() == before


def test_failed_draft_save_rolls_back_retirement_with_the_session(
    app: Flask, classroom: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity, run, history, _calls = classroom
    run()
    anchor = history().elements[1].element_bid
    run("Old answer")
    before = history().model_dump()
    session = load_agent_session(app, identity, identity, preview_mode=True).to_dict()

    def fail_stage(**_kwargs: object) -> None:
        message = "Forced draft save failure"
        raise RuntimeError(message)

    monkeypatch.setattr(preview_history, "stage_preview_turn", fail_stage)
    with pytest.raises(RuntimeError, match="Forced draft save failure"):
        run("Replacement", anchor=anchor)
    assert history().model_dump() == before
    assert (
        load_agent_session(app, identity, identity, preview_mode=True).to_dict()
        == session
    )


@pytest.mark.parametrize("dimension", ["user_bid", "shifu_bid", "outline_item_bid"])
def test_foreign_anchor_is_rejected_without_changing_the_draft(
    app: Flask, classroom: tuple, dimension: str
) -> None:
    identity, run, history, calls = classroom
    run()
    run("Old answer")
    anchor = uuid.uuid4().hex
    owner = {"user_bid": identity, "shifu_bid": identity, "outline_item_bid": identity}
    owner[dimension] = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        runs = json.loads(row.session_data)["ai_shifu_preview_presentation"]["runs"]
        db.session.add(
            LearnGeneratedElement(
                **owner,
                element_bid=anchor,
                generated_block_bid=uuid.uuid4().hex,
                run_session_bid=runs[0],
                event_type="element",
                element_type="text",
                content_text="Foreign teaching",
                is_final=1,
                status=1,
            )
        )
    before = history().model_dump()
    count = len(calls)
    with pytest.raises(AppError):
        run("Wrong scope", anchor=anchor)
    assert len(calls) == count
    assert history().model_dump() == before


@pytest.mark.parametrize(
    "corruption", [None, [None], [{"block_bid": "bad", "record": []}]]
)
def test_unusable_turn_metadata_keeps_existing_history(
    app: Flask, classroom: tuple, corruption: object
) -> None:
    identity, run, history, calls = classroom
    run()
    anchor = history().elements[1].element_bid
    run("Old answer")
    with app.app_context(), unit_of_work():
        row = LearnAgentSession.query.filter_by(user_bid=identity, deleted=0).one()
        data = json.loads(row.session_data)
        data["ai_shifu_preview_presentation"]["turns"] = corruption
        row.session_data = json.dumps(data)
    before = history().model_dump()
    count = len(calls)
    with pytest.raises(AppError):
        run("New answer", anchor=anchor)
    assert len(calls) == count
    assert history().model_dump() == before


@pytest.mark.parametrize("question", [0, 1])
def test_editing_one_of_two_questions_restores_its_own_accepting_turn(
    app: Flask, classroom: tuple, monkeypatch: pytest.MonkeyPatch, question: int
) -> None:
    identity, run, history, _calls = classroom

    async def model(messages: list, _info: object) -> AsyncIterator:
        if any(isinstance(p, ToolCallPart) for m in messages for p in m.parts):
            yield "Completed."
            yield {
                0: DeltaToolCall(
                    name="finish",
                    tool_call_id="finish-many",
                    json_args='{"summary":"Done"}',
                )
            }
            return
        yield "Teaching before both questions."
        yield {
            i: DeltaToolCall(
                name="interact",
                tool_call_id=f"many-{i}",
                json_args=json.dumps({"type": "text", "prompt": f"Question {i}?"}),
            )
            for i in range(2)
        }

    class Gateway(FunctionModel):
        def set_usage_context(self, _context: object) -> None:
            pass

    gateway = Gateway(stream_function=model)
    monkeypatch.setattr(lesson_entry, "GatewayModel", lambda *_a, **_k: gateway)
    run()
    original = history().elements
    controls = [e for e in original if e.element_type == ElementType.INTERACTION]
    assert len(controls) == 2
    run("First answer")
    run("Second answer")
    run("Replacement", anchor=controls[question].element_bid)
    restored = history().elements
    assert restored[0].element_bid == original[0].element_bid
    restored_controls = [
        e for e in restored if e.element_type == ElementType.INTERACTION
    ]
    assert [e.element_bid for e in restored_controls] == [
        e.element_bid for e in controls
    ]
    assert [e.payload.user_input or "" for e in restored_controls] == (
        ["Replacement", ""] if question == 0 else ["First answer", "Replacement"]
    )
    session = load_agent_session(app, identity, identity, preview_mode=True)
    assert session.finished is (question == 1)
    assert "Second answer" not in json.dumps(session.to_dict())


def test_regenerating_first_teaching_uses_empty_original_input(
    classroom: tuple,
) -> None:
    _identity, run, history, _calls = classroom
    run()
    first = history().elements[0].element_bid
    run("Later answer")
    run(anchor=first)
    elements = history().elements
    assert len(elements) == 2
    assert "question 3" in elements[0].content
    assert not elements[1].payload.user_input


def test_follow_ups_on_retired_teaching_are_excluded(
    classroom: tuple, app: Flask
) -> None:
    identity, run, history, _calls = classroom
    run()
    question = history().elements[1].element_bid
    run("Old answer")
    with app.app_context(), unit_of_work():
        adapter = ListenElementRunAdapter(
            app, shifu_bid=identity, outline_bid=identity, user_bid=identity
        )
        block = uuid.uuid4().hex
        anchor = history().elements[2].element_bid
        list(
            adapter.process(
                iter(
                    [
                        RunMarkdownFlowDTO(
                            outline_bid=identity,
                            generated_block_bid=block,
                            type=GeneratedType.ASK,
                            content="Explain the old answer?",
                            anchor_element_bid=anchor,
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=identity,
                            generated_block_bid=block,
                            type=GeneratedType.CONTENT,
                            content="Superseded explanation.",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=identity,
                            generated_block_bid=block,
                            type=GeneratedType.BREAK,
                            content="",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid=identity,
                            generated_block_bid=block,
                            type=GeneratedType.DONE,
                            content="",
                        ),
                    ]
                )
            )
        )
    assert any(e.element_type == ElementType.ASK for e in history().elements)
    run("New answer", anchor=question)
    assert all(
        e.element_type not in {ElementType.ASK, ElementType.ANSWER}
        for e in history().elements
    )


def test_stale_rewind_plan_cannot_retire_a_later_turn(
    app: Flask, classroom: tuple
) -> None:
    identity, run, history, _calls = classroom
    run()
    anchor = history().elements[1].element_bid
    run("Old answer")
    with app.app_context():
        plan = preview_rewind.plan_preview_rewind(
            app,
            user_bid=identity,
            shifu_bid=identity,
            outline_bid=identity,
            anchor=anchor,
            answering=True,
        )
    run("Later answer")
    before = history().model_dump()
    from flaskr.service.learn.agent.session_store import PreviewGenerationDiscardedError

    with (
        app.app_context(),
        pytest.raises(PreviewGenerationDiscardedError),
        unit_of_work(),
    ):
        preview_rewind.stage_preview_retirement(
            plan,
            generation=plan.generation,
            user_bid=identity,
            shifu_bid=identity,
            outline_bid=identity,
        )
    assert history().model_dump() == before


def test_reset_during_rewind_refuses_late_save_and_leaves_no_active_history(
    app: Flask, classroom: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity, run, history, _calls = classroom
    run()
    anchor = history().elements[1].element_bid
    run("Old answer")

    async def reset_during_model(_messages: list, _info: object) -> AsyncIterator:
        reset_learn_record(app, identity, identity, identity, preview_mode=True)
        yield "Late teaching after reset."
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="late-question",
                json_args='{"type":"text","prompt":"Late question?"}',
            )
        }

    class Gateway(FunctionModel):
        def set_usage_context(self, _context: object) -> None:
            pass

    gateway = Gateway(stream_function=reset_during_model)
    monkeypatch.setattr(lesson_entry, "GatewayModel", lambda *_a, **_k: gateway)
    run("New answer", anchor=anchor)
    assert history().elements == []
    assert load_agent_session(app, identity, identity, preview_mode=True) is None
