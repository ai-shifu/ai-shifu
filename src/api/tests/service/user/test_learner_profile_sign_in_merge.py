from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import pytest
from flaskr.dao import db
from flaskr.service.profile.learner_profile import (
    PROFILE_ONBOARDING_SCENE_KEY,
    PROFILE_ONBOARDING_VERSION,
    load_learner_profile_state,
    merge_learner_profile_for_sign_in,
)
from flaskr.service.user.auth.base import OAuthCallbackRequest
from flaskr.service.user.auth.providers.google import GoogleAuthProvider, _encode_state
from flaskr.service.user.common import update_user_info
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import AuthCredential, UserInfo, UserOnboardingState
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    create_user_entity,
    load_user_aggregate,
    transactional_session,
    upsert_credential,
)
from sqlalchemy.orm.attributes import set_committed_value

PROFILE_UPDATED_AT = datetime(2026, 8, 2, 6, 30, tzinfo=UTC)


def _assert_orm_utc(value: datetime | None, expected: datetime) -> None:
    assert value is not None
    assert value.replace(tzinfo=UTC) == expected


class _FakeRedis:
    def get(self, _key):
        return None

    def delete(self, *_keys):
        return None


class _FakeGoogleResponse:
    def __init__(self, payload) -> None:
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeGoogleSession:
    def __init__(self, profile) -> None:
        self._profile = profile

    def fetch_token(self, *_args, **_kwargs):
        return {"access_token": "fake-access-token"}

    def get(self, *_args, **_kwargs):
        return _FakeGoogleResponse(self._profile)


def _create_user(
    *,
    identify: str,
    nickname: str = "Learner",
    learner_profile: str = "",
    learner_profile_updated_at: datetime | None = None,
    state: int = USER_STATE_UNREGISTERED,
) -> UserInfo:
    return create_user_entity(
        user_bid=uuid.uuid4().hex,
        identify=identify,
        nickname=nickname,
        learner_profile=learner_profile,
        learner_profile_updated_at=learner_profile_updated_at,
        language="en-US",
        state=state,
    )


def _add_state(
    user_bid: str,
    *,
    status: str,
    trigger_source: str = "settings",
) -> UserOnboardingState:
    state = UserOnboardingState(
        user_bid=user_bid,
        scene_key=PROFILE_ONBOARDING_SCENE_KEY,
        version=PROFILE_ONBOARDING_VERSION,
        status=status,
        trigger_source=trigger_source,
        completed_at=PROFILE_UPDATED_AT,
    )
    db.session.add(state)
    return state


@pytest.mark.parametrize(
    ("source_profile", "status", "trigger_source"),
    [
        (
            "Please call me Guest Profile. prefers diagrams",
            "completed",
            "guided",
        ),
        ("prefers diagrams", "completed", "settings"),
        ("", "skipped", "settings"),
        ("", "completed", "settings"),
    ],
    ids=["completed-with-name", "completed-without-name", "skipped", "cleared"],
)
def test_merge_helper_transfers_profile_and_handled_state(
    app,
    monkeypatch,
    source_profile,
    status,
    trigger_source,
):
    monkeypatch.setattr(
        "flaskr.service.profile.learner_profile.check_text_content",
        lambda *_args, **_kwargs: pytest.fail("sign-in merge must not re-moderate"),
    )
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Stale guest name",
            learner_profile=source_profile,
            learner_profile_updated_at=(PROFILE_UPDATED_AT if source_profile else None),
        )
        target = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Existing account name",
        )
        _add_state(
            source.user_bid,
            status=status,
            trigger_source=trigger_source,
        )
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        stored_source = UserInfo.query.filter_by(user_bid=source.user_bid).one()
        target_state = load_learner_profile_state(target.user_bid)

        assert stored_target.learner_profile == source_profile
        if source_profile:
            _assert_orm_utc(
                stored_target.learner_profile_updated_at,
                PROFILE_UPDATED_AT,
            )
        else:
            assert stored_target.learner_profile_updated_at is None
        assert stored_source.learner_profile == source_profile
        assert stored_target.nickname == "Existing account name"
        assert target_state is not None
        assert target_state.status == status
        assert target_state.trigger_source == trigger_source
        _assert_orm_utc(target_state.completed_at, PROFILE_UPDATED_AT)


def test_merge_helper_preserves_target_profile_and_state(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Source name",
            learner_profile="source profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target_updated_at = datetime(2026, 8, 3, 7, 45, tzinfo=UTC)
        target = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Target name",
            learner_profile="target profile",
            learner_profile_updated_at=target_updated_at,
        )
        _add_state(source.user_bid, status="completed", trigger_source="guided")
        _add_state(target.user_bid, status="skipped", trigger_source="settings")
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        target_state = load_learner_profile_state(target.user_bid)
        assert stored_target.learner_profile == "target profile"
        assert stored_target.nickname == "Target name"
        _assert_orm_utc(
            stored_target.learner_profile_updated_at,
            target_updated_at,
        )
        assert target_state is not None
        assert target_state.status == "skipped"
        assert target_state.trigger_source == "settings"


def test_merge_helper_replaces_account_identifier_fallback_with_guest_nickname(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Guest nickname",
            learner_profile="guest profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target_email = f"{uuid.uuid4().hex[:12]}@example.com"
        target = _create_user(
            identify=target_email,
            nickname=target_email,
        )
        _add_state(source.user_bid, status="completed")
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == "guest profile"
        assert stored_target.nickname == "Guest nickname"


def test_merge_helper_keeps_target_identifier_fallback_without_guest_nickname(app):
    with app.app_context():
        source_identify = uuid.uuid4().hex
        source = _create_user(
            identify=source_identify,
            nickname=source_identify,
            learner_profile="guest profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target_email = f"{uuid.uuid4().hex[:12]}@example.com"
        target = _create_user(
            identify=target_email,
            nickname=target_email,
        )
        _add_state(source.user_bid, status="completed")
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        target_state = load_learner_profile_state(target.user_bid)
        assert stored_target.learner_profile == "guest profile"
        assert stored_target.nickname == target_email
        assert target_state is not None
        assert target_state.status == "completed"


def test_merge_helper_does_not_restore_a_profile_the_target_cleared(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Guest name",
            learner_profile="guest profile must not return",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(
            identify=uuid.uuid4().hex,
            nickname="",
        )
        _add_state(source.user_bid, status="completed", trigger_source="guided")
        _add_state(target.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        target_state = load_learner_profile_state(target.user_bid)
        assert stored_target.learner_profile == ""
        assert stored_target.learner_profile_updated_at is None
        assert stored_target.nickname == ""
        assert target_state is not None
        assert target_state.status == "completed"
        assert target_state.trigger_source == "settings"


@pytest.mark.parametrize(
    "source_identify",
    ["15500009991", "+8615500009991", "member@example.com"],
    ids=["phone", "country-prefixed-phone", "email"],
)
def test_merge_helper_never_copies_from_a_source_with_account_identifier(
    app,
    source_identify,
):
    with app.app_context():
        source = _create_user(
            identify=source_identify,
            learner_profile="registered source profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=uuid.uuid4().hex)
        _add_state(source.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == ""
        assert stored_target.learner_profile_updated_at is None
        assert load_learner_profile_state(target.user_bid) is None


@pytest.mark.parametrize(
    "source_state",
    [USER_STATE_REGISTERED, USER_STATE_TRAIL, USER_STATE_PAID],
    ids=["registered", "trial", "paid"],
)
def test_merge_helper_never_copies_from_non_guest_random_identifier(
    app,
    source_state,
):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile="registered random source",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
            state=source_state,
        )
        target = _create_user(identify=uuid.uuid4().hex)
        _add_state(source.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == ""
        assert stored_target.learner_profile_updated_at is None
        assert load_learner_profile_state(target.user_bid) is None


def test_merge_helper_allows_numeric_uuid_guest_identifier(app):
    with app.app_context():
        numeric_uuid = uuid.UUID("12345678-9012-4567-8901-234567890123").hex
        assert len(numeric_uuid) == 32
        assert numeric_uuid.isdigit()
        source = _create_user(
            identify=numeric_uuid,
            learner_profile="numeric uuid guest profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=uuid.uuid4().hex)
        _add_state(source.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == "numeric uuid guest profile"
        _assert_orm_utc(
            stored_target.learner_profile_updated_at,
            PROFILE_UPDATED_AT,
        )
        target_state = load_learner_profile_state(target.user_bid)
        assert target_state is not None
        assert target_state.status == "completed"
        assert target_state.trigger_source == "settings"


def test_merge_helper_allows_unregistered_guest_with_wechat_credential(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile="wechat guest profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=uuid.uuid4().hex)
        upsert_credential(
            app,
            user_bid=source.user_bid,
            provider_name="wechat",
            subject_id=uuid.uuid4().hex,
            subject_format="open_id",
            identifier=uuid.uuid4().hex,
            metadata={},
            verified=True,
        )
        _add_state(source.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == "wechat guest profile"
        _assert_orm_utc(
            stored_target.learner_profile_updated_at,
            PROFILE_UPDATED_AT,
        )
        assert load_learner_profile_state(target.user_bid) is not None


@pytest.mark.parametrize("provider_name", ["phone", "email"])
def test_merge_helper_allows_unregistered_guest_with_unverified_account_credential(
    app,
    provider_name,
):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile=f"unverified {provider_name} guest profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=uuid.uuid4().hex)
        identifier = (
            f"155{uuid.uuid4().int % 10**8:08d}"
            if provider_name == "phone"
            else f"{uuid.uuid4().hex[:12]}@example.com"
        )
        _add_state(source.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        source_aggregate = load_user_aggregate(source.user_bid)
        assert source_aggregate is not None
        update_user_info(
            app,
            build_user_info_from_aggregate(source_aggregate),
            name=None,
            email=identifier if provider_name == "email" else None,
            mobile=identifier if provider_name == "phone" else None,
        )

        stored_credential = AuthCredential.query.filter_by(
            user_bid=source.user_bid,
            provider_name=provider_name,
            deleted=0,
        ).one()
        stored_source = UserInfo.query.filter_by(user_bid=source.user_bid).one()
        assert stored_credential.state == CREDENTIAL_STATE_UNVERIFIED
        assert stored_source.state == USER_STATE_UNREGISTERED
        assert stored_source.user_identify == source.user_identify

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == (
            f"unverified {provider_name} guest profile"
        )
        _assert_orm_utc(
            stored_target.learner_profile_updated_at,
            PROFILE_UPDATED_AT,
        )
        target_state = load_learner_profile_state(target.user_bid)
        assert target_state is not None
        assert target_state.status == "completed"
        assert target_state.trigger_source == "settings"


@pytest.mark.parametrize("provider_name", ["phone", "email"])
def test_merge_helper_rejects_unregistered_source_with_verified_account_credential(
    app,
    provider_name,
):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile=f"verified {provider_name} account profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=uuid.uuid4().hex)
        identifier = (
            f"155{uuid.uuid4().int % 10**8:08d}"
            if provider_name == "phone"
            else f"{uuid.uuid4().hex[:12]}@example.com"
        )
        upsert_credential(
            app,
            user_bid=source.user_bid,
            provider_name=provider_name,
            subject_id=identifier,
            subject_format=provider_name,
            identifier=identifier,
            metadata={},
            verified=True,
        )
        _add_state(source.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        stored_credential = AuthCredential.query.filter_by(
            user_bid=source.user_bid,
            provider_name=provider_name,
            deleted=0,
        ).one()
        stored_source = UserInfo.query.filter_by(user_bid=source.user_bid).one()
        assert stored_credential.state == CREDENTIAL_STATE_VERIFIED
        assert stored_source.state == USER_STATE_UNREGISTERED
        assert stored_source.user_identify == source.user_identify

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == ""
        assert stored_target.learner_profile_updated_at is None
        assert load_learner_profile_state(target.user_bid) is None


def test_merge_helper_rolls_back_with_sign_in_transaction(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Rollback source name",
            learner_profile="rollback sentinel",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Rollback target name",
        )
        _add_state(source.user_bid, status="completed")
        db.session.commit()

        def merge_then_fail():
            with transactional_session():
                merge_learner_profile_for_sign_in(
                    source_user_id=source.user_bid,
                    target_user_id=target.user_bid,
                )
                db.session.flush()
                raise RuntimeError("abort sign-in")

        with pytest.raises(RuntimeError, match="abort sign-in"):
            merge_then_fail()

        db.session.expire_all()
        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == ""
        assert stored_target.learner_profile_updated_at is None
        assert stored_target.nickname == "Rollback target name"
        assert load_learner_profile_state(target.user_bid) is None


def test_merge_helper_locks_target_then_source_profile_snapshots(app, monkeypatch):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile="locked merge profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=uuid.uuid4().hex)
        _add_state(source.user_bid, status="completed")
        db.session.commit()

        query_type = type(UserInfo.query)
        original_first = query_type.first
        read_order: list[tuple[str, str, bool, bool]] = []

        def track_first(query):
            statement = str(query.statement)
            parameters = query.statement.compile().params
            user_bid = str(parameters.get("user_bid_1", ""))
            table = (
                "user_onboarding_states"
                if "user_onboarding_states" in statement
                else "user_users"
                if "user_users" in statement
                else "other"
            )
            read_order.append(
                (
                    table,
                    user_bid,
                    query._for_update_arg is not None,
                    bool(query.load_options._populate_existing),
                ),
            )
            return original_first(query)

        monkeypatch.setattr(query_type, "first", track_first)
        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        profile_snapshot_reads = [
            read
            for read in read_order
            if read[0] in {"user_users", "user_onboarding_states"}
        ]
        assert profile_snapshot_reads[:4] == [
            ("user_users", target.user_bid, True, True),
            ("user_onboarding_states", target.user_bid, True, True),
            ("user_users", source.user_bid, True, True),
            ("user_onboarding_states", source.user_bid, True, True),
        ]
        assert load_learner_profile_state(target.user_bid) is not None


def test_merge_helper_refreshes_a_stale_source_identity_map(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="新名字",
            learner_profile="可以叫我新名字。current database profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target_identify = uuid.uuid4().hex
        target = _create_user(identify=target_identify, nickname=target_identify)
        _add_state(source.user_bid, status="completed")
        source_user_id = source.user_bid
        target_user_id = target.user_bid
        db.session.commit()

        set_committed_value(
            source,
            "learner_profile",
            "可以叫我旧名字。stale identity-map profile",
        )

        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source_user_id,
                target_user_id=target_user_id,
            )
        db.session.commit()

        db.session.expire_all()
        stored_target = UserInfo.query.filter_by(user_bid=target_user_id).one()
        assert (
            stored_target.learner_profile == "可以叫我新名字。current database profile"
        )
        assert stored_target.nickname == "新名字"


def test_phone_sign_in_merges_profile_without_course_id(app, monkeypatch, caplog):
    from flaskr.service.user import phone_flow

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(phone_flow, "redis", _FakeRedis())
    monkeypatch.setattr(phone_flow, "FIX_CHECK_CODE", "9999")
    monkeypatch.setattr(phone_flow, "init_first_course", lambda *_args: False)
    monkeypatch.setattr(
        phone_flow,
        "ensure_admin_creator_and_demo_permissions",
        lambda *_args, **_kwargs: False,
    )
    with app.app_context():
        phone = f"155{uuid.uuid4().int % 10**8:08d}"
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile="phone merge sentinel",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=phone)
        _add_state(source.user_bid, status="completed")
        db.session.commit()

        app.logger.addHandler(caplog.handler)
        try:
            token, _created, _context = phone_flow.verify_phone_code(
                app,
                user_id=source.user_bid,
                phone=phone,
                code="9999",
                course_id=None,
            )
        finally:
            app.logger.removeHandler(caplog.handler)
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert token.userInfo.user_id == target.user_bid
        assert stored_target.learner_profile == "phone merge sentinel"
        _assert_orm_utc(
            stored_target.learner_profile_updated_at,
            PROFILE_UPDATED_AT,
        )
        assert load_learner_profile_state(target.user_bid) is not None
        assert UserInfo.query.filter_by(user_bid=source.user_bid).one() is not None
        assert "verify_phone_code merge_candidate" in caplog.text
        assert "phone merge sentinel" not in caplog.text


def test_email_sign_in_transfers_cleared_state_without_course_id(app, monkeypatch):
    from flaskr.service.user import email_flow

    monkeypatch.setattr(email_flow, "redis", _FakeRedis())
    monkeypatch.setattr(email_flow, "FIX_CHECK_CODE", "9999")
    monkeypatch.setattr(email_flow, "init_first_course", lambda *_args: False)
    with app.app_context():
        email = f"{uuid.uuid4().hex[:12]}@example.com"
        source = _create_user(identify=uuid.uuid4().hex)
        target = _create_user(identify=email)
        _add_state(source.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        token, _created, _context = email_flow.verify_email_code(
            app,
            user_id=source.user_bid,
            email=email,
            code="9999",
            course_id=None,
        )
        db.session.commit()

        target_state = load_learner_profile_state(target.user_bid)
        assert token.userInfo.user_id == target.user_bid
        assert target_state is not None
        assert target_state.status == "completed"
        assert target_state.trigger_source == "settings"


@pytest.mark.parametrize("sign_in_method", ["phone", "email"])
def test_legacy_profile_migration_preserves_target_nickname(
    app,
    monkeypatch,
    sign_in_method,
):
    from flaskr.service.user import email_flow, phone_flow

    flow = phone_flow if sign_in_method == "phone" else email_flow
    monkeypatch.setattr(flow, "redis", _FakeRedis())
    monkeypatch.setattr(flow, "FIX_CHECK_CODE", "9999")
    monkeypatch.setattr(flow, "init_first_course", lambda *_args: False)
    monkeypatch.setattr(flow, "migrate_user_study_record", lambda *_args: None)
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.check_text_content",
        lambda *_args: True,
    )

    with app.app_context():
        identifier = (
            f"155{uuid.uuid4().int % 10**8:08d}"
            if sign_in_method == "phone"
            else f"{uuid.uuid4().hex[:12]}@example.com"
        )
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Guest nickname",
            learner_profile="guest profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(
            identify=identifier,
            nickname="Target nickname",
        )
        _add_state(source.user_bid, status="completed")
        db.session.commit()

        if sign_in_method == "phone":
            token, _created, _context = flow.verify_phone_code(
                app,
                user_id=source.user_bid,
                phone=identifier,
                code="9999",
                course_id="nickname-migration-course",
            )
        else:
            token, _created, _context = flow.verify_email_code(
                app,
                user_id=source.user_bid,
                email=identifier,
                code="9999",
                course_id="nickname-migration-course",
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == "guest profile"
        assert stored_target.nickname == "Target nickname"
        assert token.userInfo.name == "Target nickname"


@pytest.mark.parametrize("sign_in_method", ["phone", "email"])
@pytest.mark.parametrize("target_nickname_kind", ["empty", "identifier"])
def test_legacy_profile_migration_transfers_guest_nickname_when_target_has_none(
    app,
    monkeypatch,
    sign_in_method,
    target_nickname_kind,
):
    from flaskr.service.user import email_flow, phone_flow

    flow = phone_flow if sign_in_method == "phone" else email_flow
    monkeypatch.setattr(flow, "redis", _FakeRedis())
    monkeypatch.setattr(flow, "FIX_CHECK_CODE", "9999")
    monkeypatch.setattr(flow, "init_first_course", lambda *_args: False)
    monkeypatch.setattr(flow, "migrate_user_study_record", lambda *_args: None)
    monkeypatch.setattr(
        "flaskr.service.profile.funcs.check_text_content",
        lambda *_args: True,
    )

    with app.app_context():
        identifier = (
            f"155{uuid.uuid4().int % 10**8:08d}"
            if sign_in_method == "phone"
            else f"{uuid.uuid4().hex[:12]}@example.com"
        )
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Guest nickname",
        )
        target = _create_user(
            identify=identifier,
            nickname=identifier if target_nickname_kind == "identifier" else "",
        )
        db.session.commit()

        if sign_in_method == "phone":
            token, _created, _context = flow.verify_phone_code(
                app,
                user_id=source.user_bid,
                phone=identifier,
                code="9999",
                course_id="legacy-nickname-migration-course",
            )
        else:
            token, _created, _context = flow.verify_email_code(
                app,
                user_id=source.user_bid,
                email=identifier,
                code="9999",
                course_id="legacy-nickname-migration-course",
            )
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.nickname == "Guest nickname"
        assert token.userInfo.name == "Guest nickname"


def test_google_sign_in_merges_profile_and_skipped_state(app, monkeypatch):
    import flaskr.service.user.auth.providers.google as google_provider
    from flaskr.service.user import phone_flow

    monkeypatch.setattr(
        google_provider,
        "_resolve_redirect_uri",
        lambda _app, _explicit_uri=None: "http://localhost/google-callback",
    )
    monkeypatch.setattr(
        google_provider,
        "ensure_admin_creator_and_demo_permissions",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(phone_flow, "init_first_course", lambda *_args: False)
    with app.app_context():
        email = f"{uuid.uuid4().hex[:12]}@example.com"
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Profile learner",
            learner_profile="Please call me Profile Learner. google merge sentinel",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=email)
        _add_state(source.user_bid, status="skipped")
        db.session.commit()

        provider = GoogleAuthProvider()
        monkeypatch.setattr(
            provider,
            "_create_session",
            lambda _app, _redirect_uri: _FakeGoogleSession(
                {
                    "sub": uuid.uuid4().hex,
                    "email": email,
                    "email_verified": True,
                    "name": "Google Learner",
                }
            ),
        )
        state = _encode_state(
            app,
            {"redirect_uri": "http://localhost/google-callback"},
        )
        callback = OAuthCallbackRequest(
            code="fake-google-code",
            state=state,
            current_user_id=source.user_bid,
        )

        with app.test_request_context("/login/google-callback"):
            result = provider.handle_oauth_callback(app, callback)
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        target_state = load_learner_profile_state(target.user_bid)
        assert result.user.user_id == target.user_bid
        assert stored_target.learner_profile == (
            "Please call me Profile Learner. google merge sentinel"
        )
        assert stored_target.nickname == "Google Learner"
        _assert_orm_utc(
            stored_target.learner_profile_updated_at,
            PROFILE_UPDATED_AT,
        )
        assert target_state is not None
        assert target_state.status == "skipped"
        assert UserInfo.query.filter_by(user_bid=source.user_bid).one() is not None


def test_google_sign_in_keeps_pre_profile_display_name_behavior(app, monkeypatch):
    import flaskr.service.user.auth.providers.google as google_provider
    from flaskr.service.user import phone_flow

    monkeypatch.setattr(
        google_provider,
        "_resolve_redirect_uri",
        lambda _app, _explicit_uri=None: "http://localhost/google-callback",
    )
    monkeypatch.setattr(
        google_provider,
        "ensure_admin_creator_and_demo_permissions",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(phone_flow, "init_first_course", lambda *_args: False)

    with app.app_context():
        email = f"{uuid.uuid4().hex[:12]}@example.com"
        source = _create_user(
            identify=uuid.uuid4().hex,
            nickname="Stale guest nickname",
        )
        target = _create_user(
            identify=email,
            nickname="Existing Google account name",
        )
        _add_state(source.user_bid, status="completed", trigger_source="settings")
        db.session.commit()

        provider = GoogleAuthProvider()
        monkeypatch.setattr(
            provider,
            "_create_session",
            lambda _app, _redirect_uri: _FakeGoogleSession(
                {
                    "sub": uuid.uuid4().hex,
                    "email": email,
                    "email_verified": True,
                    "name": "Google Learner",
                }
            ),
        )
        callback = OAuthCallbackRequest(
            code="fake-google-code",
            state=_encode_state(
                app,
                {"redirect_uri": "http://localhost/google-callback"},
            ),
            current_user_id=source.user_bid,
        )

        with app.test_request_context("/login/google-callback"):
            result = provider.handle_oauth_callback(app, callback)
        db.session.commit()

        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        target_state = load_learner_profile_state(target.user_bid)
        assert result.user.user_id == target.user_bid
        assert stored_target.learner_profile == ""
        assert stored_target.nickname == "Google Learner"
        assert target_state is not None
        assert target_state.status == "completed"
        assert target_state.trigger_source == "settings"
