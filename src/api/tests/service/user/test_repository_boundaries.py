"""Exercise credential corruption recovery and legacy account hydration."""

import json
import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from flaskr.dao import db
from flaskr.service.profile.models import VariableValue
from flaskr.service.user import repository
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    USER_STATE_PAID,
    USER_STATE_REGISTERED,
    USER_STATE_TRAIL,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import AuthCredential


@pytest.fixture
def account_id(app: object) -> Iterator[str]:
    with app.app_context():
        yield uuid.uuid4().hex
        db.session.rollback()


@pytest.mark.parametrize("raw", [None, "", "not-json", "[]", "null", '"scalar"'])
def test_invalid_credential_profile_never_exposes_a_password_or_metadata(
    raw: str | None,
) -> None:
    credential = AuthCredential(raw_profile=raw)
    assert repository.get_password_hash(credential) == ""
    assert repository.deserialize_raw_profile(credential) == {}
    repository.set_password_hash(credential, "replacement-hash")
    assert repository.get_password_hash(credential) == "replacement-hash"
    assert repository.deserialize_raw_profile(credential) == {}


def test_password_hash_stays_outside_public_credential_metadata() -> None:
    credential = AuthCredential(
        raw_profile=json.dumps(
            {"provider": "password", "metadata": {"label": "public"}, "extra": True}
        )
    )
    repository.set_password_hash(credential, "private-password-hash")
    assert repository.deserialize_raw_profile(credential) == {"label": "public"}
    assert repository.get_password_hash(credential) == "private-password-hash"
    assert json.loads(credential.raw_profile) == {
        "provider": "password",
        "metadata": {"label": "public"},
        "extra": True,
        "password_hash": "private-password-hash",
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, USER_STATE_UNREGISTERED),
        ("1104.0", USER_STATE_PAID),
        (" 1103 ", USER_STATE_TRAIL),
        ("unknown", USER_STATE_UNREGISTERED),
        (999, USER_STATE_UNREGISTERED),
        ("1102", USER_STATE_REGISTERED),
    ],
)
def test_legacy_account_states_are_normalized(raw: object, expected: int) -> None:
    assert repository._normalize_user_state(raw) == expected


def test_role_bootstrap_hydrates_latest_global_legacy_values(account_id: str) -> None:
    values = [
        ("sys_user_nickname", "Old name", "", 0),
        ("sys_user_nickname", " Latest name ", "", 0),
        ("sys_user_nickname", " ", "", 0),
        ("avatar", " https://example.com/avatar.png ", "", 0),
        ("language", " fr-FR ", "", 0),
        ("birth", "2000-01-02", "", 0),
        ("birth", "invalid-date", "", 0),
        ("language", "wrong-course-language", "course", 0),
        ("language", "deleted-language", "", 1),
    ]
    for key, value, course_id, deleted in values:
        db.session.add(
            VariableValue(
                user_bid=account_id,
                key=key,
                value=value,
                shifu_bid=course_id,
                deleted=deleted,
            )
        )
    db.session.flush()
    repository.mark_user_roles(account_id, is_creator=True, is_operator=False)
    user = repository.get_user_entity_by_bid(account_id)
    assert user.user_identify == account_id
    assert user.nickname == "Latest name"
    assert user.language == "fr-FR"
    assert user.avatar == "https://example.com/avatar.png"
    assert user.birthday == date(2000, 1, 2)
    assert user.is_creator == 1
    assert user.is_operator == 0
    repository.set_user_state(account_id, USER_STATE_PAID)
    assert repository.load_user_aggregate(account_id).state == USER_STATE_PAID


def test_role_noop_does_not_create_a_user(account_id: str) -> None:
    repository.mark_user_roles(account_id)
    assert repository.get_user_entity_by_bid(account_id, include_deleted=True) is None


def test_ensure_existing_identifier_only_updates_allowed_fields(
    app: object, account_id: str
) -> None:
    email = f"{account_id}@example.com"
    repository.create_user_entity(
        user_bid=account_id,
        identify=email,
        nickname="Before",
        learner_profile="Private learner profile",
    )
    aggregate, created = repository.ensure_user_for_identifier(
        app,
        provider="email",
        identifier=email.upper(),
        defaults={
            "nickname": "After",
            "language": "fr-FR",
            "user_bid": "cannot-reassign",
            "learner_profile": "cannot-overwrite",
        },
    )
    assert created is False
    assert aggregate.user_bid == account_id
    assert aggregate.nickname == "After"
    assert aggregate.language == "fr-FR"
    assert aggregate.learner_profile == "Private learner profile"


def test_ensure_aggregate_reports_creation_and_preserves_account_on_repeat(
    app: object, account_id: str
) -> None:
    first, created = repository.ensure_user_aggregate(
        app, user_bid=account_id, defaults={"nickname": "Teacher"}
    )
    second, created_again = repository.ensure_user_aggregate(
        app, user_bid=account_id, defaults={"language": "fr-FR"}
    )
    assert created is True
    assert created_again is False
    assert first.user_bid == second.user_bid == account_id
    assert second.nickname == "Teacher"
    assert second.language == "fr-FR"


def test_deleted_users_are_hidden_unless_requested_and_can_be_restored(
    account_id: str,
) -> None:
    entity = repository.create_user_entity(user_bid=account_id, identify=account_id)
    repository.update_user_entity_fields(entity, deleted=True)
    assert repository.load_user_aggregate(account_id) is None
    deleted = repository.load_user_aggregate(
        account_id, include_deleted=True, with_credentials=False
    )
    assert deleted.deleted is True
    assert deleted.credentials == []
    repository.update_user_entity_fields(
        entity, deleted=False, birthday=date(2001, 2, 3)
    )
    assert repository.load_user_aggregate(account_id).birthday == date(2001, 2, 3)


def test_wechat_credentials_keep_app_scopes_and_union_metadata_separate(
    app: object, account_id: str
) -> None:
    records = repository.upsert_wechat_credentials(
        app,
        user_bid=account_id,
        open_id="open-subject",
        union_id="union-subject",
        open_identifier="app:open-subject",
        union_identifier="app:union-subject",
        metadata={"nickname": "Teacher"},
        verified=False,
    )
    assert len(records) == 2
    assert {record.subject_format for record in records} == {"open_id", "unicon_id"}
    assert {record.identifier for record in records} == {
        "app:open-subject",
        "app:union-subject",
    }
    for record in records:
        assert repository.deserialize_raw_profile(record) == {
            "nickname": "Teacher",
            "type": record.subject_format,
        }
        assert record.state == CREDENTIAL_STATE_UNVERIFIED
    assert (
        repository.upsert_wechat_credentials(
            app, user_bid=account_id, open_id=None, union_id=None
        )
        == []
    )
