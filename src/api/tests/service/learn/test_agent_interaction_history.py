"""Exercise historical answer projection through the real database reader."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.learn.agent.legacy_protocol import render_interaction
from flaskr.service.learn.elements.history import (
    get_final_elements_for_generated_block,
)
from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from markdownflow.engine.interaction import InteractionSpec

if TYPE_CHECKING:
    from collections.abc import Iterator


def _record(pending: list, values: list[str]) -> str:
    return json.dumps(
        {
            "agent_turn": {
                "version": 1,
                "checkpoint": {"pending": pending},
                "values": values,
            }
        }
    )


@pytest.fixture
def classroom(app: object) -> Iterator[str]:
    with app.app_context():
        scope = uuid.uuid4().hex
        try:
            yield scope
        finally:
            db.session.rollback()
            LearnGeneratedElement.query.filter_by(user_bid=scope).delete()
            LearnGeneratedBlock.query.filter_by(user_bid=scope).delete()
            db.session.commit()


def _block(
    scope: str, bid: str, position: int, **kwargs: object
) -> LearnGeneratedBlock:
    block = LearnGeneratedBlock(
        user_bid=scope,
        shifu_bid=scope,
        outline_item_bid=scope,
        progress_record_bid=scope,
        generated_block_bid=bid,
        position=position,
        type=BLOCK_TYPE_MDCONTENT_VALUE,
        status=1,
        generated_content="Teacher prose must never become an answer.",
        block_content_conf=_record([], []),
    )
    for key, value in kwargs.items():
        setattr(block, key, value)
    db.session.add(block)
    return block


def _control(
    scope: str, block: LearnGeneratedBlock, content: str, index: int = 0
) -> None:
    db.session.add(
        LearnGeneratedElement(
            user_bid=scope,
            shifu_bid=scope,
            outline_item_bid=scope,
            progress_record_bid=scope,
            generated_block_bid=block.generated_block_bid,
            element_bid=block.generated_block_bid + f"-control-{index}",
            event_type="element",
            element_type="interaction",
            sequence_number=index + 1,
            is_final=1,
            content_text=content,
            payload="{}",
            status=1,
        )
    )


def _history_input(block: LearnGeneratedBlock) -> str | None:
    elements = get_final_elements_for_generated_block(
        generated_block_bid=block.generated_block_bid
    )
    assert len(elements) == 1
    return elements[0].payload.user_input if elements[0].payload else None


@pytest.mark.parametrize(
    ("kind", "options", "values", "expected"),
    [
        (
            "text",
            [],
            ["  First, second\nThird  "],
            {"selectedValues": [], "inputText": "  First, second\nThird  "},
        ),
        (
            "single",
            [{"display": "Visible A", "value": "a,b"}],
            ["Visible A"],
            {"selectedValues": ["a,b"], "inputText": ""},
        ),
        (
            "multi",
            [{"display": "A", "value": "a,b"}, {"display": "B", "value": "c"}],
            ["a,b", "c"],
            {"selectedValues": ["a,b", "c"], "inputText": ""},
        ),
        (
            "single_or_text",
            [{"display": "A", "value": "a"}],
            ["My own answer"],
            {"selectedValues": [], "inputText": "My own answer"},
        ),
        (
            "multi_or_text",
            [{"display": "A", "value": "a"}],
            ["a", "Custom, answer"],
            {"selectedValues": ["a"], "inputText": "Custom, answer"},
        ),
    ],
)
def test_reload_recovers_submitted_values(
    classroom: str,
    kind: str,
    options: list[dict[str, str]],
    values: list[str],
    expected: dict[str, object],
) -> None:
    spec = InteractionSpec(
        type=kind, prompt="Question", placeholder="Answer", options=options
    )
    question = _block(classroom, classroom + "-q", 0)
    _control(classroom, question, render_interaction(spec))
    _block(
        classroom,
        classroom + "-a",
        1,
        block_content_conf=_record(
            [{"tool_call_id": "call-q", "spec": spec.model_dump()}], values
        ),
    )
    db.session.commit()
    db.session.expire_all()

    expected["buttonText"] = "a,b" if kind == "single" else ""
    assert json.loads(_history_input(question)) == expected
    assert json.loads(_history_input(question)) == expected  # A second read is stable.
    assert question.generated_content == "Teacher prose must never become an answer."


@pytest.mark.parametrize(
    "boundary",
    [
        "user",
        "course",
        "lesson",
        "attempt",
        "inactive",
        "deleted",
        "mismatch",
        "malformed",
        "unusable",
        "no_pending",
        "confirm",
    ],
)
def test_unrelated_or_unproven_inputs_stay_empty(classroom: str, boundary: str) -> None:
    spec = InteractionSpec(type="text", prompt="Question", placeholder="Answer")
    question = _block(classroom, classroom + "-q", 0)
    _control(classroom, question, render_interaction(spec))
    pending = [{"tool_call_id": "call-q", "spec": spec.model_dump()}]
    answer = _block(
        classroom,
        classroom + "-a",
        1,
        block_content_conf=_record(pending, ["Private answer"]),
    )
    fields = {
        "user": "user_bid",
        "course": "shifu_bid",
        "lesson": "outline_item_bid",
        "attempt": "progress_record_bid",
    }
    if boundary in fields:
        setattr(answer, fields[boundary], "unrelated")
    elif boundary == "inactive":
        answer.status = 0
    elif boundary == "deleted":
        answer.deleted = 1
    elif boundary == "mismatch":
        pending[0]["spec"]["placeholder"] = "Different control"
        answer.block_content_conf = _record(pending, ["Private answer"])
    elif boundary == "malformed":
        answer.block_content_conf = '{"agent_turn": {"version": 999}}'
    elif boundary == "unusable":
        answer.block_content_conf = _record(pending, ["  "])
    elif boundary == "no_pending":
        answer.block_content_conf = _record([], ["Remark, not an answer"])
    elif boundary == "confirm":
        pending[0]["spec"] = {"type": "confirm", "prompt": "Continue"}
        answer.block_content_conf = _record(pending, ["continue"])
    db.session.commit()
    assert not _history_input(question)
    # Clean even the deliberately foreign user row.
    db.session.delete(answer)
    db.session.commit()


@pytest.mark.parametrize("reused_call_id", [False, True])
def test_same_named_control_keeps_each_historical_answer(
    classroom: str, reused_call_id: bool
) -> None:
    spec = InteractionSpec(
        type="text", prompt="Question", variable="answer", placeholder="Answer"
    )
    first = _block(classroom, classroom + "-first", 0)
    _control(classroom, first, render_interaction(spec))
    pending = [{"tool_call_id": "call-first", "spec": spec.model_dump()}]
    second = _block(
        classroom,
        classroom + "-second",
        1,
        block_content_conf=_record(pending, ["First answer"]),
    )
    _control(classroom, second, render_interaction(spec))
    pending[0]["tool_call_id"] = "call-first" if reused_call_id else "call-second"
    _block(
        classroom,
        classroom + "-third",
        2,
        block_content_conf=_record(pending, ["Second answer"]),
    )
    db.session.commit()
    assert json.loads(_history_input(first))["inputText"] == "First answer"
    assert json.loads(_history_input(second))["inputText"] == "Second answer"


def test_legacy_interaction_still_reads_its_own_answer(classroom: str) -> None:
    question = _block(
        classroom,
        classroom + "-legacy",
        0,
        type=BLOCK_TYPE_MDINTERACTION_VALUE,
        generated_content="Previously submitted",
        block_content_conf="?[...Answer]",
    )
    _control(classroom, question, "?[...Answer]")
    db.session.commit()
    assert _history_input(question) == "Previously submitted"


@pytest.mark.parametrize("identical", [False, True])
def test_parallel_questions_keep_element_specific_answers(
    classroom: str, identical: bool
) -> None:
    first = InteractionSpec(type="text", prompt="First", placeholder="First answer")
    second = (
        first
        if identical
        else InteractionSpec(type="text", prompt="Second", placeholder="Second answer")
    )
    question = _block(classroom, classroom + "-parallel", 0)
    _control(classroom, question, render_interaction(first), 0)
    _control(classroom, question, render_interaction(second), 1)
    pending = [
        {"tool_call_id": "call-first", "spec": first.model_dump()},
        {"tool_call_id": "call-second", "spec": second.model_dump()},
    ]
    next_question = _block(
        classroom,
        classroom + "-next",
        1,
        block_content_conf=_record(pending, ["First submitted"]),
    )
    _control(classroom, next_question, render_interaction(second))
    _block(
        classroom,
        classroom + "-last",
        2,
        block_content_conf=_record(pending[1:], ["Second submitted"]),
    )
    db.session.commit()
    elements = get_final_elements_for_generated_block(
        generated_block_bid=question.generated_block_bid
    )
    assert len(elements) == 2
    assert [
        json.loads(element.payload.user_input)["inputText"] for element in elements
    ] == ["First submitted", "Second submitted"]
    assert json.loads(_history_input(next_question))["inputText"] == "Second submitted"


def test_omitted_placeholder_survives_locale_change(
    classroom: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = InteractionSpec(type="text", prompt="Question")
    monkeypatch.setattr(
        "flaskr.api.markdownflow._",
        lambda _key: "Original locale hint",
    )
    question = _block(classroom, classroom + "-locale", 0)
    _control(classroom, question, render_interaction(spec))
    _block(
        classroom,
        classroom + "-answer",
        1,
        block_content_conf=_record(
            [{"tool_call_id": "call-locale", "spec": spec.model_dump()}],
            ["Retained answer"],
        ),
    )
    db.session.commit()
    monkeypatch.setattr("flaskr.api.markdownflow._", lambda _key: "New locale hint")
    assert json.loads(_history_input(question))["inputText"] == "Retained answer"


@pytest.mark.parametrize("matching_owner", [True, False])
def test_blank_progress_uses_only_its_owned_active_block(
    classroom: str, matching_owner: bool
) -> None:
    spec = InteractionSpec(type="text", prompt="Question", placeholder="Answer")
    question = _block(classroom, classroom + "-blank", 0)
    _control(classroom, question, render_interaction(spec))
    LearnGeneratedElement.query.filter_by(user_bid=classroom).update(
        {"progress_record_bid": ""}
    )
    _block(
        classroom,
        classroom + "-answer",
        1,
        block_content_conf=_record(
            [{"tool_call_id": "call-blank", "spec": spec.model_dump()}],
            ["Retained answer"],
        ),
    )
    if not matching_owner:
        question.user_bid = "unrelated"
    db.session.commit()
    value = _history_input(question)
    if matching_owner:
        assert json.loads(value)["inputText"] == "Retained answer"
    else:
        assert not value
    db.session.delete(question)
    db.session.commit()
