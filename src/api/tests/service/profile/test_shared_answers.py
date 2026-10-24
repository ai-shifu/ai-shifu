"""Exercise explicit cross-course writes against real revisioned database records."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from types import SimpleNamespace


import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.funcs import get_user_profiles, save_user_profiles
from flaskr.service.profile.models import Variable, VariableValue

from tests.service.profile.test_course_references import (
    _published_text,
    context,
)

__all__ = ["context"]


@pytest.fixture
def shared(context: SimpleNamespace) -> SimpleNamespace:
    context.share = f"share:{context.source}:goal"
    context.script = f"Ask ?[%{{{{{context.share}}}}} ...Updated goal]."
    with unit_of_work():
        db.session.add(
            Variable(
                shifu_bid=context.target, key=context.share, variable_bid=uuid4().hex
            )
        )
        db.session.add(
            Variable(shifu_bid=context.source, key="goal", variable_bid=uuid4().hex)
        )
    _published_text(context, context.script)
    return context


def source_value(c: SimpleNamespace) -> str:
    """Read the original source value for isolation assertions."""
    return (
        VariableValue.query.filter_by(user_bid=c.user, shifu_bid=c.source, key="goal")
        .order_by(VariableValue.id.desc())
        .first()
        .value
    )


def test_retired_shared_collection_cannot_read_or_write_source(
    shared: SimpleNamespace,
) -> None:
    c = shared
    before = [(v.id, v.value) for v in VariableValue.query.order_by(VariableValue.id)]
    assert c.share not in get_user_profiles(
        c.app, c.user, c.target, reference_text=c.script
    )
    with unit_of_work():
        save_user_profiles(
            c.app, c.user, c.target, [ProfileToSave(c.share, "Changed", "")]
        )
    assert source_value(c) == "Source goal"
    assert [
        (v.id, v.value) for v in VariableValue.query.order_by(VariableValue.id)
    ] == before
