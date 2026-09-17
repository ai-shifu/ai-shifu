"""Engine tests driven by pydantic-ai's FunctionModel: no network, deterministic."""

import json
from collections.abc import AsyncIterator

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
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
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
    assert s.pending[0].tool_call_id == "q1"  # still waiting
    assert s.answers == {}
    assert "picked" not in s.memory

    # A real answer still works afterwards.
    ok = await collect(engine.run_turn(s, InteractionResponseTurn(values=["A"])))
    assert any(isinstance(e, MemoryUpdated) for e in ok)
    assert s.pending == []
    assert s.memory["picked"] == "A"
