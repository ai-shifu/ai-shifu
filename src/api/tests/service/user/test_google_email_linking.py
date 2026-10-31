"""Protect Google subject identity from unverified email account association."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.service.user import utils as user_utils
from flaskr.service.user.auth.providers import google
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.models import UserToken as UserTokenModel
from flaskr.service.user.password_utils import hash_password
from flaskr.service.user.repository import (
    create_user_entity,
    set_password_hash,
    upsert_credential,
)
from flaskr.service.user.token_store import token_store

from tests.common.fixtures.fake_redis import FakeRedis
from tests.service.user.test_google_auth import (
    _reset_user_auth_tables,
    _run_google_callback,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


@pytest.fixture(scope="session")
def password_hash() -> str:
    return hash_password(uuid.uuid4().hex)


@pytest.fixture(autouse=True)
def isolated_accounts(app: Flask, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(token_store, "_cache", FakeRedis())
    with app.app_context():
        _reset_user_auth_tables()
        # Keep first-account bootstrapping out of ordinary account regressions.
        _account("sentinel@example.com")
        db.session.commit()
        yield
        _reset_user_auth_tables()


def _account(
    email: str, *, canonical: bool = True, temporary: bool = False
) -> UserEntity:
    user_bid = uuid.uuid4().hex
    return create_user_entity(
        user_bid=user_bid,
        identify=email if canonical else user_bid,
        nickname="Original name",
        state=USER_STATE_UNREGISTERED if temporary else USER_STATE_REGISTERED,
    )


def _credential(
    app: Flask,
    user: UserEntity,
    provider: str,
    identifier: str,
    *,
    subject: str | None = None,
    verified: bool = True,
) -> AuthCredential:
    return upsert_credential(
        app,
        user_bid=user.user_bid,
        provider_name=provider,
        subject_id=subject or identifier,
        subject_format=provider,
        identifier=identifier,
        metadata={},
        verified=verified,
    )


def _snapshot() -> tuple:
    return (
        [
            (
                u.user_bid,
                u.user_identify,
                u.nickname,
                u.learner_profile,
                u.state,
                u.is_creator,
                u.is_operator,
            )
            for u in UserEntity.query.order_by(UserEntity.id)
        ],
        [
            (
                c.credential_bid,
                c.user_bid,
                c.provider_name,
                c.subject_id,
                c.identifier,
                c.state,
                c.raw_profile,
                c.deleted,
            )
            for c in AuthCredential.query.order_by(AuthCredential.id)
        ],
        [
            (t.user_id, t.token)
            for t in UserTokenModel.query.order_by(UserTokenModel.id)
        ],
    )


def _profile(
    claim: object = True,
    *,
    subject: object = "google-subject",
    email: str = "owner@example.com",
) -> dict:
    profile = {"sub": subject, "email": email, "name": "Google name"}
    if claim != "missing":
        profile["email_verified"] = claim
    return profile


@pytest.mark.parametrize(
    "claim", ["missing", False, None, "false", "true", 0, 1, [], {}]
)
@pytest.mark.parametrize("canonical", [True, False])
def test_unverified_email_cannot_select_existing_email_password_account(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    claim: object,
    canonical: bool,
    password_hash: str,
) -> None:
    owner = _account("owner@example.com", canonical=canonical)
    owner.is_creator = 1
    owner.is_operator = 1
    _credential(app, owner, "email", "owner@example.com")
    password = _credential(app, owner, "password", "owner@example.com")
    set_password_hash(password, password_hash)
    guest = _account("", canonical=False, temporary=True)
    guest.learner_profile = "Guest profile must not move on rejected login."
    db.session.commit()
    before = _snapshot()
    for _ in range(2):
        with pytest.raises(AppError) as error:
            _run_google_callback(
                app, monkeypatch, _profile(claim), current_user_id=guest.user_bid
            )
        assert error.value.code == ERROR_CODE["server.user.invalidCredentials"]
        db.session.expire_all()
        assert _snapshot() == before


@pytest.mark.parametrize("claim", [False, "false"])
def test_same_email_cannot_replace_another_google_subject(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    claim: object,
) -> None:
    owner = _account("owner@example.com")
    _credential(app, owner, "google", "owner@example.com", subject="bound-subject")
    db.session.commit()
    before = _snapshot()
    with pytest.raises(AppError):
        _run_google_callback(app, monkeypatch, _profile(claim))
    assert _snapshot() == before


@pytest.mark.parametrize("claim", ["missing", False, "true", 1])
@pytest.mark.parametrize("changed_email", [False, True])
def test_bound_subject_authenticates_without_unverified_email_authority(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    claim: object,
    changed_email: bool,
) -> None:
    owner = _account("owner@example.com")
    owner.is_creator = owner.is_operator = 1
    email_credential = _credential(app, owner, "email", "owner@example.com")
    binding = _credential(
        app, owner, "google", "owner@example.com", subject="bound-subject"
    )
    victim = _account("victim@example.com")
    victim_before = (victim.user_identify, victim.nickname, victim.state)
    db.session.commit()
    result = _run_google_callback(
        app,
        monkeypatch,
        _profile(
            claim,
            subject="bound-subject",
            email="victim@example.com" if changed_email else "owner@example.com",
        ),
    )
    assert result.user.user_id == owner.user_bid
    assert result.user.is_operator is True
    assert owner.user_identify == "owner@example.com"
    assert email_credential.state == CREDENTIAL_STATE_VERIFIED
    assert binding.identifier == "owner@example.com"
    assert binding.subject_id == "bound-subject"
    assert AuthCredential.query.filter_by(provider_name="google").count() == 1
    assert (victim.user_identify, victim.nickname, victim.state) == victim_before
    assert UserTokenModel.query.one().user_id == owner.user_bid


@pytest.mark.parametrize("canonical", [True, False])
def test_verified_email_can_associate_existing_email_password_account(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    canonical: bool,
    password_hash: str,
) -> None:
    owner = _account("owner@example.com", canonical=canonical)
    _credential(app, owner, "email", "owner@example.com")
    password = _credential(app, owner, "password", "owner@example.com")
    set_password_hash(password, password_hash)
    db.session.commit()
    for _ in range(2):
        result = _run_google_callback(
            app, monkeypatch, _profile(email="OWNER@example.com")
        )
        assert result.user.user_id == owner.user_bid
    assert AuthCredential.query.filter_by(provider_name="google").count() == 1


@pytest.mark.parametrize("verified", [False, True])
def test_new_google_account_and_current_guest_association(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    verified: bool,
) -> None:
    guest = _account("", canonical=False, temporary=True)
    guest.learner_profile = "Keep this guest profile."
    original_identify = guest.user_identify
    db.session.commit()
    result = _run_google_callback(
        app, monkeypatch, _profile(verified), current_user_id=guest.user_bid
    )
    assert result.user.user_id == guest.user_bid
    assert guest.learner_profile == "Keep this guest profile."
    assert guest.state == (
        USER_STATE_REGISTERED if verified else USER_STATE_UNREGISTERED
    )
    assert guest.user_identify == (
        "owner@example.com" if verified else original_identify
    )
    assert AuthCredential.query.filter_by(provider_name="email").count() == int(
        verified
    )
    assert result.credential.state == (
        CREDENTIAL_STATE_VERIFIED if verified else CREDENTIAL_STATE_UNVERIFIED
    )


@pytest.mark.parametrize("claim", ["missing", False, None, "false", "true", 1])
def test_new_unverified_account_does_not_gain_email_or_admin_grants(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    claim: object,
) -> None:
    grants = []
    monkeypatch.setattr(
        google,
        "ensure_admin_creator_and_demo_permissions",
        lambda *args: grants.append(args),
    )
    result = _run_google_callback(
        app, monkeypatch, _profile(claim), login_context="admin"
    )
    stored = UserEntity.query.filter_by(user_bid=result.user.user_id).one()
    assert stored.state == USER_STATE_UNREGISTERED
    assert stored.is_creator == stored.is_operator == 0
    assert result.credential.state == CREDENTIAL_STATE_UNVERIFIED
    assert AuthCredential.query.filter_by(provider_name="email").count() == 0
    assert stored.user_identify != "owner@example.com"
    assert not grants
    retry = _run_google_callback(app, monkeypatch, _profile(claim))
    assert retry.user.user_id == stored.user_bid


@pytest.mark.parametrize("subject", [None, "", " ", 123, [], {}, " padded "])
def test_malformed_subject_cannot_create_identity(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    subject: object,
) -> None:
    before = _snapshot()
    with pytest.raises(RuntimeError, match="missing required identifiers"):
        _run_google_callback(app, monkeypatch, _profile(subject=subject))
    assert _snapshot() == before


@pytest.mark.parametrize("verified", [False, True])
def test_failure_after_session_write_rolls_back_account_binding_and_cache_then_retries(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    verified: bool,
) -> None:
    guest = _account("", canonical=False, temporary=True)
    db.session.commit()
    before = _snapshot()
    original_snapshot = google.build_user_profile_snapshot_from_aggregate
    issued = []
    original_generate = google.generate_token

    def record_token(*args: object) -> str:
        token = original_generate(*args)
        issued.append(token)
        return token

    def fail_snapshot(*_args: object) -> None:
        message = "injected failure after token persistence"
        raise RuntimeError(message)

    monkeypatch.setattr(google, "generate_token", record_token)
    monkeypatch.setattr(
        google, "build_user_profile_snapshot_from_aggregate", fail_snapshot
    )
    with pytest.raises(RuntimeError, match="injected failure"):
        _run_google_callback(
            app, monkeypatch, _profile(verified), current_user_id=guest.user_bid
        )
    assert issued
    db.session.expire_all()
    assert _snapshot() == before
    assert token_store._cache.get(token_store._cache_key(app, issued[0])) is None
    monkeypatch.setattr(
        google, "build_user_profile_snapshot_from_aggregate", original_snapshot
    )
    result = _run_google_callback(
        app, monkeypatch, _profile(verified), current_user_id=guest.user_bid
    )
    assert result.user.user_id == guest.user_bid
    assert AuthCredential.query.filter_by(provider_name="google").count() == 1
    assert UserTokenModel.query.one().token == result.token.token


@pytest.mark.parametrize("preverified", [False, True])
def test_verified_email_does_not_replace_a_different_subject_binding(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    preverified: bool,
) -> None:
    original = _run_google_callback(
        app, monkeypatch, _profile(preverified, subject="old-subject")
    )
    original_id = original.user.user_id
    original_binding = original.credential.credential_bid
    result = _run_google_callback(
        app, monkeypatch, _profile(claim=True, subject="new-subject")
    )
    assert (result.user.user_id == original_id) is preverified
    assert (
        AuthCredential.query.filter_by(credential_bid=original_binding).one().subject_id
        == "old-subject"
    )
    assert AuthCredential.query.filter_by(provider_name="google").count() == 2
    retry = _run_google_callback(
        app, monkeypatch, _profile(claim=True, subject="new-subject")
    )
    assert retry.user.user_id == result.user.user_id
    original_retry = _run_google_callback(
        app, monkeypatch, _profile(claim=False, subject="old-subject")
    )
    assert original_retry.user.user_id == original_id


@pytest.mark.parametrize("verified", [False, True])
def test_bound_subject_keeps_own_account_when_current_email_belongs_elsewhere(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    verified: bool,
) -> None:
    owner = _account("owner@example.com")
    _credential(app, owner, "email", "owner@example.com")
    binding = _credential(
        app, owner, "google", "owner@example.com", subject="bound-subject"
    )
    victim = _account("victim@example.com")
    _credential(app, victim, "email", "victim@example.com")
    _credential(app, victim, "google", "victim@example.com", subject="victim-subject")
    db.session.commit()
    result = _run_google_callback(
        app,
        monkeypatch,
        _profile(verified, subject="bound-subject", email="victim@example.com"),
    )
    assert result.user.user_id == owner.user_bid
    assert owner.user_identify == binding.identifier == "owner@example.com"
    assert binding.state == CREDENTIAL_STATE_VERIFIED
    assert (
        AuthCredential.query.filter_by(user_bid=owner.user_bid, provider_name="email")
        .one()
        .identifier
        == "owner@example.com"
    )
    assert (
        AuthCredential.query.filter_by(subject_id="victim-subject").one().user_bid
        == victim.user_bid
    )
    assert UserTokenModel.query.one().user_id == owner.user_bid


@pytest.mark.parametrize("verified", [False, True])
def test_current_registered_user_can_associate_a_new_subject(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    verified: bool,
) -> None:
    owner = _account("existing@example.com")
    db.session.commit()
    result = _run_google_callback(
        app, monkeypatch, _profile(verified), current_user_id=owner.user_bid
    )
    assert result.user.user_id == owner.user_bid
    assert owner.user_identify == (
        "owner@example.com" if verified else "existing@example.com"
    )
    assert result.credential.subject_id == "google-subject"


def test_subject_rotation_and_case_variants_do_not_overwrite_other_bindings(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _account("owner@example.com")
    first = _credential(
        app, owner, "google", "owner@example.com", subject="CaseSubject"
    )
    # Seed historical duplicate email labels directly; identifier-keyed upsert
    # would itself overwrite the first subject before this regression starts.
    second = AuthCredential(
        credential_bid=uuid.uuid4().hex,
        user_bid=owner.user_bid,
        provider_name="google",
        subject_id="casesubject",
        subject_format="google",
        identifier="owner@example.com",
        state=CREDENTIAL_STATE_VERIFIED,
        raw_profile="{}",
        deleted=0,
    )
    db.session.add(second)
    db.session.commit()
    result = _run_google_callback(
        app,
        monkeypatch,
        _profile(claim=True, subject="casesubject", email="changed@example.com"),
    )
    assert result.user.user_id == owner.user_bid
    assert first.subject_id == "CaseSubject"
    assert first.identifier == "owner@example.com"
    assert second.subject_id == "casesubject"
    assert second.identifier == "changed@example.com"
    assert AuthCredential.query.filter_by(provider_name="google").count() == 2


def test_subject_linking_does_not_revive_deleted_other_subject(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _account("owner@example.com")
    deleted = _credential(
        app, owner, "google", "owner@example.com", subject="deleted-subject"
    )
    deleted.deleted = 1
    db.session.commit()
    result = _run_google_callback(app, monkeypatch, _profile())
    assert result.user.user_id == owner.user_bid
    assert deleted.deleted == 1
    assert deleted.subject_id == "deleted-subject"
    assert result.credential.subject_id == "google-subject"
    assert result.credential.credential_bid != deleted.credential_bid


@pytest.mark.parametrize("bound_verified", [False, True])
@pytest.mark.parametrize("claim", [False, "true"])
@pytest.mark.parametrize("changed_email", [False, True])
def test_admin_demo_grants_follow_previously_verified_subject_trust(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    bound_verified: bool,
    claim: object,
    changed_email: bool,
) -> None:
    """Honor configured demo grants without trusting the current mailbox claim."""
    owner = _account("owner@example.com")
    binding = _credential(
        app,
        owner,
        "google",
        "owner@example.com",
        subject="bound-subject",
        verified=bound_verified,
    )
    _account("victim@example.com")
    demo_id = uuid.uuid4().hex
    monkeypatch.setitem(app.config, "ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO", value=True)
    monkeypatch.setattr(user_utils, "load_existing_demo_shifu_ids", lambda: {demo_id})
    db.session.commit()
    try:
        result = _run_google_callback(
            app,
            monkeypatch,
            _profile(
                claim,
                subject="bound-subject",
                email="victim@example.com" if changed_email else "owner@example.com",
            ),
            login_context="admin",
        )
        db.session.expire_all()
        assert result.user.user_id == owner.user_bid
        assert result.user.is_creator is bound_verified
        assert owner.is_creator == int(bound_verified)
        assert owner.is_operator == 0
        assert (owner.creator_activated_at is not None) is bound_verified
        assert result.metadata["creator_granted_now"] is bound_verified
        assert owner.user_identify == binding.identifier == "owner@example.com"
        assert AuthCredential.query.filter_by(provider_name="email").count() == 0
        grants = AiCourseAuth.query.filter_by(
            user_id=owner.user_bid, course_id=demo_id
        ).all()
        assert len(grants) == int(bound_verified)
        if grants:
            assert grants[0].status == 1
            assert grants[0].auth_type == '["view"]'
        assert UserTokenModel.query.one().user_id == owner.user_bid
        retry = _run_google_callback(
            app,
            monkeypatch,
            _profile(claim, subject="bound-subject"),
            login_context="admin",
        )
        assert retry.user.user_id == owner.user_bid
        assert retry.metadata["creator_granted_now"] is False
        assert AiCourseAuth.query.filter_by(
            user_id=owner.user_bid, course_id=demo_id
        ).count() == int(bound_verified)
    finally:
        AiCourseAuth.query.filter_by(course_id=demo_id).delete()
        db.session.commit()


@pytest.mark.parametrize(("enabled", "context"), [(False, "admin"), (True, None)])
def test_bound_subject_demo_grants_still_require_flag_and_admin_context(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    context: str | None,
) -> None:
    """Preserve both deployment and login-context controls for trusted subjects."""
    owner = _account("owner@example.com")
    _credential(app, owner, "google", "owner@example.com", subject="bound-subject")
    monkeypatch.setitem(app.config, "ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO", enabled)
    db.session.commit()
    result = _run_google_callback(
        app,
        monkeypatch,
        _profile(claim=False, subject="bound-subject"),
        login_context=context,
    )
    assert result.user.user_id == owner.user_bid
    assert result.user.is_creator is False
    assert owner.is_creator == owner.is_operator == 0
    assert owner.creator_activated_at is None
    assert result.metadata["creator_granted_now"] is False


def test_bound_subject_demo_grants_roll_back_with_session_failure(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed admin sign-in cannot leave creator/demo grants or a session."""
    owner = _account("owner@example.com")
    _credential(app, owner, "google", "owner@example.com", subject="bound-subject")
    demo_id = uuid.uuid4().hex
    monkeypatch.setitem(app.config, "ADMIN_LOGIN_GRANT_CREATOR_WITH_DEMO", value=True)
    monkeypatch.setattr(user_utils, "load_existing_demo_shifu_ids", lambda: {demo_id})
    db.session.commit()
    before = _snapshot()

    def fail_snapshot(*_args: object) -> None:
        message = "injected failure after admin grants and session write"
        raise RuntimeError(message)

    monkeypatch.setattr(
        google, "build_user_profile_snapshot_from_aggregate", fail_snapshot
    )
    with pytest.raises(RuntimeError, match="injected failure"):
        _run_google_callback(
            app,
            monkeypatch,
            _profile(claim=False, subject="bound-subject"),
            login_context="admin",
        )
    db.session.expire_all()
    assert _snapshot() == before
    assert owner.creator_activated_at is None
    assert AiCourseAuth.query.filter_by(course_id=demo_id).count() == 0
