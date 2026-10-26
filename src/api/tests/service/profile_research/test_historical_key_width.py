"""Resume the old Profile key width without relaxing new authoring or tool limits."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from flaskr.api.markdownflow import (
    InteractionSpec,
    PendingInteraction,
    ScriptBundle,
    Session,
    UnrepresentableInteractionError,
    render_question,
)
from flaskr.service.profile_research.document import validate_profile_research_document
from flaskr.service.profile_research.session import (
    PROFILE_ONBOARDING_PURPOSE,
    ProfileResearchError,
    ProfileResearchSessionNotFound,
    ProfileResearchValidationError,
    _ProfileResearchSession,
)
from markdownflow.engine.script import render_first_prompt
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)

from tests.service.profile_research.test_v2_runtime import (
    StreamChunks,
    _finish,
    _finished,
    _run,
    _runtime,
    _tool_returns,
)

if TYPE_CHECKING:
    from flaskr.service.profile_research.runtime import ProfileResearchRuntime
    from pydantic_ai.models.function import AgentInfo


def _saved_runtime(
    *, legacy: bool = True, width: int = 256, placeholder: str | None = "Answer"
) -> tuple[ProfileResearchRuntime, dict[str, Any], str, list[int]]:
    model_calls: list[int] = []

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        model_calls.append(len(messages))
        if _finished(messages):
            yield " "
        else:
            assert (
                _tool_returns(messages)[0].content == "Learner wrote: Accepted answer"
            )
            yield _finish()

    _app, runtime, _factories = _runtime(model)
    key = "q" * width
    source = "?[%{{" + key + "}}...Answer]"
    session = _ProfileResearchSession(
        session_id="historical-width",
        user_bid="v2-learner",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        document=source,
        model="test-model",
        temperature=0.3,
        output_language="en-US",
        config_revision=12,
        turn_index=1,
        awaiting_input=True,
        last_request_id="previous",
        last_user_input={key: ["Earlier answer"]},
    )
    bundle = ScriptBundle(script=source)
    arguments = {
        "type": "text",
        "prompt": "Original question?",
        "placeholder": placeholder,
        "variable" if legacy else "question": " " + key + " " if legacy else key,
    }
    native = Session(
        id=session.session_id,
        user_id=session.user_bid,
        script=bundle,
        messages=[
            ModelRequest(parts=[UserPromptPart(render_first_prompt(bundle, {}))]),
            ModelResponse(parts=[ToolCallPart("interact", arguments, "old-question")]),
        ],
        pending=[
            PendingInteraction(
                "old-question",
                InteractionSpec(
                    type="text",
                    prompt="Original question?",
                    question=key,
                    placeholder=placeholder,
                ),
            )
        ],
    )
    session.engine_session = native.to_dict()
    if legacy:
        spec = session.engine_session["pending"][0]["spec"]
        spec["variable"] = spec.pop("question")
        session.engine_session["initial_variables"] = session.engine_session.pop(
            "initial_memory"
        )
    runtime.store.save(session)
    return runtime, session.to_view(), key, model_calls


@pytest.mark.parametrize("placeholder", ["Answer", None])
def test_legacy_width_survives_cache_render_submission_and_exact_replay(
    placeholder: str | None,
) -> None:
    runtime, view, key, factories = _saved_runtime(placeholder=placeholder)
    restored = runtime.store.load(view["session_id"])
    assert restored.last_user_input == {key: ["Earlier answer"]}
    original_call = restored.engine_session["messages"][1]
    shown = _run(runtime, view, request_id="show")
    assert key in str(shown)
    assert len(key) == 256
    assert not factories
    cursor = runtime.store.load(view["session_id"]).turn_index
    result = _run(
        runtime,
        view,
        values={key: ["Accepted answer"]},
        index=cursor,
        request_id="answer",
        expected_interaction_id="old-question",
    )
    count = len(factories)
    replay = _run(
        runtime,
        view,
        values={key: ["Accepted answer"]},
        index=cursor,
        request_id="answer",
        expected_interaction_id="old-question",
    )
    assert result == replay
    assert len(factories) == count
    saved = runtime.store.load(view["session_id"])
    assert saved.done
    assert saved.memory[key] == "Accepted answer"
    assert saved.last_user_input == {key: ["Accepted answer"]}
    assert saved.engine_session["messages"][1] == original_call


def test_current_schema_cannot_claim_legacy_key_width() -> None:
    runtime, view, key, factories = _saved_runtime(legacy=False)
    with pytest.raises(ProfileResearchError, match="cannot resume"):
        _run(runtime, view, request_id="show")
    with pytest.raises(ProfileResearchValidationError, match="too long"):
        _run(
            runtime,
            view,
            values={key: ["Accepted answer"]},
            request_id="fresh",
            expected_interaction_id="old-question",
        )
    assert not factories


def test_cache_never_accepts_more_than_the_previously_supported_width() -> None:
    runtime, view, _key, factories = _saved_runtime(width=257)
    with pytest.raises(ProfileResearchSessionNotFound):
        runtime.store.load(view["session_id"])
    assert not factories


def test_new_authoring_and_default_renderer_keep_the_255_limit() -> None:
    question = "q" * 256
    with pytest.raises(ProfileResearchValidationError, match="question is too long"):
        validate_profile_research_document("?[%{{" + question + "}}...Answer]")
    with pytest.raises(UnrepresentableInteractionError):
        render_question(
            InteractionSpec(
                type="text", prompt="Question?", question=question, placeholder="Answer"
            )
        )
