"""Keep automatic course-memory definitions independent of manual APIs."""

from collections.abc import Iterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.shifu import shifu_mdflow_funcs as mdflow
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu


@pytest.fixture
def draft_course(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SimpleNamespace]:
    course = SimpleNamespace(
        bid=uuid4().hex,
        outline_bid=uuid4().hex,
        owner=uuid4().hex,
    )
    monkeypatch.setattr(mdflow, "check_text_with_risk_control", lambda *_a, **_k: None)
    monkeypatch.setattr(mdflow, "save_outline_history", lambda *_a, **_k: 0)
    monkeypatch.setattr(
        mdflow, "cleanup_outline_history_versions", lambda *_a, **_k: None
    )
    with app.app_context(), unit_of_work():
        db.session.add(
            DraftShifu(
                shifu_bid=course.bid,
                title="Automatic memory definitions",
                created_user_bid=course.owner,
                updated_user_bid=course.owner,
            )
        )
        outline = DraftOutlineItem(
            shifu_bid=course.bid,
            outline_item_bid=course.outline_bid,
            title="Lesson",
            content="Original content",
            position="01",
            created_user_bid=course.owner,
            updated_user_bid=course.owner,
        )
        db.session.add(outline)
        db.session.flush()
        course.revision = int(outline.id)
    yield course
    with app.app_context(), unit_of_work():
        for model in (VariableValue, Variable, DraftOutlineItem, DraftShifu):
            model.query.filter_by(shifu_bid=course.bid).delete(
                synchronize_session=False
            )


def _committed_course_rows(app: Flask, model: object, shifu_bid: str) -> list[object]:
    with app.app_context(), db.engine.connect() as connection:
        return connection.execute(
            model.__table__.select().where(model.shifu_bid == shifu_bid)
        ).fetchall()


@pytest.mark.parametrize("marker_prefix", ["%", ""], ids=["percent-braces", "braces"])
def test_save_creates_missing_definition_from_either_marker_syntax(
    app: Flask, draft_course: SimpleNamespace, marker_prefix: str
) -> None:
    key = f"answer_{uuid4().hex}"
    content = f"Remember {marker_prefix}{{{{{key}}}}}."

    result = mdflow.save_shifu_mdflow(
        app, draft_course.owner, draft_course.bid, draft_course.outline_bid, content
    )

    assert result["conflict"] is False
    assert result["new_revision"] != draft_course.revision
    definitions = _committed_course_rows(app, Variable, draft_course.bid)
    assert len(definitions) == 1
    assert definitions[0].key == key
    assert definitions[0].variable_bid
    assert definitions[0].deleted == 0
    assert definitions[0].is_hidden == 0
    assert definitions[0].created_user_bid == draft_course.owner
    outlines = _committed_course_rows(app, DraftOutlineItem, draft_course.bid)
    assert {row.content for row in outlines} == {"Original content", content}


def test_repeated_markers_and_saves_reuse_definition_and_preserve_learner_answer(
    app: Flask, draft_course: SimpleNamespace
) -> None:
    key = f"answer_{uuid4().hex}"
    content = f"First %{{{{{key}}}}}, then {{{{{key}}}}}."
    mdflow.save_shifu_mdflow(
        app, draft_course.owner, draft_course.bid, draft_course.outline_bid, content
    )
    definitions = _committed_course_rows(app, Variable, draft_course.bid)
    assert len(definitions) == 1
    definition = definitions[0]
    value_bid = uuid4().hex
    with app.app_context(), unit_of_work():
        db.session.add(
            VariableValue(
                variable_value_bid=value_bid,
                variable_bid=definition.variable_bid,
                shifu_bid=draft_course.bid,
                user_bid=uuid4().hex,
                key=key,
                value="Previously accepted learner answer",
            )
        )
    answers_before = _committed_course_rows(app, VariableValue, draft_course.bid)

    result = mdflow.save_shifu_mdflow(
        app,
        draft_course.owner,
        draft_course.bid,
        draft_course.outline_bid,
        content + " Use the answer in the next example.",
    )

    assert result["conflict"] is False
    assert _committed_course_rows(app, Variable, draft_course.bid) == definitions
    assert (
        _committed_course_rows(app, VariableValue, draft_course.bid) == answers_before
    )


def test_late_failure_rolls_back_outline_and_automatically_created_definitions(
    app: Flask, draft_course: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    percent_key = f"percent_{uuid4().hex}"
    braces_key = f"braces_{uuid4().hex}"
    content = f"Remember %{{{{{percent_key}}}}} and {{{{{braces_key}}}}}."
    pending_definitions: list[str] = []

    def fail_after_definition_creation(*_args: object, **_kwargs: object) -> None:
        pending_definitions.extend(
            row.key
            for row in Variable.query.filter_by(shifu_bid=draft_course.bid).all()
        )
        assert set(pending_definitions) == {percent_key, braces_key}
        assert (
            DraftOutlineItem.query.filter_by(
                shifu_bid=draft_course.bid, content=content
            ).count()
            == 1
        )
        message = "late history cleanup failure"
        raise RuntimeError(message)

    monkeypatch.setattr(
        mdflow, "cleanup_outline_history_versions", fail_after_definition_creation
    )

    with pytest.raises(RuntimeError, match="late history cleanup failure"):
        mdflow.save_shifu_mdflow(
            app, draft_course.owner, draft_course.bid, draft_course.outline_bid, content
        )

    assert set(pending_definitions) == {percent_key, braces_key}
    assert _committed_course_rows(app, Variable, draft_course.bid) == []
    outlines = _committed_course_rows(app, DraftOutlineItem, draft_course.bid)
    assert [(row.id, row.content) for row in outlines] == [
        (draft_course.revision, "Original content")
    ]
