"""Engine tests driven by pydantic-ai's FunctionModel: no network, deterministic."""

import json
from collections.abc import AsyncIterator, Callable

import pytest
from flaskr.service.learn.agent.engine import (
    ContentDelta,
    ContinueTurn,
    Engine,
    ErrorEvent,
    InMemoryMemoryStore,
    InteractionRequest,
    InteractionResponseTurn,
    MemoryUpdated,
    MessageTurn,
    NarrationDelta,
    Runner,
    SegmentEnd,
    SegmentStart,
    Session,
    SQLiteSessionStore,
    ToolCall,
    TurnDone,
)
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio

# What pydantic-ai's FunctionModel expects a streaming model double to yield: either a piece
# of text or the tool-call deltas for one step, keyed by the call's index within that step.
StreamChunks = AsyncIterator[str | dict[int, DeltaToolCall]]

SPEC = {
    "type": "single_or_text",
    "prompt": "How do you feel?",
    "options": [
        {"display": "Good", "value": "good"},
        {"display": "Bad", "value": "bad"},
    ],
    "variable": "feeling",
}


def _last_tool_return(messages: list[ModelMessage]) -> ToolReturnPart | None:
    for m in reversed(messages):
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, ToolReturnPart):
                    return p
            return None
    return None


async def scripted(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
    """Turn 1: text + interact. After the answer: remember (user scope) then text + a slide."""
    ret = _last_tool_return(messages)
    requests = [m for m in messages if isinstance(m, ModelRequest)]
    if ret is None and len(requests) > 1:  # continue / free-text turn
        yield "Continuing.\n"
    elif ret is None:
        yield "Hello "
        yield "learner.\n"
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(SPEC),
                tool_call_id="call_interact_1",
            )
        }
    elif ret.tool_name == "interact":
        assert "Learner chose: good" in str(ret.content)
        yield {
            0: DeltaToolCall(
                name="remember",
                tool_call_id="call_rem_1",
                json_args=json.dumps({"key": "pace", "value": "slow", "scope": "user"}),
            )
        }
    elif ret.tool_name == "remember":
        yield "Great, moving on.\n"
        yield "<div>slide one</div>\n"
        yield "This is slide one.\n"


def make_engine(**kw: object) -> Engine:
    return Engine(FunctionModel(stream_function=scripted), **kw)


async def collect(agen: AsyncIterator[object]) -> list[object]:
    return [e async for e in agen]


async def test_first_turn_pauses_on_interact() -> None:
    engine = make_engine()
    s = await engine.new_session("Greet the learner, then ask how they feel.")
    events = await collect(engine.run_turn(s))
    kinds = [type(e).__name__ for e in events]
    assert kinds == [
        "ContentDelta",
        "ContentDelta",
        "ToolCall",
        "InteractionRequest",
        "TurnDone",
    ]
    assert (
        "".join(e.text for e in events if isinstance(e, ContentDelta))
        == "Hello learner.\n"
    )
    req = next(e for e in events if isinstance(e, InteractionRequest))
    assert req.id == "call_interact_1"
    assert req.spec.variable == "feeling"
    assert events[-1].reason == "interaction"
    assert s.pending[0].tool_call_id == "call_interact_1"
    assert s.started
    assert s.turn == 1


async def test_resume_records_variable_and_memory_tool_without_replaying_call() -> None:
    store = InMemoryMemoryStore()
    engine = make_engine(memory_store=store)
    s = await engine.new_session("script", user_id="u1")
    await collect(engine.run_turn(s))
    events = await collect(engine.run_turn(s, InteractionResponseTurn(values=["Good"])))
    kinds = [type(e).__name__ for e in events]
    assert kinds[0] == "MemoryUpdated"
    assert events[0].source == "interaction"
    assert events[0].value == "good"
    assert "InteractionRequest" not in kinds
    assert [e for e in events if isinstance(e, ToolCall)]
    assert all(e.name == "remember" for e in events if isinstance(e, ToolCall))
    mem = [e for e in events if isinstance(e, MemoryUpdated) and e.source == "tool"]
    assert mem
    assert mem[0].key == "pace"
    assert mem[0].scope == "user"
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "end"
    assert s.memory == {"feeling": "good"}
    assert s.user_memory == {"pace": "slow"}
    assert not s.pending
    assert await store.load("u1") == {"pace": "slow"}


async def test_listen_mode_segments() -> None:
    engine = make_engine()
    s = await engine.new_session("script", listen_mode=True)
    await collect(engine.run_turn(s))
    events = await collect(engine.run_turn(s, InteractionResponseTurn(values=["good"])))
    seg = [
        e for e in events if isinstance(e, (SegmentStart, NarrationDelta, SegmentEnd))
    ]
    assert isinstance(seg[0], SegmentStart)
    assert seg[0].visual is None
    assert isinstance(seg[1], NarrationDelta)
    assert seg[1].text == "Great, moving on.\n"
    assert isinstance(seg[2], SegmentEnd)
    assert seg[2].narration == "Great, moving on.\n"
    assert isinstance(seg[3], SegmentStart)
    assert seg[3].visual.kind == "html"
    assert isinstance(seg[4], NarrationDelta)
    assert seg[4].segment_id == seg[3].segment_id
    assert isinstance(seg[5], SegmentEnd)
    assert seg[5].narration == "This is slide one.\n"
    assert seg[0].segment_id != seg[3].segment_id


async def test_wrong_turn_kinds_yield_errors() -> None:
    engine = make_engine()
    s = await engine.new_session("script")
    events = await collect(engine.run_turn(s, InteractionResponseTurn(values=["x"])))
    assert isinstance(events[0], ErrorEvent)
    await collect(engine.run_turn(s))
    events = await collect(engine.run_turn(s, ContinueTurn()))
    assert isinstance(events[0], ErrorEvent)
    assert "pending" in events[0].message
    events = await collect(
        engine.run_turn(s, InteractionResponseTurn(id="nope", values=["x"]))
    )
    assert isinstance(events[0], ErrorEvent)


async def test_instructions_include_syntax_note_only_for_v1_scripts() -> None:
    seen: list[str] = []

    async def spy(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        seen.append(messages[0].instructions or "")
        yield "ok\n"

    engine = Engine(FunctionModel(stream_function=spy))
    await collect(engine.run_turn(await engine.new_session("plain prose script")))
    await collect(
        engine.run_turn(await engine.new_session("a\n---\nb ?[%{{v}} A | B]"))
    )
    await collect(engine.run_turn(await engine.new_session("plain", listen_mode=True)))
    assert "Script notation" not in seen[0]
    assert "Listen mode" not in seen[0]
    assert (
        "Screens (HTML visuals)" in seen[0]
    )  # inherited from 1.0, present for the sandbox profile
    assert "Script notation" in seen[1]
    assert "Listen mode" in seen[2]
    assert seen[0].count("You are the runtime") == 1


async def test_runner_persists_between_turns() -> None:
    store = SQLiteSessionStore(":memory:")
    runner = Runner(make_engine(), store)
    s = await runner.new_session("script")
    await collect(runner.run(s.id))
    loaded = await store.load(s.id)
    assert loaded is not None
    assert loaded.pending
    assert loaded.turn == 1
    events = await collect(runner.run(s.id, InteractionResponseTurn(values=["good"])))
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "end"
    loaded = await store.load(s.id)
    assert loaded.memory == {"feeling": "good"}
    assert not loaded.pending
    assert loaded.turn == 2
    events = await collect(runner.run(s.id, MessageTurn(text="why?")))
    assert any(
        isinstance(e, ContentDelta) and e.text == "Continuing.\n" for e in events
    )
    assert isinstance((await collect(runner.run("missing")))[0], ErrorEvent)


async def test_finish_tool_marks_the_session_done() -> None:
    async def ending(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield "That's all for today.\n"
        yield {
            0: DeltaToolCall(
                name="finish",
                json_args=json.dumps({"summary": "learner completed the lesson"}),
                tool_call_id="fin1",
            )
        }

    async def after_finish(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> StreamChunks:
        yield "Goodbye.\n"

    calls = {"n": 0}

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        gen = (
            ending(messages, _info)
            if calls["n"] == 1
            else after_finish(messages, _info)
        )
        async for x in gen:
            yield x

    engine = Engine(FunctionModel(stream_function=model))
    s = await engine.new_session("script")
    events = await collect(engine.run_turn(s))
    kinds = [type(e).__name__ for e in events]
    assert "ToolResult" not in kinds  # finish is not surfaced as a generic tool result
    done = events[-1]
    assert isinstance(done, TurnDone)
    assert done.reason == "finished"
    assert done.summary == "learner completed the lesson"
    assert s.finished is True
    # The tool result goes back to the model like any other, so it takes another turn and writes
    # again. That writing is not the lesson: the lesson ended when it said so.
    said = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert "That's all for today." in said
    assert "Goodbye." not in said
    assert Session.from_dict(s.to_dict()).finished is True


def test_render_profiles_swap_the_html_rules() -> None:
    async def never_called(
        _messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> StreamChunks:
        yield "x"

    e = Engine(FunctionModel(stream_function=never_called))
    sandbox = e.compose_instructions(render="sandbox")
    generic = e.compose_instructions(render="generic", listen_mode=True)
    none = e.compose_instructions(render="none")
    assert "DaisyUI" in sandbox
    assert "timeline" in sandbox
    assert "DaisyUI" not in generic
    assert "plain renderer" in generic
    assert "Listen mode" in generic
    assert "Screens" not in none


async def test_confirm_without_content_is_rejected_and_retried() -> None:
    """A bare `confirm` is bounced back to the model instead of reaching the learner.

    A turn with no content has nothing to pause on, so the model must produce content first.
    Mirrors the deepseek-flash loop seen on the token script.
    """
    from pydantic_ai.messages import RetryPromptPart

    def _has_retry(messages: list[ModelMessage]) -> bool:
        last = messages[-1]
        return isinstance(last, ModelRequest) and any(
            isinstance(p, RetryPromptPart) for p in last.parts
        )

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        ret = _last_tool_return(messages)
        confirm = {
            0: DeltaToolCall(
                name="interact",
                tool_call_id=f"c{len(messages)}",
                json_args=json.dumps({"type": "confirm", "prompt": "Ready?"}),
            )
        }
        if ret is None and not _has_retry(messages):
            yield "Section one.\n"
            yield confirm
        elif (
            ret is not None
            and ret.tool_name == "interact"
            and "pressed continue" in str(ret.content)
        ):
            yield confirm  # the bad move: continue answered with another bare confirm
        elif _has_retry(messages):
            yield "Section two.\n"
            yield confirm
        else:
            msg = f"unexpected model input: {messages[-1]}"
            raise AssertionError(msg)

    engine = Engine(FunctionModel(stream_function=model))
    s = await engine.new_session("one\n---\ntwo")
    first = await collect(engine.run_turn(s))
    req = next(e for e in first if isinstance(e, InteractionRequest))
    assert req.spec.type == "confirm"

    second = await collect(
        engine.run_turn(s, InteractionResponseTurn(id=req.id, values=["continue"]))
    )
    text = "".join(e.text for e in second if isinstance(e, ContentDelta))
    assert "Section two." in text
    reqs = [e for e in second if isinstance(e, InteractionRequest)]
    assert len(reqs) == 1
    assert reqs[0].spec.prompt == "Ready?"
    assert isinstance(second[-1], TurnDone)
    assert second[-1].reason == "interaction"
    assert not any(isinstance(e, ErrorEvent) for e in second)


async def test_first_turn_may_open_with_a_question_but_not_a_bare_confirm() -> None:
    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield {
            0: DeltaToolCall(
                name="interact",
                tool_call_id="q1",
                json_args=json.dumps({"type": "text", "prompt": "Your name?"}),
            )
        }

    engine = Engine(FunctionModel(stream_function=model))
    s = await engine.new_session("ask the name")
    events = await collect(engine.run_turn(s))
    assert any(
        isinstance(e, InteractionRequest) and e.spec.type == "text" for e in events
    )


async def test_two_interactions_in_one_turn_are_answered_one_at_a_time() -> None:
    """A turn may raise several interactions, and they are asked one at a time.

    pydantic-ai refuses to resume until every deferred call has a result, so the engine asks them
    in order and only re-runs the model once all are answered. Before this, the second resume
    failed with `Tool call results need to be provided for all deferred tool calls`.
    """
    spec_a = {
        "type": "single",
        "prompt": "A?",
        "options": [{"display": "a1"}],
        "variable": "a",
    }
    spec_b = {
        "type": "single",
        "prompt": "B?",
        "options": [{"display": "b1"}],
        "variable": "b",
    }

    async def two_at_once(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> StreamChunks:
        if _last_tool_return(messages) is None:
            yield "Two questions at once.\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_a), tool_call_id="ia"
                ),
                1: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_b), tool_call_id="ib"
                ),
            }
        else:
            yield "Both answered."

    engine = Engine(FunctionModel(stream_function=two_at_once), render="none")
    session = await engine.new_session("script")

    first = [e async for e in engine.run_turn(session)]
    asked = [e for e in first if isinstance(e, InteractionRequest)]
    assert len(asked) == 2
    assert [e.reason for e in first if isinstance(e, TurnDone)] == ["interaction"]
    assert len(session.pending) == 2

    # Answering the first one must not call the model again; it just surfaces the second.
    second = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="ia", values=["a1"])
        )
    ]
    assert [e.spec.prompt for e in second if isinstance(e, InteractionRequest)] == [
        "B?"
    ]
    assert not any(isinstance(e, ErrorEvent) for e in second)
    assert session.memory["a"] == "a1"
    assert len(session.pending) == 1

    third = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="ib", values=["b1"])
        )
    ]
    assert not any(isinstance(e, ErrorEvent) for e in third)
    assert (
        "".join(e.text for e in third if isinstance(e, ContentDelta))
        == "Both answered."
    )
    assert session.memory == {"a": "a1", "b": "b1"}
    assert session.pending == []
    assert session.answers == {}


async def test_pending_answers_survive_a_store_round_trip() -> None:
    """Answers collected so far have to come back from storage intact.

    The host answers one question per request and persists the session in between, so a partially
    answered turn spans several processes.
    """
    spec_a = {
        "type": "single",
        "prompt": "A?",
        "options": [{"display": "a1"}],
        "variable": "a",
    }
    spec_b = {
        "type": "single",
        "prompt": "B?",
        "options": [{"display": "b1"}],
        "variable": "b",
    }

    async def two_at_once(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> StreamChunks:
        if _last_tool_return(messages) is None:
            yield "Two at once.\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_a), tool_call_id="ia"
                ),
                1: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_b), tool_call_id="ib"
                ),
            }
        else:
            yield "Both answered."

    engine = Engine(FunctionModel(stream_function=two_at_once), render="none")
    session = await engine.new_session("script")
    async for _ in engine.run_turn(session):
        pass

    session = Session.loads(session.dumps())
    async for _ in engine.run_turn(
        session, InteractionResponseTurn(id="ia", values=["a1"])
    ):
        pass
    assert session.answers == {"ia": "Learner chose: a1"}
    assert [p.tool_call_id for p in session.pending] == ["ib"]

    session = Session.loads(session.dumps())
    events = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="ib", values=["b1"])
        )
    ]
    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert (
        "".join(e.text for e in events if isinstance(e, ContentDelta))
        == "Both answered."
    )
    assert session.memory == {"a": "a1", "b": "b1"}
    assert session.answers == {}


async def test_interactions_can_be_answered_out_of_order_and_without_an_id() -> None:
    spec_a = {
        "type": "single",
        "prompt": "A?",
        "options": [{"display": "a1"}],
        "variable": "a",
    }
    spec_b = {
        "type": "single",
        "prompt": "B?",
        "options": [{"display": "b1"}],
        "variable": "b",
    }
    spec_c = {
        "type": "single",
        "prompt": "C?",
        "options": [{"display": "c1"}],
        "variable": "c",
    }

    async def three_at_once(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> StreamChunks:
        if _last_tool_return(messages) is None:
            yield "Three at once.\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_a), tool_call_id="ia"
                ),
                1: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_b), tool_call_id="ib"
                ),
                2: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_c), tool_call_id="ic"
                ),
            }
        else:
            yield "All three answered."

    engine = Engine(FunctionModel(stream_function=three_at_once), render="none")
    session = await engine.new_session("script")
    async for _ in engine.run_turn(session):
        pass
    assert len(session.pending) == 3

    # Last one first, then the first by id, then the remaining one with no id at all.
    async for _ in engine.run_turn(
        session, InteractionResponseTurn(id="ic", values=["c1"])
    ):
        pass
    async for _ in engine.run_turn(
        session, InteractionResponseTurn(id="ia", values=["a1"])
    ):
        pass
    events = [
        e
        async for e in engine.run_turn(session, InteractionResponseTurn(values=["b1"]))
    ]

    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert (
        "".join(e.text for e in events if isinstance(e, ContentDelta))
        == "All three answered."
    )
    assert session.memory == {"a": "a1", "b": "b1", "c": "c1"}
    assert session.pending == []
    assert session.answers == {}


async def test_a_pending_interaction_rejects_anything_but_an_answer() -> None:
    """While the engine is still collecting answers it must not be talked past."""
    spec_a = {
        "type": "single",
        "prompt": "A?",
        "options": [{"display": "a1"}],
        "variable": "a",
    }
    spec_b = {
        "type": "single",
        "prompt": "B?",
        "options": [{"display": "b1"}],
        "variable": "b",
    }
    calls = 0

    async def two_at_once(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> StreamChunks:
        nonlocal calls
        calls += 1
        if _last_tool_return(messages) is None:
            yield "Two at once.\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_a), tool_call_id="ia"
                ),
                1: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec_b), tool_call_id="ib"
                ),
            }
        else:
            yield "Both answered."

    engine = Engine(FunctionModel(stream_function=two_at_once), render="none")
    session = await engine.new_session("script")
    async for _ in engine.run_turn(session):
        pass
    async for _ in engine.run_turn(
        session, InteractionResponseTurn(id="ia", values=["a1"])
    ):
        pass
    after_answers = calls

    for turn in (ContinueTurn(), MessageTurn(text="can we move on?")):
        errors = [
            e.message
            async for e in engine.run_turn(session, turn)
            if isinstance(e, ErrorEvent)
        ]
        assert errors == ["an interaction is pending; send interaction.response"]

    # Answering the same interaction twice is rejected rather than silently accepted.
    errors = [
        e.message
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="ia", values=["a1"])
        )
        if isinstance(e, ErrorEvent)
    ]
    assert errors == ["unknown interaction id 'ia'"]

    assert calls == after_answers, "none of the rejected turns may reach the model"
    assert [p.tool_call_id for p in session.pending] == ["ib"]
    assert session.answers == {"ia": "Learner chose: a1"}


async def test_a_failed_resume_can_be_retried_instead_of_stranding_the_learner() -> (
    None
):
    """A failed resume keeps the answers so the next turn can send them again.

    Clearing them before the call would leave an unanswered deferred call in the history that no
    later turn could satisfy, stranding the learner.
    """
    spec = {
        "type": "single",
        "prompt": "A?",
        "options": [{"display": "a1"}],
        "variable": "a",
    }
    fail_next = True

    async def flaky(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> StreamChunks:
        nonlocal fail_next
        if _last_tool_return(messages) is None:
            yield "Question.\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(spec), tool_call_id="ia"
                )
            }
            return
        if fail_next:
            fail_next = False
            msg = "upstream exploded"
            raise RuntimeError(msg)
        yield "Answered."

    engine = Engine(FunctionModel(stream_function=flaky), render="none")
    session = await engine.new_session("script")
    async for _ in engine.run_turn(session):
        pass

    failed = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="ia", values=["a1"])
        )
    ]
    assert [type(e).__name__ for e in failed if isinstance(e, ErrorEvent)] == [
        "ErrorEvent"
    ]
    assert session.answers == {"ia": "Learner chose: a1"}, (
        "the answer must not be thrown away"
    )

    # The learner retries; no interaction is pending any more, so the stored answer is what
    # carries the turn.
    retried = [e async for e in engine.run_turn(session, ContinueTurn())]
    assert not any(isinstance(e, ErrorEvent) for e in retried)
    assert (
        "".join(e.text for e in retried if isinstance(e, ContentDelta)) == "Answered."
    )
    assert session.answers == {}
    assert session.memory == {"a": "a1"}


async def test_pressing_continue_does_not_overwrite_an_answer() -> None:
    """Pressing a confirm button must not overwrite the answer the learner typed.

    Reported from the playground: the learner described a situation, the coach read it back and
    asked for confirmation, and pressing "yes, that's it" replaced the stored description with the
    button's label.
    """
    question = {"type": "text", "prompt": "说说看", "variable": "卡点场景"}
    # The model attaches the same variable to its confirmation, which is what caused the loss.
    confirm = {
        "type": "confirm",
        "prompt": "一致吗",
        "options": [{"display": "对，就是这样"}],
        "variable": "卡点场景",
    }

    async def coach(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> StreamChunks:
        ret = _last_tool_return(messages)
        if ret is None:
            yield "最近有没有一件卡住你的事？\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(question), tool_call_id="q1"
                )
            }
        elif "客户" in str(ret.content):
            yield "我复述一下。\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(confirm), tool_call_id="q2"
                )
            }
        else:
            yield "好的，我们继续。"

    engine = Engine(FunctionModel(stream_function=coach), render="none")
    session = await engine.new_session(
        "问学员卡点场景。\n\n?[%{{卡点场景}}...说说看]\n"
    )
    async for _ in engine.run_turn(session):
        pass

    told = "有一个客户，跟我谈了两个月，客户那边预算突然没有了。"
    async for _ in engine.run_turn(
        session, InteractionResponseTurn(id="q1", text=told)
    ):
        pass
    assert session.memory["卡点场景"] == told

    events = [
        e
        async for e in engine.run_turn(
            session, InteractionResponseTurn(id="q2", values=["对，就是这样"])
        )
    ]
    assert session.memory["卡点场景"] == told, (
        "the confirmation must not touch the answer"
    )
    assert not [e for e in events if isinstance(e, MemoryUpdated)]


async def test_a_finished_lesson_does_not_run_the_model_again() -> None:
    """A duplicate or late request on a finished session must not bill another model run."""
    calls = {"n": 0}

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        if calls["n"] == 1:
            yield {
                0: DeltaToolCall(
                    name="finish",
                    tool_call_id="fin_1",
                    json_args=json.dumps({"summary": "done"}),
                )
            }
        else:
            yield "Goodbye.\n"

    engine = Engine(FunctionModel(stream_function=model))
    s = await engine.new_session("Say goodbye.")
    await collect(engine.run_turn(s))
    assert s.finished is True
    calls_after_finishing = calls["n"]

    again = await collect(engine.run_turn(s, ContinueTurn()))
    assert calls["n"] == calls_after_finishing  # the model was not called again
    assert [type(e).__name__ for e in again] == ["TurnDone"]
    assert again[-1].reason == "finished"


async def test_an_unanswerable_response_keeps_the_question_pending() -> None:
    """A value that is not one of the options must not let a required question be skipped."""
    single = {
        "type": "single",
        "prompt": "Pick one",
        "options": [{"display": "A"}, {"display": "B"}],
        "variable": "picked",
    }

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _last_tool_return(messages) is None:
            yield "Here is the question.\n"
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="q1",
                    json_args=json.dumps(single),
                )
            }
        else:
            yield "Thanks.\n"

    engine = Engine(FunctionModel(stream_function=model))
    s = await engine.new_session("Ask one question.")
    await collect(engine.run_turn(s))
    assert s.pending[0].tool_call_id == "q1"

    events = await collect(
        engine.run_turn(s, InteractionResponseTurn(values=["not an option"]))
    )
    assert [type(e).__name__ for e in events] == [
        "ErrorEvent",
        "InteractionRequest",
        "TurnDone",
    ]
    assert events[0].retryable is True
    # Put again, not asked anew: its text is already on the learner's screen.
    assert events[1].asked_before is True
    assert s.pending[0].tool_call_id == "q1"  # still waiting
    assert s.answers == {}
    assert "picked" not in s.memory

    # A real answer still works afterwards.
    ok = await collect(engine.run_turn(s, InteractionResponseTurn(values=["A"])))
    assert any(isinstance(e, MemoryUpdated) for e in ok)
    assert s.pending == []
    assert s.memory["picked"] == "A"


async def test_a_lesson_out_of_turns_ends_instead_of_running_the_model() -> None:
    """A backstop against a lesson that never ends: the model often never calls `finish`.

    Nothing else stops a lesson that has run out of script — the learner keeps continuing, and
    each continuation is another model call and another slice of session. Reaching the limit
    means the lesson is going in circles, not that it is long: the longest real lesson in
    production runs to 138 blocks, and the default sits far above that.
    """
    called = False

    async def never_called(
        _messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> StreamChunks:
        nonlocal called
        called = True
        yield "x"

    engine = Engine(FunctionModel(stream_function=never_called), turn_limit=3)
    session = await engine.new_session("script")
    session.turn = 3

    events = await collect(engine.run_turn(session))

    assert [type(e).__name__ for e in events] == ["TurnDone"]
    assert events[0].reason == "finished"
    assert called is False
    # Marked finished, so a reload reads the lesson as over rather than starting it again.
    assert session.finished is True


async def test_a_lesson_within_its_turns_still_runs() -> None:
    """The limit is a backstop; one turn below it changes nothing."""
    engine = make_engine(turn_limit=3)
    session = await engine.new_session("Greet the learner, then ask how they feel.")
    session.turn = 2

    events = await collect(engine.run_turn(session))

    assert isinstance(events[0], ContentDelta)
    assert session.finished is False


async def test_the_answer_to_the_last_turn_s_question_is_still_accepted() -> None:
    """Reaching the limit refuses another turn of teaching, not the answer to the one just asked.

    The final allowed turn can end on a question. Refusing the answer would throw away what the
    script asked for, and the memory it sets, while marking the lesson complete.
    """
    engine = make_engine(turn_limit=1)
    session = await engine.new_session("script", user_id="u1")
    await collect(engine.run_turn(session))
    assert session.turn == 1  # the limit is now reached
    assert session.pending

    events = await collect(
        engine.run_turn(session, InteractionResponseTurn(values=["Good"]))
    )

    memory = [e for e in events if isinstance(e, MemoryUpdated)]
    assert memory, [type(e).__name__ for e in events]
    assert session.memory == {"feeling": "good"}
    assert not session.pending
    # And the answer reached the model: recording it without resuming would leave the script
    # waiting on a reply it had already been given.
    assert [e for e in events if isinstance(e, ContentDelta)], [
        type(e).__name__ for e in events
    ]


async def test_a_resume_that_never_reached_the_model_may_be_retried() -> None:
    """One network failure on the last turn must not end the lesson for good.

    An answer already recorded is replayed on the next call; that call is finishing a turn that
    was begun, not starting a new one, so the limit does not apply to it.
    """
    engine = make_engine(turn_limit=1)
    session = await engine.new_session("script", user_id="u1")
    await collect(engine.run_turn(session))
    await collect(engine.run_turn(session, InteractionResponseTurn(values=["Good"])))
    # The resume above reached the model; stage the state a failed one leaves behind.
    session.answers = {"call_interact_1": "good"}
    session.turn = 1

    events = await collect(engine.run_turn(session))

    assert not isinstance(events[0], TurnDone) or events[0].reason != "finished"
    assert session.finished is False


async def test_a_closing_line_is_not_said_twice() -> None:
    """The model writes the lesson's last line, calls `finish`, and writes it again.

    Word for word, with nothing between them, which is what the learner read: `两种选择题都测完了。`
    followed immediately by `两种选择题都测完了。`. Found by walking a real lesson on the
    simulation environment; 2 of 200 recent turns carried it, both of them lessons that end on a
    closing line with nothing after it.
    """
    closing = "That is everything for this lesson."

    async def ending(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield closing
        yield {
            0: DeltaToolCall(
                name="finish",
                json_args=json.dumps({"summary": "done"}),
                tool_call_id="f1",
            )
        }

    async def again(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield closing

    calls = {"n": 0}

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        gen = ending(messages, _info) if calls["n"] == 1 else again(messages, _info)
        async for x in gen:
            yield x

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    events = await collect(engine.run_turn(session))
    said = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert said.count(closing) == 1, said


# --- a lesson the model never says is over -------------------------------------------------


def _repeating_model(
    first: str, then: str
) -> tuple[Callable[..., StreamChunks], list[str]]:
    """Build a model that writes `first` on its first turn and `then` on every later one.

    Also collects the text of each user prompt it was sent, so a test can read what the host
    said when it carried the lesson on.
    """
    prompts: list[str] = []
    calls = {"n": 0}

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        prompts.extend(
            p.content
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, UserPromptPart) and isinstance(p.content, str)
        )
        yield first if calls["n"] == 1 else then

    return model, prompts


async def test_a_continue_that_repeats_the_last_turn_ends_the_lesson() -> None:
    """The script ran out and the model did not say so.

    Told to continue, it wrote the whole previous turn again, and a learner on the simulation
    environment read a lesson twice and then watched it stop with the lesson still described as
    in progress. A repeat is the model's way of saying there is nothing left.
    """
    whole = "That is everything the script had to say, delivered once and in full.\n"
    model, _ = _repeating_model(whole, whole)
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    first = await collect(engine.run_turn(session))
    assert first[-1].reason == "end"
    assert session.finished is False
    second = await collect(engine.run_turn(session))
    assert second[-1].reason == "finished"
    assert session.finished is True


async def test_a_continue_that_says_something_new_carries_on() -> None:
    model, _ = _repeating_model("Part one.\n", "Part two.\n")
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session))
    assert second[-1].reason == "end"
    assert session.finished is False


async def test_a_repeat_the_learner_asked_for_is_not_the_end() -> None:
    """A learner who says "again?" and gets the explanation again got what they asked for."""
    model, _ = _repeating_model("Once more.\n", "Once more.\n")
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session, MessageTurn(text="again?")))
    assert second[-1].reason == "end"
    assert session.finished is False


async def test_carrying_on_tells_the_model_to_finish_if_nothing_remains() -> None:
    """The word alone gave a model with nothing left nothing to do but write it again."""
    model, prompts = _repeating_model("Part one.\n", "Part two.\n")
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    await collect(engine.run_turn(session))
    carried_on = prompts[-1]
    assert carried_on.startswith("continue")
    assert "`finish`" in carried_on


async def test_a_short_line_said_twice_is_not_the_end() -> None:
    """A script may say the same short thing twice in a row -- a drill, a heading.

    A model delivering that faithfully repeats it, and ending the lesson there would drop
    everything the script still had after it. Only a repeat long enough to be a turn's worth of
    lesson counts; in 5,884 published lessons no adjacent identical blocks exceed 3 characters.
    """
    model, _ = _repeating_model("Repeat: hello.\n", "Repeat: hello.\n")
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session))
    assert second[-1].reason == "end"
    assert session.finished is False


def _said(events: list[object]) -> str:
    return "".join(e.text for e in events if isinstance(e, ContentDelta))


async def test_a_continue_that_repeats_the_last_turn_shows_the_learner_nothing() -> (
    None
):
    """The repeat is known only once it has been written, so it must not be streamed meanwhile.

    On the simulation environment (boundary lesson 3-2, 2026-09-24) the model wrote the whole
    lesson again on being told to carry on; the repeat detection ended the lesson, but the
    learner had already read the copy.
    """
    whole = "That is everything the script had to say, delivered once and in full.\n"
    model, _ = _repeating_model(whole, whole)
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session))
    assert _said(second) == ""
    assert second[-1].reason == "finished"


async def test_a_continue_that_starts_the_last_turn_over_and_stops_is_a_repeat() -> (
    None
):
    whole = "That is everything the script had to say, delivered once and in full.\n"
    model, _ = _repeating_model(whole, whole[:60])
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session))
    assert _said(second) == ""
    assert second[-1].reason == "finished"


async def test_a_continue_that_begins_like_the_last_turn_is_shown_once_it_differs() -> (
    None
):
    """Held only while it reads as the previous turn; released whole the moment it does not."""
    first = "## Step one\n\nThe first step, in full.\n"
    then = "## Step two\n\nThe second step, in full.\n"
    calls = {"n": 0}

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        text = first if calls["n"] == 1 else then
        for piece in (text[:3], text[3:8], text[8:]):
            yield piece

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session))
    assert _said(second) == then
    # `## ` and `Step ` read as the previous turn and were held; the piece that differed
    # released them, and all of it went out together.
    assert [e.text for e in second if isinstance(e, ContentDelta)] == [then]
    assert second[-1].reason == "end"
    assert session.finished is False


async def test_a_short_continue_that_reads_like_the_last_turn_is_still_shown() -> None:
    """Too short to be taken as a repeat, so it is the model's text and goes out at the end."""
    model, _ = _repeating_model("Repeat: hello.\n", "Repeat: hello.\n")
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session))
    assert _said(second) == "Repeat: hello.\n"
    assert second[-1].reason == "end"


def _closing_again_model(
    first: list[str], then: list[str]
) -> Callable[..., StreamChunks]:
    """Model: the first turn writes `first`; told to carry on, it writes `then` and finishes.

    Given the `finish` result it writes `then` once more, as the model on the simulation
    environment did.
    """
    calls = {"n": 0}

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        if calls["n"] == 1:
            for piece in first:
                yield piece
            return
        for piece in then:
            yield piece
        if calls["n"] == 2:
            yield {
                0: DeltaToolCall(
                    name="finish",
                    json_args=json.dumps({"summary": "done"}),
                    tool_call_id="f1",
                )
            }

    return model


async def test_a_continue_that_says_the_last_line_again_and_finishes_shows_nothing() -> (
    None
):
    """The previous turn's closing line, written again before `finish`, is not shown twice.

    Boundary lesson 6-3 (2026-09-24): told to carry on, the model wrote the line the previous
    turn ended on -- "……理解「名字指向什么」是同一件事。" -- and called `finish`, and the
    learner read it twice in a row. Only a repeat of the previous turn's *start* was held.
    """
    closing = "不管从哪条路来，理解「名字指向什么」是同一件事。"
    model = _closing_again_model(
        ["做菜的时候，你会给东西起名字。\n\n", closing], [closing[:8], closing[8:]]
    )
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    first = await collect(engine.run_turn(session))
    assert _said(first).count(closing) == 1
    second = await collect(engine.run_turn(session))
    assert _said(second) == ""
    assert second[-1].reason == "finished"


async def test_a_continue_that_goes_on_from_a_line_it_repeated_is_shown() -> None:
    """Held only while it is something the previous turn said; new text releases all of it."""
    part_two = "下面讲第二部分：名字和它指向的东西是两回事。" * 20
    model = _closing_again_model(
        ["第一部分讲完了。\n\n小结：名字指向东西。"], ["小结：", part_two]
    )
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session))
    # The model's text, as it wrote it: the repeat was only held, never cut, once it went on.
    assert _said(second) == "小结：" + part_two


async def test_a_continue_that_announces_it_has_nothing_left_shows_nothing() -> None:
    """What a model with nothing left writes before `finish` is addressed to the host.

    General-education course, 3 of 40 lesson runs (2026-09-24): told to carry on, the model wrote
    "The script has been fully delivered -- ... Nothing remains." and then called `finish`, and
    the learner read it under the lesson.
    """
    note = (
        "The script has been fully delivered — the last section (the thinking question, its two "
        "reasons, and the model distillation point) was completed in the previous turn."
    )
    model = _closing_again_model(["第一部分讲完了。"], [note[:40], note[40:]])
    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    await collect(engine.run_turn(session))
    second = await collect(engine.run_turn(session))
    assert _said(second) == ""
    assert second[-1].reason == "finished"


async def test_what_the_model_writes_after_finishing_a_continue_is_not_shown() -> None:
    """Told to carry on, the model calls `finish` first and then writes.

    On the simulation environment (boundary lessons 4-2 and 3-3, 2026-09-24) that text was the
    previous turn's last line again, and an announcement that the script was all delivered. The
    exception that lets a closing line through after `finish` is for a turn that has something to
    close; a turn the host carried on has nothing, or the model would not have stopped before it.
    """
    closing = "You chose the email pattern.\n"

    async def deliver(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield closing

    async def finish_first(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> StreamChunks:
        yield {
            0: DeltaToolCall(
                name="finish",
                json_args=json.dumps({"summary": "done"}),
                tool_call_id="f1",
            )
        }

    async def then_write(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> StreamChunks:
        yield "The script has been delivered in full.\n"

    calls = {"n": 0}

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        gen = {1: deliver, 2: finish_first}.get(calls["n"], then_write)
        async for x in gen(messages, _info):
            yield x

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    first = await collect(engine.run_turn(session))
    assert _said(first) == closing
    second = await collect(engine.run_turn(session))
    assert _said(second) == ""
    assert second[-1].reason == "finished"


async def test_a_closing_line_written_after_finish_still_reaches_the_learner() -> None:
    """Calling `finish` first and writing the closing line after it is still writing it.

    Dropping everything after `finish` assumed the closing line always comes before the call.
    Across 25 finished lessons on the simulation environment it did, but a model that orders
    them the other way would leave the learner a turn with nothing in it at all.
    """

    async def finish_first(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> StreamChunks:
        yield {
            0: DeltaToolCall(
                name="finish",
                json_args=json.dumps({"summary": "done"}),
                tool_call_id="f1",
            )
        }

    async def then_write(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> StreamChunks:
        yield "That is the end of the lesson.\n"

    calls = {"n": 0}

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        gen = (
            finish_first(messages, _info)
            if calls["n"] == 1
            else then_write(messages, _info)
        )
        async for x in gen:
            yield x

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    events = await collect(engine.run_turn(session))
    said = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert "That is the end of the lesson." in said
    assert isinstance(events[-1], TurnDone)
    assert events[-1].reason == "finished"


async def test_a_newline_before_finish_does_not_withhold_the_closing_line() -> None:
    """A turn whose only output so far is whitespace has shown the learner nothing.

    Counting raw characters made a stray newline look like delivered content, so the closing
    line written after `finish` was suppressed and the turn ended with a blank line for it.
    """

    async def blank_then_finish(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> StreamChunks:
        yield "\n"
        yield {
            0: DeltaToolCall(
                name="finish",
                json_args=json.dumps({"summary": "done"}),
                tool_call_id="f1",
            )
        }

    async def closing(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield "That is the end of the lesson.\n"

    calls = {"n": 0}

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        gen = (
            blank_then_finish(messages, _info)
            if calls["n"] == 1
            else closing(messages, _info)
        )
        async for x in gen:
            yield x

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    events = await collect(engine.run_turn(session))
    said = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert "That is the end of the lesson." in said


async def test_a_confirm_the_model_left_unlabelled_says_so_after_the_round_trip() -> (
    None
):
    """The flag has to survive the JSON the engine hands the host, or it tells the host nothing.

    A unit test that builds the spec directly cannot see this: the engine passes it through
    `model_dump` and the host validates it back, and a field excluded from the dump arrives as
    its default. This goes through the real deferred-tool path.
    """

    async def confirm_then_stop(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> StreamChunks:
        if _last_tool_return(messages) is None:
            yield "Read this first.\n"
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args=json.dumps({"type": "confirm", "prompt": "Ready?"}),
                    tool_call_id="c1",
                )
            }

    engine = Engine(FunctionModel(stream_function=confirm_then_stop))
    session = await engine.new_session("script")
    events = await collect(engine.run_turn(session))
    asked = [e for e in events if isinstance(e, InteractionRequest)]
    assert len(asked) == 1
    assert asked[0].spec.labelled_by_engine is True
    # And it survives being stored and loaded again with the session.
    reloaded = Session.loads(session.dumps())
    assert reloaded.pending[0].spec.labelled_by_engine is True


async def test_a_confirm_the_model_labelled_itself_says_so_too() -> None:
    async def labelled(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        if _last_tool_return(messages) is None:
            yield "Read this first.\n"
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args=json.dumps(
                        {
                            "type": "confirm",
                            "prompt": "",
                            "options": [{"display": "开始"}],
                        }
                    ),
                    tool_call_id="c1",
                )
            }

    engine = Engine(FunctionModel(stream_function=labelled))
    session = await engine.new_session("script")
    events = await collect(engine.run_turn(session))
    asked = [e for e in events if isinstance(e, InteractionRequest)]
    assert asked[0].spec.labelled_by_engine is False
    assert asked[0].spec.options[0].display == "开始"


async def test_a_question_the_host_cannot_show_is_asked_again_instead() -> None:
    """A question the host cannot render never waits for an answer.

    Deferred, it reached the learner as text with no controls: the lesson waited for an answer
    that could not be given, and every return to the lesson asked it again. Refused, the model
    is told why and asks it in a form the host can show.
    """
    from pydantic_ai.messages import RetryPromptPart

    bad = {
        "type": "single",
        "prompt": "Which one?",
        "options": [{"display": "%{{x}} first"}, {"display": "second"}],
    }
    good = {
        "type": "single",
        "prompt": "Which one?",
        "options": [{"display": "first"}, {"display": "second"}],
    }
    retries: list[str] = []

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        last = messages[-1]
        retry = next(
            (p for p in getattr(last, "parts", []) if isinstance(p, RetryPromptPart)),
            None,
        )
        if retry is None:
            yield "Pick one.\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(bad), tool_call_id="c1"
                )
            }
        else:
            retries.append(retry.model_response())
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(good), tool_call_id="c2"
                )
            }

    def check(spec: object) -> str | None:
        options = getattr(spec, "options", [])
        return (
            "an option contains %{{"
            if any("%{{" in o.display for o in options)
            else None
        )

    engine = Engine(FunctionModel(stream_function=model), interaction_check=check)
    s = await engine.new_session("Ask which one.")
    events = await collect(engine.run_turn(s))

    asked = [e for e in events if isinstance(e, InteractionRequest)]
    assert [o.display for o in asked[0].spec.options] == ["first", "second"]
    assert len(asked) == 1
    assert [p.spec.options[0].display for p in s.pending] == ["first"]
    assert len(retries) == 1
    assert "an option contains %{{" in retries[0]
    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert events[-1].reason == "interaction"


async def test_without_a_check_every_question_is_deferred_as_before() -> None:
    engine = make_engine()
    s = await engine.new_session("Greet the learner, then ask how they feel.")
    events = await collect(engine.run_turn(s))
    assert any(isinstance(e, InteractionRequest) for e in events)


async def test_a_saved_question_the_host_cannot_show_is_asked_again() -> None:
    """A session already waiting on an unshowable question is not left waiting forever.

    It was saved before the host could refuse it: the learner has only its text and nothing to
    answer with. Returning to the lesson hands it back to the model to be asked again.
    """
    bad = {
        "type": "single",
        "prompt": "Which one?",
        "options": [{"display": "%{{x}} first"}, {"display": "second"}],
    }
    good = {
        "type": "single",
        "prompt": "Which one?",
        "options": [{"display": "first"}, {"display": "second"}],
    }
    told: list[str] = []

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        ret = _last_tool_return(messages)
        if ret is None:
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(bad), tool_call_id="c1"
                )
            }
        else:
            told.append(str(ret.content))
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(good), tool_call_id="c2"
                )
            }

    def check(spec: object) -> str | None:
        options = getattr(spec, "options", [])
        return (
            "an option contains %{{"
            if any("%{{" in o.display for o in options)
            else None
        )

    # Saved by code that could not refuse it.
    before = Engine(FunctionModel(stream_function=model))
    s = await before.new_session("Ask which one.")
    await collect(before.run_turn(s))
    assert [p.tool_call_id for p in s.pending] == ["c1"]

    # The learner comes back with nothing to answer: the frontend sends an empty answer.
    after = Engine(FunctionModel(stream_function=model), interaction_check=check)
    events = await collect(after.run_turn(s, InteractionResponseTurn(values=[])))

    asked = [e for e in events if isinstance(e, InteractionRequest)]
    assert [o.display for o in asked[0].spec.options] == ["first", "second"]
    assert [p.tool_call_id for p in s.pending] == ["c2"]
    assert "never shown" in told[0]
    assert "an option contains %{{" in told[0]
    assert not any(isinstance(e, ErrorEvent) for e in events)


def _two_questions_model(first: dict, second: dict, told: list[str]):  # noqa: ANN202
    """Build a model that asks two questions in one turn, then re-asks one renderable one."""
    good = {
        "type": "single",
        "prompt": "Again?",
        "options": [{"display": "yes"}, {"display": "no"}],
    }

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        last = messages[-1]
        returns = [
            p for p in getattr(last, "parts", []) if isinstance(p, ToolReturnPart)
        ]
        if not returns:
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(first), tool_call_id="q1"
                ),
                1: DeltaToolCall(
                    name="interact", json_args=json.dumps(second), tool_call_id="q2"
                ),
            }
        else:
            told.extend(str(p.content) for p in returns)
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(good), tool_call_id="q3"
                )
            }

    return model


_BAD = {
    "type": "single",
    "prompt": "Which one?",
    "options": [{"display": "%{{x}} first"}, {"display": "second"}],
}
_GOOD = {
    "type": "single",
    "prompt": "Which one?",
    "options": [{"display": "first"}, {"display": "second"}],
}


def _refuses_variable_syntax(spec: object) -> str | None:
    options = getattr(spec, "options", [])
    return (
        "an option contains %{{" if any("%{{" in o.display for o in options) else None
    )


async def test_every_unshowable_question_saved_in_a_turn_is_set_aside() -> None:
    """Two questions from one turn, both unshowable: neither is left for the learner."""
    told: list[str] = []
    model = _two_questions_model(_BAD, _BAD, told)
    s = await Engine(FunctionModel(stream_function=model)).new_session("Ask twice.")
    await collect(Engine(FunctionModel(stream_function=model)).run_turn(s))
    assert [p.tool_call_id for p in s.pending] == ["q1", "q2"]

    after = Engine(
        FunctionModel(stream_function=model), interaction_check=_refuses_variable_syntax
    )
    events = await collect(after.run_turn(s, InteractionResponseTurn(values=[])))

    asked = [e for e in events if isinstance(e, InteractionRequest)]
    assert [e.id for e in asked] == ["q3"]
    assert len(told) == 2
    assert all("never shown" in t for t in told)
    assert not any(isinstance(e, ErrorEvent) for e in events)


async def test_the_next_question_after_an_answer_is_checked_too() -> None:
    """Answering a good question must not put an unshowable one in front of the learner."""
    told: list[str] = []
    model = _two_questions_model(_GOOD, _BAD, told)
    s = await Engine(FunctionModel(stream_function=model)).new_session("Ask twice.")
    await collect(Engine(FunctionModel(stream_function=model)).run_turn(s))
    assert [p.tool_call_id for p in s.pending] == ["q1", "q2"]

    after = Engine(
        FunctionModel(stream_function=model), interaction_check=_refuses_variable_syntax
    )
    events = await collect(
        after.run_turn(s, InteractionResponseTurn(id="q1", values=["first"]))
    )

    asked = [e for e in events if isinstance(e, InteractionRequest)]
    assert [e.id for e in asked] == ["q3"]
    assert any("Learner chose: first" in t for t in told)
    assert any("never shown" in t for t in told)
    assert not any(isinstance(e, ErrorEvent) for e in events)


_ESCAPED_SCRIPT = (
    "请照原样呈现这道题：\n\n"
    "?[%{{正则}} 匹配小数 \\d+\\.\\d+ || 含竖线的 a\\|b || 省略号 wait\\.\\.\\. ok "
    "|| 文档 https:\\/\\/docs.python.org]"
)


def _asks(options: list[dict]):  # noqa: ANN202
    """Build a model that asks one multi-select with `options`, as the model wrote them."""

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(
                    {"type": "multi", "prompt": "认识哪些？", "options": options}
                ),
                tool_call_id="q1",
            )
        }

    return model


async def test_an_option_copied_from_the_script_loses_the_notation_s_escapes() -> None:
    r"""The model copies a script's question with its escapes; the learner saw `a\|b`."""
    copied = [
        {"display": "匹配小数 \\d+\\.\\d+"},
        {"display": "含竖线的 a\\|b"},
        {"display": "省略号 wait\\.\\.\\. ok"},
        {"display": "文档 https:\\/\\/docs.python.org"},
    ]
    engine = Engine(FunctionModel(stream_function=_asks(copied)))
    s = await engine.new_session(_ESCAPED_SCRIPT)
    events = await collect(engine.run_turn(s))

    asked = next(e for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in asked.spec.options] == [
        "匹配小数 \\d+.\\d+",
        "含竖线的 a|b",
        "省略号 wait... ok",
        "文档 https://docs.python.org",
    ]


async def test_an_option_the_model_made_up_keeps_what_it_wrote() -> None:
    """Only the script's own notation is read as notation; a new option is the model's text."""
    made_up = [{"display": "正则 a\\|b 的写法"}, {"display": "都不认识"}]
    engine = Engine(FunctionModel(stream_function=_asks(made_up)))
    s = await engine.new_session(_ESCAPED_SCRIPT)
    events = await collect(engine.run_turn(s))

    asked = next(e for e in events if isinstance(e, InteractionRequest))
    assert [o.display for o in asked.spec.options] == ["正则 a\\|b 的写法", "都不认识"]


def test_the_engine_reads_escapes_exactly_as_the_grammar_does() -> None:
    """The engine keeps its own copy of the rule; it must not drift from MarkdownFlow's."""
    from flaskr.service.learn.agent.engine.tools import _unescape
    from markdown_flow.escaping import unescape_interaction_text

    samples = [
        "a\\|b",
        "wait\\.\\.\\.",
        "https:\\/\\/x.org\\/y",
        "\\d+\\.\\d+",
        "$\\pi$ \\\\ \\beta",
        "[a-z\\]+",
        "trailing \\",
        "\\\\|",
        "",
    ]
    for sample in samples:
        assert _unescape(sample) == unescape_interaction_text(sample), sample


async def _shown(script: str, options: list[dict]) -> list[tuple[str, str | None]]:
    engine = Engine(FunctionModel(stream_function=_asks(options)))
    s = await engine.new_session(script)
    events = await collect(engine.run_turn(s))
    asked = next(e for e in events if isinstance(e, InteractionRequest))
    return [(o.display, o.value) for o in asked.spec.options]


async def test_an_option_already_read_as_the_grammar_reads_it_is_left_alone() -> None:
    r"""`a\\|b` is the option `a\|b`; handed that, the model's text must not lose its backslash."""
    script = "?[%{{x}} a\\\\|b | c]"
    assert await _shown(script, [{"display": "a\\|b"}, {"display": "c"}]) == [
        ("a\\|b", None),
        ("c", None),
    ]
    # Copied as written, it is read the way the grammar reads it.
    assert await _shown(script, [{"display": "a\\\\|b"}, {"display": "c"}]) == [
        ("a\\|b", None),
        ("c", None),
    ]


async def test_text_outside_the_script_s_questions_is_not_an_option() -> None:
    """Prose and code that happen to contain the same characters were never an option."""
    script = "看这个例子：`a\\|b`\n\n```\n?[x\\|y | z]\n```\n\n?[%{{ok}} 是 | 否]"
    assert await _shown(script, [{"display": "a\\|b"}, {"display": "x\\|y"}]) == [
        ("a\\|b", None),
        ("x\\|y", None),
    ]


async def test_a_value_the_model_made_up_keeps_what_it_wrote() -> None:
    """Only a field taken from the script is read as notation; each field is judged alone."""
    script = "?[%{{x}} a\\|b | c]"
    assert await _shown(
        script, [{"display": "a\\|b", "value": "code\\|name"}, {"display": "c"}]
    ) == [("a|b", "code\\|name"), ("c", None)]


def test_the_engine_splits_a_script_s_options_as_the_grammar_does() -> None:
    """Checked against MarkdownFlow's own parser, so the two cannot drift apart."""
    from flaskr.service.learn.agent.engine.tools import script_options
    from markdown_flow import InteractionParser

    questions = [
        "?[%{{x}} a | b | c]",
        "?[%{{x}} a || b || c]",
        "?[%{{x}} Beginner//1 | Expert//3]",
        "?[%{{x}} a\\|b | wait\\.\\.\\. ok | https:\\/\\/x.org]",
        "?[%{{x}} a\\\\|b | [a-z\\]+ || c]",
        "?[%{{x}} 前端 | 后端 | ...你关心什么方向？]",
        "?[%{{x}} \\d+\\.\\d+ | $\\pi$]",
        "?[继续]",
    ]
    for question in questions:
        expected = {
            raw: decoded
            for b in InteractionParser().parse(question)["buttons"]
            for raw, decoded in [(b["display"], b["display"]), (b["value"], b["value"])]
        }
        decoded = set(script_options(question).values())
        assert decoded == set(expected.values()), question


# --- pauses the script did not write ---------------------------------------------------------


def test_a_script_pauses_only_where_it_puts_a_single_button() -> None:
    from flaskr.service.learn.agent.engine.tools import script_pauses

    assert script_pauses("讲一段。\n\n?[继续]\n\n再讲一段。") == 1
    assert script_pauses("?[准备好了//continue]\n?[继续]") == 2
    # A question, not a pause: a variable, a text box, or more than one choice.
    assert script_pauses("?[%{{name}} 好的]") == 0
    assert script_pauses("?[...写点什么]") == 0
    assert script_pauses("?[A | B]") == 0
    assert script_pauses("?[A || B]") == 0
    # Prose, a link and an example in a code fence are not buttons.
    assert script_pauses("让用户思考一下，再继续讲。") == 0
    assert script_pauses("?[看这里](https://example.com)") == 0
    assert script_pauses("```\n?[继续]\n```") == 0


def _pausing_model(
    told: list[str],
) -> Callable[..., StreamChunks]:
    """Model: writes a part, then pauses with a `confirm`; records what each call returned."""

    async def model(messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        ret = _last_tool_return(messages)
        if ret is not None:
            told.append(str(ret.content))
            yield "Part two.\n"
            return
        yield "Part one.\n"
        yield {
            0: DeltaToolCall(
                name="interact",
                json_args=json.dumps(
                    {"type": "confirm", "prompt": "", "options": [{"display": "继续"}]}
                ),
                tool_call_id="c1",
            )
        }

    return model


async def test_a_pause_the_script_did_not_write_is_not_put_to_the_learner() -> None:
    """General-education course (2026-09-24): 17 unasked-for "继续" buttons over 4 lessons.

    A 1.0 lesson pauses only where its author put a button, and a host whose scripts are written
    that way says so. The lesson goes on in the same turn instead.
    """
    told: list[str] = []
    engine = Engine(
        FunctionModel(stream_function=_pausing_model(told)), pauses_from_notation=True
    )
    session = await engine.new_session("让用户思考一下，再继续讲下一部分。")
    events = await collect(engine.run_turn(session))

    assert not [e for e in events if isinstance(e, InteractionRequest)]
    assert _said(events) == "Part one.\nPart two.\n"
    assert told
    assert "No pause here" in told[0]
    assert session.pending == []


async def test_a_pause_the_script_wrote_is_still_put_to_the_learner() -> None:
    told: list[str] = []
    engine = Engine(
        FunctionModel(stream_function=_pausing_model(told)), pauses_from_notation=True
    )
    session = await engine.new_session("讲一段。\n\n?[继续]\n\n再讲一段。")
    events = await collect(engine.run_turn(session))

    (asked,) = [e for e in events if isinstance(e, InteractionRequest)]
    assert asked.spec.type == "confirm"
    assert events[-1].reason == "interaction"


async def test_a_script_with_a_button_leaves_its_pauses_to_the_model() -> None:
    """Where the script has buttons, nothing says which part of it the model has reached.

    A count of buttons, spent as the model paused, let an early unscripted pause use up the one
    the author wrote, and the author's button was then skipped (review of #2957). So the model
    keeps placing pauses in such a lesson, as before.
    """
    told: list[str] = []
    engine = Engine(
        FunctionModel(stream_function=_pausing_model(told)), pauses_from_notation=True
    )
    session = await engine.new_session("讲一段。\n\n?[继续]\n\n再讲一段。")
    await collect(engine.run_turn(session))
    await collect(engine.run_turn(session, InteractionResponseTurn(values=["继续"])))
    events = await collect(engine.run_turn(session, ContinueTurn()))
    assert [e for e in events if isinstance(e, InteractionRequest)]


async def test_a_button_in_the_brief_is_not_a_pause_of_the_lesson() -> None:
    """A brief may show `?[继续]` as an example of the notation; the lesson itself has none."""
    from flaskr.service.learn.agent.engine.script import ScriptBundle

    told: list[str] = []
    engine = Engine(
        FunctionModel(stream_function=_pausing_model(told)), pauses_from_notation=True
    )
    session = await engine.new_session(
        ScriptBundle(
            script="让用户思考一下，再继续讲下一部分。",
            constraints="写停顿的方式是 ?[继续]，本节不需要。",
        )
    )
    events = await collect(engine.run_turn(session))
    assert not [e for e in events if isinstance(e, InteractionRequest)]


async def test_the_model_decides_pauses_unless_the_host_says_otherwise() -> None:
    told: list[str] = []
    engine = Engine(FunctionModel(stream_function=_pausing_model(told)))
    session = await engine.new_session("让用户思考一下，再继续讲下一部分。")
    events = await collect(engine.run_turn(session))
    assert [e for e in events if isinstance(e, InteractionRequest)]


# --- nothing is asked after `finish` -------------------------------------------------------

_AGAIN = {
    "type": "single",
    "prompt": "你是不是已经迫不及待了？",
    "options": [{"display": "是"}, {"display": "还不确定"}],
}


def _finish_call(call_id: str = "f1") -> dict[int, DeltaToolCall]:
    return {
        0: DeltaToolCall(
            name="finish",
            json_args=json.dumps({"summary": "done"}),
            tool_call_id=call_id,
        )
    }


async def test_a_question_asked_after_finish_does_not_keep_the_lesson_going() -> None:
    """General-education course (2026-09-24): after `finish`, the model taught the lesson again.

    Given the `finish` result it started over and asked its first question once more; taken as a
    question, that left the lesson unfinished, and every answer brought the same lesson and the
    same question back -- 14 times.
    """
    calls = {"n": 0}

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        if calls["n"] == 1:
            yield "最后一部分讲完了。\n"
            yield _finish_call()
        elif calls["n"] == 2:
            yield "咱们开始吧。\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(_AGAIN), tool_call_id="q2"
                )
            }
        else:
            yield "好的。"

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    events = await collect(engine.run_turn(session))

    assert not [e for e in events if isinstance(e, InteractionRequest)]
    assert events[-1].reason == "finished"
    assert session.finished is True
    assert session.pending == []


async def test_a_model_that_keeps_asking_after_finish_still_ends_the_lesson() -> None:
    """Asking again and again after `finish` runs into the request limit; the end still stands."""
    calls = {"n": 0}

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        if calls["n"] == 1:
            yield "最后一部分讲完了。\n"
            yield _finish_call()
        else:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    json_args=json.dumps(_AGAIN),
                    tool_call_id=f"q{calls['n']}",
                )
            }

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    events = await collect(engine.run_turn(session))

    assert not [e for e in events if isinstance(e, (InteractionRequest, ErrorEvent))]
    assert events[-1].reason == "finished"
    assert session.finished is True


async def test_a_question_asked_beside_finish_is_not_left_pending() -> None:
    """Asking and finishing in one response: the lesson is over, and nothing waits on the learner."""
    calls = {"n": 0}

    async def model(_messages: list[ModelMessage], _info: AgentInfo) -> StreamChunks:
        calls["n"] += 1
        if calls["n"] == 1:
            yield "最后一部分讲完了。\n"
            yield {
                0: DeltaToolCall(
                    name="interact", json_args=json.dumps(_AGAIN), tool_call_id="q1"
                ),
                1: DeltaToolCall(
                    name="finish",
                    json_args=json.dumps({"summary": "done"}),
                    tool_call_id="f1",
                ),
            }
        else:
            yield "好的。"

    engine = Engine(FunctionModel(stream_function=model))
    session = await engine.new_session("script")
    events = await collect(engine.run_turn(session))

    assert not [e for e in events if isinstance(e, InteractionRequest)]
    assert events[-1].reason == "finished"
    assert session.pending == []
