"""Verify admin contact resolution, identifier lookup, and account boundaries."""

import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu import admin_user_profiles as profiles
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
)
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.datetime import now_utc


@pytest.fixture
def account_scope(app: object) -> Iterator[str]:
    with app.app_context():
        yield uuid.uuid4().hex
        db.session.rollback()


def _credential(
    user_bid: str, provider: str, identifier: str, **kwargs: object
) -> AuthCredential:
    row = AuthCredential(
        credential_bid=uuid.uuid4().hex,
        user_bid=user_bid,
        provider_name=provider,
        identifier=identifier,
        state=CREDENTIAL_STATE_VERIFIED,
        **kwargs,
    )
    db.session.add(row)
    return row


def test_admin_contact_map_loads_legacy_phone_and_email_accounts_without_credentials(
    account_scope: str,
) -> None:
    phone_bid, email_bid = f"{account_scope}-phone", f"{account_scope}-email"
    db.session.add_all(
        [
            UserEntity(user_bid=phone_bid, user_identify="13800138000"),
            UserEntity(user_bid=email_bid, user_identify="legacy@example.com"),
        ]
    )
    db.session.flush()
    result = profiles._load_operator_user_contact_map([phone_bid, email_bid])
    assert result[phone_bid] == {
        "mobile": "13800138000",
        "email": "",
        "login_methods": ["phone"],
    }
    assert result[email_bid] == {
        "mobile": "",
        "email": "legacy@example.com",
        "login_methods": ["email"],
    }
    assert profiles._load_operator_user_registration_source_map(
        [phone_bid, email_bid]
    ) == {
        phone_bid: "phone",
        email_bid: "email",
    }


def test_registration_source_is_resolved_without_loading_accounts_when_credentials_are_complete() -> (
    None
):
    result = profiles._load_operator_user_registration_source_map(
        ["user"],
        credential_rows=[
            SimpleNamespace(
                user_bid="user", provider_name="google", created_at=None, id=1
            )
        ],
    )
    assert result == {"user": "google"}


def test_admin_profile_rejects_unknown_quick_filters_and_ignores_empty_provider() -> (
    None
):
    with pytest.raises(AppError):
        profiles._resolve_operator_user_quick_filter("unsupported")
    assert profiles._normalize_login_method("  ") == ""


def test_admin_contact_map_skips_orphan_credentials_without_promoting_them() -> None:
    result = profiles._load_operator_user_contact_map(
        ["user"],
        users=[],
        credential_rows=[
            AuthCredential(
                user_bid="", provider_name="email", identifier="orphan@example.com"
            )
        ],
    )
    assert result == {"user": {"mobile": "", "email": "", "login_methods": []}}


def test_course_contact_maps_prefer_latest_credentials_and_fall_back_to_account_identify(
    account_scope: str,
) -> None:
    email_user, phone_user, bound_user = [f"{account_scope}-{i}" for i in range(3)]
    db.session.add_all(
        [
            UserEntity(
                user_bid=email_user,
                user_identify="fallback@example.com",
                nickname="Email learner",
            ),
            UserEntity(
                user_bid=phone_user,
                user_identify="13800138000",
                nickname="Phone learner",
            ),
            UserEntity(
                user_bid=bound_user,
                user_identify="old@example.com",
                nickname="Bound learner",
            ),
        ]
    )
    _credential(bound_user, "email", "old-bound@example.com")
    _credential(bound_user, "google", "latest@example.com")
    _credential(bound_user, "phone", "13800138001")
    _credential(bound_user, "email", "deleted@example.com", deleted=1)
    db.session.flush()
    bids = [email_user, phone_user, bound_user]
    contacts = profiles._load_course_user_contact_map(bids)
    assert contacts[email_user] == {"mobile": "", "email": "fallback@example.com"}
    assert contacts[phone_user] == {"mobile": "13800138000", "email": ""}
    assert contacts[bound_user] == {
        "mobile": "13800138001",
        "email": "latest@example.com",
    }
    users = profiles._load_user_map(bids)
    assert users[bound_user] == {
        "mobile": "13800138001",
        "email": "latest@example.com",
        "identify": "old@example.com",
        "nickname": "Bound learner",
    }
    assert users[email_user]["email"] == "fallback@example.com"
    assert users[phone_user]["mobile"] == "13800138000"


def test_admin_contact_maps_do_not_promote_unverified_contact_information(
    account_scope: str,
) -> None:
    row = UserEntity(user_bid=account_scope, user_identify="canonical@example.com")
    verified = AuthCredential(
        id=1,
        user_bid=account_scope,
        provider_name="email",
        identifier="verified@example.com",
        state=CREDENTIAL_STATE_VERIFIED,
    )
    unverified = AuthCredential(
        id=2,
        user_bid=account_scope,
        provider_name="email",
        identifier="unverified@example.com",
        state=CREDENTIAL_STATE_UNVERIFIED,
    )
    unknown = AuthCredential(
        id=3,
        user_bid=account_scope,
        provider_name="legacy-provider",
        identifier="",
        state=CREDENTIAL_STATE_UNVERIFIED,
    )
    result = profiles._load_operator_user_contact_map(
        [account_scope], users=[row], credential_rows=[verified, unverified, unknown]
    )
    assert result[account_scope]["email"] == "verified@example.com"
    assert result[account_scope]["login_methods"] == ["email", "unknown"]


def test_registration_source_uses_earliest_recognized_credential_and_identifier_fallbacks() -> (
    None
):
    now = now_utc()
    credentials = [
        SimpleNamespace(
            user_bid="bound", provider_name="unknown", created_at=now, id=1
        ),
        SimpleNamespace(user_bid="bound", provider_name="import", created_at=now, id=2),
        SimpleNamespace(user_bid="bound", provider_name="google", created_at=now, id=3),
        SimpleNamespace(user_bid="", provider_name="email", created_at=now, id=4),
    ]
    users = [
        SimpleNamespace(user_bid=bid, user_identify=identify)
        for bid, identify in [
            ("bound", "ignored@example.com"),
            ("phone", "13800138000"),
            ("email", "fallback@example.com"),
            ("unknown", "opaque"),
        ]
    ]
    result = profiles._load_operator_user_registration_source_map(
        ["bound", "phone", "email", "unknown"], users=users, credential_rows=credentials
    )
    assert result == {
        "bound": "imported",
        "phone": "phone",
        "email": "email",
        "unknown": "unknown",
    }


def test_creator_and_user_identifier_lookup_ignores_deleted_rows(
    account_scope: str,
) -> None:
    user_id = account_scope
    email = f"{account_scope}@example.com"
    db.session.add(UserEntity(user_bid=user_id, user_identify="canonical"))
    _credential(user_id, "email", email)
    _credential("deleted-account", "email", email, deleted=1)
    db.session.flush()
    assert profiles._find_matching_creator_bids(email) == {user_id}
    assert profiles._find_matching_creator_bids(user_id) == {user_id}
    assert profiles._find_matching_user_bids_by_identifier(account_scope) == {user_id}
    assert profiles._find_matching_creator_bids("unmatched@example.com") == set()
    assert profiles._find_matching_creator_bids(" ") is None
    assert profiles._find_matching_user_bids_by_identifier(" ") is None


@pytest.mark.parametrize(
    "loader",
    [
        profiles._load_course_user_contact_map,
        profiles._load_user_map,
        profiles._load_operator_user_auth_credentials,
        profiles._load_operator_user_registration_source_map,
        profiles._load_operator_user_last_login_map,
        profiles._load_operator_user_total_paid_amount_map,
        profiles._load_operator_user_last_learning_map,
        profiles._load_operator_user_contact_map,
    ],
)
def test_empty_admin_user_queries_return_empty_results_without_database_access(
    loader: object,
) -> None:
    assert not loader([])


@pytest.mark.parametrize(
    ("creator", "operator", "student", "expected"),
    [
        (False, False, False, "normal"),
        (False, False, True, "student"),
        (True, False, True, "creator"),
        (True, True, True, "operator"),
    ],
)
def test_course_user_role_has_stable_precedence(
    creator: bool, operator: bool, student: bool, expected: str
) -> None:
    assert (
        profiles._resolve_course_user_role(
            is_creator=creator, is_operator=operator, is_student=student
        )
        == expected
    )


@pytest.mark.parametrize(
    ("learned", "total", "expected"),
    [
        (0, 0, "not_started"),
        (0, 3, "not_started"),
        (1, 3, "learning"),
        (3, 3, "completed"),
        (5, 3, "completed"),
    ],
)
def test_learning_status_requires_progress_and_a_nonempty_course(
    learned: int, total: int, expected: str
) -> None:
    assert (
        profiles._resolve_course_user_learning_status(
            learned_lesson_count=learned, total_lesson_count=total
        )
        == expected
    )


def test_admin_lookup_only_includes_cancelled_accounts_when_explicit(
    account_scope: str,
) -> None:
    db.session.add(
        UserEntity(user_bid=account_scope, user_identify=account_scope, deleted=1)
    )
    db.session.flush()
    with pytest.raises(AppError) as missing:
        profiles._load_operator_user_or_raise(account_scope)
    assert missing.value.code == ERROR_CODE["server.user.userNotFound"]
    assert (
        profiles._load_operator_user_or_raise(
            account_scope, include_cancelled=True
        ).deleted
        == 1
    )
    with pytest.raises(AppError) as invalid:
        profiles._load_operator_user_or_raise(" ")
    assert invalid.value.code == ERROR_CODE["server.common.paramsError"]
