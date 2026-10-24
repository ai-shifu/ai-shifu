"""Verify latest-course queries preserve visibility, activity, and draft history."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.learn.const import LEARN_STATUS_IN_PROGRESS, LEARN_STATUS_RESET
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu import admin_course_summaries as summaries
from flaskr.service.shifu.admin_operations import courses_listing as listing
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, PublishedShifu
from flaskr.util.datetime import now_utc


@pytest.fixture
def course_scope(app: object) -> Iterator[str]:
    with app.app_context():
        yield uuid.uuid4().hex
        db.session.rollback()


def _course(
    scope: str, bid: str, model: type = DraftShifu, **overrides: object
) -> object:
    now = now_utc()
    row = model(
        **{
            "shifu_bid": bid,
            "title": "Course",
            "created_user_bid": scope,
            "updated_user_bid": scope,
            "llm": "model",
            "tts_model": "voice-model",
            "created_at": now - timedelta(days=2),
            "updated_at": now - timedelta(days=1),
            "price": Decimal("12.34"),
            **overrides,
        }
    )
    db.session.add(row)
    db.session.flush()
    return row


def _filters(**overrides: object) -> dict:
    return {
        "shifu_bid": "",
        "course_name": "",
        "creator_bids": None,
        "start_time": None,
        "end_time": None,
        "updated_start_time": None,
        "updated_end_time": None,
        **overrides,
    }


@pytest.mark.parametrize("module", [listing, summaries], ids=["listing", "summaries"])
@pytest.mark.parametrize("lightweight", [False, True])
def test_latest_course_loaders_filter_current_revision_and_preserve_prompt_flags(
    course_scope: str,
    module: object,
    lightweight: bool,
) -> None:
    now = now_utc()
    bid = uuid.uuid4().hex
    _course(course_scope, bid, title="Old title")
    latest = _course(
        course_scope, bid, title="Current title", llm_system_prompt="Course instruction"
    )
    _course(course_scope, bid, title="Deleted revision", deleted=1)
    _course("other-owner", uuid.uuid4().hex, title="Current title")
    filters = _filters(
        shifu_bid=bid,
        course_name="Current",
        creator_bids={course_scope},
        start_time=now - timedelta(days=3),
        end_time=now,
        updated_start_time=now - timedelta(days=2),
        updated_end_time=now,
    )
    result = module._load_latest_shifus(
        DraftShifu, **filters, lightweight=lightweight, attach_prompt_flags=True
    )
    assert len(result) == 1
    assert result[0].id == latest.id
    assert result[0].title == "Current title"
    if not lightweight:
        assert result[0].has_course_prompt is True
    seeds = module._load_latest_shifu_seeds(DraftShifu, **filters)
    assert len(seeds) == 1
    assert seeds[0].shifu_bid == bid
    assert seeds[0].llm == "model"
    assert module._load_latest_shifus(DraftShifu, **_filters(creator_bids=set())) == []
    assert (
        module._load_latest_shifu_seeds(DraftShifu, **_filters(creator_bids=set()))
        == []
    )


@pytest.mark.parametrize("module", [listing, summaries], ids=["listing", "summaries"])
@pytest.mark.parametrize("include_activity", [False, True])
def test_candidate_query_merges_latest_draft_and_published_rows_and_current_outline_activity(
    course_scope: str,
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    include_activity: bool,
) -> None:
    now = now_utc()
    bid, demo_bid = uuid.uuid4().hex, uuid.uuid4().hex
    _course(course_scope, bid, model=PublishedShifu, title="Published")
    latest = _course(course_scope, bid, title="Latest draft")
    _course(course_scope, demo_bid)
    monkeypatch.setattr(module, "load_demo_shifu_bids", lambda: {demo_bid})
    db.session.add_all(
        [
            DraftOutlineItem(
                shifu_bid=bid,
                outline_item_bid="active",
                updated_at=now,
                updated_user_bid="editor",
            ),
            DraftOutlineItem(
                shifu_bid=bid,
                outline_item_bid="removed",
                updated_at=now + timedelta(days=2),
                updated_user_bid="removed-editor",
            ),
        ]
    )
    db.session.flush()
    db.session.add(
        DraftOutlineItem(
            shifu_bid=bid,
            outline_item_bid="removed",
            deleted=1,
            updated_at=now + timedelta(days=3),
        )
    )
    db.session.flush()
    result = module._build_operator_course_candidate_query(
        shifu_bid="",
        course_name="",
        creator_bids={course_scope},
        start_time=now - timedelta(days=3),
        end_time=now,
        include_activity=include_activity,
    ).all()
    assert len(result) == 1
    candidate = module._build_operator_course_list_candidate(result[0])
    assert candidate.id == latest.id
    assert candidate.title == "Latest draft"
    assert candidate.selected_source == "draft"
    assert candidate.course_status == "published"
    if include_activity:
        assert candidate.activity_updated_at == now
        assert candidate.activity_updated_user_bid == "editor"


@pytest.mark.parametrize("module", [listing, summaries], ids=["listing", "summaries"])
def test_candidate_query_applies_exact_course_name_owner_and_creation_boundaries(
    course_scope: str,
    module: object,
) -> None:
    now = now_utc()
    bid = uuid.uuid4().hex
    _course(course_scope, bid, title="Searchable course")
    args = {
        "shifu_bid": bid,
        "course_name": "Searchable",
        "creator_bids": {course_scope},
        "start_time": now - timedelta(days=3),
        "end_time": now,
    }
    assert [
        row.shifu_bid
        for row in module._build_operator_course_candidate_query(**args).all()
    ] == [bid]
    assert (
        module._build_operator_course_candidate_query(**{**args, "creator_bids": set()})
        is None
    )


def test_tts_fallback_preserves_latest_course_model_and_explicit_configuration(
    course_scope: str,
) -> None:
    bid = uuid.uuid4().hex
    _course(course_scope, bid, llm="fallback-model", tts_model="fallback-voice")
    latest = _course(course_scope, bid, llm="", tts_model="")
    result = listing._load_latest_shifus(DraftShifu, **_filters(shifu_bid=bid))
    assert result == [latest]
    assert latest.llm == ""
    assert latest.tts_model == "fallback-voice"
    explicit = SimpleNamespace(
        shifu_bid=bid, llm="explicit", tts_model="explicit-voice"
    )
    orphan = SimpleNamespace(shifu_bid="missing", llm="", tts_model="")
    listing._apply_latest_nonempty_model_fields(DraftShifu, [explicit, orphan])
    assert (explicit.llm, explicit.tts_model) == ("explicit", "explicit-voice")
    assert orphan.llm == ""
    listing._apply_latest_nonempty_model_fields(DraftShifu, [])
    listing._apply_latest_nonempty_model_fields(
        DraftShifu, [SimpleNamespace(shifu_bid="")]
    )


@pytest.mark.parametrize(
    ("quick_filter", "status", "expected"),
    [
        ("draft", "", {"draft", "old"}),
        ("published", "", {"published"}),
        ("created_last_7d", "", {"draft", "published"}),
        ("learning_active_30d", "", {"draft"}),
        ("paid_order_30d", "", {"published"}),
        ("", "published", {"published"}),
    ],
)
def test_sql_course_quick_filters_select_only_matching_activity_and_status(
    course_scope: str,
    quick_filter: str,
    status: str,
    expected: set,
) -> None:
    now = now_utc()
    bids = {name: f"{course_scope}-{name}" for name in ("draft", "published", "old")}
    _course(course_scope, bids["draft"])
    _course(course_scope, bids["published"], model=PublishedShifu)
    _course(course_scope, bids["old"], created_at=now - timedelta(days=40))
    db.session.add_all(
        [
            LearnProgressRecord(
                shifu_bid=bids["draft"], status=LEARN_STATUS_IN_PROGRESS, created_at=now
            ),
            LearnProgressRecord(
                shifu_bid=bids["old"], status=LEARN_STATUS_RESET, created_at=now
            ),
            Order(
                shifu_bid=bids["published"], status=ORDER_STATUS_SUCCESS, created_at=now
            ),
        ]
    )
    db.session.flush()
    candidates = listing._build_operator_course_candidate_query(
        shifu_bid="",
        course_name="",
        creator_bids={course_scope},
        start_time=None,
        end_time=None,
        include_activity=True,
    ).subquery()
    rows = listing._apply_operator_course_list_filters(
        db.session.query(candidates),
        candidates,
        course_status=status,
        quick_filter=quick_filter,
        updated_start_time=now - timedelta(days=3),
        updated_end_time=now,
        apply_updated_filters=True,
    ).all()
    assert {row.shifu_bid for row in rows} == {bids[name] for name in expected}


def test_recent_course_activity_queries_are_scoped_and_ignore_reset_deleted_or_failed_rows(
    course_scope: str,
) -> None:
    now = now_utc()
    active, stale, deleted, reset, other = [
        f"{course_scope}-{name}"
        for name in ("active", "stale", "deleted", "reset", "other")
    ]
    for bid, status, is_deleted, created in [
        (active, LEARN_STATUS_IN_PROGRESS, 0, now),
        (stale, LEARN_STATUS_IN_PROGRESS, 0, now - timedelta(days=40)),
        (deleted, LEARN_STATUS_IN_PROGRESS, 1, now),
        (reset, LEARN_STATUS_RESET, 0, now),
        (other, LEARN_STATUS_IN_PROGRESS, 0, now),
    ]:
        db.session.add(
            LearnProgressRecord(
                shifu_bid=bid, status=status, deleted=is_deleted, created_at=created
            )
        )
        db.session.add(
            Order(
                shifu_bid=bid,
                status=ORDER_STATUS_SUCCESS if status != LEARN_STATUS_RESET else 0,
                deleted=is_deleted,
                created_at=created,
            )
        )
    db.session.flush()
    for loader in [
        listing._load_recent_learning_active_course_bids,
        listing._load_recent_paid_order_course_bids,
    ]:
        assert loader(
            since=now - timedelta(days=30), shifu_bids=[active, stale, deleted, reset]
        ) == {active}
        assert loader(since=now - timedelta(days=30), shifu_bids=[]) == set()


def test_course_transfer_and_history_loaders_respect_latest_deletion_tombstones(
    course_scope: str,
) -> None:
    bid = uuid.uuid4().hex
    published = _course(course_scope, bid, model=PublishedShifu)
    assert summaries._load_latest_course_for_transfer(bid) == published
    draft = _course(course_scope, bid)
    assert summaries._load_latest_course_for_transfer(bid) == draft
    assert summaries._load_latest_course_versions(bid) == (draft, published)
    for outline_bid, position, deleted in [
        ("kept", "2", 0),
        ("removed", "1", 0),
        ("removed", "1", 1),
        ("first", "1", 0),
    ]:
        db.session.add(
            DraftOutlineItem(
                shifu_bid=bid,
                outline_item_bid=outline_bid,
                position=position,
                deleted=deleted,
            )
        )
    db.session.flush()
    assert [
        row.outline_item_bid
        for row in summaries._load_latest_active_draft_outlines(bid)
    ] == ["first", "kept"]


def test_outline_history_tree_sorts_siblings_and_retains_markdown_block_counts(
    course_scope: str,
) -> None:
    outlines = [
        DraftOutlineItem(
            id=3,
            shifu_bid=course_scope,
            outline_item_bid="second",
            parent_bid="",
            position="2",
            content="",
        ),
        DraftOutlineItem(
            id=2,
            shifu_bid=course_scope,
            outline_item_bid="lesson",
            parent_bid="chapter",
            position="1",
            content="A teaching block",
        ),
        DraftOutlineItem(
            id=1,
            shifu_bid=course_scope,
            outline_item_bid="chapter",
            parent_bid="",
            position="1",
            content="",
        ),
    ]
    tree = summaries._build_outline_history_tree(outlines)
    assert [item.bid for item in tree] == ["chapter", "second"]
    assert tree[0].children[0].bid == "lesson"
    assert tree[0].children[0].child_count == 1
    assert tree[1].child_count == 0


def test_course_copy_titles_keep_custom_names_and_enforce_the_shared_length_limit(
    app: object,
) -> None:
    with app.app_context():
        assert summaries._resolve_course_copy_title("Source", " Custom ") == "Custom"
        assert summaries._resolve_course_copy_title("Source", "").startswith("Source")
        assert (
            len(
                summaries._build_course_copy_title(
                    "A" * summaries.SHIFU_NAME_MAX_LENGTH
                )
            )
            == summaries.SHIFU_NAME_MAX_LENGTH
        )
        assert summaries._build_course_copy_title("")
        with pytest.raises(AppError):
            summaries._resolve_course_copy_title(
                "Source", "A" * (summaries.SHIFU_NAME_MAX_LENGTH + 1)
            )


@pytest.mark.parametrize(("value", "expected"), [(None, ""), (Decimal("4.25"), "4.2")])
def test_average_rating_format_preserves_missing_scores(
    value: Decimal | None, expected: str
) -> None:
    assert summaries._format_average_score(value) == expected


@pytest.mark.parametrize(
    ("value", "mode", "sort"),
    [
        (" LISTEN ", "listen", ""),
        ("read", "read", ""),
        ("", "", "latest_desc"),
        ("score_asc", "", "score_asc"),
        ("unsupported", "", ""),
    ],
)
def test_rating_filters_normalize_known_modes_and_sort_orders(
    value: str, mode: str, sort: str
) -> None:
    assert summaries._resolve_course_rating_mode(value) == mode
    assert summaries._resolve_course_rating_sort_by(value) == sort


def test_course_quick_filter_and_recent_window_boundaries(app: object) -> None:
    with app.app_context():
        assert summaries._resolve_course_quick_filter(" PUBLISHED ") == "published"
        assert summaries._resolve_course_quick_filter("") == ""
        with pytest.raises(AppError):
            summaries._resolve_course_quick_filter("unsupported")
    now = now_utc()
    start, end = summaries._resolve_created_last_7d_window(now)
    assert start == (now - timedelta(days=6)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    assert end == now.replace(hour=23, minute=59, second=59, microsecond=0)


@pytest.mark.parametrize("status", ["draft", "published"])
def test_legacy_course_listing_matches_status_and_activity_filters(
    course_scope: str,
    app: object,
    status: str,
) -> None:
    now = now_utc()
    bid = uuid.uuid4().hex
    draft = _course(course_scope, bid, title="Visible course")
    if status == "published":
        _course(course_scope, bid, model=PublishedShifu)
    result = listing._list_operator_courses_legacy(
        app,
        1,
        20,
        {
            "shifu_bid": bid,
            "course_query": bid,
            "quick_filter": status,
            "updated_start_time": now - timedelta(days=2),
            "updated_end_time": now,
        },
    )
    assert result.total == 1
    assert result.items[0].shifu_bid == bid
    assert result.items[0].course_name == draft.title


def test_course_overview_legacy_fallback_counts_scoped_drafts_publications_and_activity(
    course_scope: str,
    app: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = now_utc()
    draft_bid, published_bid = uuid.uuid4().hex, uuid.uuid4().hex
    _course(course_scope, draft_bid)
    _course(course_scope, published_bid, model=PublishedShifu)
    db.session.add_all(
        [
            LearnProgressRecord(
                shifu_bid=draft_bid, status=LEARN_STATUS_IN_PROGRESS, created_at=now
            ),
            Order(shifu_bid=published_bid, status=ORDER_STATUS_SUCCESS, created_at=now),
        ]
    )
    db.session.flush()
    original_loader = listing._load_latest_shifus

    def scoped_loader(model: object, **kwargs: object) -> list:
        return original_loader(model, **{**kwargs, "creator_bids": {course_scope}})

    monkeypatch.setattr(listing, "_load_latest_shifus", scoped_loader)
    monkeypatch.setattr(
        listing, "_can_use_operator_course_sql_optimization", lambda _app: False
    )
    result = listing._build_operator_course_overview(app)
    assert result.total_course_count == 2
    assert result.draft_course_count == 1
    assert result.published_course_count == 1
    assert result.learning_active_30d_course_count == 1
    assert result.paid_order_30d_course_count == 1
    assert result.created_last_7d_course_count == 2


def test_summary_mapper_uses_latest_activity_user_and_preserves_price_precision(
    course_scope: str,
) -> None:
    course = _course(course_scope, uuid.uuid4().hex)
    now = now_utc()
    result = summaries._build_course_summary(
        course,
        {"editor": {"nickname": "Latest editor"}},
        "published",
        activity={"updated_at": now, "updated_user_bid": "editor"},
    )
    assert result.updater_nickname == "Latest editor"
    assert result.updated_at == now
    assert Decimal(result.price) == Decimal("12.34")
    for module in (summaries, listing):
        activity = module._load_course_activity_map([course], [])
        assert activity[course.shifu_bid]["updated_at"] == course.updated_at


@pytest.mark.parametrize("loader", ["seeds", "lightweight"])
def test_latest_lightweight_seeds_recover_tts_without_changing_course_model_selection(
    course_scope: str,
    loader: str,
) -> None:
    bid = uuid.uuid4().hex
    _course(course_scope, bid, llm="saved-model", tts_model="saved-voice")
    latest = _course(course_scope, bid, llm="", tts_model="")
    seeds = (
        listing._load_latest_shifu_seeds(DraftShifu, **_filters(shifu_bid=bid))
        if loader == "seeds"
        else listing._load_latest_shifus(
            DraftShifu, **_filters(shifu_bid=bid), lightweight=True
        )
    )
    assert [(row.llm, row.tts_model) for row in seeds] == [("", "saved-voice")]
    assert (latest.llm, latest.tts_model) == ("", "")
    assert latest not in db.session.dirty
