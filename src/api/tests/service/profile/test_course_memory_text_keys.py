"""Keep self-service memory keys exact under a case-folding database collation."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.profile.course_memory import (
    course_memory_deletion_state,
    course_memory_value_versions,
    delete_course_memory,
    list_course_memory,
)
from flaskr.service.profile.models import VariableValue
from sqlalchemy import MetaData, String


@pytest.fixture
def text_key_app(tmp_path: Path) -> Iterator[Flask]:
    app = Flask("exact-course-memory-keys")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'course-memory.db'}",
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


def _store(
    key: str, value: str, *, user: str = "learner", course: str = "course"
) -> VariableValue:
    row = VariableValue(
        variable_value_bid=uuid4().hex,
        user_bid=user,
        shifu_bid=course,
        key=key,
        value=value,
        deleted=0,
    )
    db.session.add(row)
    return row


@pytest.mark.usefixtures("text_key_app")
def test_listing_preserves_each_exact_live_key_and_does_not_resurrect_history() -> None:
    with unit_of_work():
        _store("Name", "old upper")
        upper = _store("Name", "current upper")
        lower = _store("name", "current lower")
        _store("Name", "another learner", user="other")
        _store("Name", "another course", course="other")
        _store("Name", "global value", course="")
    page = list_course_memory("learner", "course")
    assert {item["key"]: item["value"] for item in page["items"]} == {
        "Name": "current upper",
        "name": "current lower",
    }
    assert [item["value_id"] for item in page["items"]] == [
        str(lower.id),
        str(upper.id),
    ]
    assert list_course_memory("learner", "course", before=upper.id)["items"] == []


@pytest.mark.usefixtures("text_key_app")
def test_delete_invalidates_only_the_selected_exact_keys_history_and_generation() -> (
    None
):
    with unit_of_work():
        old = _store("Name", "old upper")
        upper = _store("Name", "current upper")
        lower = _store("name", "current lower")
        other_user = _store("Name", "another learner", user="other")
        other_course = _store("Name", "another course", course="other")
        global_row = _store("Name", "global value", course="")
    assert delete_course_memory("learner", "course", old.id) == {"conflict": True}
    assert not old.deleted
    assert not upper.deleted
    assert not lower.deleted
    assert delete_course_memory("learner", "course", upper.id) == {"conflict": False}
    assert old.deleted
    assert upper.deleted
    assert not lower.deleted
    assert not other_user.deleted
    assert not other_course.deleted
    assert not global_row.deleted
    assert [
        item["key"] for item in list_course_memory("learner", "course")["items"]
    ] == ["name"]
    generations, deleted = course_memory_deletion_state("learner", "course")
    assert deleted == {"Name"}
    assert generations["Name"] > lower.id
    assert course_memory_value_versions("learner", "course") == {
        "Name": generations["Name"],
        "name": lower.id,
    }
    assert delete_course_memory("learner", "course", upper.id) == {"conflict": False}
    assert course_memory_deletion_state("learner", "course") == (generations, deleted)


@pytest.mark.parametrize(
    ("reserved", "custom"),
    [("sys_note", "SYS_note"), ("sys_user_language", "Sys_user_language")],
)
@pytest.mark.usefixtures("text_key_app")
def test_reserved_key_filters_and_deletion_preserve_exact_identity(
    reserved: str, custom: str
) -> None:
    with unit_of_work():
        system_row = _store(reserved, "reserved value")
        custom_row = _store(custom, "custom value")
        _store("", "legacy empty key")
    assert [
        item["key"] for item in list_course_memory("learner", "course")["items"]
    ] == [custom]
    assert course_memory_value_versions("learner", "course") == {custom: custom_row.id}
    assert delete_course_memory("learner", "course", system_row.id) == {
        "conflict": False
    }
    assert not system_row.deleted
    assert not custom_row.deleted
    assert delete_course_memory("learner", "course", custom_row.id) == {
        "conflict": False
    }
    assert custom_row.deleted
    assert not system_row.deleted
    assert course_memory_deletion_state("learner", "course")[1] == {custom}
    assert list_course_memory("learner", "course")["items"] == []
