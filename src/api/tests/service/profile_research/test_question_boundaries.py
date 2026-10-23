"""The default questionnaire presents each authored control exactly at its static block."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from markdown_flow import BlockType, MarkdownFlow
from pydantic_ai.messages import ModelRequest, RetryPromptPart

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _finish,
    _finished,
    _interact,
    _run,
    _runtime,
    _start,
    _terminal,
    _tool_returns,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


def test_default_questionnaire_retries_a_premature_question_until_its_authored_block() -> (
    None
):
    source = (
        Path(__file__).resolve().parents[4]
        / "i18n/en-US/modules/profile-onboarding.json"
    )
    document = json.loads(source.read_text(encoding="utf-8"))["admin"][
        "defaultMarkdownflow"
    ]
    blocks = MarkdownFlow(document).get_all_blocks()
    assert blocks[0].block_type == BlockType.CONTENT
    assert "then ask the first question" in blocks[0].content
    assert blocks[1].block_type == BlockType.INTERACTION
    first_content_calls = 0
    retries: list[RetryPromptPart] = []

    async def script(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        nonlocal first_content_calls
        if factories[-1] == 0:
            first_content_calls += 1
            if first_content_calls == 1:
                yield {
                    0: _interact(
                        call_id="premature-name",
                        variable="sys_user_nickname",
                        prompt="What would you like me to call you?",
                    )
                }
            else:
                retries.extend(
                    part
                    for message in messages
                    if isinstance(message, ModelRequest)
                    for part in message.parts
                    if isinstance(part, RetryPromptPart)
                )
                yield "Welcome! I can adapt these courses to your background. What should I call you?"
        elif _finished(messages):
            yield " "
        elif _tool_returns(messages):
            yield _finish()
        else:
            yield {
                0: _interact(
                    call_id="official-name",
                    variable="sys_user_nickname",
                    prompt="What would you like me to call you?",
                )
            }

    _app, runtime, factories = _runtime(script)
    view = _start(runtime, document)
    introduction = _run(runtime, view)

    assert first_content_calls == 2
    assert retries
    assert not any(event["event_type"] == "interaction" for event in introduction)
    assert _terminal(introduction)["next_block_index"] == 1
    assert _terminal(introduction)["awaiting_input"] is False
    assert runtime.store.load(view["session_id"]).variables == {}

    question = _run(runtime, view, index=1, request_id="render-name")
    interactions = [event for event in question if event["event_type"] == "interaction"]
    assert len(interactions) == 1
    assert interactions[0]["interaction_id"] == "official-name"
    assert _terminal(question)["next_block_index"] == 1
    assert _terminal(question)["awaiting_input"] is True

    answer = _run(
        runtime,
        view,
        index=1,
        values={"sys_user_nickname": ["River"]},
        request_id="name",
        expected_interaction_id="official-name",
    )
    assert not any(event["event_type"] == "interaction" for event in answer)
    assert _terminal(answer)["next_block_index"] == 2
    assert runtime.store.load(view["session_id"]).variables == {
        "sys_user_nickname": "River"
    }
