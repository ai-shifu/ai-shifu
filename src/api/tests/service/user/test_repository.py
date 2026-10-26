"""Verify user aggregates resolve active and legacy credentials."""

import uuid
from collections.abc import Iterator
from datetime import datetime

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao import db
from flaskr.service.common.dtos import has_login_identity
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
)
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    create_user_entity,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    upsert_user_entity,
)
from flaskr.util.datetime import now_utc


@pytest.fixture
def app() -> Iterator[Flask]:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)

    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


@pytest.fixture
def user_bid() -> str:
    return uuid.uuid4().hex[:32]


def _insert_email_credential(
    user_bid: str,
    email: str,
    *,
    provider_name: str = "email",
    state: int = CREDENTIAL_STATE_VERIFIED,
    created_at: datetime | None = None,
) -> AuthCredential:
    credential_created_at = created_at or now_utc()
    credential = AuthCredential(
        credential_bid=uuid.uuid4().hex[:32],
        user_bid=user_bid,
        provider_name=provider_name,
        subject_id=email,
        subject_format="email",
        identifier=email,
        raw_profile=f'{{"provider": "{provider_name}", "metadata": {{}}}}',
        state=state,
        deleted=0,
        created_at=credential_created_at,
        updated_at=credential_created_at,
    )
    db.session.add(credential)
    return credential


def _insert_phone_credential(
    user_bid: str,
    phone: str,
    *,
    state: int = CREDENTIAL_STATE_VERIFIED,
) -> AuthCredential:
    credential = AuthCredential(
        credential_bid=uuid.uuid4().hex[:32],
        user_bid=user_bid,
        provider_name="phone",
        subject_id=phone,
        subject_format="phone",
        identifier=phone,
        raw_profile='{"provider": "phone", "metadata": {}}',
        state=state,
        deleted=0,
    )
    db.session.add(credential)
    return credential


@pytest.mark.parametrize("verified", [True, False])
@pytest.mark.parametrize("deleted", [0, 1])
def test_contactless_local_login_fact_uses_active_verified_credentials(
    app: Flask, user_bid: str, verified: bool, deleted: int
) -> None:
    _ = app
    user = create_user_entity(
        user_bid=user_bid, identify=f"local:{user_bid}", state=USER_STATE_REGISTERED
    )
    user.is_operator = 1
    user.is_creator = 1
    db.session.add(
        AuthCredential(
            credential_bid=uuid.uuid4().hex,
            user_bid=user_bid,
            provider_name="local_password",
            identifier="local_owner",
            subject_id="local_owner",
            subject_format="username",
            state=(
                CREDENTIAL_STATE_VERIFIED if verified else CREDENTIAL_STATE_UNVERIFIED
            ),
            deleted=deleted,
        )
    )
    db.session.flush()
    aggregate = load_user_aggregate(user_bid)
    assert aggregate is not None
    assert aggregate.mobile == aggregate.email == ""
    assert aggregate.has_local_password is (verified and not deleted)
    assert has_login_identity(aggregate) is (verified and not deleted)
    assert has_login_identity(aggregate.to_user_info()) is (verified and not deleted)


def _create_user(
    user_bid: str,
    email: str,
    *,
    is_operator: bool = False,
) -> UserEntity:
    entity = create_user_entity(
        user_bid=user_bid,
        identify=email,
        nickname="Test User",
        language="en-US",
        avatar="",
        state=USER_STATE_REGISTERED,
    )
    entity.is_operator = 1 if is_operator else 0
    entity.created_at = now_utc()
    entity.updated_at = now_utc()
    db.session.flush()
    _insert_email_credential(user_bid, email)
    db.session.commit()
    return entity


def test_load_user_aggregate_returns_expected_data(
    app: object, user_bid: object
) -> None:
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    with app.app_context():
        _create_user(user_bid, email, is_operator=True)
        aggregate = load_user_aggregate(user_bid)
        try:
            assert aggregate is not None
            assert aggregate.user_bid == user_bid
            assert aggregate.email == email
            assert aggregate.username == email
            assert aggregate.display_name == "Test User"
            assert aggregate.public_state == 1
            assert aggregate.is_operator is True

            dto = build_user_info_from_aggregate(aggregate)
            assert dto.email == email
            assert dto.name == "Test User"
            assert dto.user_state == "已注册"
            assert dto.is_operator is True
        finally:
            AuthCredential.query.filter_by(user_bid=user_bid).delete()
            UserEntity.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()


def test_public_paid_state_normalizes_to_canonical_paid_state(
    app: object, user_bid: str
) -> None:
    with app.app_context():
        entity = create_user_entity(
            user_bid=user_bid,
            identify=f"{uuid.uuid4().hex[:12]}@example.com",
            state=3,
        )
        db.session.commit()

        aggregate = load_user_aggregate(user_bid)

        assert entity.state == USER_STATE_PAID
        assert aggregate is not None
        assert aggregate.state == USER_STATE_PAID
        assert aggregate.public_state == 3


def test_persisted_legacy_paid_state_loads_as_canonical_paid_state(
    app: object, user_bid: str
) -> None:
    with app.app_context():
        entity = create_user_entity(
            user_bid=user_bid,
            identify=f"{uuid.uuid4().hex[:12]}@example.com",
            state=USER_STATE_REGISTERED,
        )
        entity.state = 3
        db.session.commit()

        aggregate = load_user_aggregate(user_bid)

        assert entity.state == 3
        assert aggregate is not None
        assert aggregate.state == USER_STATE_PAID
        assert aggregate.public_state == 3


def test_load_user_aggregate_by_identifier_uses_credentials(
    app: object, user_bid: object
) -> None:
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    with app.app_context():
        _create_user(user_bid, email)
        try:
            aggregate = load_user_aggregate_by_identifier(email)
            assert aggregate is not None
            assert aggregate.email == email
            assert aggregate.username == email
        finally:
            AuthCredential.query.filter_by(user_bid=user_bid).delete()
            UserEntity.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()


def test_load_user_aggregate_by_identifier_ignores_soft_deleted_direct_match(
    app: object,
) -> None:
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    deleted_user_bid = uuid.uuid4().hex[:32]
    active_user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        deleted_entity = create_user_entity(
            user_bid=deleted_user_bid,
            identify=email,
            nickname="Deleted User",
            language="en-US",
            avatar="",
            state=USER_STATE_REGISTERED,
        )
        deleted_entity.deleted = 1
        create_user_entity(
            user_bid=active_user_bid,
            identify=email,
            nickname="Active User",
            language="en-US",
            avatar="",
            state=USER_STATE_REGISTERED,
        )
        db.session.commit()
        try:
            aggregate = load_user_aggregate_by_identifier(email, providers=["email"])

            assert aggregate is not None
            assert aggregate.user_bid == active_user_bid
            assert aggregate.display_name == "Active User"
        finally:
            UserEntity.query.filter(
                UserEntity.user_bid.in_([deleted_user_bid, active_user_bid])
            ).delete(synchronize_session=False)
            db.session.commit()


def test_load_user_aggregate_by_identifier_finds_legacy_prefixed_phone_credential(
    app: object,
) -> None:
    phone = "15500008888"
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        create_user_entity(
            user_bid=user_bid,
            identify=user_bid,
            nickname="Legacy Phone",
            language="en-US",
            avatar="",
            state=USER_STATE_REGISTERED,
        )
        _insert_phone_credential(user_bid, f"+86{phone}")
        db.session.commit()
        try:
            aggregate = load_user_aggregate_by_identifier(
                f"+86{phone}", providers=["phone"]
            )

            assert aggregate is not None
            assert aggregate.user_bid == user_bid
            assert aggregate.mobile == f"+86{phone}"
        finally:
            AuthCredential.query.filter_by(user_bid=user_bid).delete()
            UserEntity.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()


def test_upsert_user_entity_creates_and_updates_records(app: object) -> None:
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        entity, created = upsert_user_entity(
            user_bid=user_bid,
            defaults={"identify": email, "nickname": "User"},
        )
        try:
            assert created is True
            assert entity.user_identify == email
            assert entity.nickname == "User"

            entity, created = upsert_user_entity(
                user_bid=user_bid,
                defaults={"nickname": "Updated"},
            )
            assert created is False
            assert entity.nickname == "Updated"
        finally:
            AuthCredential.query.filter_by(user_bid=user_bid).delete()
            UserEntity.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()
