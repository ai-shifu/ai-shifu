"""Exercise real account and outline revision queries used by course operations."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.shifu.admin_operations import courses_shared as shared
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity


@pytest.fixture
def query_context(app: object) -> Iterator[str]:
    with app.app_context():
        yield uuid.uuid4().hex
        db.session.rollback()


def _user(identifier: str, **overrides: object) -> UserEntity:
    row = UserEntity(
        **{
            "user_bid": uuid.uuid4().hex,
            "user_identify": identifier,
            "nickname": "Learner",
            **overrides,
        }
    )
    db.session.add(row)
    db.session.flush()
    return row


def _credential(
    user: UserEntity, provider: str, identifier: str, **overrides: object
) -> None:
    db.session.add(
        AuthCredential(
            **{
                "credential_bid": uuid.uuid4().hex,
                "user_bid": user.user_bid,
                "provider_name": provider,
                "identifier": identifier,
                **overrides,
            }
        )
    )
    db.session.flush()


def test_contact_queries_prefer_current_credentials_and_keep_legacy_account_fallbacks(
    query_context: str,
) -> None:
    registered = _user(f"{query_context}@example.test")
    _credential(registered, "phone", "13800000001")
    _credential(registered, "phone", "13800000002")
    _credential(registered, "phone", "13800000003", deleted=1)
    _credential(registered, "email", "old@example.test")
    _credential(registered, "google", "current@example.test")
    _credential(registered, "email", "deleted@example.test", deleted=1)
    _credential(registered, "other", "unsupported@example.test")
    phone_legacy = _user("13800000004")
    email_legacy = _user(f"legacy-{query_context}@example.test")
    deleted = _user("13800000005", deleted=1)
    user_bids = [
        registered.user_bid,
        phone_legacy.user_bid,
        email_legacy.user_bid,
        deleted.user_bid,
    ]

    contacts = shared._load_course_user_contact_map([*user_bids, "", " "])
    users = shared._load_user_map(user_bids)
    assert contacts[registered.user_bid] == {
        "mobile": "13800000002",
        "email": "current@example.test",
    }
    assert users[registered.user_bid] == {
        "mobile": "13800000002",
        "email": "current@example.test",
        "nickname": "Learner",
        "identify": registered.user_identify,
    }
    assert contacts[phone_legacy.user_bid] == {"mobile": "13800000004", "email": ""}
    assert users[phone_legacy.user_bid]["mobile"] == "13800000004"
    assert contacts[email_legacy.user_bid] == {
        "mobile": "",
        "email": email_legacy.user_identify,
    }
    assert users[email_legacy.user_bid]["email"] == email_legacy.user_identify
    assert contacts[deleted.user_bid] == {"mobile": "", "email": ""}
    assert deleted.user_bid not in users
    assert shared._load_course_user_contact_map(["", " "]) == {}
    assert shared._load_user_map([]) == {}


def test_creator_search_unions_exact_current_identity_and_supported_credentials(
    query_context: str,
) -> None:
    keyword = f"{query_context}@example.test"
    canonical = _user(keyword)
    credential = _user("legacy")
    excluded = _user("excluded")
    _user(keyword, deleted=1)
    _credential(credential, "email", keyword)
    _credential(excluded, "email", keyword, deleted=1)
    _credential(excluded, "google", keyword)
    _credential(excluded, "phone", f"prefix{keyword}")
    assert shared._find_matching_creator_bids(f" {keyword} ") == {
        canonical.user_bid,
        credential.user_bid,
    }
    assert shared._find_matching_creator_bids(canonical.user_bid) == {
        canonical.user_bid
    }
    assert shared._find_matching_creator_bids("absent@example.test") == set()
    assert shared._find_matching_creator_bids(" ") is None
    assert shared._load_operator_user_last_login_map([]) == {}


@pytest.mark.parametrize("model", [DraftOutlineItem, PublishedOutlineItem])
def test_outline_query_orders_mixed_positions_and_does_not_resurrect_deleted_revision(
    query_context: str, model: type
) -> None:
    rows = []
    for position in ["1.10", "1.a", "", "1..2", "1.1"]:
        row = model(
            shifu_bid=query_context,
            outline_item_bid=uuid.uuid4().hex,
            title=f"Lesson {position}",
            position=position,
        )
        db.session.add(row)
        db.session.flush()
        rows.append(row)
    removed_bid = uuid.uuid4().hex
    db.session.add(
        model(
            shifu_bid=query_context,
            outline_item_bid=removed_bid,
            title="Former lesson",
            position="1.3",
        )
    )
    db.session.flush()
    db.session.add(
        model(shifu_bid=query_context, outline_item_bid=removed_bid, deleted=1)
    )
    db.session.add(
        model(
            shifu_bid="other-course",
            outline_item_bid=uuid.uuid4().hex,
            title="Other course",
        )
    )
    db.session.flush()
    result = shared._load_latest_outline_items(model, query_context)
    assert result == [rows[index] for index in [2, 4, 3, 0, 1]]
    assert removed_bid not in {row.outline_item_bid for row in result}


def test_outline_context_handles_orphans_and_cycles_without_inventing_parent_data(
    query_context: str,
) -> None:
    items = [
        DraftOutlineItem(
            shifu_bid=query_context,
            outline_item_bid="orphan",
            parent_bid="missing",
            title="Orphan",
        ),
        DraftOutlineItem(
            shifu_bid=query_context,
            outline_item_bid="first",
            parent_bid="second",
            title="First",
        ),
        DraftOutlineItem(
            shifu_bid=query_context,
            outline_item_bid="second",
            parent_bid="first",
            title="Second",
        ),
        DraftOutlineItem(
            shifu_bid=query_context,
            outline_item_bid="self",
            parent_bid="self",
            title="Self",
        ),
    ]
    result = shared._build_course_outline_context_map(items)
    assert result["orphan"] == {
        "chapter_outline_item_bid": "orphan",
        "chapter_title": "Orphan",
        "lesson_outline_item_bid": "orphan",
        "lesson_title": "Orphan",
    }
    assert result["first"]["chapter_outline_item_bid"] == "second"
    assert result["second"]["chapter_outline_item_bid"] == "first"
    assert result["self"]["chapter_outline_item_bid"] == "self"


@pytest.mark.parametrize("draft_exists", [False, True])
def test_detail_source_selects_editable_draft_but_retains_published_status(
    query_context: str, draft_exists: bool
) -> None:
    published = PublishedShifu(
        shifu_bid=query_context, title="Published", created_user_bid="owner"
    )
    db.session.add(published)
    db.session.add(
        PublishedOutlineItem(
            shifu_bid=query_context,
            outline_item_bid="published",
            title="Published lesson",
        )
    )
    draft = None
    if draft_exists:
        draft = DraftShifu(
            shifu_bid=query_context, title="Draft", created_user_bid="owner"
        )
        db.session.add(draft)
        db.session.add(
            DraftOutlineItem(
                shifu_bid=query_context, outline_item_bid="draft", title="Draft lesson"
            )
        )
    db.session.flush()
    source, outlines = shared._load_operator_course_outline_items(query_context)
    assert source["course"] is (draft if draft_exists else published)
    assert source["course_status"] == shared.COURSE_STATUS_PUBLISHED
    assert source["outline_model"] is (
        DraftOutlineItem if draft_exists else PublishedOutlineItem
    )
    assert [item.title for item in outlines] == [
        "Draft lesson" if draft_exists else "Published lesson"
    ]


def test_deleted_only_course_cannot_supply_outline_data(query_context: str) -> None:
    db.session.add(DraftShifu(shifu_bid=query_context, title="Removed", deleted=1))
    db.session.add(DraftOutlineItem(shifu_bid=query_context, outline_item_bid="stale"))
    db.session.flush()
    assert shared._load_operator_course_detail_source(query_context) is None
    with pytest.raises(AppError) as caught:
        shared._load_operator_course_outline_items(query_context)
    assert caught.value.code == 4008


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("invalid date", None),
        (123, None),
        (datetime(2026, 1, 2, 3), datetime(2026, 1, 2, 3)),
        (datetime(2026, 1, 2, 3, tzinfo=UTC), datetime(2026, 1, 2, 3)),
        (
            datetime(2026, 1, 2, 11, tzinfo=timezone(timedelta(hours=8))),
            datetime(2026, 1, 2, 3),
        ),
        ("2026-01-02T03:00:00Z", datetime(2026, 1, 2, 3)),
        ("2026-01-02T11:00:00+08:00", datetime(2026, 1, 2, 3)),
        ("2026-01-02T03:00:00", datetime(2026, 1, 2, 3)),
    ],
)
def test_operator_timestamps_are_utc_naive_before_database_filtering(
    app: object, value: object, expected: datetime | None
) -> None:
    with app.app_context():
        assert shared._coerce_operator_datetime(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" MANUAL_GRANT ", "manual_credit"),
        ("manual_credit", "manual_credit"),
        ("referral_reward", "referral_reward"),
        ("invalid", "manual_credit"),
    ],
)
def test_grant_kind_normalizes_legacy_and_supported_values(
    value: str, expected: str
) -> None:
    assert shared._resolve_operator_credit_grant_type(value) == expected
