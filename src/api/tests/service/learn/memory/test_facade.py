"""Keep course memory aligned with existing profile persistence and resolution."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.context_v2 import RunScriptContextV2
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.memory import (
    MemorySnapshot,
    MemoryUpdate,
    VariableMemoryUpdate,
    load_learner_memory,
    load_memory,
    stage_memory,
)
from flaskr.service.profile.funcs import (
    get_profile_labels,
    get_user_profiles,
    update_user_profile_with_lable,
)
from flaskr.service.profile.learner_profile import clear_learner_profile
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.user.repository import create_user_entity
from sqlalchemy import func, select

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


@pytest.fixture
def scope(app: Flask) -> Iterator[tuple[str, str]]:
    """Provide real profile services with an isolated user and course definition."""
    user_bid, shifu_bid = uuid4().hex, uuid4().hex
    with app.app_context():
        with unit_of_work():
            create_user_entity(
                user_bid=user_bid,
                identify=user_bid,
                nickname="Current learner",
                language="en-US",
                learner_profile="Current background",
            )
            db.session.add(
                Variable(
                    variable_bid=uuid4().hex, shifu_bid=shifu_bid, key="base_level"
                )
            )
        yield user_bid, shifu_bid


def test_course_values_follow_settings_and_keep_user_course_isolation(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    other_user, other_course = uuid4().hex, uuid4().hex
    with unit_of_work():
        create_user_entity(
            user_bid=other_user, identify=other_user, nickname="Other learner"
        )
        db.session.add(
            Variable(variable_bid=uuid4().hex, shifu_bid=other_course, key="base_level")
        )
        stage_memory(
            app,
            user_bid,
            shifu_bid,
            MemoryUpdate(
                variables=[VariableMemoryUpdate("base_level", "beginner", "")]
            ),
        )
        stage_memory(
            app,
            user_bid,
            other_course,
            MemoryUpdate(
                variables=[VariableMemoryUpdate("base_level", "advanced", "")]
            ),
        )
        stage_memory(
            app,
            other_user,
            shifu_bid,
            MemoryUpdate(variables=[VariableMemoryUpdate("base_level", "expert", "")]),
        )

    assert load_memory(app, user_bid, shifu_bid).variables["base_level"] == "beginner"
    with unit_of_work():
        update_user_profile_with_lable(
            app,
            user_bid,
            [{"key": "base_level", "value": "intermediate"}],
            course_id=shifu_bid,
        )

    db.session.expire_all()
    assert (
        load_memory(app, user_bid, shifu_bid).variables["base_level"] == "intermediate"
    )
    assert (
        load_memory(app, user_bid, other_course).variables["base_level"] == "advanced"
    )
    assert load_memory(app, other_user, shifu_bid).variables["base_level"] == "expert"


def test_runtime_resolution_preserves_global_fallback_and_definition_filtering(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    with unit_of_work():
        stage_memory(
            app,
            user_bid,
            "",
            MemoryUpdate(
                variables=[VariableMemoryUpdate("base_level", "global default", "")]
            ),
        )
        stage_memory(
            app,
            user_bid,
            shifu_bid,
            MemoryUpdate(
                variables=[VariableMemoryUpdate("unlisted", "stored only", "")]
            ),
        )

    variables = load_memory(app, user_bid, shifu_bid).variables
    assert variables == get_user_profiles(app, user_bid, shifu_bid)
    assert variables["base_level"] == "global default"
    assert "unlisted" not in variables
    assert load_learner_memory(app, user_bid, shifu_bid=shifu_bid).get("unlisted") == (
        "stored only"
    )


def test_canonical_fields_and_profile_clear_override_stale_variable_rows(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    with unit_of_work():
        for key in ("sys_user_nickname", "sys_user_language", "sys_user_background"):
            db.session.add(
                VariableValue(
                    variable_value_bid=uuid4().hex,
                    user_bid=user_bid,
                    shifu_bid="",
                    key=key,
                    value="Stale compatibility value",
                )
            )

    variables = load_memory(app, user_bid, shifu_bid).variables
    assert variables["sys_user_nickname"] == "Current learner"
    assert variables["sys_user_language"] == "en-US"
    assert variables["sys_user_background"] == "Current background"

    clear_learner_profile(user_id=user_bid)
    assert load_memory(app, user_bid, shifu_bid).variables["sys_user_background"] == ""


def test_mapped_assignment_preserves_stored_value_and_updates_memory_payload(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    assignment = VariableMemoryUpdate("language", "en-US", "")
    mapped_language = get_profile_labels()["language"]["items_mapping"]["en-US"]
    assert mapped_language != assignment.value
    with unit_of_work():
        assert (
            stage_memory(app, user_bid, shifu_bid, MemoryUpdate(variables=[assignment]))
            is True
        )

    row = VariableValue.query.filter_by(user_bid=user_bid, key="language").one()
    assert row.shifu_bid == ""
    assert row.value == "en-US"
    assert assignment.value == mapped_language
    assert load_memory(app, user_bid, shifu_bid).variables == get_user_profiles(
        app, user_bid, shifu_bid
    )


def test_repeated_and_empty_assignments_preserve_existing_row_semantics(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    for value in ("a,b", "a,b", ""):
        with unit_of_work():
            stage_memory(
                app,
                user_bid,
                shifu_bid,
                MemoryUpdate(variables=[VariableMemoryUpdate("base_level", value, "")]),
            )
    rows = (
        VariableValue.query.filter_by(user_bid=user_bid, shifu_bid=shifu_bid)
        .order_by(VariableValue.id)
        .all()
    )
    assert [row.value for row in rows] == ["a,b", ""]
    assert load_memory(app, user_bid, shifu_bid).variables["base_level"] == ""


def test_staging_does_not_commit_and_the_owner_can_roll_back(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    count_values = (
        select(func.count())
        .select_from(VariableValue)
        .where(VariableValue.user_bid == user_bid)
    )

    def failing_step() -> None:
        with unit_of_work():
            stage_memory(
                app,
                user_bid,
                shifu_bid,
                MemoryUpdate(
                    variables=[VariableMemoryUpdate("base_level", "beginner", "")]
                ),
            )
            assert db.session.scalar(count_values) == 1
            with db.engine.connect() as connection:
                assert connection.scalar(count_values) == 0
            message = "owning step failed"
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="owning step failed"):
        failing_step()

    with db.engine.connect() as connection:
        assert connection.scalar(count_values) == 0
    assert "base_level" not in load_memory(app, user_bid, shifu_bid).variables


def test_prompt_projection_does_not_mutate_the_memory_snapshot() -> None:
    """Runtime variable overlays must not alter the loaded memory view."""
    memory = MemorySnapshot(variables={"base_level": "beginner"})
    variables = memory.as_variables()
    variables["base_level"] = "runtime override"
    variables["temporary"] = "session only"
    assert memory.variables == {"base_level": "beginner"}


def test_memory_patch_preserves_omitted_values_and_definition_identity(
    app: Flask, scope: tuple[str, str]
) -> None:
    """A memory update is a patch, including when it carries no assignments."""
    user_bid, shifu_bid = scope
    definition_bid = uuid4().hex
    with unit_of_work():
        db.session.add(
            Variable(variable_bid=definition_bid, shifu_bid=shifu_bid, key="goal")
        )
        stage_memory(
            app,
            user_bid,
            shifu_bid,
            MemoryUpdate(variables=[VariableMemoryUpdate("base_level", "beginner")]),
        )
    with unit_of_work():
        stage_memory(
            app,
            user_bid,
            shifu_bid,
            MemoryUpdate(
                variables=[VariableMemoryUpdate("goal", "practice", definition_bid)]
            ),
        )
        assert stage_memory(app, user_bid, shifu_bid, MemoryUpdate()) is True

    memory = load_memory(app, user_bid, shifu_bid)
    assert memory.variables["base_level"] == "beginner"
    assert memory.variables["goal"] == "practice"
    rows = VariableValue.query.filter_by(user_bid=user_bid, shifu_bid=shifu_bid).all()
    assert len(rows) == 2
    assert next(row for row in rows if row.key == "goal").variable_bid == definition_bid


def test_runtime_memory_update_preserves_normalization_and_mapped_events(
    app: Flask, scope: tuple[str, str]
) -> None:
    """Accepted assignments retain stored values and the mapped SSE contract."""
    user_bid, shifu_bid = scope
    definition = Variable.query.filter_by(shifu_bid=shifu_bid, key="base_level").one()
    validated = {"base_level": ["a", None, "b"], "language": "en-US", "empty": None}
    state = SimpleNamespace(
        run_script_info=SimpleNamespace(block_position=0, outline_bid="outline-memory"),
        mdflow_context=SimpleNamespace(
            process=Mock(return_value=SimpleNamespace(metadata={}, variables=validated))
        ),
        message_list=[],
        user_profile={},
        variable_definition_key_id_map={"base_level": definition.variable_bid},
    )
    ctx = RunScriptContextV2.__new__(RunScriptContextV2)
    ctx.app = app
    ctx._user_info = SimpleNamespace(user_id=user_bid)
    ctx._outline_item_info = SimpleNamespace(shifu_bid=shifu_bid)
    ctx._current_attend = SimpleNamespace(block_position=0)
    ctx._run_recorder = Mock()
    block = SimpleNamespace(generated_block_bid="block-memory")

    with unit_of_work():
        events = list(ctx._phase_validate_input_and_advance(app, state, block, {}))

    assert [event.type for event in events] == [GeneratedType.VARIABLE_UPDATE] * 3
    assert [
        (event.content.variable_name, event.content.variable_value) for event in events
    ] == [
        ("base_level", "a,b"),
        ("language", get_profile_labels()["language"]["items_mapping"]["en-US"]),
        ("empty", ""),
    ]
    rows = {
        row.key: row for row in VariableValue.query.filter_by(user_bid=user_bid).all()
    }
    assert rows["base_level"].value == "a,b"
    assert rows["base_level"].variable_bid == definition.variable_bid
    assert rows["language"].value == "en-US"
    assert rows["language"].shifu_bid == ""
    assert rows["empty"].value == ""
    ctx._recorder.update_progress_pointer.assert_called_once()
