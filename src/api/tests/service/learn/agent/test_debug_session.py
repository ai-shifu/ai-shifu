"""Editor debug sessions resume safely without touching lesson sessions."""

from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.service.common.models import AppError
from flaskr.service.learn import routes
from flaskr.service.learn.agent import debug_session
from flaskr.service.learn.agent.rewind import (
    RewindUnavailableError,
    checkpoint_of,
    turn_record,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    PlaygroundPreviewRequest,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from markdownflow.engine.interaction import InteractionSpec
from markdownflow.engine.script import ScriptBundle
from markdownflow.engine.session import PendingInteraction, Session
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.function import FunctionModel

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class _Cache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.locks: dict[str, object] = {}

    def lock(self, key: str, **_kwargs: object) -> object:
        return self.locks.setdefault(key, threading.Lock())

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


def _store(app: object, run: str = "one") -> debug_session.DebugSessionStore:
    return debug_session.DebugSessionStore(
        app, user_bid="teacher", shifu_bid="course", outline_bid="lesson", run_bid=run
    )


def _record(session: Session, values: list[str] | None = None) -> str:
    checkpoint = checkpoint_of(session)
    checkpoint["user_memory"] = dict(session.user_memory)
    return turn_record(checkpoint, values or [])


def _request_messages(
    app: object, factory: Callable[[], Iterator[RunElementSSEMessageDTO]]
) -> list[SimpleNamespace]:
    # HTTP completion belongs to the request boundary, not the lesson generator.
    with app.test_request_context("/"):
        response = routes._stream_sse_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
            terminal_event_factory=lambda: RunElementSSEMessageDTO(
                type="done", event_type="done", content="", is_terminal=True
            ),
        )
        try:
            return [
                SimpleNamespace(**json.loads(chunk.removeprefix("data: ")))
                for chunk in response.response
            ]
        finally:
            response.close()


def test_debug_session_resumes_only_the_same_run_and_script(
    app: object, monkeypatch: object
) -> None:
    cache = _Cache()
    monkeypatch.setattr(debug_session, "cache", cache)
    first = debug_session.DebugSessionStore(
        app, user_bid="teacher", shifu_bid="course", outline_bid="lesson", run_bid="one"
    )
    other = debug_session.DebugSessionStore(
        app, user_bid="teacher", shifu_bid="course", outline_bid="lesson", run_bid="two"
    )
    session = Session(script=ScriptBundle(script="Current draft"))
    session.memory["answer"] = "yes"

    first.save(session)

    assert first.load(script="Current draft").memory["answer"] == "yes"
    assert first.load(script="Edited draft") is None
    assert other.load(script="Current draft") is None
    assert list(cache.ttls.values()) == [30 * 60]
    restarted = Session(script=ScriptBundle(script="Current draft"))
    restarted.memory["answer"] = "fresh answer"
    other.save(restarted)
    assert other.load(script="Current draft").memory["answer"] == "fresh answer"
    assert first.load(script="Current draft").memory["answer"] == "yes"
    assert cache.ttls[other._key] == 30 * 60
    cache.values[first._key] = "invalid history"
    assert first.load(script="Current draft") is None
    assert other.load(script="Current draft").memory["answer"] == "fresh answer"


def test_editor_debug_uses_the_existing_lesson_and_element_pipeline(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    calls: list[dict[str, object]] = []

    def lesson_events(_app: object, **kwargs: object) -> object:
        calls.append(kwargs)
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="turn",
            type=GeneratedType.CONTENT,
            content="Taught by the agent",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="turn",
            type=GeneratedType.DONE,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current editor draft",
                block_index=0,
                variables={"goal": "learn"},
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="run-one",
        ),
    )

    assert messages[0].type == "preview_engine"
    assert messages[0].content == "2.0"
    assert any(message.type == "element" for message in messages)
    assert messages[-1].type == "done"
    assert calls[0]["script_override"] == "Current editor draft"
    assert calls[0]["preview_mode"] is True
    assert isinstance(calls[0]["debug_store"], debug_session.DebugSessionStore)


def test_expired_debug_answer_does_not_start_a_new_lesson(
    app: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(debug_session, "cache", _Cache())
    stream = debug_session.stream_debug_preview(
        app,
        preview_request=PlaygroundPreviewRequest(
            content="Current draft",
            block_index=0,
            user_input={"answer": ["yes"]},
        ),
        shifu_bid="course",
        outline_bid="lesson",
        user_bid="teacher",
        run_bid="expired-run",
    )

    with pytest.raises(AppError) as exc_info:
        next(stream)
    assert exc_info.value.code == 4019


def test_question_closes_editor_response_without_ending_the_lesson(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    def lesson_events(_app: object, **_kwargs: object) -> object:
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="question",
            type=GeneratedType.INTERACTION,
            content="Which option?",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="question",
            type=GeneratedType.BREAK,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft", block_index=0
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="question-run",
        ),
    )

    done_messages = [message for message in messages if message.type == "done"]
    assert [message.is_terminal for message in done_messages] == [False, True]


def test_finished_debug_reopening_closes_the_empty_response(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    # Finished lessons deliberately produce no new block or model request.
    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lambda *_a, **_k: iter(()))
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft", block_index=0
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="finished-run",
        ),
    )

    assert [message.type for message in messages] == ["preview_engine", "done"]
    assert messages[-1].is_terminal is True
    assert not getattr(messages[-1], "generated_block_bid", None)


def test_debug_regeneration_keeps_prefix_and_replays_only_the_selected_turn(
    app: object, monkeypatch: object
) -> None:
    """Drop future answers and user notes without echoing them back from the UI."""
    from flaskr.service.learn.agent import run_agent

    monkeypatch.setattr(debug_session, "cache", _Cache())
    store = _store(app)
    session = Session(
        script=ScriptBundle(script="Current draft"),
        user_memory={"goal": "original"},
    )
    first = _record(session)
    session.messages.append(ModelRequest(parts=[UserPromptPart("First teaching")]))
    session.memory["prefix"] = "retained"
    session.turn = 1
    session.pending = [
        PendingInteraction(
            "first-question", InteractionSpec(type="text", prompt="First?")
        )
    ]
    store.save(session, generated_block_bid="prefix", turn_record=first)

    second = _record(session, ["original answer"])
    session.messages.append(ModelRequest(parts=[UserPromptPart("Second teaching")]))
    session.memory["first_answer"] = "original answer"
    session.user_memory["note"] = "from second step"
    session.turn = 2
    session.pending = [
        PendingInteraction(
            "second-question", InteractionSpec(type="text", prompt="Second?")
        )
    ]
    store.save(session, generated_block_bid="selected", turn_record=second)

    third = _record(session, ["future answer"])
    session.messages.append(ModelRequest(parts=[UserPromptPart("Future teaching")]))
    session.memory["future"] = "future answer"
    session.user_memory["future_note"] = "discard"
    session.pending = []
    session.turn = 3
    session.finished = True
    session.teaching_summaries["future"] = "obsolete summary"
    store.save(session, generated_block_bid="future", turn_record=third)

    plan = store.plan_rewind(script="Current draft", block_bid="selected")
    assert plan.replay_values == ["original answer"]
    assert plan.retired_block_bids == ["selected", "future"]
    factory, finished = run_agent._load_or_start(
        app,
        SimpleNamespace(),
        user_bid="teacher",
        shifu_bid="course",
        outline_bid="lesson",
        script="Current draft",
        preview_mode=True,
        debug_store=store,
        rewind=plan,
        preview_variables={
            "goal": "echoed",
            "future": "future answer",
            "future_note": "discard",
        },
    )
    resumed = asyncio.run(factory())
    assert not finished
    assert resumed.id == session.id
    assert resumed.turn == 1
    assert not resumed.finished
    assert len(resumed.messages) == 1
    assert resumed.all_memory() == {"goal": "original", "prefix": "retained"}
    assert resumed.pending[0].tool_call_id == "first-question"
    assert resumed.answers == {}
    assert resumed.teaching_summaries == {}

    store.save(
        resumed, generated_block_bid="replacement", turn_record=second, rewind=plan
    )
    turns = store._payload(script="Current draft")["turns"]
    assert [turn["block_bid"] for turn in turns] == ["prefix", "replacement"]
    assert store.plan_rewind(
        script="Current draft", block_bid="replacement"
    ).replay_values == ["original answer"]
    with pytest.raises(RewindUnavailableError):
        store.plan_rewind(script="Current draft", block_bid="future")


@pytest.mark.parametrize(
    "invalid", ["unknown", "element-in-selected", "prefix-from-other-run"]
)
def test_debug_rewind_requires_a_current_run_checkpoint(
    app: object, monkeypatch: object, invalid: str
) -> None:
    monkeypatch.setattr(debug_session, "cache", _Cache())
    session = Session(script=ScriptBundle(script="Current draft"))
    store = _store(app)
    store.save(session, generated_block_bid="selected", turn_record=_record(session))
    _store(app, "other").save(
        session,
        generated_block_bid="prefix-from-other-run",
        turn_record=_record(session),
    )
    with pytest.raises(RewindUnavailableError):
        store.plan_rewind(script="Current draft", block_bid=invalid)
    with pytest.raises(RewindUnavailableError):
        store.plan_rewind(script="Edited draft", block_bid="selected")


def test_debug_regeneration_stream_restores_variables_and_forwards_the_anchor(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    monkeypatch.setattr(debug_session, "cache", _Cache())
    session = Session(
        script=ScriptBundle(script="Current draft"), memory={"prefix": "kept"}
    )
    record = _record(session)
    session.memory["future"] = "discard"
    _store(app).save(session, generated_block_bid="selected", turn_record=record)
    seen: list[dict] = []

    def lesson_events(_app: object, **kwargs: object) -> object:
        seen.append(kwargs)
        saved = kwargs["debug_store"].load(script="Current draft")
        saved.memory = {"prefix": "kept", "replayed_answer": "original"}
        kwargs["debug_store"].save(saved)
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="replacement",
            type=GeneratedType.DONE,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft",
                block_index=0,
                reload_generated_block_bid="selected",
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="one",
        ),
    )
    assert seen[0]["reload_generated_block_bid"] == "selected"
    snapshots = [
        json.loads(message.content)
        for message in messages
        if message.type == "debug_variables"
    ]
    assert snapshots == [
        {"prefix": "kept"},
        {"prefix": "kept", "replayed_answer": "original"},
    ]
    assert messages[0].type == "debug_variables"
    assert messages[-2].type == "debug_variables"
    assert messages[-1].type == "done"


def test_expired_debug_regeneration_does_not_restart_the_lesson(
    app: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(debug_session, "cache", _Cache())
    stream = debug_session.stream_debug_preview(
        app,
        preview_request=PlaygroundPreviewRequest(
            content="Current draft",
            block_index=0,
            reload_generated_block_bid="selected",
        ),
        shifu_bid="course",
        outline_bid="lesson",
        user_bid="teacher",
        run_bid="expired-run",
    )
    with pytest.raises(AppError) as exc_info:
        next(stream)
    assert exc_info.value.code == 4019


def test_real_debug_turns_record_replayable_checkpoints_and_discard_future_history(
    app: object, monkeypatch: object
) -> None:
    """Exercise the real engine, cache saves and rewind rather than constructing turn metadata."""
    from flaskr.service.learn.agent import run_agent
    from markdownflow.engine import Engine

    from tests.service.learn.agent.test_memory_integration import _drive

    monkeypatch.setattr(debug_session, "cache", _Cache())
    calls = 0
    replay_history: list[str] = []

    async def model(messages: list, _info: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 4:
            replay_history.extend(
                part.content
                for message in messages
                for part in message.parts
                if isinstance(part, UserPromptPart) and isinstance(part.content, str)
            )
        yield f"Teaching step {calls}."

    engine = Engine(FunctionModel(stream_function=model))
    with app.app_context():
        for user_input in (
            None,
            {"input": ["Original selected request"]},
            {"input": ["Discarded future request"]},
        ):
            list(
                run_agent.run_agent_lesson(
                    app,
                    engine=engine,
                    script="Current draft",
                    user_bid="teacher",
                    shifu_bid="course",
                    outline_bid="lesson",
                    preview_mode=True,
                    debug_store=_store(app),
                    preview_variables={"goal": "original"},
                    user_input=user_input,
                    iter_turn=_drive,
                )
            )
        store = _store(app)
        before = store.load(script="Current draft")
        turns = store._payload(script="Current draft")["turns"]
        assert len(turns) == 3
        assert turns[1]["record"]["values"] == ["Original selected request"]
        assert turns[1]["record"]["checkpoint"]["user_memory"] == {"goal": "original"}
        plan = store.plan_rewind(
            script="Current draft", block_bid=turns[1]["block_bid"]
        )
        list(
            run_agent.run_agent_lesson(
                app,
                engine=engine,
                script="Current draft",
                user_bid="teacher",
                shifu_bid="course",
                outline_bid="lesson",
                preview_mode=True,
                debug_store=store,
                preview_variables={"goal": "echoed", "future_answer": "discard"},
                rewind=plan,
                iter_turn=_drive,
            )
        )
        after = store.load(script="Current draft")
    assert calls == 4
    assert after.id == before.id
    assert after.turn == 2
    assert after.user_memory == {"goal": "original"}
    saved_turns = store._payload(script="Current draft")["turns"]
    assert saved_turns[0]["block_bid"] == turns[0]["block_bid"]
    assert len(saved_turns) == 2
    assert any("Original selected request" in text for text in replay_history)
    assert all("Discarded future request" not in text for text in replay_history)


def test_new_debug_request_prevents_a_stopped_stream_from_overwriting_its_save(
    app: object, monkeypatch: object
) -> None:
    """A late terminal event from the previous host cannot restore discarded future state."""
    monkeypatch.setattr(debug_session, "cache", _Cache())
    older = _store(app)
    older.begin_request()
    old_session = Session(script=ScriptBundle(script="Current draft"))
    older.save(
        old_session, generated_block_bid="selected", turn_record=_record(old_session)
    )

    replacement = _store(app)
    plan = replacement.plan_rewind(script="Current draft", block_bid="selected")
    replacement.begin_request()
    current = replacement.load(script="Current draft")
    current.memory["new"] = "replacement"
    replacement.save(
        current,
        generated_block_bid="replacement",
        turn_record=_record(current),
        rewind=plan,
    )
    old_session.memory["future"] = "stale terminal save"
    with pytest.raises(RewindUnavailableError):
        older.save(old_session)

    assert replacement.load(script="Current draft").memory == {"new": "replacement"}
    assert [
        turn["block_bid"]
        for turn in replacement._payload(script="Current draft")["turns"]
    ] == ["replacement"]


def test_debug_rewind_retires_a_turn_saved_before_the_replacement_claim(
    app: object, monkeypatch: object
) -> None:
    """The runtime re-plans after claiming the request, including a racing old save."""
    from flaskr.service.learn.agent.rewind import restore
    from flaskr.service.learn.agent.run_agent import TurnOutcome

    from tests.service.learn.agent.test_lesson_entry_contracts import _entry_with_runner

    monkeypatch.setattr(debug_session, "cache", _Cache())
    older = _store(app)
    older.begin_request()
    session = Session(script=ScriptBundle(script="Current draft"))
    first = _record(session)
    session.messages.append(ModelRequest(parts=[UserPromptPart("Teaching A")]))
    session.memory["prefix"] = "kept"
    older.save(session, generated_block_bid="A", turn_record=first)
    selected = _record(session)
    session.messages.append(ModelRequest(parts=[UserPromptPart("Teaching B")]))
    session.memory["selected"] = "old B"
    older.save(session, generated_block_bid="B", turn_record=selected)

    begin_request = debug_session.DebugSessionStore.begin_request

    def racing_claim(store: debug_session.DebugSessionStore) -> None:
        # The stopped host completes between the preview's early plan and token claim.
        racing = _record(session)
        session.messages.append(ModelRequest(parts=[UserPromptPart("Teaching C")]))
        session.memory["future"] = "discard"
        older.save(session, generated_block_bid="C", turn_record=racing)
        begin_request(store)

    monkeypatch.setattr(debug_session.DebugSessionStore, "begin_request", racing_claim)
    runner = _entry_with_runner(monkeypatch)
    retired: list[str] = []

    def replacement_turn(_app: object, **kwargs: object) -> object:
        store = kwargs["debug_store"]
        plan = kwargs["rewind"]
        retired.extend(plan.retired_block_bids)
        restored = store.load(script="Current draft")
        restore(restored, plan.checkpoint)
        restored.user_memory = dict(plan.checkpoint["user_memory"])
        assert restored.all_memory() == {"prefix": "kept"}
        # Once the replacement claims its token, the stopped host cannot save again.
        with pytest.raises(RewindUnavailableError):
            older.save(session)
        restored.memory["replacement"] = "new B"
        store.save(
            restored,
            generated_block_bid="replacement",
            turn_record=selected,
            rewind=plan,
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="replacement",
            type=GeneratedType.DONE,
            content="",
        )
        return TurnOutcome(reason="interaction", taught=True)

    runner.side_effect = replacement_turn
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft", block_index=0, reload_generated_block_bid="B"
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="one",
        ),
    )
    assert retired == ["B", "C"]
    snapshots = [
        json.loads(message.content)
        for message in messages
        if message.type == "debug_variables"
    ]
    assert snapshots == [
        {"prefix": "kept"},
        {"prefix": "kept", "replacement": "new B"},
    ]
    latest = _store(app)
    assert [
        turn["block_bid"] for turn in latest._payload(script="Current draft")["turns"]
    ] == ["A", "replacement"]
    with pytest.raises(RewindUnavailableError):
        latest.plan_rewind(script="Current draft", block_bid="C")


def test_debug_automatic_continuation_preserves_restored_output_language(
    app: object, monkeypatch: object
) -> None:
    """Dropping the browser's future snapshot must keep the checkpoint's teaching language."""
    from flaskr.i18n import clear_language, set_language
    from flaskr.service.learn.agent import run_agent

    monkeypatch.setattr(debug_session, "cache", _Cache())
    session = Session(
        script=ScriptBundle(script="Current draft"),
        user_memory={"sys_user_language": "fr-FR", "goal": "retained"},
    )
    store = _store(app)
    store.save(session)
    engine = SimpleNamespace(output_language=None)
    set_language("en-US")
    try:
        factory, _finished = run_agent._load_or_start(
            app,
            engine,
            user_bid="teacher",
            shifu_bid="course",
            outline_bid="lesson",
            script="Current draft",
            preview_mode=True,
            debug_store=store,
            preview_variables=None,
            use_learner_language=True,
        )
        resumed = asyncio.run(factory())
    finally:
        clear_language()
    assert resumed.user_memory == {"sys_user_language": "fr-FR", "goal": "retained"}
    assert engine.output_language == "Français"
