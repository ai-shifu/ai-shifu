"""Verify follow-up source history and dashboard filtering against persisted rows."""

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.dashboard import funcs as dashboard
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_COMPLETED, LEARN_STATUS_RESET
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.shifu.models import PublishedOutlineItem, PublishedShifu
from flaskr.service.user.models import AuthCredential, UserInfo
from flaskr.util.datetime import now_utc


@pytest.fixture
def follow_up(app: object) -> object:
    bid, owner = uuid.uuid4().hex, uuid.uuid4().hex
    stamp = now_utc()
    ask_bid, answer_bid, anchor_bid = (uuid.uuid4().hex for _ in range(3))
    with app.app_context(), unit_of_work():
        db.session.add(
            PublishedShifu(
                shifu_bid=bid, title="History course", created_user_bid=owner, deleted=0
            )
        )
        db.session.add(
            PublishedOutlineItem(
                shifu_bid=bid,
                outline_item_bid=bid,
                title="History lesson",
                parent_bid="",
                position=0,
                deleted=0,
            )
        )
        db.session.add(
            UserInfo(
                user_bid=bid,
                nickname="Ada Learner",
                user_identify=f"{bid}@example.test",
                deleted=0,
            )
        )
        for block_bid, kind, role, text in (
            (ask_bid, BLOCK_TYPE_MDASK_VALUE, ROLE_STUDENT, "Why this step?"),
            (
                answer_bid,
                BLOCK_TYPE_MDANSWER_VALUE,
                ROLE_TEACHER,
                "Because of the rule.",
            ),
        ):
            db.session.add(
                LearnGeneratedBlock(
                    generated_block_bid=block_bid,
                    progress_record_bid=bid,
                    shifu_bid=bid,
                    outline_item_bid=bid,
                    user_bid=bid,
                    type=kind,
                    role=role,
                    generated_content=text,
                    block_content_conf="",
                    position=3,
                    created_at=stamp,
                    status=1,
                    deleted=0,
                )
            )
        db.session.add(
            LearnGeneratedElement(
                element_bid=anchor_bid,
                generated_block_bid="source-block",
                progress_record_bid=bid,
                shifu_bid=bid,
                outline_item_bid=bid,
                user_bid=bid,
                event_type="element",
                element_type="text",
                content_text="Explanation seen before the question",
                created_at=stamp - timedelta(seconds=1),
                run_event_seq=1,
                sequence_number=1,
                status=0,
                deleted=0,
            )
        )
        db.session.add(
            LearnGeneratedElement(
                element_bid=uuid.uuid4().hex,
                generated_block_bid=answer_bid,
                progress_record_bid=bid,
                shifu_bid=bid,
                outline_item_bid=bid,
                user_bid=bid,
                event_type="element",
                element_type="ask",
                payload=json.dumps({"anchor_element_bid": anchor_bid}),
                created_at=stamp,
                run_event_seq=2,
                sequence_number=2,
                status=1,
                deleted=0,
            )
        )
    yield SimpleNamespace(
        bid=bid,
        owner=owner,
        ask_bid=ask_bid,
        answer_bid=answer_bid,
        anchor_bid=anchor_bid,
        stamp=stamp,
    )
    with app.app_context(), unit_of_work():
        for model in (
            LearnGeneratedElement,
            LearnGeneratedBlock,
            LearnProgressRecord,
            PublishedOutlineItem,
            PublishedShifu,
        ):
            model.query.filter_by(shifu_bid=bid).delete()
        AuthCredential.query.filter_by(user_bid=bid).delete()
        UserInfo.query.filter_by(user_bid=bid).delete()


def _source(follow_up: object, **overrides: object) -> dict:
    arguments = {
        "shifu_bid": follow_up.bid,
        "user_bid": follow_up.bid,
        "progress_record_bid": follow_up.bid,
        "answer_generated_block_bid": follow_up.answer_bid,
        "fallback_position": 3,
        "ask_created_at": follow_up.stamp,
    }
    return dashboard._resolve_follow_up_source_from_element(**(arguments | overrides))


def test_dashboard_follow_up_uses_anchor_snapshot_from_the_time_of_the_question(
    app: object, follow_up: object
) -> None:
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnGeneratedElement(
                element_bid=uuid.uuid4().hex,
                target_element_bid=follow_up.anchor_bid,
                generated_block_bid="source-block",
                progress_record_bid=follow_up.bid,
                shifu_bid=follow_up.bid,
                outline_item_bid=follow_up.bid,
                user_bid=follow_up.bid,
                event_type="element",
                element_type="text",
                content_text="New content after the question",
                created_at=follow_up.stamp + timedelta(seconds=1),
                sequence_number=10,
                run_event_seq=10,
                status=1,
                deleted=0,
            )
        )
    with app.app_context():
        assert _source(follow_up) == {
            "source_output_content": "Explanation seen before the question",
            "source_output_type": "element",
            "source_position": 3,
            "source_element_bid": follow_up.anchor_bid,
            "source_element_type": "text",
        }
        assert (
            _source(follow_up, ask_created_at=None)["source_output_content"]
            == "New content after the question"
        )
    listing = dashboard.build_dashboard_course_follow_ups(
        app, follow_up.owner, follow_up.bid, source_status="resolved"
    )
    assert listing.total == 1
    assert listing.items[0].generated_block_bid == follow_up.ask_bid
    assert listing.items[0].has_source_output is True
    assert (
        dashboard.build_dashboard_course_follow_ups(
            app, follow_up.owner, follow_up.bid, source_status="missing"
        ).total
        == 0
    )


@pytest.mark.parametrize(
    "scope",
    ["shifu_bid", "user_bid", "progress_record_bid", "answer_generated_block_bid"],
)
def test_source_lookup_cannot_cross_course_learner_or_progress_boundaries(
    app: object, follow_up: object, scope: str
) -> None:
    with app.app_context():
        assert _source(follow_up, **{scope: "another-scope"}) == {}
        assert _source(follow_up, **{scope: ""}) == {}


def test_deleted_anchor_retains_identity_but_is_reported_as_missing_source(
    app: object, follow_up: object
) -> None:
    with app.app_context(), unit_of_work():
        LearnGeneratedElement.query.filter_by(
            element_bid=follow_up.anchor_bid
        ).one().deleted = 1
    with app.app_context():
        source = _source(follow_up)
        assert source["source_element_bid"] == follow_up.anchor_bid
        assert source["source_output_content"] == ""
    listing = dashboard.build_dashboard_course_follow_ups(
        app, follow_up.owner, follow_up.bid, source_status="missing"
    )
    assert listing.total == 1
    assert listing.items[0].has_source_output is False


@pytest.mark.parametrize("payload", ["", "invalid", "null", "[]", "{}"])
def test_malformed_anchor_payload_leaves_source_unresolved(
    app: object, follow_up: object, payload: str
) -> None:
    with app.app_context(), unit_of_work():
        LearnGeneratedElement.query.filter_by(
            generated_block_bid=follow_up.answer_bid
        ).one().payload = payload
    with app.app_context():
        assert _source(follow_up) == {}
    assert (
        dashboard.build_dashboard_course_follow_ups(
            app, follow_up.owner, follow_up.bid, source_status="missing"
        ).total
        == 1
    )


@pytest.mark.parametrize("interaction", [False, True])
@pytest.mark.parametrize("fallback", [False, True])
def test_legacy_follow_up_source_uses_pre_question_content_with_prompt_fallback(
    app: object, follow_up: object, interaction: bool, fallback: bool
) -> None:
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnGeneratedBlock(
                generated_block_bid=uuid.uuid4().hex,
                progress_record_bid=follow_up.bid,
                shifu_bid=follow_up.bid,
                outline_item_bid=follow_up.bid,
                user_bid=follow_up.bid,
                type=BLOCK_TYPE_MDINTERACTION_VALUE
                if interaction
                else BLOCK_TYPE_MDCONTENT_VALUE,
                role=ROLE_TEACHER,
                position=3,
                generated_content="Generated source" if interaction == fallback else "",
                block_content_conf="Prompt source" if interaction != fallback else "",
                created_at=follow_up.stamp - timedelta(seconds=2),
                status=0,
                deleted=0,
            )
        )
    with app.app_context():
        ask = LearnGeneratedBlock.query.filter_by(
            generated_block_bid=follow_up.ask_bid
        ).one()
        source = dashboard._resolve_follow_up_source_from_blocks(ask)
        assert source["source_output_content"] == (
            "Generated source" if interaction == fallback else "Prompt source"
        )
        assert source["source_output_type"] == (
            "interaction" if interaction else "content"
        )
        assert source["source_position"] == 3


def test_follow_up_detail_keeps_current_question_and_answer_paired(
    app: object, follow_up: object
) -> None:
    detail = dashboard.build_dashboard_course_follow_up_detail(
        app, follow_up.owner, follow_up.bid, follow_up.ask_bid
    )
    assert detail.current_record.follow_up_content == "Why this step?"
    assert detail.current_record.answer_content == "Because of the rule."
    assert detail.basic_info.turn_index == 1
    assert detail.basic_info.email == f"{follow_up.bid}@example.test"
    assert [(item.role, item.is_current) for item in detail.timeline] == [
        ("student", True),
        ("teacher", True),
    ]
    with pytest.raises(AppError):
        dashboard.build_dashboard_course_follow_up_detail(
            app, "another-owner", follow_up.bid, follow_up.ask_bid
        )


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "bad"},
        {"start_date": "2026-01-02", "end_date": "2026-01-01"},
        {"start_date": "2024-01-01", "end_date": "2026-01-01"},
    ],
)
def test_entry_rejects_invalid_date_ranges_before_querying_metrics(
    app: object, follow_up: object, params: dict
) -> None:
    with pytest.raises(AppError):
        dashboard.build_dashboard_entry(app, follow_up.owner, **params)


def test_date_filtered_entry_omits_courses_with_no_activity_in_range(
    app: object, follow_up: object
) -> None:
    result = dashboard.build_dashboard_entry(
        app, follow_up.owner, start_date="2000-01-01", end_date="2000-01-02"
    )
    assert result.items == []
    assert result.total == 0
    assert result.summary.course_count == 0


@pytest.mark.parametrize(
    ("keyword", "matched"),
    [
        ("", True),
        ("ADA", True),
        ("learner@example.test", True),
        ("LEARNER@EXAMPLE.TEST", True),
        ("example.test", False),
        ("13800138000", True),
        ("1380013", False),
        ("unmatched", False),
    ],
)
def test_dashboard_identity_search_uses_exact_contact_and_partial_nickname_matches(
    keyword: str, matched: bool
) -> None:
    assert (
        dashboard._dashboard_learner_keyword_matches(
            keyword=keyword,
            nickname="Ada Learner",
            mobile="13800138000",
            email="Learner@Example.Test",
        )
        is matched
    )


@pytest.mark.parametrize(
    "filter_kind",
    [
        "nickname",
        "email",
        "phone",
        "outline",
        "learner",
        "date",
        "missing-outline",
        "missing-user",
    ],
)
def test_follow_up_filters_use_persisted_contacts_lesson_and_utc_time(
    app: object, follow_up: object, filter_kind: str
) -> None:
    with app.app_context(), unit_of_work():
        db.session.add(
            AuthCredential(
                credential_bid=uuid.uuid4().hex,
                user_bid=follow_up.bid,
                provider_name="phone",
                identifier="13800138000",
                deleted=0,
            )
        )
    filters = {
        "nickname": {"keyword": "ada"},
        "email": {"keyword": f"{follow_up.bid}@example.test"},
        "phone": {"keyword": "13800138000"},
        "outline": {"chapter_keyword": "history lesson"},
        "learner": {"user_bid": follow_up.bid},
        "date": {
            "start_time": follow_up.stamp.date().isoformat(),
            "end_time": follow_up.stamp.date().isoformat(),
        },
        "missing-outline": {"chapter_keyword": "absent lesson"},
        "missing-user": {"user_bid": "unknown"},
    }[filter_kind]
    result = dashboard.build_dashboard_course_follow_ups(
        app, follow_up.owner, follow_up.bid, **filters
    )
    assert result.total == (0 if filter_kind.startswith("missing-") else 1)
    assert result.summary.follow_up_count == 1
    if result.items:
        assert result.items[0].mobile == "13800138000"


def test_dashboard_progress_aggregates_ignore_resets_deleted_and_other_learners(
    app: object, follow_up: object
) -> None:
    with app.app_context(), unit_of_work():
        for user, status, deleted, seconds in (
            (follow_up.bid, LEARN_STATUS_COMPLETED, 0, 1),
            (follow_up.bid, LEARN_STATUS_RESET, 0, 2),
            (follow_up.bid, LEARN_STATUS_COMPLETED, 1, 3),
            ("other-user", LEARN_STATUS_COMPLETED, 0, 4),
        ):
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid=uuid.uuid4().hex,
                    user_bid=user,
                    shifu_bid=follow_up.bid,
                    outline_item_bid=follow_up.bid,
                    status=status,
                    deleted=deleted,
                    updated_at=follow_up.stamp + timedelta(seconds=seconds),
                )
            )
    with app.app_context():
        assert dashboard._load_dashboard_course_last_learning_map(
            follow_up.bid, [follow_up.bid]
        ) == {follow_up.bid: follow_up.stamp + timedelta(seconds=1)}
        assert dashboard._load_dashboard_course_learned_lesson_count_map(
            follow_up.bid, [follow_up.bid], [follow_up.bid]
        ) == {follow_up.bid: 1}
        assert dashboard._load_dashboard_course_follow_up_count_map(
            follow_up.bid, [follow_up.bid]
        ) == {follow_up.bid: 1}
        assert (
            dashboard._load_dashboard_course_last_learning_map(follow_up.bid, []) == {}
        )
        assert (
            dashboard._load_dashboard_course_follow_up_count_map(follow_up.bid, [])
            == {}
        )


@pytest.mark.parametrize(
    "resource", ["follow-ups", "ratings", "learners", "detail", "follow-up-detail"]
)
def test_dashboard_resources_reject_missing_course_identity(
    app: object, follow_up: object, resource: str
) -> None:
    loaders = {
        "follow-ups": lambda: dashboard.build_dashboard_course_follow_ups(
            app, follow_up.owner, ""
        ),
        "ratings": lambda: dashboard.build_dashboard_course_ratings(
            app, follow_up.owner, ""
        ),
        "learners": lambda: dashboard.build_dashboard_course_learners(
            app, follow_up.owner, ""
        ),
        "detail": lambda: dashboard.build_dashboard_course_detail(
            app, follow_up.owner, ""
        ),
        "follow-up-detail": lambda: dashboard.build_dashboard_course_follow_up_detail(
            app, follow_up.owner, follow_up.bid, ""
        ),
    }
    with pytest.raises(AppError):
        loaders[resource]()
