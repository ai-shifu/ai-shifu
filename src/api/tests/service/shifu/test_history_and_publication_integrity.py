"""Protect revision metadata, historical trees, and published author listings."""

import uuid
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu import shifu_draft_funcs as drafts
from flaskr.service.shifu import shifu_history_manager as history
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    PublishedShifu,
)
from flaskr.service.user.models import UserInfo as UserEntity


@pytest.fixture
def author_scope(app: object) -> Iterator[str]:
    author = uuid.uuid4().hex
    with app.app_context():
        yield author
        db.session.rollback()
        for model in (DraftShifu, PublishedShifu, DraftOutlineItem, LogDraftStruct):
            model.query.filter_by(created_user_bid=author).delete()
        UserEntity.query.filter_by(user_bid=author).delete()
        db.session.commit()


def _outline(author: str, bid: str, course: str, **values: object) -> DraftOutlineItem:
    row = DraftOutlineItem(
        **{
            "outline_item_bid": bid,
            "shifu_bid": course,
            "created_user_bid": author,
            "updated_user_bid": author,
            "title": "Lesson",
            "content": "Teaching content",
            **values,
        }
    )
    db.session.add(row)
    db.session.flush()
    return row


def test_revision_metadata_tracks_content_change_and_tombstone_in_callers_transaction(
    app: object, author_scope: str
) -> None:
    course = uuid.uuid4().hex
    outline = uuid.uuid4().hex
    db.session.add(
        UserEntity(user_bid=author_scope, user_identify="author@example.test")
    )
    first = _outline(author_scope, outline, course)
    _outline(author_scope, outline, course, title="Renamed without content change")
    assert history.get_shifu_draft_revision(app, course, outline) == first.id
    metadata = history.get_shifu_draft_meta(app, course, outline)
    assert metadata["revision"] == first.id
    assert metadata["updated_user"] == {
        "user_bid": author_scope,
        "phone": "au***@example.test",
    }
    assert metadata["updated_at"].endswith("Z")
    changed = _outline(author_scope, outline, course, content="New teaching content")
    assert history.get_shifu_draft_revision(app, course, outline) == changed.id
    deleted = _outline(
        author_scope, outline, course, content="New teaching content", deleted=1
    )
    metadata = history.get_shifu_draft_meta(app, course, outline)
    assert metadata["revision"] == deleted.id
    assert metadata["deleted"] == 1
    assert history.get_shifu_draft_meta(app, course, "missing") == {
        "revision": 0,
        "updated_at": None,
        "updated_user": None,
        "deleted": 0,
    }
    assert (
        list(history.iter_outline_item_versions_desc(course, outline, max_rows=0)) == []
    )


def test_struct_history_reordering_retains_legacy_blocks_and_deleting_parent_removes_subtree(
    app: object, author_scope: str
) -> None:
    course = uuid.uuid4().hex
    block = history.HistoryItem(bid="block", id=10, type="block")
    lesson = history.HistoryItem(bid="lesson", id=20, type="outline", children=[block])
    chapter = history.HistoryItem(
        bid="chapter", id=30, type="outline", children=[lesson]
    )
    history.save_outline_tree_history(app, author_scope, course, [chapter], shifu_id=40)
    root = history.get_shifu_history(app, course)
    assert history.HistoryItem.from_json(root.to_json()) == root
    history.save_outline_tree_history(
        app,
        author_scope,
        course,
        [
            history.HistoryItem(bid="lesson", id=21, type="outline"),
            history.HistoryItem(bid="empty", id=31, type="outline"),
        ],
        shifu_id=41,
    )
    reordered = history.get_shifu_history(app, course)
    assert reordered.id == 41
    assert reordered.children[0].children == [block]
    assert reordered.children[1].children == []
    revision = history.save_outline_history(
        app, author_scope, course, "lesson", 22, child_count=3
    )
    assert history.get_shifu_draft_revision(app, course) == revision
    assert history.get_shifu_history(app, course).children[0].child_count == 3
    history.delete_outline_history(app, author_scope, course, "lesson")
    assert [item.bid for item in history.get_shifu_history(app, course).children] == [
        "empty"
    ]
    latest = history._get_latest_draft_log(course, for_update=True)
    assert latest.id == history.get_shifu_draft_meta(app, course)["revision"]
    snapshots = (
        LogDraftStruct.query.filter_by(shifu_bid=course)
        .order_by(LogDraftStruct.id)
        .all()
    )
    assert len(snapshots) == 4
    assert history.HistoryItem.from_json(snapshots[0].struct).children == [chapter]


def test_new_top_level_history_item_respects_insertion_index(
    app: object, author_scope: str
) -> None:
    course = uuid.uuid4().hex
    history.save_new_outline_history(app, author_scope, course, "last", 1, "")
    history.save_new_outline_history(app, author_scope, course, "first", 2, "", index=0)
    history.save_new_outline_history(
        app, author_scope, course, "middle", 3, "", index=1
    )
    assert [item.bid for item in history.get_shifu_history(app, course).children] == [
        "first",
        "middle",
        "last",
    ]


@pytest.mark.parametrize(
    ("identifier", "masked"),
    [
        (None, ""),
        ("", ""),
        ("5", "5"),
        ("12", "1****2"),
        ("abc", ""),
        ("138-0000-0001", "138****0001"),
        ("@example.test", "***@example.test"),
        ("a@example.test", "a***@example.test"),
        ("alice@example.test", "al***@example.test"),
    ],
)
def test_history_contact_masking_never_returns_complete_identity(
    identifier: str | None, masked: str
) -> None:
    assert history.mask_contact_identifier(identifier) == masked


def _published(author: str, bid: str, title: str, **values: object) -> PublishedShifu:
    row = PublishedShifu(
        **{
            "shifu_bid": bid,
            "title": title,
            "created_user_bid": author,
            "updated_user_bid": author,
            **values,
        }
    )
    db.session.add(row)
    db.session.flush()
    return row


def test_published_list_deduplicates_latest_revisions_clamps_page_and_preserves_owner_rights(
    app: object, author_scope: str
) -> None:
    first_bid, second_bid = uuid.uuid4().hex, uuid.uuid4().hex
    _published(author_scope, first_bid, "Old title")
    _published(author_scope, first_bid, "A current")
    _published(author_scope, first_bid, "Deleted revision", deleted=1)
    _published(author_scope, second_bid, "B current")
    _published(author_scope, uuid.uuid4().hex, "Deleted course", deleted=1)
    db.session.commit()
    bids = drafts.get_user_created_published_shifu_bids(app, author_scope)
    assert set(bids) == {first_bid, second_bid}
    result = drafts.get_shifu_published_list(
        app, author_scope, page_index=100, page_size=1
    )
    assert (result.page, result.page_count, result.total) == (2, 2, 2)
    assert [(item.bid, item.name) for item in result.data] == [
        (second_bid, "B current")
    ]
    assert result.data[0].can_manage_permissions is True
    assert result.data[0].can_manage_archive is True
    first_page = drafts.get_shifu_published_list(
        app, author_scope, page_index=0, page_size=0
    )
    assert first_page.page == first_page.page_size == 1
    assert first_page.data[0].name == "A current"


def test_published_list_accepts_explicit_collaborator_permission_without_owner_rights(
    app: object, author_scope: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bid = uuid.uuid4().hex
    _published(author_scope, bid, "Shared course")
    db.session.commit()
    learner = uuid.uuid4().hex
    permission = Mock(return_value={bid: {"view"}})
    monkeypatch.setattr(drafts, "get_user_shifu_permissions", permission)
    result = drafts.get_shifu_published_list(app, learner, 1, 10, creator_only=False)
    assert result.total == 1
    assert result.data[0].bid == bid
    assert result.data[0].can_manage_permissions is False
    permission.assert_called_once_with(app, learner)
    assert (
        drafts.get_shifu_published_list(app, learner, 1, 10, creator_only=True).total
        == 0
    )
    permission.return_value = {}
    assert (
        drafts.get_shifu_published_list(app, learner, 1, 10, creator_only=False).data
        == []
    )


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("", ""),
        ("x" * 501, ""),
        ("Valid", "x" * 501),
    ],
)
def test_course_creation_rejects_invalid_lengths_before_storing_drafts(
    app: object, author_scope: str, name: str, description: str
) -> None:
    with pytest.raises(AppError):
        drafts.create_shifu_draft(app, author_scope, name, description, "")
    assert DraftShifu.query.filter_by(created_user_bid=author_scope).count() == 0


@pytest.mark.parametrize("minimum", ["invalid", "-1", "NaN"])
def test_invalid_minimum_price_configuration_rejects_new_course_price(
    app: object, monkeypatch: pytest.MonkeyPatch, minimum: str
) -> None:
    monkeypatch.setattr(drafts, "get_config", lambda _key: minimum)
    with app.app_context(), pytest.raises(AppError) as caught:
        drafts._resolve_shifu_price(None)
    assert caught.value.code == ERROR_CODE["server.common.paramsError"]


def test_first_draft_save_preserves_initial_history_and_language_revision(
    app: object, author_scope: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bid = uuid.uuid4().hex
    monkeypatch.setattr(drafts, "get_config", lambda _key: 0)
    monkeypatch.setattr(drafts, "shifu_permission_verification", lambda *_args: True)
    risk = Mock()
    monkeypatch.setattr(drafts, "check_text_with_risk_control", risk)
    payload = {
        "shifu_name": "First course",
        "shifu_description": "Course description",
        "shifu_avatar": "",
        "shifu_keywords": [],
        "shifu_model": "",
        "shifu_temperature": None,
        "shifu_price": None,
        "shifu_system_prompt": "Teach clearly",
        "base_url": "https://courses.example",
        "ask_enabled_status": 999,
    }
    first = drafts.save_shifu_draft_info(app, author_scope, bid, **payload)
    original = DraftShifu.query.filter_by(shifu_bid=bid).one()
    assert first.bid == bid
    assert float(original.llm_temperature) == pytest.approx(0.3)
    assert original.ask_enabled_status == drafts.ASK_MODE_DEFAULT
    assert history.get_shifu_history(app, bid).id == original.id
    changed = drafts.save_shifu_draft_info(
        app, author_scope, bid, **payload, use_learner_language=True
    )
    revisions = DraftShifu.query.filter_by(shifu_bid=bid).order_by(DraftShifu.id).all()
    assert len(revisions) == 2
    assert original.use_learner_language == 0
    assert revisions[-1].use_learner_language == 1
    assert changed.use_learner_language is True
    assert history.get_shifu_history(app, bid).id == revisions[-1].id
    risk.assert_called_once()
    assert drafts._get_user_archive_map(app, author_scope, []) == {}


def test_missing_draft_read_and_archive_report_not_found(app: object) -> None:
    bid = uuid.uuid4().hex
    with pytest.raises(AppError) as read_error:
        drafts.get_shifu_draft_info(app, "author", bid, "https://courses.example")
    assert read_error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
    with pytest.raises(AppError) as archive_error:
        drafts._set_shifu_archive_state(app, "author", bid, archived=True)
    assert archive_error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
