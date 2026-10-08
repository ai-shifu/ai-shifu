"""Verify source writeback through actual engine, host save and rollback paths."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from types import SimpleNamespace

    from flaskr.service.learn.agent.engine.session import Session
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine, MemoryUpdated
from flaskr.service.profile.models import VariableValue
from flaskr.service.shifu.models import DraftShifu, PublishedOutlineItem
from pydantic_ai.messages import ModelMessage, RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from tests.service.learn.agent.test_memory_integration import _drive
from tests.service.profile.test_shared_answers import context, shared, source_value

__all__ = ["context", "shared"]


def teacher(
    c: SimpleNamespace, before_reply: Callable[[], None] | None = None
) -> Engine:
    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        returned = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
        if any(isinstance(p, RetryPromptPart) for p in messages[-1].parts):
            yield "The source is unavailable; use an ordinary local answer."
        elif not returned:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="shared-goal",
                    json_args=json.dumps(
                        {
                            "type": "text",
                            "prompt": "Your updated goal?",
                            "variable": c.share,
                        }
                    ),
                )
            }
        else:
            if before_reply:
                before_reply()
            yield "We will use your answer for this example."

    return Engine(
        FunctionModel(stream_function=model),
        memory_admission=True,
        memory_readonly_prefixes=("course:", "share:"),
    )


def run(
    c: SimpleNamespace, engine: Engine, answer: str | None = None, **kwargs: object
) -> list[RunMarkdownFlowDTO]:
    return list(
        run_agent.run_agent_lesson(
            c.app,
            engine=engine,
            user_bid=c.user,
            shifu_bid=c.target,
            outline_bid=c.outline,
            script=c.script,
            user_input=answer,
            iter_turn=_drive,
            **kwargs,
        )
    )


def test_real_named_answer_updates_source_keeps_full_history_and_no_local_copy(
    shared: SimpleNamespace,
) -> None:
    c = shared
    engine = teacher(c)
    run(c, engine)
    prefix = session_store.load_agent_session(c.app, c.user, c.outline).to_dict()[
        "messages"
    ]
    answer = "Updated exact goal\n" + "é" * 3000
    run(c, engine, answer)
    assert source_value(c) == answer
    assert (
        VariableValue.query.filter_by(user_bid=c.user, shifu_bid=c.target).count() == 0
    )
    stored = session_store.load_agent_session(c.app, c.user, c.outline)
    assert any(
        isinstance(p, ToolReturnPart)
        and p.tool_name == "interact"
        and answer in str(p.content)
        for m in stored.messages
        for p in m.parts
    )
    assert stored.to_dict()["messages"][: len(prefix)] == prefix
    assert stored.memory[c.share] == answer
    assert json.loads(stored.dumps())["memory"][c.share] == answer


@pytest.mark.parametrize("change", ["delete", "transfer", "publication", "value"])
def test_inflight_revocation_retains_answer_without_updating_source(
    shared: SimpleNamespace, change: str
) -> None:
    c = shared

    def revoke() -> None:
        with unit_of_work():
            if change == "transfer":
                DraftShifu.query.filter_by(shifu_bid=c.source).update(
                    {DraftShifu.created_user_bid: uuid4().hex}
                )
            elif change == "publication":
                db.session.add(
                    PublishedOutlineItem(
                        shifu_bid=c.target,
                        outline_item_bid=c.outline,
                        content="Collection removed.",
                    )
                )
            else:
                db.session.add(
                    VariableValue(
                        user_bid=c.user,
                        shifu_bid=c.source,
                        key="goal",
                        value="Concurrent change",
                        deleted=int(change == "delete"),
                    )
                )

    engine = teacher(c, revoke)
    run(c, engine)
    run(c, engine, "A new answer")
    assert source_value(c) == (
        "Source goal" if change in ("transfer", "publication") else "Concurrent change"
    )
    stored = session_store.load_agent_session(c.app, c.user, c.outline)
    assert any(
        isinstance(p, ToolReturnPart)
        and p.tool_name == "interact"
        and "A new answer" in str(p.content)
        for m in stored.messages
        for p in m.parts
    )
    assert c.share not in stored.all_memory()


def test_real_session_save_failure_rolls_back_source_and_preserves_pending_answer(
    shared: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = shared
    engine = teacher(c)
    run(c, engine)
    before = session_store.load_agent_session(c.app, c.user, c.outline).dumps()
    original = session_store._apply

    def fail(row: object, session: Session) -> None:
        original(row, session)
        assert source_value(c) == "New answer"
        message = "injected save failure"
        raise RuntimeError(message)

    with monkeypatch.context() as patch:
        patch.setattr(session_store, "_apply", fail)
        with pytest.raises(RuntimeError, match="injected save failure"):
            run(c, engine, "New answer")
    db.session.remove()
    assert source_value(c) == "Source goal"
    assert session_store.load_agent_session(c.app, c.user, c.outline).dumps() == before
    run(c, engine, "New answer")
    assert source_value(c) == "New answer"


def test_answer_grant_does_not_authorize_model_remember(
    shared: SimpleNamespace,
) -> None:
    c = shared

    async def check() -> None:
        outputs = []

        async def model(
            messages: list[ModelMessage], _info: AgentInfo
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            returned = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
            if returned:
                outputs.extend(p.content for p in returned)
                yield "Continue teaching."
            else:
                yield {
                    0: DeltaToolCall(
                        name="remember",
                        tool_call_id="note",
                        json_args=json.dumps(
                            {
                                "key": c.share,
                                "value": "Forbidden",
                                "scope": "user",
                                "request": None,
                            }
                        ),
                    )
                }

        engine = Engine(
            FunctionModel(stream_function=model),
            memory_admission=True,
            memory_readonly_prefixes=("course:", "share:"),
        )
        session = await engine.new_session(c.script)
        events = [
            e
            async for e in engine.run_turn(
                session, memory_answer_keys=frozenset({c.share})
            )
        ]
        assert not any(isinstance(e, MemoryUpdated) for e in events)
        assert c.share not in session.all_memory()
        assert "read-only reference" in outputs[0]

    asyncio.run(check())


@pytest.mark.parametrize("replay", [True, False])
def test_rewind_replay_cannot_overwrite_source_but_a_fresh_answer_can(
    shared: SimpleNamespace, replay: bool
) -> None:
    from flaskr.service.learn.agent.rewind import RewindPlan, checkpoint_of

    from tests.service.profile.test_course_references import _value

    c = shared
    engine = teacher(c)
    run(c, engine)
    checkpoint = checkpoint_of(
        session_store.load_agent_session(c.app, c.user, c.outline)
    )
    run(c, engine, "Old answer")
    _value(c, "Newer source")
    plan = RewindPlan(
        checkpoint=checkpoint, replay_values=["Old answer"] if replay else None
    )
    run(c, engine, "Fresh revised answer", rewind=plan)
    assert source_value(c) == ("Newer source" if replay else "Fresh revised answer")
    stored = session_store.load_agent_session(c.app, c.user, c.outline)
    expected = "Old answer" if replay else "Fresh revised answer"
    assert any(
        isinstance(p, ToolReturnPart) and expected in str(p.content)
        for m in stored.messages
        for p in m.parts
    )


def test_real_preview_has_no_shared_answer_grant(shared: SimpleNamespace) -> None:
    c = shared
    run(c, teacher(c), preview_mode=True)
    assert source_value(c) == "Source goal"
    stored = session_store.load_agent_session(
        c.app, c.user, c.outline, preview_mode=True
    )
    assert c.share not in stored.all_memory()
    assert not stored.pending


def test_source_memory_controls_and_resumed_host_do_not_resurrect_deleted_writeback(
    shared: SimpleNamespace,
) -> None:
    from flaskr.service.profile.api import delete_course_memory, list_course_memory

    c = shared
    engine = teacher(c)
    run(c, engine)
    run(c, engine, "Shared updated goal")
    row = next(
        item
        for item in list_course_memory(c.user, c.source)["items"]
        if item["key"] == "goal"
    )
    assert row["value"] == "Shared updated goal"
    delete_course_memory(c.user, c.source, int(row["value_id"]))
    assert not list_course_memory(c.user, c.source)["items"]
    run(c, engine)
    stored = session_store.load_agent_session(c.app, c.user, c.outline)
    assert c.share not in stored.all_memory()
    assert "Shared updated goal" in str(stored.messages)
    assert (
        VariableValue.query.filter_by(
            user_bid=c.user, shifu_bid=c.source, key="goal", deleted=0
        ).count()
        == 0
    )
