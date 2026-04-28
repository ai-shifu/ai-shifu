from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from flask import Flask

from flaskr.dao import db
from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.shifu import admin as admin_module
from flaskr.service.shifu.admin import (
    _load_course_activity_map,
    _load_latest_shifus,
    list_operator_courses,
)
from flaskr.service.shifu.admin_dtos import AdminOperationCourseSummaryDTO
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu


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

    assert isinstance(result, PageNationDTO)
    assert result.total == 1
    assert len(result.data) == 1
    item = result.data[0]
    assert isinstance(item, AdminOperationCourseSummaryDTO)
    assert item.shifu_bid == "course-1"
    assert item.course_name == "Draft Course"
    assert item.course_status == "published"
    assert item.price == "199"
    assert item.course_model == "gpt-4.1-mini"
    assert item.course_prompt == "You are a patient course assistant."
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
                    creator_mock.return_value = None
                    latest_mock.side_effect = [[draft_course], [published_only_course]]
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
    assert len(result.data) == 1
    assert result.data[0].shifu_bid == "course-1"


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

    assert [item.shifu_bid for item in result.data] == [
        "course-activity",
        "course-older",
    ]
    assert result.data[0].updater_user_bid == "editor-9"
    assert result.data[0].updater_mobile == "13223532334"
    assert result.data[0].updater_nickname == "Editor Nine"
    assert result.data[0].updated_at == "2025-04-05T09:00:00Z"


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
    assert len(result.data) == 1
    assert result.data[0].shifu_bid == "course-activity-filter"
    assert result.data[0].updated_at == "2025-04-05T09:00:00Z"
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
    assert len(result.data) == 2
    assert {item.shifu_bid for item in result.data} == {
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

    assert [item.shifu_bid for item in unpublished_result.data] == ["course-draft-only"]
    assert unpublished_result.data[0].course_status == "unpublished"
    assert [item.shifu_bid for item in published_result.data] == ["course-published"]
    assert published_result.data[0].course_status == "published"


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
