"""Exercise deferred questions through the formal classroom and reload paths."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from flaskr.api import langfuse_markdownflow
from flaskr.api.langfuse import MockClient
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import lesson_entry
from flaskr.service.learn.agent.rewind import read_turn_record
from flaskr.service.learn.elements.run_adapter import (
    ListenElementRunAdapter,
    get_listen_element_record,
)
from flaskr.service.learn.host import lesson as host_lesson
from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.service.user.repository import create_user_entity
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from tests.service.learn import published_course

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from flask import Flask
    from flaskr.service.metering.api import UsageContext
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

runtime_dependencies = published_course.runtime_dependencies


@pytest.mark.usefixtures("runtime_dependencies")
@pytest.mark.parametrize(
    "prompts", [("Question A?", "Question B?"), ("Same?", "Same?")]
)
def test_multiple_deferred_questions_keep_controls_and_individual_answers(
    app: Flask, monkeypatch: pytest.MonkeyPatch, prompts: tuple[str, str]
) -> None:
    course = published_course._seed_course(app)
    with app.app_context(), unit_of_work():
        create_user_entity(
            user_bid=course.user_bid, identify=course.user_bid, nickname="Learner"
        )
    monkeypatch.setattr(langfuse_markdownflow, "get_langfuse_client", MockClient)

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        calls = [
            part.tool_name
            for message in messages
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
        if "finish" in calls:
            return
        if "interact" in calls:
            yield "Completed."
            yield {
                0: DeltaToolCall(
                    name="finish", tool_call_id="finish", json_args='{"summary":"Done"}'
                )
            }
            return
        yield "Teaching before both questions."
        yield "\n\n" + "\n\n".join(prompts)
        yield {
            index: DeltaToolCall(
                name="interact",
                tool_call_id=f"question-{index}",
                json_args=json.dumps({"type": "text", "question": prompt}),
            )
            for index, prompt in enumerate(prompts)
        }

    class Gateway(FunctionModel):
        def set_usage_context(self, _context: UsageContext) -> None:
            pass

    gateway = Gateway(stream_function=model)
    monkeypatch.setattr(lesson_entry, "GatewayModel", lambda *_args, **_kwargs: gateway)

    def run(
        answer: str | None = None, *, anchor: str | None = None
    ) -> list[ElementDTO]:
        with app.app_context():
            adapter = ListenElementRunAdapter(
                app,
                shifu_bid=course.course_bid,
                outline_bid=course.outline_bid,
                user_bid=course.user_bid,
                persist_only_final=True,
            )
            events = host_lesson._lesson_events(
                app=app,
                user_bid=course.user_bid,
                shifu_bid=course.course_bid,
                outline_bid=course.outline_bid,
                user_input=answer,
                input_type=None,
                reload_generated_block_bid=None,
                reload_element_bid=anchor,
                listen=False,
                learning_mode="read",
                preview_mode=False,
                stop_event=None,
                element_adapter=adapter,
                heartbeat_interval=0.5,
            )
            return [
                event.content
                for event in events
                if isinstance(event.content, ElementDTO)
                and event.content.element_type == ElementType.INTERACTION
            ]

    def controls() -> list[ElementDTO]:
        with app.app_context():
            history = get_listen_element_record(
                app,
                course.course_bid,
                course.outline_bid,
                course.user_bid,
                preview_mode=False,
            )
            return [
                e for e in history.elements if e.element_type == ElementType.INTERACTION
            ]

    run()
    first, second = controls()
    assert first.element_bid != second.element_bid
    assert [
        first.payload.interaction_question,
        second.payload.interaction_question,
    ] == list(prompts)
    redisplayed = run("Answer A", anchor=first.element_bid)
    assert len(redisplayed) == 1
    assert redisplayed[0].element_bid != second.element_bid

    reloaded = controls()
    assert [e.element_bid for e in reloaded] == [first.element_bid, second.element_bid]
    assert json.loads(reloaded[0].payload.user_input)["inputText"] == "Answer A"
    assert not reloaded[1].payload.user_input

    run("Answer B", anchor=second.element_bid)
    assert [json.loads(e.payload.user_input)["inputText"] for e in controls()] == [
        "Answer A",
        "Answer B",
    ]
    with app.app_context():
        blocks = (
            LearnGeneratedBlock.query.filter_by(
                user_bid=course.user_bid,
                shifu_bid=course.course_bid,
                outline_item_bid=course.outline_bid,
                status=1,
                deleted=0,
            )
            .order_by(LearnGeneratedBlock.id)
            .all()
        )
        records = [record for block in blocks if (record := read_turn_record(block))]
        assert [record["question_ids"] for record in records] == [
            ["question-0", "question-1"],
            ["question-1"],
            [],
        ]
        assert [record["answered_question_id"] for record in records] == [
            None,
            "question-0",
            "question-1",
        ]
