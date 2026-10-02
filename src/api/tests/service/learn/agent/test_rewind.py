"""Cover taking a 2.0 lesson back to an earlier turn.

The learner goes back to a block -- a question answered differently, or content regenerated -- and
the lesson has to continue from exactly there: the engine's conversation restored to the state it
had then, the rows written after it retired, and nothing else touched.
"""

from __future__ import annotations

import json

import pytest
from flaskr.dao import db
from flaskr.service.learn.agent import rewind
from flaskr.service.learn.agent.engine.interaction import InteractionSpec, Option
from flaskr.service.learn.agent.engine.script import ScriptBundle
from flaskr.service.learn.agent.engine.session import PendingInteraction, Session
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS, LEARN_STATUS_RESET
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
)
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

USER = "learner-rewind"
SHIFU = "course-rewind"
OUTLINE = "outline-rewind"
RECORD = "record-rewind"

_QUESTION = InteractionSpec(
    type="single",
    prompt="Which way?",
    options=[Option(display="Left"), Option(display="Right")],
    variable="way",
)


def _session_waiting_on_a_question() -> Session:
    return Session(
        script=ScriptBundle(script="Ask which way."),
        messages=[
            ModelRequest(parts=[UserPromptPart(content="start")]),
            ModelResponse(parts=[TextPart(content="Pick one.")]),
        ],
        memory={"name": "Ada"},
        pending=[PendingInteraction("q1", _QUESTION)],
        turn=1,
    )


# --- the session --------------------------------------------------------------------------


def test_a_session_is_restored_to_the_state_its_checkpoint_recorded() -> None:
    session = _session_waiting_on_a_question()
    checkpoint = json.loads(json.dumps(rewind.checkpoint_of(session)))

    # What the lesson went on to do after the checkpoint.
    session.messages.append(ModelResponse(parts=[TextPart(content="You went left.")]))
    session.memory["way"] = "Left"
    session.pending = []
    session.answers = {"q1": "Learner chose: Left"}
    session.turn = 3
    session.finished = True

    rewind.restore(session, checkpoint)

    assert len(session.messages) == 2
    assert session.memory == {"name": "Ada"}
    assert [p.tool_call_id for p in session.pending] == ["q1"]
    assert session.pending[0].spec == _QUESTION
    assert session.answers == {}
    assert session.turn == 1
    assert session.finished is False


def test_a_turn_record_is_json_and_keeps_the_values_the_turn_ran_with() -> None:
    record = rewind.turn_record(
        rewind.checkpoint_of(_session_waiting_on_a_question()), ["x"]
    )
    data = json.loads(record)["agent_turn"]
    assert data["version"] == 1
    assert data["values"] == ["x"]
    assert data["checkpoint"]["messages"] == 2


# --- planning a rewind --------------------------------------------------------------------


def _clean() -> None:
    LearnGeneratedElement.query.delete()
    LearnGeneratedBlock.query.delete()
    LearnProgressRecord.query.delete()
    db.session.commit()


def _record(status: int = LEARN_STATUS_IN_PROGRESS) -> None:
    db.session.add(
        LearnProgressRecord(
            progress_record_bid=RECORD,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_item_bid=OUTLINE,
            status=status,
            block_position=0,
        )
    )


def _block(
    bid: str,
    *,
    checkpoint: dict | None,
    values: list[str] | None = None,
    block_type: int = BLOCK_TYPE_MDCONTENT_VALUE,
) -> None:
    db.session.add(
        LearnGeneratedBlock(
            generated_block_bid=bid,
            progress_record_bid=RECORD,
            user_bid=USER,
            shifu_bid=SHIFU,
            outline_item_bid=OUTLINE,
            block_bid="",
            type=block_type,
            role=0,
            generated_content=f"taught in {bid}",
            block_content_conf=(
                rewind.turn_record(checkpoint, values or [])
                if checkpoint is not None
                else ""
            ),
            status=1,
            deleted=0,
            position=0,
        )
    )
    db.session.flush()


def _element(bid: str, block_bid: str) -> None:
    db.session.add(
        LearnGeneratedElement(
            element_bid=bid,
            progress_record_bid=RECORD,
            user_bid=USER,
            generated_block_bid=block_bid,
            outline_item_bid=OUTLINE,
            shifu_bid=SHIFU,
            run_session_bid="run",
            run_event_seq=1,
            event_type="element",
            role="teacher",
            element_index=0,
            element_type="text",
            element_type_code=213,
            change_type="render",
            target_element_bid="",
            is_renderable=0,
            is_new=1,
            is_marker=0,
            sequence_number=1,
            is_speakable=1,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=1,
            content_text="x",
            payload="{}",
            status=1,
        )
    )


_BEFORE_B1 = {
    "messages": 0,
    "memory": {},
    "pending": [],
    "answers": {},
    "turn": 0,
    "finished": False,
}
_WAITING = {
    "messages": 2,
    "memory": {},
    "pending": [{"tool_call_id": "q1", "spec": _QUESTION.model_dump(mode="json")}],
    "answers": {},
    "turn": 1,
    "finished": False,
}
_AFTER = {
    "messages": 4,
    "memory": {"way": "Left"},
    "pending": [],
    "answers": {},
    "turn": 2,
    "finished": False,
}


def _lesson() -> None:
    """B1 asked the question, B2 received the answer "Left", B3 carried on; a follow-up between."""
    _record()
    _block("B1", checkpoint=_BEFORE_B1, values=[])
    _block("B2", checkpoint=_WAITING, values=["Left"])
    _block("ASK", checkpoint=None, block_type=BLOCK_TYPE_MDASK_VALUE)
    _block("B3", checkpoint=_AFTER, values=[])
    db.session.commit()


def _plan(anchor: str, *, answering: bool) -> rewind.RewindPlan | None:
    return rewind.plan_rewind(
        user_bid=USER, outline_bid=OUTLINE, anchor=anchor, answering=answering
    )


def test_answering_a_question_again_goes_back_to_the_turn_that_received_the_answer(
    app: object,
) -> None:
    with app.app_context():
        _clean()
        _lesson()
        plan = _plan("B1", answering=True)

    assert plan is not None
    assert plan.checkpoint == _WAITING
    # The learner's new answer, not the old one.
    assert plan.replay_values is None
    # From the answer's turn on; the follow-up is kept, as 1.0 keeps it.
    assert plan.retired_block_bids == ["B2", "B3"]


def test_regenerating_content_goes_back_to_its_own_turn_with_its_own_input(
    app: object,
) -> None:
    with app.app_context():
        _clean()
        _lesson()
        plan = _plan("B2", answering=False)

    assert plan is not None
    assert plan.checkpoint == _WAITING
    assert plan.replay_values == ["Left"]
    assert plan.retired_block_bids == ["B2", "B3"]


def test_an_element_identifier_finds_its_block(app: object) -> None:
    """The browser sends an element's identifier for content, 1.0 accepts either, so does this."""
    with app.app_context():
        _clean()
        _lesson()
        _element("E3", "B3")
        db.session.commit()
        plan = _plan("E3", answering=False)

    assert plan is not None
    assert plan.checkpoint == _AFTER
    assert plan.retired_block_bids == ["B3"]


def test_a_question_never_answered_has_nothing_to_take_back(app: object) -> None:
    with app.app_context():
        _clean()
        _record()
        _block("B1", checkpoint=_BEFORE_B1, values=[])
        db.session.commit()
        assert _plan("B1", answering=True) is None


def test_a_turn_written_before_checkpoints_cannot_be_taken_back(app: object) -> None:
    with app.app_context():
        _clean()
        _record()
        _block("B1", checkpoint=None)
        _block("B2", checkpoint=None)
        db.session.commit()
        with pytest.raises(rewind.RewindUnavailableError):
            _plan("B1", answering=True)
        with pytest.raises(rewind.RewindUnavailableError):
            _plan("B2", answering=False)


def test_a_block_from_before_a_reset_cannot_be_taken_back(app: object) -> None:
    with app.app_context():
        _clean()
        _record(status=LEARN_STATUS_RESET)
        _block("B1", checkpoint=_BEFORE_B1, values=[])
        _block("B2", checkpoint=_WAITING, values=["Left"])
        db.session.commit()
        with pytest.raises(rewind.RewindUnavailableError):
            _plan("B1", answering=True)


def test_retiring_touches_only_the_superseded_rows(app: object) -> None:
    with app.app_context():
        _clean()
        _lesson()
        for block_bid in ("B1", "B2", "ASK", "B3"):
            _element(f"el-{block_bid}", block_bid)
        db.session.commit()

        rewind.stage_retirement(
            rewind.RewindPlan(
                checkpoint={}, replay_values=None, retired_block_bids=["B2", "B3"]
            ),
            user_bid=USER,
            outline_bid=OUTLINE,
        )
        db.session.commit()

        blocks = {
            b.generated_block_bid: b.status for b in LearnGeneratedBlock.query.all()
        }
        elements = {
            e.generated_block_bid: e.status for e in LearnGeneratedElement.query.all()
        }

    assert blocks == {"B1": 1, "B2": 0, "ASK": 1, "B3": 0}
    assert elements == {"B1": 1, "B2": 0, "ASK": 1, "B3": 0}
