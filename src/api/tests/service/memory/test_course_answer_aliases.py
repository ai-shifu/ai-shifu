"""Verify course aliases resolve without duplicating or reviving stored answers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.memory.api import (
    MemoryUpdate,
    VariableMemoryUpdate,
    delete_course_memory,
    load_memory,
    stage_memory,
)
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.repository import create_user_entity

if TYPE_CHECKING:
    from flask import Flask


def test_referenced_alias_loads_an_older_scoped_answer_and_respects_delete(
    app: Flask,
) -> None:
    user, course, other_course = (uuid4().hex for _ in range(3))
    question = "What would you like to learn?"
    with app.app_context():
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            assert stage_memory(
                app,
                user,
                course,
                MemoryUpdate(
                    variables=[
                        VariableMemoryUpdate(key="goal", value="Old answer"),
                        VariableMemoryUpdate(
                            key=question,
                            value="Algebra",
                            alias="goal",
                            question_answer=True,
                        ),
                    ]
                ),
            )
            db.session.add_all(
                VariableValue(
                    user_bid=user,
                    shifu_bid=course,
                    key=f"Other question {i}?",
                    value="Another answer",
                    variable_value_bid=uuid4().hex,
                )
                for i in range(101)
            )
        snapshot = load_memory(app, user, course, include_course_variables=True)
        assert question not in snapshot.variables
        assert "goal" not in snapshot.as_variables()
        referenced = load_memory(
            app,
            user,
            course,
            include_course_variables=True,
            reference_text="Build on {{goal}}.",
        )
        assert referenced.aliases == {"goal": question}
        assert referenced.as_variables()["goal"] == "Algebra"
        assert referenced.variables[question] == "Algebra"
        assert (
            "goal"
            not in load_memory(
                app, user, other_course, reference_text="{{goal}}"
            ).as_variables()
        )
        assert [
            row.value
            for row in VariableValue.query.filter_by(
                user_bid=user, shifu_bid=course, key="goal"
            ).all()
        ] == ["Old answer"]

        row = VariableValue.query.filter_by(
            user_bid=user, shifu_bid=course, key=question
        ).one()
        assert delete_course_memory(user, course, row.id) == {"conflict": False}
        removed = load_memory(
            app, user, course, reference_text="{{goal}}", include_course_variables=True
        )
        assert removed.aliases == {"goal": question}
        assert question not in removed.variables
        assert "goal" not in removed.as_variables()


def test_canonical_answer_takes_over_alias_atomically(app: Flask) -> None:
    user, course = (uuid4().hex for _ in range(2))
    old_question = "What do you want to learn?"
    question = "What would you like to learn?"
    with app.app_context():
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            assert stage_memory(
                app,
                user,
                course,
                MemoryUpdate(
                    variables=[
                        VariableMemoryUpdate(
                            key=question,
                            value="Algebra",
                            alias=old_question,
                            question_answer=True,
                        )
                    ]
                ),
            )
        update = MemoryUpdate(
            variables=[
                VariableMemoryUpdate(
                    key=old_question, value="Geometry", question_answer=True
                )
            ]
        )

        def stage_and_abort() -> None:
            with unit_of_work():
                assert stage_memory(app, user, course, update)
                msg = "abort"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="abort"):
            stage_and_abort()
        snapshot = load_memory(app, user, course, include_course_variables=True)
        assert snapshot.as_variables()[old_question] == "Algebra"
        assert old_question not in snapshot.variables

        with unit_of_work():
            assert stage_memory(app, user, course, update)
        snapshot = load_memory(app, user, course, include_course_variables=True)
        assert snapshot.aliases == {}
        assert snapshot.as_variables()[old_question] == "Geometry"
