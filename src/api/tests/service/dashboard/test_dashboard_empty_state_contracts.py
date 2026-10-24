"""Preserve dashboard access boundaries and totals when filters match nothing."""

import uuid
from datetime import timedelta

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.dashboard import funcs as dashboard
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_COMPLETED
from flaskr.service.shifu.models import PublishedOutlineItem, PublishedShifu
from flaskr.service.user.models import AuthCredential, UserInfo

from . import test_dashboard_query_contracts as queries

follow_up = queries.follow_up


@pytest.mark.parametrize("resource", ["follow-ups", "ratings", "learners", "detail"])
def test_existing_course_data_cannot_be_read_by_an_unrelated_teacher(
    app: object,
    follow_up: object,
    resource: str,
) -> None:
    loaders = {
        "follow-ups": dashboard.build_dashboard_course_follow_ups,
        "ratings": dashboard.build_dashboard_course_ratings,
        "learners": dashboard.build_dashboard_course_learners,
        "detail": dashboard.build_dashboard_course_detail,
    }
    with pytest.raises(AppError) as error:
        loaders[resource](app, uuid.uuid4().hex, follow_up.bid)
    assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]


@pytest.mark.parametrize("course", ["", " "])
def test_follow_up_detail_rejects_missing_course_even_when_question_exists(
    app: object,
    follow_up: object,
    course: str,
) -> None:
    with pytest.raises(AppError):
        dashboard.build_dashboard_course_follow_up_detail(
            app, follow_up.owner, course, follow_up.ask_bid
        )


@pytest.mark.parametrize("missing", ["unknown", "answer", "orphan"])
def test_follow_up_detail_requires_an_active_question_in_a_valid_progress_group(
    app: object,
    follow_up: object,
    missing: str,
) -> None:
    bid = follow_up.ask_bid
    if missing == "orphan":
        with app.app_context(), unit_of_work():
            LearnGeneratedBlock.query.filter_by(generated_block_bid=bid).update(
                {"progress_record_bid": ""}
            )
    elif missing == "answer":
        bid = follow_up.answer_bid
    else:
        bid = uuid.uuid4().hex
    with pytest.raises(AppError):
        dashboard.build_dashboard_course_follow_up_detail(
            app, follow_up.owner, follow_up.bid, bid
        )


def test_empty_entry_keeps_pagination_and_zero_totals_without_matching_courses(
    app: object,
    follow_up: object,
) -> None:
    result = dashboard.build_dashboard_entry(
        app,
        follow_up.owner,
        keyword="absent-course",
        start_date=" ",
        end_date="",
        page_index=-1,
        page_size=999,
    )
    assert result.items == []
    assert (result.page, result.page_size, result.total, result.page_count) == (
        1,
        100,
        0,
        0,
    )
    assert result.summary.__json__() == {
        "course_count": 0,
        "learner_count": 0,
        "order_count": 0,
        "order_amount": "0.00",
    }
    assert dashboard.build_dashboard_entry(app, uuid.uuid4().hex).total == 0


def test_rating_filters_preserve_course_summary_after_all_rows_are_filtered_out(
    app: object,
    follow_up: object,
) -> None:
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnLessonFeedback(
                bid=uuid.uuid4().hex,
                lesson_feedback_bid=uuid.uuid4().hex,
                shifu_bid=follow_up.bid,
                outline_item_bid=follow_up.bid,
                user_bid=follow_up.bid,
                score=4,
                comment="Helpful",
                deleted=0,
            )
        )
    try:
        for filters in (
            {"chapter_keyword": "absent-chapter"},
            {"keyword": "absent-learner"},
            {"score": "1"},
        ):
            result = dashboard.build_dashboard_course_ratings(
                app, follow_up.owner, follow_up.bid, **filters
            )
            assert result.items == []
            assert result.total == result.page_count == 0
            assert result.summary.rating_count == result.summary.user_count == 1
            assert str(result.summary.average_score).startswith("4")
    finally:
        with app.app_context(), unit_of_work():
            LearnLessonFeedback.query.filter_by(shifu_bid=follow_up.bid).delete()


def test_legacy_phone_identity_is_used_only_until_a_phone_credential_exists(
    app: object,
    follow_up: object,
) -> None:
    with app.app_context(), unit_of_work():
        UserInfo.query.filter_by(user_bid=follow_up.bid).update(
            {"user_identify": "13800138000"}
        )
    with app.app_context():
        assert (
            dashboard._load_dashboard_course_user_contact_map([follow_up.bid])[
                follow_up.bid
            ]["mobile"]
            == "13800138000"
        )
        with unit_of_work():
            db.session.add(
                AuthCredential(
                    credential_bid=uuid.uuid4().hex,
                    user_bid=follow_up.bid,
                    provider_name="phone",
                    identifier="13900139000",
                    deleted=0,
                )
            )
        assert (
            dashboard._load_dashboard_course_user_contact_map([follow_up.bid])[
                follow_up.bid
            ]["mobile"]
            == "13900139000"
        )


def test_published_only_course_uses_earliest_release_time_and_ignores_deleted_releases_for_status(
    app: object,
    follow_up: object,
) -> None:
    earlier = follow_up.stamp - timedelta(days=30)
    with app.app_context(), unit_of_work():
        db.session.add(
            PublishedShifu(
                shifu_bid=follow_up.bid,
                title="Old release",
                created_user_bid=follow_up.owner,
                created_at=earlier,
                deleted=1,
            )
        )
    with app.app_context():
        assert dashboard._load_dashboard_course_created_at(follow_up.bid) == earlier
        assert dashboard._resolve_dashboard_course_status(follow_up.bid) == "published"
        with unit_of_work():
            PublishedShifu.query.filter_by(shifu_bid=follow_up.bid).update(
                {"deleted": 1}
            )
        assert (
            dashboard._resolve_dashboard_course_status(follow_up.bid) == "unpublished"
        )


def test_hidden_only_course_has_no_completed_learners_or_exposed_lesson_details(
    app: object,
    follow_up: object,
) -> None:
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=follow_up.bid,
                user_bid=follow_up.bid,
                shifu_bid=follow_up.bid,
                outline_item_bid=follow_up.bid,
                status=LEARN_STATUS_COMPLETED,
                deleted=0,
            )
        )
    before = dashboard.build_dashboard_course_learners(
        app, follow_up.owner, follow_up.bid
    )
    assert [(item.user_bid, item.learning_status) for item in before.items] == [
        (follow_up.bid, "completed")
    ]
    with app.app_context(), unit_of_work():
        PublishedOutlineItem.query.filter_by(shifu_bid=follow_up.bid).update(
            {"hidden": 1}
        )
    result = dashboard.build_dashboard_course_learners(
        app, follow_up.owner, follow_up.bid
    )
    assert [(item.user_bid, item.learning_status) for item in result.items] == [
        (follow_up.bid, "not_started")
    ]
    assert (
        dashboard.build_dashboard_course_learners(
            app, follow_up.owner, follow_up.bid, learning_status="completed"
        ).total
        == 0
    )
