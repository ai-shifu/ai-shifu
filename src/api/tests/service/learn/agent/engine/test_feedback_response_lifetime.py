"""Keep rejection identities unique until retry and saved-history projection end."""

import gc
import weakref
from collections.abc import AsyncIterator

import pytest
from flaskr.service.learn.agent.engine import Engine, InteractionResponseTurn, Session
from flaskr.service.learn.agent.engine.direction import (
    direction_history,
    feedback_retry_history,
)
from flaskr.service.learn.agent.engine.tools import Deps
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .test_direction_feedback import _call, _collect, _text


def test_projected_rejection_stays_alive_only_for_its_turn() -> None:
    """Prevent ID reuse after SDK projection without retaining a finished turn."""

    def project_turn() -> weakref.ReferenceType[ModelResponse]:
        """Finish the owner scope, including assertion temporaries, before release."""
        deps = Deps(memory={}, user_memory={})
        rejected = ModelResponse(
            parts=[TextPart("Undisplayed draft"), ToolCallPart("interact", {}, "bad")]
        )
        reference = weakref.ref(rejected)
        deps.hide_feedback_response(rejected)
        messages = [
            rejected,
            ModelRequest(
                parts=[RetryPromptPart("Invalid feedback", tool_call_id="bad")]
            ),
        ]
        projected = feedback_retry_history(messages, deps.hidden_feedback_responses)
        assert projected[0] is not rejected
        del rejected, messages
        gc.collect()
        assert reference() is not None

        accepted = ModelResponse(parts=[TextPart("Complete replacement")])
        assert id(accepted) not in deps.hidden_feedback_responses
        saved = direction_history(
            [*projected, accepted], {}, deps.hidden_feedback_responses
        )
        assert saved[-1] is accepted
        assert (
            "Undisplayed draft"
            not in ModelMessagesTypeAdapter.dump_json(saved).decode()
        )
        return reference

    reference = project_turn()
    gc.collect()
    assert reference() is None


@pytest.mark.anyio
@pytest.mark.parametrize("reload", [False, True])
async def test_native_retries_release_rejections_after_complete_delivery(
    reload: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retain all rejected SDK objects across retries, then release at turn end."""
    references = []
    hide = Deps.hide_feedback_response

    def track(deps: Deps, response: ModelResponse) -> None:
        """Observe lifetime through weak references without keeping objects alive."""
        references.append(weakref.ref(response))
        hide(deps, response)

    monkeypatch.setattr(Deps, "hide_feedback_response", track)
    script = "Answer side questions briefly.\nExplain a loop.\n?[...Answer]\n"
    question = "What does a loop condition do?"
    calls = 0

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator:
        """Produce two rejected drafts followed by one complete clarification."""
        nonlocal calls
        calls += 1
        args = {"type": "text", "prompt": "", "placeholder": "Answer"}
        if calls == 1:
            yield _call(args, "original")
            return
        if calls == 4:
            gc.collect()
            assert references
            assert all(ref() is not None for ref in references)
        yield "Complete clarification" if calls == 4 else "Undisplayed draft"
        yield _call(
            {
                **args,
                "review": {
                    "answer_id": "original" if calls == 4 else "invalid",
                    "phase": "clarification",
                    "submission_quote": question,
                    "reason": "Answer the side question and retain the pending exercise.",
                },
            },
            f"reply-{calls}",
        )

    engine = Engine(
        FunctionModel(stream_function=stream), feedback_contract=True, request_limit=3
    )
    session = await engine.new_session(script)
    await _collect(engine.run_turn(session))
    if reload:
        session = Session.loads(session.dumps())
    before = ModelMessagesTypeAdapter.dump_json(session.messages)
    count = len(session.messages)
    events = await _collect(
        engine.run_turn(session, InteractionResponseTurn(text=question))
    )
    assert _text(events) == "Complete clarification"
    assert session.pending[0].tool_call_id == "reply-4"
    assert calls == 4
    assert ModelMessagesTypeAdapter.dump_json(session.messages[:count]) == before
    assert "Undisplayed draft" not in session.dumps()
    assert not session.all_memory()
    gc.collect()
    assert all(ref() is None for ref in references)
