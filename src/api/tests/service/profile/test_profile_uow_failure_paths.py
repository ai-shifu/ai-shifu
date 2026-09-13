"""Unit-of-work behavior for profile definition writes (B1 migration)."""

from __future__ import annotations

import pytest
from flaskr import dao
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


def test_save_profile_item_rolls_back_when_the_dto_build_fails(
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

    with app.app_context(), pytest.raises(RuntimeError, match="dto boom"):
        profile_manage.save_profile_item(app, "", shifu_bid, "uow-user", key)

    assert _variable_count(app, shifu_bid, key) == 0


def test_save_profile_item_commits_on_clean_exit(app: object) -> None:
    shifu_bid = "uow-profile-shifu-2"
    key = "uow_profile_key_2"

    with app.app_context():
        definition = profile_manage.save_profile_item(
            app, "", shifu_bid, "uow-user", key
        )

    assert definition.profile_key == key
    assert _variable_count(app, shifu_bid, key) == 1


def test_hidden_state_update_is_visible_to_the_read_back(app: object) -> None:
    """The list read-back opens its own app context, so it must run after the commit."""
    shifu_bid = "uow-profile-shifu-3"
    key = "uow_profile_key_3"

    with app.app_context():
        profile_manage.save_profile_item(app, "", shifu_bid, "uow-user", key)
        definitions = profile_manage.update_profile_item_hidden_state(
            app, shifu_bid, [key], hidden=True, user_id="uow-user"
        )

    hidden = {item.profile_key: item for item in definitions}[key]
    assert hidden.is_hidden is True
