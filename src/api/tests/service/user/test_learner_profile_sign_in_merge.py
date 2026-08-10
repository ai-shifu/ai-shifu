from __future__ import annotations

import logging
import uuid
from datetime import datetime

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
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.service.user.models import UserInfo, UserOnboardingState
from flaskr.service.user.repository import (
    create_user_entity,
    transactional_session,
    upsert_credential,
)

PROFILE_UPDATED_AT = datetime.fromisoformat("2026-08-02T06:30:00")


class _FakeRedis:
    def get(self, _key):
        return None

    def delete(self, *_keys):
        return None


class _FakeGoogleResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeGoogleSession:
    def __init__(self, profile):
        self._profile = profile

    def fetch_token(self, *_args, **_kwargs):
        return {"access_token": "fake-access-token"}

    def get(self, *_args, **_kwargs):
        return _FakeGoogleResponse(self._profile)


def _create_user(
    *,
    identify: str,
    learner_profile: str = "",
    learner_profile_updated_at: datetime | None = None,
    state: int = USER_STATE_UNREGISTERED,
) -> UserInfo:
    return create_user_entity(
        user_bid=uuid.uuid4().hex,
        identify=identify,
        nickname="Learner",
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
        ("prefers diagrams", "completed", "guided"),
        ("", "skipped", "settings"),
        ("", "completed", "settings"),
    ],
    ids=["completed", "skipped", "cleared"],
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
            learner_profile=source_profile,
            learner_profile_updated_at=(PROFILE_UPDATED_AT if source_profile else None),
        )
        target = _create_user(identify=uuid.uuid4().hex)
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
        assert stored_target.learner_profile_updated_at == (
            PROFILE_UPDATED_AT if source_profile else None
        )
        assert stored_source.learner_profile == source_profile
        assert target_state is not None
        assert target_state.status == status
        assert target_state.trigger_source == trigger_source
        assert target_state.completed_at == PROFILE_UPDATED_AT


def test_merge_helper_preserves_target_profile_and_state(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile="source profile",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target_updated_at = datetime.fromisoformat("2026-08-03T07:45:00")
        target = _create_user(
            identify=uuid.uuid4().hex,
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
        assert stored_target.learner_profile_updated_at == target_updated_at
        assert target_state is not None
        assert target_state.status == "skipped"
        assert target_state.trigger_source == "settings"


def test_merge_helper_does_not_restore_a_profile_the_target_cleared(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile="guest profile must not return",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=uuid.uuid4().hex)
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
        assert target_state is not None
        assert target_state.status == "completed"
        assert target_state.trigger_source == "settings"


@pytest.mark.parametrize("source_identify", ["15500009991", "member@example.com"])
def test_merge_helper_never_copies_from_a_registered_source(app, source_identify):
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


def test_merge_helper_never_copies_from_registered_random_identifier(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile="registered random source",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
            state=USER_STATE_REGISTERED,
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
        assert stored_target.learner_profile_updated_at == PROFILE_UPDATED_AT
        assert load_learner_profile_state(target.user_bid) is not None


def test_merge_helper_rolls_back_with_sign_in_transaction(app):
    with app.app_context():
        source = _create_user(
            identify=uuid.uuid4().hex,
            learner_profile="rollback sentinel",
            learner_profile_updated_at=PROFILE_UPDATED_AT,
        )
        target = _create_user(identify=uuid.uuid4().hex)
        _add_state(source.user_bid, status="completed")
        db.session.commit()

        with pytest.raises(RuntimeError, match="abort sign-in"):
            with transactional_session():
                merge_learner_profile_for_sign_in(
                    source_user_id=source.user_bid,
                    target_user_id=target.user_bid,
                )
                db.session.flush()
                raise RuntimeError("abort sign-in")

        db.session.expire_all()
        stored_target = UserInfo.query.filter_by(user_bid=target.user_bid).one()
        assert stored_target.learner_profile == ""
        assert stored_target.learner_profile_updated_at is None
        assert load_learner_profile_state(target.user_bid) is None


def test_merge_helper_locks_target_before_copying_state(app, monkeypatch):
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
        original_with_for_update = query_type.with_for_update
        lock_calls = []

        def track_with_for_update(query, *args, **kwargs):
            lock_calls.append((args, kwargs))
            return original_with_for_update(query, *args, **kwargs)

        monkeypatch.setattr(query_type, "with_for_update", track_with_for_update)
        with transactional_session():
            merge_learner_profile_for_sign_in(
                source_user_id=source.user_bid,
                target_user_id=target.user_bid,
            )
        db.session.commit()

        assert lock_calls == [((), {})]
        assert load_learner_profile_state(target.user_bid) is not None


def test_phone_sign_in_merges_profile_without_course_id(app, monkeypatch, caplog):
    import flaskr.service.user.phone_flow as phone_flow

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
        assert stored_target.learner_profile_updated_at == PROFILE_UPDATED_AT
        assert load_learner_profile_state(target.user_bid) is not None
        assert UserInfo.query.filter_by(user_bid=source.user_bid).one() is not None
        assert "verify_phone_code merge_candidate" in caplog.text
        assert "phone merge sentinel" not in caplog.text


def test_email_sign_in_transfers_cleared_state_without_course_id(app, monkeypatch):
    import flaskr.service.user.email_flow as email_flow

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


def test_google_sign_in_merges_profile_and_skipped_state(app, monkeypatch):
    import flaskr.service.user.auth.providers.google as google_provider
    import flaskr.service.user.phone_flow as phone_flow

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
            learner_profile="google merge sentinel",
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
        assert stored_target.learner_profile == "google merge sentinel"
        assert stored_target.learner_profile_updated_at == PROFILE_UPDATED_AT
        assert target_state is not None
        assert target_state.status == "skipped"
        assert UserInfo.query.filter_by(user_bid=source.user_bid).one() is not None
