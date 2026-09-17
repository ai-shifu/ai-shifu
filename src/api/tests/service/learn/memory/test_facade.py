"""Keep course memory aligned with existing profile persistence and resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.memory import (
    load_course_variables,
    load_learner_memory,
    stage_course_variables,
)
from flaskr.service.profile.dtos import ProfileToSave
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
        stage_course_variables(
            app, user_bid, shifu_bid, [ProfileToSave("base_level", "beginner", "")]
        )
        stage_course_variables(
            app, user_bid, other_course, [ProfileToSave("base_level", "advanced", "")]
        )
        stage_course_variables(
            app, other_user, shifu_bid, [ProfileToSave("base_level", "expert", "")]
        )

    assert load_course_variables(app, user_bid, shifu_bid)["base_level"] == "beginner"
    with unit_of_work():
        update_user_profile_with_lable(
            app,
            user_bid,
            [{"key": "base_level", "value": "intermediate"}],
            course_id=shifu_bid,
        )

    db.session.expire_all()
    assert (
        load_course_variables(app, user_bid, shifu_bid)["base_level"] == "intermediate"
    )
    assert (
        load_course_variables(app, user_bid, other_course)["base_level"] == "advanced"
    )
    assert load_course_variables(app, other_user, shifu_bid)["base_level"] == "expert"


def test_runtime_resolution_preserves_global_fallback_and_definition_filtering(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    with unit_of_work():
        stage_course_variables(
            app, user_bid, "", [ProfileToSave("base_level", "global default", "")]
        )
        stage_course_variables(
            app, user_bid, shifu_bid, [ProfileToSave("unlisted", "stored only", "")]
        )

    variables = load_course_variables(app, user_bid, shifu_bid)
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

    variables = load_course_variables(app, user_bid, shifu_bid)
    assert variables["sys_user_nickname"] == "Current learner"
    assert variables["sys_user_language"] == "en-US"
    assert variables["sys_user_background"] == "Current background"

    clear_learner_profile(user_id=user_bid)
    assert load_course_variables(app, user_bid, shifu_bid)["sys_user_background"] == ""


def test_mapped_assignment_preserves_stored_value_and_mutates_the_original_dto(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    assignment = ProfileToSave("language", "en-US", "")
    mapped_language = get_profile_labels()["language"]["items_mapping"]["en-US"]
    assert mapped_language != assignment.value
    with unit_of_work():
        assert stage_course_variables(app, user_bid, shifu_bid, [assignment]) is True

    row = VariableValue.query.filter_by(user_bid=user_bid, key="language").one()
    assert row.shifu_bid == ""
    assert row.value == "en-US"
    assert assignment.value == mapped_language
    assert load_course_variables(app, user_bid, shifu_bid) == get_user_profiles(
        app, user_bid, shifu_bid
    )


def test_repeated_and_empty_assignments_preserve_existing_row_semantics(
    app: Flask, scope: tuple[str, str]
) -> None:
    user_bid, shifu_bid = scope
    for value in ("a,b", "a,b", ""):
        with unit_of_work():
            stage_course_variables(
                app, user_bid, shifu_bid, [ProfileToSave("base_level", value, "")]
            )
    rows = (
        VariableValue.query.filter_by(user_bid=user_bid, shifu_bid=shifu_bid)
        .order_by(VariableValue.id)
        .all()
    )
    assert [row.value for row in rows] == ["a,b", ""]
    assert load_course_variables(app, user_bid, shifu_bid)["base_level"] == ""


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
            stage_course_variables(
                app, user_bid, shifu_bid, [ProfileToSave("base_level", "beginner", "")]
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
    assert "base_level" not in load_course_variables(app, user_bid, shifu_bid)
