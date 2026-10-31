"""Keep distinct authored text keys separate even when SQL text comparison folds case."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.memory.reader import (
    load_course_variables,
    load_learner_memory,
)
from flaskr.service.profile.models import VariableValue
from sqlalchemy import MetaData, String


@pytest.fixture
def text_key_app(tmp_path: Path) -> Iterator[Flask]:
    app = Flask("exact-text-key-reader")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'text-keys.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={},
    )
    db.init_app(app)
    table = VariableValue.__table__.to_metadata(MetaData())
    table.c.key.type = String(255, collation="NOCASE")
    with app.app_context():
        table.create(db.engine)
        yield app
        db.session.remove()
        db.engine.dispose()


def _store(*values: tuple[str, str, str]) -> None:
    with unit_of_work():
        for key, value, course in values:
            db.session.add(
                VariableValue(
                    variable_value_bid=uuid4().hex,
                    variable_bid=uuid4().hex,
                    user_bid="learner",
                    shifu_bid=course,
                    key=key,
                    value=value,
                    deleted=0,
                )
            )


@pytest.mark.usefixtures("text_key_app")
def test_course_supplement_groups_and_excludes_exact_keys() -> None:
    _store(
        ("Goal?", "old", "course"),
        ("goal?", "lower", "course"),
        ("Goal?", "upper", "course"),
        ("你的 目标？", "中文", "course"),
    )
    assert load_course_variables("learner", "course") == {
        "Goal?": "upper",
        "goal?": "lower",
        "你的 目标？": "中文",
    }
    assert load_course_variables(
        "learner", "course", exclude_keys=frozenset({"Goal?"})
    ) == {"goal?": "lower", "你的 目标？": "中文"}


@pytest.mark.usefixtures("text_key_app")
def test_course_supplement_compares_reserved_keys_exactly() -> None:
    _store(
        ("sys_note", "reserved", "course"),
        ("SYS_note", "local", "course"),
        ("sys_user_language", "registered", "course"),
        ("Sys_user_language", "distinct system spelling", "course"),
        ("sex", "ordinary course variable", "course"),
        ("Sex", "distinct", "course"),
    )
    assert load_course_variables("learner", "course") == {
        "SYS_note": "local",
        "Sex": "distinct",
        "sex": "ordinary course variable",
        "Sys_user_language": "distinct system spelling",
    }


def test_memory_limits_count_exact_live_keys_after_collapsing_history(
    text_key_app: Flask,
) -> None:
    _store(("goal?", "lower", "course"))
    _store(*(("Goal?", f"upper-{i}", "course") for i in range(20)))
    memory = load_learner_memory(text_key_app, "learner", shifu_bid="course", limit=2)
    assert memory.as_variables() == {"Goal?": "upper-19", "goal?": "lower"}
    assert memory.truncated is False
    capped = load_learner_memory(text_key_app, "learner", shifu_bid="course", limit=1)
    assert capped.as_variables() == {"Goal?": "upper-19"}
    assert capped.truncated is True


def test_scope_precedence_and_elsewhere_use_the_same_exact_identity(
    text_key_app: Flask,
) -> None:
    _store(
        ("Goal?", "course-upper", "course"),
        ("goal?", "course-lower", "course"),
        ("Goal?", "global-upper", ""),
        ("Goal?", "other-upper", "other"),
        ("goal?", "other-lower", "other"),
    )
    memory = load_learner_memory(text_key_app, "learner", shifu_bid="course")
    assert memory.as_variables() == {
        "Goal?": "course-upper",
        "goal?": "course-lower",
    }
    assert {
        key: [entry.value for entry in entries]
        for key, entries in memory.elsewhere.items()
    } == {
        "Goal?": ["other-upper"],
        "goal?": ["other-lower"],
    }
