"""Verify operator-managed phone and email replacement."""

from __future__ import annotations

import json

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.user import operator_contact_change as contact_change_module
from flaskr.service.user.consts import CREDENTIAL_STATE_VERIFIED, USER_STATE_REGISTERED
from flaskr.service.user.models import AuthCredential, UserInfo, UserToken
from flaskr.service.user.operator_contact_change import change_operator_user_contact
from flaskr.util.datetime import now_utc


def _seed_user(
    *, user_bid: str, contact_type: str, identifier: str, with_password: bool = True
) -> None:
    db.session.add(
        UserInfo(
            user_bid=user_bid,
            user_identify=identifier,
            nickname="Learner",
            state=USER_STATE_REGISTERED,
            deleted=0,
        )
    )
    db.session.add(
        AuthCredential(
            credential_bid=f"credential-{user_bid}",
            user_bid=user_bid,
            provider_name=contact_type,
            subject_id=identifier,
            subject_format=contact_type,
            identifier=identifier,
            raw_profile="{}",
            state=CREDENTIAL_STATE_VERIFIED,
            deleted=0,
        )
    )
    if with_password:
        db.session.add(
            AuthCredential(
                credential_bid=f"password-{user_bid}",
                user_bid=user_bid,
                provider_name="password",
                subject_id=identifier,
                subject_format=contact_type,
                identifier=identifier,
                raw_profile=json.dumps({"password_hash": "preserved"}),
                state=CREDENTIAL_STATE_VERIFIED,
                deleted=0,
            )
        )


@pytest.fixture(autouse=True)
def _isolate_user_tables(app: object) -> object:
    with app.app_context():
        db.session.query(UserToken).delete()
        db.session.query(AuthCredential).delete()
        db.session.query(UserInfo).delete()
        db.session.commit()
    yield
    with app.app_context():
        db.session.query(UserToken).delete()
        db.session.query(AuthCredential).delete()
        db.session.query(UserInfo).delete()
        db.session.commit()


def test_operator_replaces_phone_and_revokes_every_session(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contact_change_module, "resolve_primary_contact_type", lambda: "phone"
    )
    with app.app_context():
        _seed_user(user_bid="user-1", contact_type="phone", identifier="13800138000")
        db.session.add_all(
            [
                UserToken(
                    user_id="user-1",
                    token="token-1",
                    token_expired_at=now_utc().replace(year=now_utc().year + 1),
                ),
                UserToken(
                    user_id="user-1",
                    token="token-2",
                    token_expired_at=now_utc().replace(year=now_utc().year + 1),
                ),
            ]
        )
        db.session.commit()

        result = change_operator_user_contact(
            app,
            user_bid="user-1",
            operator_user_bid="operator-1",
            contact_type="phone",
            new_identifier="13900139000",
            reason="User requested a phone replacement",
        )

        assert result == {
            "user_bid": "user-1",
            "contact_type": "phone",
            "identifier": "13900139000",
            "revoked_sessions": 2,
        }
        user = UserInfo.query.filter_by(user_bid="user-1").one()
        assert user.user_identify == "13900139000"
        old_phone = AuthCredential.query.filter_by(
            user_bid="user-1", provider_name="phone", identifier="13800138000"
        ).one()
        assert old_phone.deleted == 1
        new_phone = AuthCredential.query.filter_by(
            user_bid="user-1", provider_name="phone", identifier="13900139000"
        ).one()
        assert new_phone.state == CREDENTIAL_STATE_VERIFIED
        assert new_phone.deleted == 0
        password = AuthCredential.query.filter_by(
            user_bid="user-1", provider_name="password"
        ).one()
        assert password.identifier == "13900139000"
        assert json.loads(password.raw_profile)["password_hash"] == "preserved"
        assert UserToken.query.filter_by(user_id="user-1").count() == 0


def test_operator_replaces_email_in_email_deployment(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contact_change_module, "resolve_primary_contact_type", lambda: "email"
    )
    with app.app_context():
        _seed_user(
            user_bid="user-email",
            contact_type="email",
            identifier="old@example.com",
        )
        db.session.commit()

        change_operator_user_contact(
            app,
            user_bid="user-email",
            operator_user_bid="operator-1",
            contact_type="email",
            new_identifier="NEW@Example.com",
            reason="User requested an email replacement",
        )

        user = UserInfo.query.filter_by(user_bid="user-email").one()
        assert user.user_identify == "new@example.com"
        assert AuthCredential.query.filter_by(
            user_bid="user-email",
            provider_name="email",
            identifier="new@example.com",
            deleted=0,
        ).one()


def test_registered_contact_is_rejected_without_partial_changes(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contact_change_module, "resolve_primary_contact_type", lambda: "phone"
    )
    with app.app_context():
        _seed_user(user_bid="user-1", contact_type="phone", identifier="13800138000")
        _seed_user(
            user_bid="user-2",
            contact_type="phone",
            identifier="13900139000",
            with_password=False,
        )
        db.session.commit()

        with pytest.raises(AppError) as error:
            change_operator_user_contact(
                app,
                user_bid="user-1",
                operator_user_bid="operator-1",
                contact_type="phone",
                new_identifier="13900139000",
                reason="Duplicate should be rejected",
            )

        assert error.value.code == 1040
        db.session.expire_all()
        user = UserInfo.query.filter_by(user_bid="user-1").one()
        assert user.user_identify == "13800138000"
        assert AuthCredential.query.filter_by(
            user_bid="user-1",
            provider_name="phone",
            identifier="13800138000",
            deleted=0,
        ).one()


def test_operator_cannot_send_the_other_deployments_contact_type(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        contact_change_module, "resolve_primary_contact_type", lambda: "email"
    )
    with app.app_context(), pytest.raises(AppError):
        change_operator_user_contact(
            app,
            user_bid="user-1",
            operator_user_bid="operator-1",
            contact_type="phone",
            new_identifier="13800138000",
            reason="Wrong deployment contact type",
        )
