from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from flask import Flask

from flaskr.dao import db
from flaskr.service.shifu import admin as admin_module
from flaskr.service.shifu.admin import (
    _load_course_activity_map,
    _load_latest_shifus,
    _build_operator_course_overview,
    list_operator_courses,
)
from flaskr.service.learn.const import LEARN_STATUS_COMPLETED
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import ORDER_STATUS_INIT, ORDER_STATUS_SUCCESS
from flaskr.service.order.models import Order
from flaskr.service.shifu.admin_dtos import (
    AdminOperationCourseListDTO,
    AdminOperationCourseOverviewDTO,
    AdminOperationCourseSummaryDTO,
)
from flaskr.service.shifu.models import PublishedShifu
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu


EMPTY_COURSE_OVERVIEW = AdminOperationCourseOverviewDTO()


class DummyCourse:
    def __init__(
        self,
        *,
        shifu_bid: str,
        title: str,
        price: str,
        created_user_bid: str,
        updated_user_bid: str,
        created_at: datetime,
        updated_at: datetime,
        llm: str = "",
        llm_system_prompt: str = "",
    ):
        self.shifu_bid = shifu_bid
        self.title = title
        self.price = price
        self.llm = llm
        self.llm_system_prompt = llm_system_prompt
        self.has_course_prompt = bool(str(llm_system_prompt or "").strip())
        self.created_user_bid = created_user_bid
        self.updated_user_bid = updated_user_bid
        self.created_at = created_at
        self.updated_at = updated_at


def test_list_operator_courses_prefers_latest_draft_and_formats_contacts():
    app = Flask(__name__)
    updated_start_time = datetime(2025, 4, 2, 0, 0, 0)
    updated_end_time = datetime(2025, 4, 3, 23, 59, 59)
    draft_course = DummyCourse(
        shifu_bid="course-1",
        title="Draft Course",
        price="199.00",
        created_user_bid="creator-1",
        updated_user_bid="editor-1",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 3, 10, 0, 0),
        llm="gpt-4.1-mini",
        llm_system_prompt="You are a patient course assistant.",
    )
    published_course = DummyCourse(
        shifu_bid="course-1",
        title="Published Course",
        price="99.00",
        created_user_bid="creator-1",
        updated_user_bid="editor-1",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 2, 10, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._find_matching_creator_bids"
    ) as creator_mock:
        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            with patch(
                "flaskr.service.shifu.admin._load_course_activity_map"
            ) as activity_mock:
                with patch(
                    "flaskr.service.shifu.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.shifu.admin._build_operator_course_overview",
                        return_value=EMPTY_COURSE_OVERVIEW,
                    ):
                        creator_mock.return_value = {"creator-1"}
                        latest_mock.side_effect = [[draft_course], [published_course]]
                        activity_mock.return_value = {}
                        user_map_mock.return_value = {
                            "creator-1": {
                                "mobile": "15811112222",
                                "email": "creator@example.com",
                                "nickname": "Creator Mars",
                            },
                            "editor-1": {
                                "mobile": "15833334444",
                                "email": "editor@example.com",
                                "nickname": "Editor Venus",
                            },
                        }

                        result = list_operator_courses(
                            app,
                            1,
                            20,
                            {
                                "course_name": "Draft",
                                "creator_keyword": "creator@example.com",
                                "updated_start_time": updated_start_time,
                                "updated_end_time": updated_end_time,
                            },
                        )

    assert isinstance(result, AdminOperationCourseListDTO)
    assert result.total == 1
    assert len(result.items) == 1
    item = result.items[0]
    assert isinstance(item, AdminOperationCourseSummaryDTO)
    assert item.shifu_bid == "course-1"
    assert item.course_name == "Draft Course"
    assert item.course_status == "published"
    assert item.price == "199"
    assert item.course_model == "gpt-4.1-mini"
    assert item.has_course_prompt is True
    assert item.creator_mobile == "15811112222"
    assert item.creator_email == "creator@example.com"
    assert item.creator_nickname == "Creator Mars"
    assert item.updater_email == "editor@example.com"
    assert item.updater_nickname == "Editor Venus"
    assert latest_mock.call_args_list[0].kwargs["updated_start_time"] is None
    assert latest_mock.call_args_list[0].kwargs["updated_end_time"] is None
    assert latest_mock.call_args_list[1].kwargs["updated_start_time"] is None
    assert latest_mock.call_args_list[1].kwargs["updated_end_time"] is None


def test_list_operator_courses_paginates_merged_results():
    app = Flask(__name__)
    draft_course = DummyCourse(
        shifu_bid="course-2",
        title="Draft Course 2",
        price="29.00",
        created_user_bid="creator-2",
        updated_user_bid="creator-2",
        created_at=datetime(2025, 4, 2, 10, 0, 0),
        updated_at=datetime(2025, 4, 4, 10, 0, 0),
    )
    published_only_course = DummyCourse(
        shifu_bid="course-1",
        title="Published Only",
        price="59.00",
        created_user_bid="creator-1",
        updated_user_bid="creator-1",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 3, 10, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._find_matching_creator_bids"
    ) as creator_mock:
        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            with patch(
                "flaskr.service.shifu.admin._load_course_activity_map"
            ) as activity_mock:
                with patch(
                    "flaskr.service.shifu.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.shifu.admin._build_operator_course_overview",
                        return_value=EMPTY_COURSE_OVERVIEW,
                    ):
                        creator_mock.return_value = None
                        latest_mock.side_effect = [
                            [draft_course],
                            [published_only_course],
                        ]
                        activity_mock.return_value = {}
                        user_map_mock.return_value = {
                            "creator-1": {
                                "mobile": "",
                                "email": "creator-1@example.com",
                                "nickname": "",
                            },
                            "creator-2": {
                                "mobile": "",
                                "email": "creator-2@example.com",
                                "nickname": "",
                            },
                        }

                        result = list_operator_courses(app, 2, 1, {})

    assert result.total == 2
    assert len(result.items) == 1
    assert result.items[0].shifu_bid == "course-1"


def test_list_operator_courses_uses_latest_activity_for_updater_and_updated_at():
    app = Flask(__name__)
    draft_course = DummyCourse(
        shifu_bid="course-activity",
        title="Course Activity",
        price="39.00",
        created_user_bid="creator-1",
        updated_user_bid="creator-1",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 2, 10, 0, 0),
    )
    older_course = DummyCourse(
        shifu_bid="course-older",
        title="Course Older",
        price="29.00",
        created_user_bid="creator-2",
        updated_user_bid="creator-2",
        created_at=datetime(2025, 4, 1, 11, 0, 0),
        updated_at=datetime(2025, 4, 3, 10, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._find_matching_creator_bids"
    ) as creator_mock:
        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            with patch(
                "flaskr.service.shifu.admin._load_course_activity_map"
            ) as activity_mock:
                with patch(
                    "flaskr.service.shifu.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.shifu.admin._build_operator_course_overview",
                        return_value=EMPTY_COURSE_OVERVIEW,
                    ):
                        creator_mock.return_value = None
                        latest_mock.side_effect = [[draft_course, older_course], []]
                        activity_mock.return_value = {
                            "course-activity": {
                                "updated_at": datetime(2025, 4, 5, 9, 0, 0),
                                "updated_user_bid": "editor-9",
                            }
                        }
                        user_map_mock.return_value = {
                            "creator-1": {
                                "mobile": "15811112222",
                                "email": "creator-1@example.com",
                                "nickname": "Creator One",
                            },
                            "creator-2": {
                                "mobile": "15822223333",
                                "email": "creator-2@example.com",
                                "nickname": "Creator Two",
                            },
                            "editor-9": {
                                "mobile": "13223532334",
                                "email": "editor-9@example.com",
                                "nickname": "Editor Nine",
                            },
                        }

                        result = list_operator_courses(app, 1, 20, {})

    assert [item.shifu_bid for item in result.items] == [
        "course-activity",
        "course-older",
    ]
    assert result.items[0].updater_user_bid == "editor-9"
    assert result.items[0].updater_mobile == "13223532334"
    assert result.items[0].updater_nickname == "Editor Nine"
    assert result.items[0].updated_at == "2025-04-05T09:00:00Z"


def test_list_operator_courses_filters_by_latest_activity_updated_range():
    app = Flask(__name__)
    draft_course = DummyCourse(
        shifu_bid="course-activity-filter",
        title="Course Activity Filter",
        price="39.00",
        created_user_bid="creator-1",
        updated_user_bid="creator-1",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 2, 10, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._find_matching_creator_bids"
    ) as creator_mock:
        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            with patch(
                "flaskr.service.shifu.admin._load_course_activity_map"
            ) as activity_mock:
                with patch(
                    "flaskr.service.shifu.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.shifu.admin._build_operator_course_overview",
                        return_value=EMPTY_COURSE_OVERVIEW,
                    ):
                        creator_mock.return_value = None
                        latest_mock.side_effect = [[draft_course], []]
                        activity_mock.return_value = {
                            "course-activity-filter": {
                                "updated_at": datetime(2025, 4, 5, 9, 0, 0),
                                "updated_user_bid": "editor-9",
                            }
                        }
                        user_map_mock.return_value = {
                            "creator-1": {
                                "mobile": "15811112222",
                                "email": "creator-1@example.com",
                                "nickname": "Creator One",
                            },
                            "editor-9": {
                                "mobile": "13223532334",
                                "email": "editor-9@example.com",
                                "nickname": "Editor Nine",
                            },
                        }

                        result = list_operator_courses(
                            app,
                            1,
                            20,
                            {
                                "updated_start_time": datetime(2025, 4, 5, 0, 0, 0),
                                "updated_end_time": datetime(2025, 4, 5, 23, 59, 59),
                            },
                        )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].shifu_bid == "course-activity-filter"
    assert result.items[0].updated_at == "2025-04-05T09:00:00Z"
    assert latest_mock.call_args_list[0].kwargs["updated_start_time"] is None
    assert latest_mock.call_args_list[0].kwargs["updated_end_time"] is None


def test_load_course_activity_map_prefers_latest_outline_activity_row(app):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]

    with app.app_context():
        draft_course = DraftShifu(
            shifu_bid=shifu_bid,
            title="Outline Activity Course",
            description="desc",
            avatar_res_bid="",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("0"),
            created_user_bid=creator_bid,
            updated_user_bid=creator_bid,
            updated_at=datetime(2025, 4, 2, 10, 0, 0),
        )
        db.session.add(draft_course)
        db.session.flush()

        db.session.add_all(
            [
                DraftOutlineItem(
                    outline_item_bid=uuid.uuid4().hex[:32],
                    shifu_bid=shifu_bid,
                    title="First",
                    parent_bid="",
                    position="1",
                    created_user_bid=creator_bid,
                    updated_user_bid="editor-1",
                    updated_at=datetime(2025, 4, 4, 10, 0, 0),
                ),
                DraftOutlineItem(
                    outline_item_bid=uuid.uuid4().hex[:32],
                    shifu_bid=shifu_bid,
                    title="Second",
                    parent_bid="",
                    position="2",
                    created_user_bid=creator_bid,
                    updated_user_bid="editor-2",
                    updated_at=datetime(2025, 4, 5, 10, 0, 0),
                ),
            ]
        )
        db.session.commit()

        activity_map = _load_course_activity_map([draft_course], [])

    assert activity_map[shifu_bid]["updated_user_bid"] == "editor-2"
    assert activity_map[shifu_bid]["updated_at"] == datetime(2025, 4, 5, 10, 0, 0)


def test_load_course_activity_map_prefers_outline_when_timestamp_ties_course(app):
    shifu_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    shared_updated_at = datetime(2025, 4, 5, 10, 0, 0)

    with app.app_context():
        draft_course = DraftShifu(
            shifu_bid=shifu_bid,
            title="Outline Tie Course",
            description="desc",
            avatar_res_bid="",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("0"),
            created_user_bid=creator_bid,
            updated_user_bid="course-editor",
            updated_at=shared_updated_at,
        )
        db.session.add(draft_course)
        db.session.flush()

        db.session.add(
            DraftOutlineItem(
                outline_item_bid=uuid.uuid4().hex[:32],
                shifu_bid=shifu_bid,
                title="Outline Tie",
                parent_bid="",
                position="1",
                created_user_bid=creator_bid,
                updated_user_bid="outline-editor",
                updated_at=shared_updated_at,
            )
        )
        db.session.commit()

        activity_map = _load_course_activity_map([draft_course], [])

    assert activity_map[shifu_bid]["updated_user_bid"] == "outline-editor"
    assert activity_map[shifu_bid]["updated_at"] == shared_updated_at


def test_list_operator_courses_filters_out_builtin_demo_courses_only():
    app = Flask(__name__)
    builtin_demo_course = DummyCourse(
        shifu_bid="course-system",
        title="AI-Shifu Creation Guide",
        price="0.00",
        created_user_bid="system",
        updated_user_bid="system",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 4, 10, 0, 0),
    )
    system_custom_course = DummyCourse(
        shifu_bid="course-system-custom",
        title="Custom System Course",
        price="39.00",
        created_user_bid="system",
        updated_user_bid="system",
        created_at=datetime(2025, 4, 1, 11, 0, 0),
        updated_at=datetime(2025, 4, 4, 11, 0, 0),
    )
    normal_course = DummyCourse(
        shifu_bid="course-1",
        title="Normal Course",
        price="59.00",
        created_user_bid="creator-1",
        updated_user_bid="editor-1",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 3, 10, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._find_matching_creator_bids"
    ) as creator_mock:
        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            with patch(
                "flaskr.service.shifu.admin._load_course_activity_map"
            ) as activity_mock:
                with patch(
                    "flaskr.service.shifu.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.shifu.admin._build_operator_course_overview",
                        return_value=EMPTY_COURSE_OVERVIEW,
                    ):
                        creator_mock.return_value = None
                        latest_mock.side_effect = [
                            [builtin_demo_course, system_custom_course],
                            [normal_course],
                        ]
                        activity_mock.return_value = {}
                        user_map_mock.return_value = {
                            "creator-1": {
                                "mobile": "15811112222",
                                "email": "creator@example.com",
                                "nickname": "Creator Mars",
                            },
                            "editor-1": {
                                "mobile": "15833334444",
                                "email": "editor@example.com",
                                "nickname": "Editor Venus",
                            },
                        }

                        result = list_operator_courses(app, 1, 20, {})

    assert result.total == 2
    assert len(result.items) == 2
    assert {item.shifu_bid for item in result.items} == {
        "course-1",
        "course-system-custom",
    }


def test_list_operator_courses_skips_system_user_lookup():
    app = Flask(__name__)
    system_course = DummyCourse(
        shifu_bid="course-system-custom",
        title="Custom System Course",
        price="39.00",
        created_user_bid="system",
        updated_user_bid="system",
        created_at=datetime(2025, 4, 1, 11, 0, 0),
        updated_at=datetime(2025, 4, 4, 11, 0, 0),
    )
    normal_course = DummyCourse(
        shifu_bid="course-1",
        title="Normal Course",
        price="59.00",
        created_user_bid="creator-1",
        updated_user_bid="editor-1",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 3, 10, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._find_matching_creator_bids"
    ) as creator_mock:
        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            with patch(
                "flaskr.service.shifu.admin._load_course_activity_map"
            ) as activity_mock:
                with patch(
                    "flaskr.service.shifu.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.shifu.admin._build_operator_course_overview",
                        return_value=EMPTY_COURSE_OVERVIEW,
                    ):
                        creator_mock.return_value = None
                        latest_mock.side_effect = [[system_course], [normal_course]]
                        activity_mock.return_value = {}
                        user_map_mock.return_value = {
                            "creator-1": {
                                "mobile": "15811112222",
                                "email": "creator@example.com",
                                "nickname": "Creator Mars",
                            },
                            "editor-1": {
                                "mobile": "15833334444",
                                "email": "editor@example.com",
                                "nickname": "Editor Venus",
                            },
                        }

                        list_operator_courses(app, 1, 20, {})

    assert set(user_map_mock.call_args.args[0]) == {"creator-1", "editor-1"}
    assert "system" not in user_map_mock.call_args.args[0]


def test_list_operator_courses_filters_by_course_status():
    app = Flask(__name__)
    draft_only_course = DummyCourse(
        shifu_bid="course-draft-only",
        title="Draft Only",
        price="39.00",
        created_user_bid="creator-1",
        updated_user_bid="creator-1",
        created_at=datetime(2025, 4, 1, 9, 0, 0),
        updated_at=datetime(2025, 4, 2, 9, 0, 0),
    )
    published_course = DummyCourse(
        shifu_bid="course-published",
        title="Published Course",
        price="59.00",
        created_user_bid="creator-2",
        updated_user_bid="creator-2",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 2, 10, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._find_matching_creator_bids"
    ) as creator_mock:
        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            with patch(
                "flaskr.service.shifu.admin._load_course_activity_map"
            ) as activity_mock:
                with patch(
                    "flaskr.service.shifu.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.shifu.admin._build_operator_course_overview",
                        return_value=EMPTY_COURSE_OVERVIEW,
                    ):
                        creator_mock.return_value = None
                        latest_mock.side_effect = lambda model, **kwargs: (
                            [draft_only_course]
                            if model.__name__ == "DraftShifu"
                            else [published_course]
                        )
                        activity_mock.return_value = {}
                        user_map_mock.return_value = {
                            "creator-1": {
                                "mobile": "",
                                "email": "creator-1@example.com",
                                "nickname": "",
                            },
                            "creator-2": {
                                "mobile": "",
                                "email": "creator-2@example.com",
                                "nickname": "",
                            },
                        }

                        unpublished_result = list_operator_courses(
                            app, 1, 20, {"course_status": "unpublished"}
                        )
                        published_result = list_operator_courses(
                            app, 1, 20, {"course_status": "published"}
                        )

    assert [item.shifu_bid for item in unpublished_result.items] == [
        "course-draft-only"
    ]
    assert unpublished_result.items[0].course_status == "unpublished"
    assert [item.shifu_bid for item in published_result.items] == ["course-published"]
    assert published_result.items[0].course_status == "published"


def test_list_operator_courses_applies_quick_filters(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 5, 1, 12, 0, 0)

    monkeypatch.setattr(admin_module, "datetime", FixedDateTime)

    app = Flask(__name__)
    recent_course = DummyCourse(
        shifu_bid="course-recent",
        title="Recent Course",
        price="39.00",
        created_user_bid="creator-1",
        updated_user_bid="creator-1",
        created_at=datetime(2025, 4, 30, 9, 0, 0),
        updated_at=datetime(2025, 4, 30, 9, 0, 0),
    )
    paid_course = DummyCourse(
        shifu_bid="course-paid",
        title="Paid Course",
        price="59.00",
        created_user_bid="creator-2",
        updated_user_bid="creator-2",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 2, 10, 0, 0),
    )
    learning_course = DummyCourse(
        shifu_bid="course-learning",
        title="Learning Course",
        price="29.00",
        created_user_bid="creator-3",
        updated_user_bid="creator-3",
        created_at=datetime(2025, 3, 20, 10, 0, 0),
        updated_at=datetime(2025, 4, 2, 10, 0, 0),
    )
    rolling_window_only_course = DummyCourse(
        shifu_bid="course-rolling-window-only",
        title="Rolling Window Only Course",
        price="19.00",
        created_user_bid="creator-4",
        updated_user_bid="creator-4",
        created_at=datetime(2025, 4, 24, 18, 0, 0),
        updated_at=datetime(2025, 4, 24, 18, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._find_matching_creator_bids"
    ) as creator_mock:
        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            with patch(
                "flaskr.service.shifu.admin._load_course_activity_map"
            ) as activity_mock:
                with patch(
                    "flaskr.service.shifu.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.shifu.admin._load_recent_learning_active_course_bids"
                    ) as learning_mock:
                        with patch(
                            "flaskr.service.shifu.admin._load_recent_paid_order_course_bids"
                        ) as paid_mock:
                            with patch(
                                "flaskr.service.shifu.admin._build_operator_course_overview",
                                return_value=EMPTY_COURSE_OVERVIEW,
                            ):
                                creator_mock.return_value = None
                                latest_mock.side_effect = lambda model, **kwargs: (
                                    [
                                        recent_course,
                                        paid_course,
                                        learning_course,
                                        rolling_window_only_course,
                                    ]
                                    if model.__name__ == "DraftShifu"
                                    else []
                                )
                                activity_mock.return_value = {}
                                user_map_mock.return_value = {
                                    "creator-1": {
                                        "mobile": "",
                                        "email": "creator-1@example.com",
                                        "nickname": "",
                                    },
                                    "creator-2": {
                                        "mobile": "",
                                        "email": "creator-2@example.com",
                                        "nickname": "",
                                    },
                                    "creator-3": {
                                        "mobile": "",
                                        "email": "creator-3@example.com",
                                        "nickname": "",
                                    },
                                    "creator-4": {
                                        "mobile": "",
                                        "email": "creator-4@example.com",
                                        "nickname": "",
                                    },
                                }
                                learning_mock.return_value = {"course-learning"}
                                paid_mock.return_value = {"course-paid"}

                                created_result = list_operator_courses(
                                    app, 1, 20, {"quick_filter": "created_last_7d"}
                                )
                                learning_result = list_operator_courses(
                                    app, 1, 20, {"quick_filter": "learning_active_30d"}
                                )
                                paid_result = list_operator_courses(
                                    app, 1, 20, {"quick_filter": "paid_order_30d"}
                                )

    assert [item.shifu_bid for item in created_result.items] == ["course-recent"]
    assert [item.shifu_bid for item in learning_result.items] == ["course-learning"]
    assert [item.shifu_bid for item in paid_result.items] == ["course-paid"]


def test_build_operator_course_overview_returns_expected_counts(app, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 5, 1, 12, 0, 0)

    monkeypatch.setattr(admin_module, "datetime", FixedDateTime)

    draft_only_bid = uuid.uuid4().hex[:32]
    published_only_bid = uuid.uuid4().hex[:32]
    published_with_draft_bid = uuid.uuid4().hex[:32]
    builtin_demo_bid = uuid.uuid4().hex[:32]
    creator_bid = uuid.uuid4().hex[:32]
    user_bid = uuid.uuid4().hex[:32]

    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=draft_only_bid,
                    title="Draft Only Course",
                    description="desc",
                    avatar_res_bid="",
                    keywords="",
                    llm="gpt-test",
                    llm_temperature=Decimal("0"),
                    llm_system_prompt="",
                    price=Decimal("0"),
                    created_user_bid=creator_bid,
                    updated_user_bid=creator_bid,
                    created_at=datetime(2025, 4, 28, 9, 0, 0),
                    updated_at=datetime(2025, 4, 28, 9, 0, 0),
                ),
                DraftShifu(
                    shifu_bid=published_with_draft_bid,
                    title="Published Draft Course",
                    description="desc",
                    avatar_res_bid="",
                    keywords="",
                    llm="gpt-test",
                    llm_temperature=Decimal("0"),
                    llm_system_prompt="Prompt",
                    price=Decimal("99"),
                    created_user_bid=creator_bid,
                    updated_user_bid=creator_bid,
                    created_at=datetime(2025, 4, 30, 9, 0, 0),
                    updated_at=datetime(2025, 4, 30, 9, 0, 0),
                ),
                DraftShifu(
                    shifu_bid=builtin_demo_bid,
                    title="AI-Shifu Creation Guide",
                    description="desc",
                    avatar_res_bid="",
                    keywords="",
                    llm="gpt-test",
                    llm_temperature=Decimal("0"),
                    llm_system_prompt="",
                    price=Decimal("0"),
                    created_user_bid="system",
                    updated_user_bid="system",
                    created_at=datetime(2025, 4, 29, 9, 0, 0),
                    updated_at=datetime(2025, 4, 29, 9, 0, 0),
                ),
                PublishedShifu(
                    shifu_bid=published_only_bid,
                    title="Published Only Course",
                    description="desc",
                    avatar_res_bid="",
                    keywords="",
                    llm="gpt-test",
                    llm_temperature=Decimal("0"),
                    llm_system_prompt="",
                    price=Decimal("49"),
                    created_user_bid=creator_bid,
                    updated_user_bid=creator_bid,
                    created_at=datetime(2025, 4, 15, 9, 0, 0),
                    updated_at=datetime(2025, 4, 15, 9, 0, 0),
                ),
                PublishedShifu(
                    shifu_bid=published_with_draft_bid,
                    title="Published Draft Course",
                    description="desc",
                    avatar_res_bid="",
                    keywords="",
                    llm="gpt-test",
                    llm_temperature=Decimal("0"),
                    llm_system_prompt="",
                    price=Decimal("79"),
                    created_user_bid=creator_bid,
                    updated_user_bid=creator_bid,
                    created_at=datetime(2025, 4, 20, 9, 0, 0),
                    updated_at=datetime(2025, 4, 20, 9, 0, 0),
                ),
            ]
        )
        db.session.flush()

        db.session.add_all(
            [
                LearnProgressRecord(
                    progress_record_bid=uuid.uuid4().hex[:32],
                    shifu_bid=published_only_bid,
                    outline_item_bid=uuid.uuid4().hex[:32],
                    user_bid=user_bid,
                    status=LEARN_STATUS_COMPLETED,
                    created_at=datetime(2025, 4, 20, 10, 0, 0),
                    updated_at=datetime(2025, 4, 20, 10, 0, 0),
                ),
                LearnProgressRecord(
                    progress_record_bid=uuid.uuid4().hex[:32],
                    shifu_bid=published_with_draft_bid,
                    outline_item_bid=uuid.uuid4().hex[:32],
                    user_bid=user_bid,
                    status=LEARN_STATUS_COMPLETED,
                    created_at=datetime(2025, 4, 29, 10, 0, 0),
                    updated_at=datetime(2025, 4, 29, 10, 0, 0),
                ),
                LearnProgressRecord(
                    progress_record_bid=uuid.uuid4().hex[:32],
                    shifu_bid=draft_only_bid,
                    outline_item_bid=uuid.uuid4().hex[:32],
                    user_bid=user_bid,
                    status=LEARN_STATUS_COMPLETED,
                    created_at=datetime(2025, 3, 15, 10, 0, 0),
                    updated_at=datetime(2025, 3, 15, 10, 0, 0),
                ),
                LearnProgressRecord(
                    progress_record_bid=uuid.uuid4().hex[:32],
                    shifu_bid=builtin_demo_bid,
                    outline_item_bid=uuid.uuid4().hex[:32],
                    user_bid=user_bid,
                    status=LEARN_STATUS_COMPLETED,
                    created_at=datetime(2025, 4, 28, 10, 0, 0),
                    updated_at=datetime(2025, 4, 28, 10, 0, 0),
                ),
                Order(
                    order_bid=uuid.uuid4().hex[:32],
                    shifu_bid=draft_only_bid,
                    user_bid=user_bid,
                    payable_price=Decimal("19"),
                    paid_price=Decimal("19"),
                    status=ORDER_STATUS_SUCCESS,
                    created_at=datetime(2025, 4, 25, 10, 0, 0),
                    updated_at=datetime(2025, 4, 25, 10, 0, 0),
                ),
                Order(
                    order_bid=uuid.uuid4().hex[:32],
                    shifu_bid=published_with_draft_bid,
                    user_bid=user_bid,
                    payable_price=Decimal("29"),
                    paid_price=Decimal("29"),
                    status=ORDER_STATUS_SUCCESS,
                    created_at=datetime(2025, 4, 29, 10, 0, 0),
                    updated_at=datetime(2025, 4, 29, 10, 0, 0),
                ),
                Order(
                    order_bid=uuid.uuid4().hex[:32],
                    shifu_bid=published_only_bid,
                    user_bid=user_bid,
                    payable_price=Decimal("39"),
                    paid_price=Decimal("0"),
                    status=ORDER_STATUS_INIT,
                    created_at=datetime(2025, 4, 29, 10, 0, 0),
                    updated_at=datetime(2025, 4, 29, 10, 0, 0),
                ),
                Order(
                    order_bid=uuid.uuid4().hex[:32],
                    shifu_bid=builtin_demo_bid,
                    user_bid=user_bid,
                    payable_price=Decimal("0"),
                    paid_price=Decimal("0"),
                    status=ORDER_STATUS_SUCCESS,
                    created_at=datetime(2025, 4, 29, 10, 0, 0),
                    updated_at=datetime(2025, 4, 29, 10, 0, 0),
                ),
            ]
        )
        db.session.commit()
        draft_rows = (
            DraftShifu.query.filter(
                DraftShifu.shifu_bid.in_(
                    [
                        draft_only_bid,
                        published_with_draft_bid,
                        builtin_demo_bid,
                    ]
                )
            )
            .order_by(DraftShifu.id.asc())
            .all()
        )
        published_rows = (
            PublishedShifu.query.filter(
                PublishedShifu.shifu_bid.in_(
                    [published_only_bid, published_with_draft_bid]
                )
            )
            .order_by(PublishedShifu.id.asc())
            .all()
        )

        with patch("flaskr.service.shifu.admin._load_latest_shifus") as latest_mock:
            latest_mock.side_effect = [draft_rows, published_rows]
            summary = _build_operator_course_overview(app)

    assert summary.total_course_count == 3
    assert summary.draft_course_count == 1
    assert summary.published_course_count == 2
    assert summary.created_last_7d_course_count == 2
    assert summary.learning_active_30d_course_count == 2
    assert summary.paid_order_30d_course_count == 2


def test_merge_courses_checks_published_visibility_once():
    draft_course = DummyCourse(
        shifu_bid="course-draft",
        title="Draft Course",
        price="19.00",
        created_user_bid="creator-1",
        updated_user_bid="creator-1",
        created_at=datetime(2025, 4, 1, 10, 0, 0),
        updated_at=datetime(2025, 4, 2, 10, 0, 0),
    )
    published_course = DummyCourse(
        shifu_bid="course-published",
        title="Published Course",
        price="29.00",
        created_user_bid="creator-2",
        updated_user_bid="creator-2",
        created_at=datetime(2025, 4, 1, 11, 0, 0),
        updated_at=datetime(2025, 4, 2, 11, 0, 0),
    )

    with patch(
        "flaskr.service.shifu.admin._is_operator_visible_course",
        side_effect=[True, True],
    ) as visible_mock:
        merged_courses, published_bids = admin_module._merge_courses(
            [draft_course], [published_course]
        )

    assert visible_mock.call_count == 2
    assert [course.shifu_bid for course in merged_courses] == [
        "course-published",
        "course-draft",
    ]
    assert published_bids == {"course-published"}


class FakeColumn:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def __ge__(self, other):
        return ("ge", self.name, other)

    def __le__(self, other):
        return ("le", self.name, other)

    def ilike(self, value: str):
        return ("ilike", self.name, value)

    def in_(self, value):
        return ("in", self.name, value)

    def desc(self):
        return ("desc", self.name)

    def label(self, alias: str):
        return ("label", self.name, alias)


class FakeMaxExpression:
    def __init__(self, column: FakeColumn):
        self.column = column

    def label(self, alias: str):
        return ("max", self.column.name, alias)


class FakeLatestSubquery:
    def __init__(self):
        self.c = type("Columns", (), {"max_id": "latest-max-id"})()


class FakeLatestQuery:
    def __init__(self):
        self.filters = []
        self.grouped_by = []
        self.subquery_value = FakeLatestSubquery()

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def group_by(self, *columns):
        self.grouped_by.extend(columns)
        return self

    def subquery(self):
        return self.subquery_value


class FakeIdQuery:
    def __init__(self, target):
        self.target = target


class FakeOuterQuery:
    def __init__(self, result):
        self.filters = []
        self.ordering = []
        self.result = result

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def order_by(self, *ordering):
        self.ordering.extend(ordering)
        return self

    def all(self):
        return self.result


class FakeSession:
    def __init__(self, latest_query: FakeLatestQuery, outer_query: FakeOuterQuery):
        self.latest_query = latest_query
        self.outer_query = outer_query
        self.id_queries = []

    def query(self, target):
        if target == ("max", "id", "max_id"):
            return self.latest_query
        if target is FakeModel:
            return self.outer_query
        id_query = FakeIdQuery(target)
        self.id_queries.append(id_query)
        return id_query


class FakeFunc:
    @staticmethod
    def max(column: FakeColumn):
        return FakeMaxExpression(column)


class FakeDB:
    def __init__(self, latest_query: FakeLatestQuery, outer_query: FakeOuterQuery):
        self.session = FakeSession(latest_query, outer_query)
        self.func = FakeFunc()


class FakeModel:
    id = FakeColumn("id")
    deleted = FakeColumn("deleted")
    shifu_bid = FakeColumn("shifu_bid")
    title = FakeColumn("title")
    created_user_bid = FakeColumn("created_user_bid")
    created_at = FakeColumn("created_at")
    updated_at = FakeColumn("updated_at")


def test_load_latest_shifus_filters_on_latest_rows(monkeypatch):
    latest_query = FakeLatestQuery()
    expected_rows = ["latest-course-row"]
    outer_query = FakeOuterQuery(expected_rows)
    fake_db = FakeDB(latest_query, outer_query)
    monkeypatch.setattr(admin_module, "db", fake_db)

    creator_bids = {"creator-1"}
    start_time = datetime(2025, 4, 1, 0, 0, 0)
    end_time = datetime(2025, 4, 30, 23, 59, 59)
    updated_start_time = datetime(2025, 4, 2, 0, 0, 0)
    updated_end_time = datetime(2025, 4, 3, 23, 59, 59)

    result = _load_latest_shifus(
        FakeModel,
        shifu_bid="course-1",
        course_name="Latest Title",
        creator_bids=creator_bids,
        start_time=start_time,
        end_time=end_time,
        updated_start_time=updated_start_time,
        updated_end_time=updated_end_time,
    )

    assert result == expected_rows
    assert latest_query.filters == [
        ("eq", "deleted", 0),
        ("eq", "shifu_bid", "course-1"),
    ]
    assert latest_query.grouped_by == [FakeModel.shifu_bid]
    assert outer_query.filters == [
        ("in", "id", fake_db.session.id_queries[0]),
        ("ilike", "title", "%Latest Title%"),
        ("in", "created_user_bid", creator_bids),
        ("ge", "created_at", start_time),
        ("le", "created_at", end_time),
        ("ge", "updated_at", updated_start_time),
        ("le", "updated_at", updated_end_time),
    ]
    assert outer_query.ordering == [
        ("desc", "updated_at"),
        ("desc", "id"),
    ]
