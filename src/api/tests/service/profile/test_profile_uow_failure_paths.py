"""Verify caller-owned transactions and shared definition visibility writes."""

from __future__ import annotations

import pytest
from flaskr import dao
from flaskr.dao.uow import unit_of_work
from flaskr.service.profile import profile_manage
from flaskr.service.profile.models import Variable


def _variable_count(app: object, shifu_bid: str, key: str) -> int:
    with app.app_context(), dao.db.engine.connect() as connection:
        rows = connection.execute(
            Variable.__table__.select().where(
                Variable.shifu_bid == shifu_bid,
                Variable.key == key,
                Variable.deleted == 0,
            )
        ).fetchall()
    return len(rows)


def test_internal_definition_write_rolls_back_with_its_caller(
    app: object, monkeypatch: object
) -> None:
    shifu_bid = "uow-profile-shifu-1"
    key = "uow_profile_key_1"

    def failing_convert(_definition: object) -> object:
        message = "dto boom"
        raise RuntimeError(message)

    monkeypatch.setattr(
        profile_manage,
        "convert_variable_definition_to_profile_item_definition",
        failing_convert,
    )

    with (
        app.app_context(),
        pytest.raises(RuntimeError, match="dto boom"),
        unit_of_work(),
    ):
        profile_manage.add_profile_item_quick_internal(app, shifu_bid, key, "uow-user")

    assert _variable_count(app, shifu_bid, key) == 0


def test_internal_definition_write_commits_with_its_caller(app: object) -> None:
    shifu_bid = "uow-profile-shifu-2"
    key = "uow_profile_key_2"

    with app.app_context(), unit_of_work():
        definition = profile_manage.add_profile_item_quick_internal(
            app, shifu_bid, key, "uow-user"
        )

    assert definition.profile_key == key
    assert _variable_count(app, shifu_bid, key) == 1


def test_hidden_state_update_is_visible_to_the_read_back(app: object) -> None:
    """The list read-back opens its own app context, so it must run after the commit."""
    shifu_bid = "uow-profile-shifu-3"
    key = "uow_profile_key_3"

    with app.app_context():
        with unit_of_work():
            profile_manage.add_profile_item_quick_internal(
                app, shifu_bid, key, "uow-user"
            )
        definitions = profile_manage.update_profile_item_hidden_state(
            app, shifu_bid, [key], hidden=True, user_id="uow-user"
        )

    hidden = {item.profile_key: item for item in definitions}[key]
    assert hidden.is_hidden is True


def test_nested_hidden_state_read_back_sees_the_staged_update(app: object) -> None:
    """Inside a caller's unit of work the read-back joins that session."""
    shifu_bid = "uow-profile-shifu-4"
    key = "uow_profile_key_4"

    with app.app_context():
        with unit_of_work():
            profile_manage.add_profile_item_quick_internal(
                app, shifu_bid, key, "uow-user"
            )
        with unit_of_work():
            definitions = profile_manage.update_profile_item_hidden_state(
                app, shifu_bid, [key], hidden=True, user_id="uow-user"
            )
            staged = {item.profile_key: item for item in definitions}[key]
            assert staged.is_hidden is True
        dao.db.session.expire_all()
        row = Variable.query.filter_by(shifu_bid=shifu_bid, key=key).one()
        assert row.is_hidden == 1
