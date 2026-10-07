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


def test_agent_projection_includes_only_current_course_undeclared_variables(
    app: Flask, scope: tuple[str, str]
) -> None:
    """Opt-in reads keep legacy rows, use latest live values and defer system fields."""
    user, course = scope
    with unit_of_work():
        for owner, context, key, value, deleted in [
            (user, course, "requested", "old", 0),
            (user, course, "requested", "latest", 0),
            (user, course, "requested", "deleted", 1),
            (user, "other-course", "elsewhere", "private", 0),
            ("other-user", course, "other_user", "private", 0),
            (user, "", "global_undeclared", "global", 0),
            (user, course, "sys_user_nickname", "stale", 0),
            (user, course, "sys_arbitrary", "not canonical", 0),
            (user, course, "language", "not course scoped", 0),
            (user, course, "sysXliteral", "not a system prefix", 0),
        ]:
            db.session.add(
                VariableValue(
                    variable_value_bid=uuid4().hex,
                    user_bid=owner,
                    shifu_bid=context,
                    key=key,
                    value=value,
                    deleted=deleted,
                )
            )
    default = load_memory(app, user, course).variables
    assert "requested" not in default
    memory = load_memory(app, user, course, include_course_variables=True).variables
    assert memory == {
        **default,
        "requested": "latest",
        "sysXliteral": "not a system prefix",
    }
    assert memory["sys_user_nickname"] == "Current learner"


def test_supplementary_course_projection_considers_only_the_newest_hundred_keys(
    app: Flask, scope: tuple[str, str]
) -> None:
    """A projection bound never deletes history or caps the existing defined-variable path."""
    user, course = scope
    with unit_of_work():
        for index in range(120):
            db.session.add(
                VariableValue(
                    variable_value_bid=uuid4().hex,
                    user_bid=user,
                    shifu_bid=course,
                    key=f"extra_{index}",
                    value="kept",
                )
            )
        stage_memory(
            app,
            user,
            course,
            MemoryUpdate(
                variables=[VariableMemoryUpdate("base_level", "defined answer")]
            ),
        )
    memory = load_memory(app, user, course, include_course_variables=True).variables
    extras = {key: value for key, value in memory.items() if key.startswith("extra_")}
    assert set(extras) == {f"extra_{index}" for index in range(20, 120)}
    assert memory["base_level"] == "defined answer"
    assert VariableValue.query.filter_by(user_bid=user, shifu_bid=course).count() == 121


def test_supplementary_json_budget_keeps_whole_values_and_exact_defined_answers(
    app: Flask, scope: tuple[str, str]
) -> None:
    """Escaping counts; oversized unknown rows stay stored while named answers remain exact."""
    import json

    user, course = scope
    answer = "é" * 50_000
    with unit_of_work():
        stage_memory(
            app,
            user,
            course,
            MemoryUpdate(variables=[VariableMemoryUpdate("base_level", answer)]),
        )
        for index in range(5):
            db.session.add(
                VariableValue(
                    variable_value_bid=uuid4().hex,
                    user_bid=user,
                    shifu_bid=course,
                    key=f"extra_{index}",
                    value="\x00" * 2000,
                )
            )
        db.session.add(
            VariableValue(
                variable_value_bid=uuid4().hex,
                user_bid=user,
                shifu_bid=course,
                key="oversized_unknown",
                value="é" * 40_000,
            )
        )
    memory = load_memory(app, user, course, include_course_variables=True).variables
    extras = {key: value for key, value in memory.items() if key.startswith("extra_")}
    assert set(extras) == {"extra_4", "extra_3"}
    assert len(json.dumps(extras, ensure_ascii=False, indent=2)) <= 32_768
    assert all(value == "\x00" * 2000 for value in extras.values())
    assert memory["base_level"] == answer
    assert "oversized_unknown" not in memory
    assert (
        VariableValue.query.filter_by(user_bid=user, key="oversized_unknown")
        .one()
        .value
        == "é" * 40_000
    )


@pytest.mark.parametrize("fresh", [False, True])
def test_legacy_runtime_does_not_restore_a_value_deleted_during_validation(
    app: Flask,
    scope: tuple[str, str],
    fresh: bool,
) -> None:
    from flaskr.service.profile.api import (
        course_memory_deletion_state,
        delete_course_memory,
        list_course_memory,
    )

    user, course = scope
    with unit_of_work():
        stage_memory(
            app,
            user,
            course,
            MemoryUpdate(variables=[VariableMemoryUpdate("base_level", "old")]),
        )
    generation, _ = course_memory_deletion_state(user, course)
    selected = list_course_memory(user, course)["items"][0]
    delete_course_memory(user, course, int(selected["value_id"]))
    if fresh:
        generation, _ = course_memory_deletion_state(user, course)
    state = SimpleNamespace(
        run_script_info=SimpleNamespace(block_position=0, outline_bid="lesson"),
        mdflow_context=SimpleNamespace(
            process=Mock(
                return_value=SimpleNamespace(
                    metadata={}, variables={"base_level": "new answer"}
                )
            )
        ),
        message_list=[],
        user_profile={},
        variable_definition_key_id_map={},
        memory_generations=generation,
    )
    ctx = RunScriptContextV2.__new__(RunScriptContextV2)
    ctx.app = app
    ctx._user_info = SimpleNamespace(user_id=user)
    ctx._outline_item_info = SimpleNamespace(shifu_bid=course)
    ctx._current_attend = SimpleNamespace(block_position=0)
    ctx._run_recorder = Mock()
    block = SimpleNamespace(generated_block_bid="block")
    events = list(ctx._phase_validate_input_and_advance(app, state, block, {}))
    values = list_course_memory(user, course)["items"]
    assert len(values) == int(fresh)
    assert len(events) == int(fresh)
    if fresh:
        assert values[0]["value"] == "new answer"
    ctx._recorder.update_progress_pointer.assert_called_once()


def test_legacy_memory_and_progress_failure_roll_back_together(
    app: Flask,
    scope: tuple[str, str],
) -> None:
    user, course = scope
    state = SimpleNamespace(
        run_script_info=SimpleNamespace(block_position=0, outline_bid="lesson"),
        mdflow_context=SimpleNamespace(
            process=Mock(
                return_value=SimpleNamespace(
                    metadata={}, variables={"base_level": "new answer"}
                )
            )
        ),
        message_list=[],
        user_profile={},
        variable_definition_key_id_map={},
        memory_generations={},
    )
    ctx = RunScriptContextV2.__new__(RunScriptContextV2)
    ctx.app = app
    ctx._user_info = SimpleNamespace(user_id=user)
    ctx._outline_item_info = SimpleNamespace(shifu_bid=course)
    ctx._current_attend = SimpleNamespace(block_position=0)
    ctx._run_recorder = Mock()
    ctx._run_recorder.update_progress_pointer.side_effect = RuntimeError(
        "progress failure"
    )
    block = SimpleNamespace(generated_block_bid="block")
    with pytest.raises(RuntimeError, match="progress failure"):
        next(ctx._phase_validate_input_and_advance(app, state, block, {}))
    assert not VariableValue.query.filter_by(user_bid=user, shifu_bid=course).all()
