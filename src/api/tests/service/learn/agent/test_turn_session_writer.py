"""Keep save boundaries identical across formal, preview and editor sessions."""

from __future__ import annotations

import pytest
from flask import Flask
from flaskr.api.markdownflow import (
    ContentDelta,
    ErrorEvent,
    LessonPager,
    MemoryUpdated,
    ScriptBundle,
    Session,
    TurnDone,
)
from flaskr.service.learn.agent import debug_session, run_agent
from flaskr.service.learn.learn_dtos import GeneratedType
from markdownflow.engine.interaction import InteractionSpec
from markdownflow.engine.session import PendingInteraction


class _Cache:
    """Keep real debug-store serialization local to this test."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.values[key] = value


@pytest.mark.parametrize("destination", ["formal", "preview", "debug"])
@pytest.mark.parametrize("boundary", ["prepared", "terminal", "partial-failure"])
def test_stream_uses_one_save_strategy_at_the_existing_boundary(
    monkeypatch: pytest.MonkeyPatch,
    destination: str,
    boundary: str,
) -> None:
    """Save once, retain late-bound state, and keep debug out of durable history."""
    app = Flask(__name__)
    cache = _Cache()
    monkeypatch.setattr(debug_session, "cache", cache)
    preview = destination != "formal"
    session = Session(script=ScriptBundle(script="Current lesson"))
    session.memory = {"pace": "slow"}
    session.usage = {"requests": 2, "input_tokens": 40, "output_tokens": 5}
    holder = {
        "session": session,
        "turn_record": "old checkpoint",
        "content_revision": 1,
    }
    memory = MemoryUpdated(key="pace", value="slow", scope="user")
    events = [memory]
    if boundary == "prepared":
        session.pending = [
            PendingInteraction(
                "correction",
                InteractionSpec(type="text", prompt="Try again"),
            )
        ]
        events.append(
            ContentDelta(
                text="Accepted feedback.\n",
                prepared_content="===Accepted feedback.===\n",
            )
        )
    else:
        events.append(ContentDelta(text="Accepted feedback.\n"))
    events.append(
        ErrorEvent(message="Input budget exceeded", code="input_budget_exceeded")
        if boundary == "partial-failure"
        else TurnDone(reason="end")
    )

    writes: list[dict] = []
    ordering: list[tuple[str, object]] = []
    strategy_choices: list[object] = []
    original_writer = run_agent._turn_session_writer

    def choose_writer(*args: object, **kwargs: object) -> object:
        strategy_choices.append(kwargs["debug_store"])
        return original_writer(*args, **kwargs)

    monkeypatch.setattr(run_agent, "_turn_session_writer", choose_writer)

    def persist(_app: Flask, saved: Session, **kwargs: object) -> bool:
        assert destination != "debug", "Editor state must not enter durable persistence"
        assert saved is session
        writes.append(kwargs)
        ordering.append(("save", "durable"))
        return True

    monkeypatch.setattr(run_agent, "_persist", persist)
    store = None
    if destination == "debug":
        store = debug_session.DebugSessionStore(
            app,
            user_bid="user",
            shifu_bid="course",
            outline_bid="lesson",
            run_bid="run",
        )
        save_debug = store.save

        def record_debug(saved: Session) -> None:
            ordering.append(("save", "debug"))
            save_debug(saved)

        monkeypatch.setattr(store, "save", record_debug)

    def bridge(_make_events: object, **_kwargs: object) -> object:
        # These become available after the strategy has already been selected.
        holder.update(
            turn_record="current checkpoint",
            rewind="current rewind",
            memory_generations={"pace": 2},
            preview_generation="current generation" if preview else None,
            content_revision=42,
        )
        return iter(events)

    stream = run_agent._stream_turn(
        app,
        run_turn_on_thread=bridge,
        voice=None,
        pager=LessonPager(clean_markers=True),
        make_events=lambda: None,
        session_holder=holder,
        user_bid="user",
        shifu_bid="course",
        outline_bid="lesson",
        preview_mode=preview,
        progress_record_bid="progress",
        generated_block_bid="block",
        heartbeat_interval=0.1,
        debug_store=store,
    )
    while True:
        try:
            payload = next(stream)
        except StopIteration as done:
            outcome = done.value
            break
        ordering.append(("yield", payload.type))

    assert strategy_choices == [store]
    assert len([entry for entry in ordering if entry[0] == "save"]) == 1
    assert not outcome.discarded
    assert outcome.reason == (None if boundary == "partial-failure" else "end")
    assert outcome.error_code == (
        "input_budget_exceeded" if boundary == "partial-failure" else None
    )
    save_index = next(index for index, item in enumerate(ordering) if item[0] == "save")
    if boundary == "prepared":
        assert save_index == 0
    elif boundary == "terminal":
        assert save_index < ordering.index(("yield", GeneratedType.BREAK))
    else:
        assert ordering[-1][0] == "save"
        assert not any(item == ("yield", GeneratedType.BREAK) for item in ordering)

    if store is not None:
        assert writes == []
        assert len(cache.values) == 1
        assert ":agent_debug:" in next(iter(cache.values))
        restored = store.load(script="Current lesson")
        assert restored is not None
        assert restored.memory == session.memory
        assert restored.usage == session.usage
        other = debug_session.DebugSessionStore(
            app,
            user_bid="user",
            shifu_bid="course",
            outline_bid="lesson",
            run_bid="other-run",
        )
        assert other.load(script="Current lesson") is None
    else:
        assert cache.values == {}
        assert len(writes) == 1
        saved = writes[0]
        assert saved["memory"] == [memory]
        assert saved["taught"] == "Accepted feedback.\n"
        assert saved["preview_mode"] is preview
        assert saved["progress_record_bid"] == "progress"
        assert saved["generated_block_bid"] == "block"
        assert saved["turn_record"] == "current checkpoint"
        assert saved["rewind"] == "current rewind"
        assert saved["memory_generations"] == {"pace": 2}
        assert saved["preview_generation"] == (
            "current generation" if preview else None
        )
        assert saved["content_revision"] == (None if boundary == "prepared" else 42)
        assert saved["preview_question_ids"] == (
            ["correction"] if boundary == "prepared" else []
        )


@pytest.mark.parametrize("boundary", ["prepared", "terminal"])
def test_failed_save_prevents_the_boundary_from_reaching_the_client(
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    """Propagate the existing save error before reporting accepted content or completion."""
    session = Session(script=ScriptBundle(script="Current lesson"))
    events = (
        [ContentDelta(text="Accepted feedback.\n", prepared_content="Full feedback.\n")]
        if boundary == "prepared"
        else []
    ) + [TurnDone(reason="end")]
    calls = []

    def reject_save(*_args: object, **_kwargs: object) -> bool:
        calls.append("save")
        message = "Save failed"
        raise RuntimeError(message)

    monkeypatch.setattr(run_agent, "_persist", reject_save)
    stream = run_agent._stream_turn(
        Flask(__name__),
        run_turn_on_thread=lambda *_args, **_kwargs: iter(events),
        voice=None,
        pager=LessonPager(clean_markers=True),
        make_events=lambda: None,
        session_holder={"session": session},
        user_bid="user",
        shifu_bid="course",
        outline_bid="lesson",
        preview_mode=True,
        progress_record_bid="",
        generated_block_bid="block",
        heartbeat_interval=0.1,
    )

    with pytest.raises(RuntimeError, match="Save failed"):
        next(stream)
    assert calls == ["save"]
