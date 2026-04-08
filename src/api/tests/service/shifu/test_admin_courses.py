from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from flask import Flask

from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.shifu.admin import list_operator_courses
from flaskr.service.shifu.admin_dtos import AdminOperationCourseSummaryDTO


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
    ):
        self.shifu_bid = shifu_bid
        self.title = title
        self.price = price
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
            with patch("flaskr.service.shifu.admin._load_user_map") as user_map_mock:
                creator_mock.return_value = {"creator-1"}
                latest_mock.side_effect = [[draft_course], [published_course]]
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

    assert isinstance(result, PageNationDTO)
    assert result.total == 1
    assert len(result.data) == 1
    item = result.data[0]
    assert isinstance(item, AdminOperationCourseSummaryDTO)
    assert item.shifu_bid == "course-1"
    assert item.course_name == "Draft Course"
    assert item.course_status == "published"
    assert item.price == "199"
    assert item.creator_mobile == "15811112222"
    assert item.creator_email == "creator@example.com"
    assert item.creator_nickname == "Creator Mars"
    assert item.updater_email == "editor@example.com"
    assert item.updater_nickname == "Editor Venus"
    assert (
        latest_mock.call_args_list[0].kwargs["updated_start_time"] == updated_start_time
    )
    assert latest_mock.call_args_list[0].kwargs["updated_end_time"] == updated_end_time
    assert (
        latest_mock.call_args_list[1].kwargs["updated_start_time"] == updated_start_time
    )
    assert latest_mock.call_args_list[1].kwargs["updated_end_time"] == updated_end_time


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
            with patch("flaskr.service.shifu.admin._load_user_map") as user_map_mock:
                creator_mock.return_value = None
                latest_mock.side_effect = [[draft_course], [published_only_course]]
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
    assert len(result.data) == 1
    assert result.data[0].shifu_bid == "course-1"


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
            with patch("flaskr.service.shifu.admin._load_user_map") as user_map_mock:
                creator_mock.return_value = None
                latest_mock.side_effect = [
                    [builtin_demo_course, system_custom_course],
                    [normal_course],
                ]
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
    assert len(result.data) == 2
    assert {item.shifu_bid for item in result.data} == {
        "course-1",
        "course-system-custom",
    }


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
            with patch("flaskr.service.shifu.admin._load_user_map") as user_map_mock:
                creator_mock.return_value = None
                latest_mock.side_effect = lambda model, **kwargs: (
                    [draft_only_course]
                    if model.__name__ == "DraftShifu"
                    else [published_course]
                )
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

    assert [item.shifu_bid for item in unpublished_result.data] == ["course-draft-only"]
    assert unpublished_result.data[0].course_status == "unpublished"
    assert [item.shifu_bid for item in published_result.data] == ["course-published"]
    assert published_result.data[0].course_status == "published"
