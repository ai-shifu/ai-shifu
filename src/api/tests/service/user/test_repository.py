import uuid
from datetime import datetime

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.dao import db
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_REGISTERED,
)
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    create_user_entity,
    get_first_verified_credential_created_at,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    upsert_user_entity,
)


@pytest.fixture
def app():
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
    credential_created_at = created_at or datetime.now()
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
    entity.created_at = datetime.now()
    entity.updated_at = datetime.now()
    db.session.flush()
    _insert_email_credential(user_bid, email)
    db.session.commit()
    return entity


def test_load_user_aggregate_returns_expected_data(app, user_bid):
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


def test_load_user_aggregate_by_identifier_uses_credentials(app, user_bid):
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


def test_upsert_user_entity_creates_and_updates_records(app):
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


def test_get_first_verified_credential_created_at_prefers_earliest_verified(app):
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        create_user_entity(
            user_bid=user_bid,
            identify="user@example.com",
            nickname="Test User",
            language="en-US",
            avatar="",
            state=USER_STATE_REGISTERED,
        )
        _insert_email_credential(
            user_bid,
            "late@example.com",
            created_at=datetime(2026, 4, 9, 10, 0, 0),
        )
        _insert_email_credential(
            user_bid,
            "early@example.com",
            provider_name="google",
            created_at=datetime(2026, 4, 8, 10, 0, 0),
        )
        _insert_email_credential(
            user_bid,
            "ignored@example.com",
            provider_name="phone",
            state=CREDENTIAL_STATE_UNVERIFIED,
            created_at=datetime(2026, 4, 7, 10, 0, 0),
        )
        db.session.commit()

        try:
            assert get_first_verified_credential_created_at(user_bid=user_bid) == (
                datetime(2026, 4, 8, 10, 0, 0)
            )
        finally:
            AuthCredential.query.filter_by(user_bid=user_bid).delete()
            UserEntity.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()


def test_get_first_verified_credential_created_at_returns_none_without_verified(
    app,
):
    user_bid = uuid.uuid4().hex[:32]
    with app.app_context():
        create_user_entity(
            user_bid=user_bid,
            identify="user@example.com",
            nickname="Test User",
            language="en-US",
            avatar="",
            state=USER_STATE_REGISTERED,
        )
        _insert_email_credential(
            user_bid,
            "pending@example.com",
            state=CREDENTIAL_STATE_UNVERIFIED,
            created_at=datetime(2026, 4, 9, 10, 0, 0),
        )
        db.session.commit()

        try:
            assert get_first_verified_credential_created_at(user_bid=user_bid) is None
        finally:
            AuthCredential.query.filter_by(user_bid=user_bid).delete()
            UserEntity.query.filter_by(user_bid=user_bid).delete()
            db.session.commit()
