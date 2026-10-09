"""Exercise actual follow-up tool calls without network or provider credentials."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from flaskr.service.learn.follow_up_memory_writer import (
    FollowUpMemoryPatch,
    FollowUpMemoryRun,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

REQUEST = "Please remember that my practice code is 7319."


def note_model(
    notes: list[dict], returns: list[str], *, fail: bool = False
) -> FunctionModel:
    """Emit real tool deltas, then either answer or fail after admission."""

    async def stream(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        last = messages[-1]
        parts = (
            [p for p in last.parts if isinstance(p, ToolReturnPart)]
            if isinstance(last, ModelRequest)
            else []
        )
        if parts:
            returns.extend(str(p.content) for p in parts)
            if fail:
                message = "provider interrupted"
                raise RuntimeError(message)
            yield "Acknowledged."
        else:
            yield {
                i: DeltaToolCall(
                    name="remember",
                    tool_call_id=f"note-{i}",
                    json_args=json.dumps(note),
                )
                for i, note in enumerate(notes)
            }

    return FunctionModel(stream_function=stream)


@pytest.mark.parametrize(
    ("declared", "quote", "approved", "allowed"),
    [
        (frozenset({"practice_code"}), None, False, True),
        (frozenset(), REQUEST, True, True),
        (frozenset(), REQUEST, False, False),
        (frozenset(), "An old learner request", True, False),
        (frozenset(), None, True, False),
    ],
)
def test_follow_up_uses_actual_declared_or_requested_admission(
    declared: object, quote: object, approved: object, allowed: object
) -> None:
    """Only current authored declarations or independently approved current requests grant writes."""
    patch = FollowUpMemoryPatch()
    checker = AsyncMock(return_value=approved)
    returns = []
    run = FollowUpMemoryRun(
        note_model(
            [{"key": "practice_code", "value": "7319", "request": quote}], returns
        ),
        patch=patch,
        current_input=REQUEST,
        declared_keys=declared,
        snapshot={},
        deleted_keys=frozenset(),
        generations={},
        reserved_keys=frozenset({"sys_nickname"}),
        request_check=checker,
        preview=False,
    )
    chunks = list(run.stream([{"role": "user", "content": REQUEST}]))
    assert "".join(c.result for c in chunks) == "Acknowledged."
    assert [(x.key, x.value) for x in patch.variables] == (
        [("practice_code", "7319")] if allowed else []
    )
    assert returns
    assert returns[0].startswith("remembered ") == allowed
    if declared or quote != REQUEST:
        checker.assert_not_awaited()


@pytest.mark.parametrize("failure", ["provider", "disconnect", "preview"])
def test_unfinished_or_preview_answers_do_not_publish_memory_patch(
    failure: object,
) -> None:
    """Approved native-thread proposals only leave a successfully consumed real answer."""
    patch = FollowUpMemoryPatch()
    run = FollowUpMemoryRun(
        note_model(
            [{"key": "practice_code", "value": "7319", "request": REQUEST}],
            [],
            fail=failure == "provider",
        ),
        patch=patch,
        current_input=REQUEST,
        declared_keys=frozenset(),
        snapshot={},
        deleted_keys=frozenset(),
        generations={},
        reserved_keys=frozenset(),
        request_check=AsyncMock(return_value=True),
        preview=failure == "preview",
    )
    stream = run.stream([{"role": "user", "content": REQUEST}])
    if failure == "provider":
        with pytest.raises(RuntimeError, match="provider interrupted"):
            list(stream)
    elif failure == "disconnect":
        next(stream)
        stream.close()
    else:
        list(stream)
    assert patch.variables == []


@pytest.mark.parametrize(
    ("key", "deleted", "snapshot", "value", "allowed"),
    [
        ("sys_nickname", frozenset(), {}, "Name", False),
        ("course:other:secret", frozenset(), {}, "secret", False),
        ("share:secret", frozenset(), {}, "secret", False),
        ("practice_code", frozenset({"practice_code"}), {}, "7319", True),
        ("practice_code", frozenset(), {}, "x" * 2001, False),
        (
            "new_note",
            frozenset(),
            {f"item_{i}": "old" for i in range(100)},
            "small",
            False,
        ),
        ("item_0", frozenset(), {f"item_{i}": "old" for i in range(100)}, "new", True),
    ],
)
def test_follow_up_reuses_system_reference_deletion_and_capacity_policy(
    key: object, deleted: object, snapshot: object, value: object, allowed: object
) -> None:
    """A successful model answer cannot bypass the existing memory tool's storage constraints."""
    patch = FollowUpMemoryPatch()
    run = FollowUpMemoryRun(
        note_model([{"key": key, "value": value, "request": REQUEST}], []),
        patch=patch,
        current_input=REQUEST,
        declared_keys=frozenset(),
        snapshot=snapshot,
        deleted_keys=deleted,
        generations={"practice_code": 3},
        reserved_keys=frozenset({"sys_nickname"}),
        request_check=AsyncMock(return_value=True),
        preview=False,
    )
    list(run.stream([{"role": "user", "content": REQUEST}]))
    assert bool(patch.variables) == allowed
    if allowed:
        assert patch.generations == {"practice_code": 3}
    assert run.snapshot == snapshot


def test_plain_question_does_not_add_admission_model_requests() -> None:
    """Ordinary answers need only their original model request and produce no memory writes."""
    calls = []

    async def stream(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        calls.append(messages)
        yield "A normal answer."

    patch = FollowUpMemoryPatch()
    checker = AsyncMock()
    run = FollowUpMemoryRun(
        FunctionModel(stream_function=stream),
        patch=patch,
        current_input="Explain this.",
        declared_keys=frozenset(),
        snapshot={},
        deleted_keys=frozenset(),
        generations={},
        reserved_keys=frozenset(),
        request_check=checker,
        preview=False,
    )
    assert (
        "".join(
            x.result for x in run.stream([{"role": "user", "content": "Explain this."}])
        )
        == "A normal answer."
    )
    assert len(calls) == 1
    checker.assert_not_awaited()
    assert patch.variables == []


@pytest.fixture
def storage_scope(app: object) -> object:
    """Create a real learner, retained published script and learning attempt."""
    from types import SimpleNamespace
    from uuid import uuid4

    from flaskr.dao import db
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.learn.models import LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
    from flaskr.service.shifu.models import PublishedOutlineItem
    from flaskr.service.user.repository import create_user_entity

    user, course, outline, progress = (uuid4().hex for _ in range(4))
    with app.app_context(), unit_of_work():
        create_user_entity(user_bid=user, identify=user, nickname="Learner")
        row = PublishedOutlineItem(
            shifu_bid=course,
            outline_item_bid=outline,
            content="Collect %{{practice_code}}.\n```md\n%{{example}}\n```",
            title="Lesson",
            position="1",
        )
        db.session.add(row)
        db.session.add(
            LearnProgressRecord(
                user_bid=user,
                shifu_bid=course,
                outline_item_bid=outline,
                progress_record_bid=progress,
                status=LEARN_STATUS_IN_PROGRESS,
            )
        )
        db.session.flush()
        row_id = row.id
    return SimpleNamespace(
        user=user, course=course, outline=outline, progress=progress, row_id=row_id
    )


def test_policy_uses_retained_course_bound_main_script(
    app: object, storage_scope: object
) -> None:
    """A later publication or another course cannot silently grant write permission."""
    from flaskr.dao import db
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.learn.follow_up_memory_writer import (
        load_follow_up_memory_policy,
    )
    from flaskr.service.shifu.models import PublishedOutlineItem

    scope = storage_scope
    args = {
        "user_bid": scope.user,
        "shifu_bid": scope.course,
        "outline_bid": scope.outline,
        "outline_row_id": scope.row_id,
        "preview": False,
    }
    with app.app_context():
        with unit_of_work():
            db.session.add(
                PublishedOutlineItem(
                    shifu_bid=scope.course,
                    outline_item_bid=scope.outline,
                    content="Collect %{{future}}.",
                    title="New lesson",
                    position="1",
                )
            )
        policy = load_follow_up_memory_policy(**args)
        assert policy.declared_keys == frozenset({"practice_code"})
        assert (
            load_follow_up_memory_policy(**{**args, "shifu_bid": "another-course"})
            is None
        )
        assert load_follow_up_memory_policy(**{**args, "outline_row_id": None}) is None


def test_completed_memory_patch_is_course_scoped_and_atomic_with_history(
    app: object, storage_scope: object
) -> None:
    """The host transaction owns both notes and answer rows, with real rollback coverage."""
    from flaskr.dao import db
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.learn.follow_up_memory_writer import stage_follow_up_memory
    from flaskr.service.learn.memory import VariableMemoryUpdate, load_memory
    from flaskr.service.learn.models import LearnGeneratedBlock

    scope = storage_scope
    args = {
        "user_bid": scope.user,
        "shifu_bid": scope.course,
        "outline_bid": scope.outline,
        "progress_record_bid": scope.progress,
    }
    with app.app_context():

        def failing_step() -> None:
            with unit_of_work():
                db.session.add(
                    LearnGeneratedBlock(
                        generated_block_bid=scope.progress,
                        user_bid=scope.user,
                        shifu_bid=scope.course,
                        generated_content="An answer",
                    )
                )
                assert stage_follow_up_memory(
                    app,
                    **args,
                    patch=FollowUpMemoryPatch(
                        variables=[VariableMemoryUpdate("practice_code", "7319")]
                    ),
                )
                message = "history failed"
                raise RuntimeError(message)

        with pytest.raises(RuntimeError, match="history failed"):
            failing_step()
        assert (
            LearnGeneratedBlock.query.filter_by(
                generated_block_bid=scope.progress
            ).first()
            is None
        )
        assert (
            "practice_code"
            not in load_memory(
                app, scope.user, scope.course, include_course_variables=True
            ).as_variables()
        )
        with unit_of_work():
            assert stage_follow_up_memory(
                app,
                **args,
                patch=FollowUpMemoryPatch(
                    variables=[VariableMemoryUpdate("practice_code", "7319")]
                ),
            )
        assert (
            load_memory(
                app, scope.user, scope.course, include_course_variables=True
            ).as_variables()["practice_code"]
            == "7319"
        )
        assert (
            "practice_code"
            not in load_memory(
                app, scope.user, "another-course", include_course_variables=True
            ).as_variables()
        )


@pytest.mark.parametrize("race", ["reset", "delete", "wrong-course"])
def test_completed_patch_cannot_restore_a_reset_attempt_or_concurrent_deletion(
    app: object, storage_scope: object, race: object
) -> None:
    """Check the live attempt and deletion generation inside the same final write transaction."""
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.learn.follow_up_memory_writer import stage_follow_up_memory
    from flaskr.service.learn.memory import (
        MemoryUpdate,
        VariableMemoryUpdate,
        load_memory,
        stage_memory,
    )
    from flaskr.service.learn.models import LearnProgressRecord
    from flaskr.service.order.consts import LEARN_STATUS_RESET
    from flaskr.service.profile.api import (
        course_memory_deletion_state,
        delete_course_memory,
    )
    from flaskr.service.profile.models import VariableValue

    scope = storage_scope
    with app.app_context():
        with unit_of_work():
            stage_memory(
                app,
                scope.user,
                scope.course,
                MemoryUpdate(variables=[VariableMemoryUpdate("practice_code", "old")]),
            )
        generations, _ = course_memory_deletion_state(scope.user, scope.course)
        patch = FollowUpMemoryPatch(
            variables=[VariableMemoryUpdate("practice_code", "7319")],
            generations=generations,
        )
        with unit_of_work():
            if race == "reset":
                LearnProgressRecord.query.filter_by(
                    progress_record_bid=scope.progress
                ).first().status = LEARN_STATUS_RESET
            elif race == "delete":
                row = VariableValue.query.filter_by(
                    user_bid=scope.user,
                    shifu_bid=scope.course,
                    key="practice_code",
                    deleted=0,
                ).first()
                delete_course_memory(scope.user, scope.course, row.id)
        with unit_of_work():
            assert not stage_follow_up_memory(
                app,
                user_bid=scope.user,
                shifu_bid="wrong-course" if race == "wrong-course" else scope.course,
                outline_bid=scope.outline,
                progress_record_bid=scope.progress,
                patch=patch,
            )
        current = load_memory(
            app, scope.user, scope.course, include_course_variables=True
        ).as_variables()
        assert current.get("practice_code") == (None if race == "delete" else "old")


def test_idle_native_follow_up_notices_request_cancellation() -> None:
    """A quiet provider must not hide a disconnected request until its next text chunk."""
    import asyncio
    import threading
    import time

    started = threading.Event()

    async def stream(_messages: object, _info: object) -> AsyncIterator[str]:
        started.set()
        await asyncio.sleep(10)
        yield "Too late"

    patch = FollowUpMemoryPatch()
    run = FollowUpMemoryRun(
        FunctionModel(stream_function=stream),
        patch=patch,
        current_input=REQUEST,
        declared_keys=frozenset(),
        snapshot={},
        deleted_keys=frozenset(),
        generations={},
        reserved_keys=frozenset(),
        request_check=AsyncMock(),
        preview=False,
        cancelled=started.is_set,
    )
    start = time.monotonic()
    with pytest.raises(GeneratorExit):
        list(run.stream([{"role": "user", "content": REQUEST}]))
    assert time.monotonic() - start < 3
    assert patch.variables == []


def test_declared_system_field_uses_existing_global_profile_storage(
    app: object, storage_scope: object
) -> None:
    """Author-declared registered fields remain global; explicit undeclared requests cannot edit them."""
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.learn.follow_up_memory_writer import stage_follow_up_memory
    from flaskr.service.learn.memory import load_memory

    scope = storage_scope
    patch = FollowUpMemoryPatch()
    checker = AsyncMock(return_value=False)
    run = FollowUpMemoryRun(
        note_model(
            [{"key": "sys_user_nickname", "value": "Student", "request": None}], []
        ),
        patch=patch,
        current_input="Call me Student.",
        declared_keys=frozenset({"sys_user_nickname"}),
        snapshot={},
        deleted_keys=frozenset(),
        generations={},
        reserved_keys=frozenset({"sys_user_nickname"}),
        request_check=checker,
        preview=False,
    )
    list(run.stream([{"role": "user", "content": "Call me Student."}]))
    with app.app_context(), unit_of_work():
        assert stage_follow_up_memory(
            app,
            user_bid=scope.user,
            shifu_bid=scope.course,
            outline_bid=scope.outline,
            progress_record_bid=scope.progress,
            patch=patch,
        )
    with app.app_context():
        assert (
            load_memory(app, scope.user, "another-course").as_variables()[
                "sys_user_nickname"
            ]
            == "Student"
        )
    checker.assert_not_awaited()
