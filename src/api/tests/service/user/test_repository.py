import uuid
from datetime import datetime

import pytest

from flaskr.dao import db
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_REGISTERED,
)
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    create_user_entity,
    load_user_aggregate,
    load_user_aggregate_by_identifier,
    upsert_user_entity,
)


@pytest.fixture
def user_bid() -> str:
    return uuid.uuid4().hex[:32]


def _insert_email_credential(user_bid: str, email: str) -> AuthCredential:
    credential = AuthCredential(
        credential_bid=uuid.uuid4().hex[:32],
        user_bid=user_bid,
        provider_name="email",
        subject_id=email,
        subject_format="email",
        identifier=email,
        raw_profile='{"provider": "email", "metadata": {}}',
        state=CREDENTIAL_STATE_VERIFIED,
        deleted=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(credential)
    return credential


def _create_user(user_bid: str, email: str) -> UserEntity:
    entity = create_user_entity(
        user_bid=user_bid,
        identify=email,
        nickname="Test User",
        language="en-US",
        avatar="",
        state=USER_STATE_REGISTERED,
    )
    entity.created_at = datetime.utcnow()
    entity.updated_at = datetime.utcnow()
    db.session.flush()
    _insert_email_credential(user_bid, email)
    db.session.commit()
    return entity


def test_load_user_aggregate_returns_expected_data(app, user_bid):
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    with app.app_context():
        _create_user(user_bid, email)
        aggregate = load_user_aggregate(user_bid)
        try:
            assert aggregate is not None
            assert aggregate.user_bid == user_bid
            assert aggregate.email == email
            assert aggregate.username == email
            assert aggregate.display_name == "Test User"
            assert aggregate.public_state == 1

            dto = build_user_info_from_aggregate(aggregate)
            assert dto.email == email
            assert dto.name == "Test User"
            assert dto.user_state == "已注册"
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
