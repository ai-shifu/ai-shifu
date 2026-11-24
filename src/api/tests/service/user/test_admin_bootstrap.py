"""Verify the admin account bootstrap and that sign-in never grants it."""

from __future__ import annotations

import json
import uuid
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user import admin_bootstrap
from flaskr.service.user.admin_bootstrap import (
    BOOTSTRAP_ADMIN_USERNAME,
    bootstrap_admin_account,
    generate_bootstrap_password,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import AuthCredential, UserInfo, UserToken
from flaskr.service.user.password_utils import validate_password_strength


@pytest.fixture(autouse=True)
def _isolate_tables(app: object) -> object:
    def _clear() -> None:
        with app.app_context():
            db.session.query(UserToken).delete()
            db.session.query(AuthCredential).delete()
            db.session.query(UserInfo).delete()
            db.session.query(PublishedShifu).delete()
            db.session.query(DraftShifu).delete()
            db.session.commit()

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def post_auth(monkeypatch: pytest.MonkeyPatch) -> Mock:
    hook = Mock()
    monkeypatch.setattr(admin_bootstrap, "run_creator_granted_post_auth", hook)
    return hook


def _login(client: object, identifier: str, password: str) -> dict:
    response = client.post(
        "/api/user/login_password",
        data=json.dumps({"identifier": identifier, "password": password}),
        content_type="application/json",
    )
    assert response.status_code == 200
    return json.loads(response.data)


def _add_user(app: object, *, is_operator: int = 0) -> str:
    user_bid = uuid.uuid4().hex
    with app.app_context():
        db.session.add(
            UserInfo(
                user_bid=user_bid,
                user_identify=f"user-{user_bid[:8]}",
                state=USER_STATE_REGISTERED,
                is_operator=is_operator,
                deleted=0,
            )
        )
        db.session.commit()
    return user_bid


def _admin(app: object) -> UserInfo:
    with app.app_context():
        return UserInfo.query.filter_by(user_identify="admin", deleted=0).one()


def test_generated_passwords_are_random_and_pass_strength_rules() -> None:
    passwords = {generate_bootstrap_password() for _ in range(50)}

    assert len(passwords) == 50
    for password in passwords:
        assert len(password) == 20
        validate_password_strength(password)


def test_fresh_install_creates_admin_that_signs_in(
    app: object, test_client: object, post_auth: Mock
) -> None:
    result = bootstrap_admin_account(app)

    assert result.created is True
    assert result.username == BOOTSTRAP_ADMIN_USERNAME
    admin = _admin(app)
    assert admin.is_operator == 1
    assert admin.is_creator == 1
    assert admin.creator_activated_at is not None
    post_auth.assert_called_once_with(
        app,
        user_id=admin.user_bid,
        source="bootstrap_admin",
        login_context="admin",
        created_new_user=True,
    )

    body = _login(test_client, "admin", result.password)
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["userInfo"]["user_id"] == admin.user_bid


def test_admin_is_created_even_when_another_account_signed_in_first(
    app: object,
) -> None:
    earlier_user = _add_user(app)

    result = bootstrap_admin_account(app)

    assert result.created is True
    assert _admin(app).is_operator == 1
    with app.app_context():
        earlier = UserInfo.query.filter_by(user_bid=earlier_user).one()
        assert earlier.is_operator == 0
        assert earlier.is_creator == 0


def test_existing_operator_skips_bootstrap(app: object, post_auth: Mock) -> None:
    _add_user(app, is_operator=1)

    result = bootstrap_admin_account(app)

    assert result.created is False
    assert result.reason == "operator_exists"
    assert result.password == ""
    post_auth.assert_not_called()
    with app.app_context():
        assert UserInfo.query.filter_by(user_identify="admin").count() == 0


def test_second_run_skips_and_keeps_the_first_password(
    app: object, test_client: object
) -> None:
    first = bootstrap_admin_account(app)
    second = bootstrap_admin_account(app)

    assert second.created is False
    assert second.reason == "operator_exists"
    assert second.password == ""
    assert _login(test_client, "admin", first.password)["code"] == 0


def test_taken_admin_username_is_skipped_without_a_password(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a concurrent run that created "admin" after the operator check.
    monkeypatch.setattr(admin_bootstrap, "_has_operator", lambda: False)
    first = bootstrap_admin_account(app)
    second = bootstrap_admin_account(app)

    assert first.created is True
    assert second.created is False
    assert second.reason == "username_taken"
    assert second.password == ""


def test_admin_owns_the_single_demo_course(app: object) -> None:
    shifu_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        db.session.add(PublishedShifu(shifu_bid=shifu_bid, title="Published demo"))
        db.session.add(DraftShifu(shifu_bid=shifu_bid, title="Draft demo"))
        db.session.commit()

    bootstrap_admin_account(app)

    admin_bid = _admin(app).user_bid
    with app.app_context():
        published = PublishedShifu.query.filter_by(shifu_bid=shifu_bid).one()
        draft = DraftShifu.query.filter_by(shifu_bid=shifu_bid).one()
        assert published.created_user_bid == admin_bid
        assert draft.created_user_bid == admin_bid


def test_admin_does_not_take_over_when_several_courses_exist(app: object) -> None:
    with app.app_context():
        for title in ("First", "Second"):
            db.session.add(PublishedShifu(shifu_bid=uuid.uuid4().hex[:32], title=title))
        db.session.commit()

    bootstrap_admin_account(app)

    admin_bid = _admin(app).user_bid
    with app.app_context():
        owners = {row.created_user_bid for row in PublishedShifu.query.all()}
        assert admin_bid not in owners


def test_admin_does_not_take_over_a_teacher_owned_single_course(app: object) -> None:
    teacher_bid = _add_user(app)
    shifu_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        db.session.add(
            PublishedShifu(
                shifu_bid=shifu_bid,
                title="Teacher course",
                created_user_bid=teacher_bid,
            )
        )
        db.session.add(
            DraftShifu(
                shifu_bid=shifu_bid,
                title="Teacher course",
                created_user_bid=teacher_bid,
            )
        )
        db.session.commit()

    assert bootstrap_admin_account(app).created is True

    with app.app_context():
        assert (
            PublishedShifu.query.filter_by(shifu_bid=shifu_bid).one().created_user_bid
            == teacher_bid
        )
        assert (
            DraftShifu.query.filter_by(shifu_bid=shifu_bid).one().created_user_bid
            == teacher_bid
        )


def test_failed_role_grant_rolls_back_so_the_next_start_retries(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_grant = admin_bootstrap._grant_bootstrap_admin_roles
    calls: list[str] = []

    def fail_first_grant(user_bid: str) -> bool:
        calls.append(user_bid)
        if len(calls) == 1:
            message = "grant failed"
            raise RuntimeError(message)
        return real_grant(user_bid)

    monkeypatch.setattr(
        admin_bootstrap, "_grant_bootstrap_admin_roles", fail_first_grant
    )
    with pytest.raises(RuntimeError):
        bootstrap_admin_account(app)
    with app.app_context():
        assert UserInfo.query.filter_by(user_identify="admin").count() == 0
        assert AuthCredential.query.filter_by(identifier="admin").count() == 0

    retried = bootstrap_admin_account(app)
    assert retried.created is True
    assert _admin(app).is_operator == 1
