from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from flaskr.dao import db
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
)
from flaskr.service.shifu.models import (
    DraftShifu,
    LogPublishedStruct,
    PublishedOutlineItem,
    ShifuUserArchive,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem


@dataclass
class _OutlineSeed:
    bid: str
    title: str
    type: int = UNIT_TYPE_VALUE_NORMAL
    hidden: int = 0
    parent_bid: str = ""


@pytest.mark.usefixtures("app")
class TestDashboardRoutes:
    def _mock_request_user(self, monkeypatch, *, user_id: str = "teacher-1"):
        dummy_user = SimpleNamespace(
            user_id=user_id,
            language="en-US",
            is_creator=True,
        )
        monkeypatch.setattr(
            "flaskr.route.user.validate_user",
            lambda _app, _token: dummy_user,
            raising=False,
        )

    def _allow_permission(self, monkeypatch, *, allowed: bool):
        monkeypatch.setattr(
            "flaskr.service.dashboard.funcs.shifu_permission_verification",
            lambda _app, _user_id, _shifu_bid, _perm: allowed,
            raising=False,
        )

    def _seed_published_struct(self, *, shifu_bid: str, outlines: list[_OutlineSeed]):
        now = datetime.utcnow()
        rows: list[PublishedOutlineItem] = []
        for idx, outline in enumerate(outlines):
            rows.append(
                PublishedOutlineItem(
                    outline_item_bid=outline.bid,
                    shifu_bid=shifu_bid,
                    title=outline.title,
                    type=outline.type,
                    hidden=outline.hidden,
                    parent_bid=outline.parent_bid,
                    position=str(idx),
                    content="",
                    deleted=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        db.session.add_all(rows)
        db.session.flush()

        struct = HistoryItem(
            bid=shifu_bid,
            id=0,
            type="shifu",
            children=[
                HistoryItem(
                    bid=row.outline_item_bid,
                    id=row.id,
                    type="outline",
                    children=[],
                )
                for row in rows
            ],
        )
        db.session.add(
            LogPublishedStruct(
                struct_bid="struct-" + shifu_bid,
                shifu_bid=shifu_bid,
                struct=struct.to_json(),
                deleted=0,
                created_at=now,
            )
        )
        db.session.commit()
        return rows

    def _seed_dashboard_course(
        self,
        *,
        shifu_bid: str,
        title: str,
        user_id: str = "teacher-1",
    ) -> None:
        now = datetime.utcnow()
        db.session.add(
            DraftShifu(
                shifu_bid=shifu_bid,
                title=title,
                description="",
                avatar_res_bid="",
                llm="",
                llm_temperature=0,
                llm_system_prompt="",
                ask_enabled_status=0,
                ask_llm="",
                ask_llm_temperature=0,
                ask_llm_system_prompt="",
                price=0,
                deleted=0,
                created_at=now,
                created_user_bid=user_id,
                updated_at=now,
                updated_user_bid=user_id,
            )
        )

    def test_entry_summary_excludes_archived_courses(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        now = datetime(2025, 1, 15, 10, 0, 0)
        with app.app_context():
            self._seed_dashboard_course(shifu_bid="course-a", title="Course A")
            self._seed_dashboard_course(shifu_bid="course-b", title="Course B")
            db.session.add(
                ShifuUserArchive(
                    shifu_bid="course-b",
                    user_bid="teacher-1",
                    archived=1,
                    archived_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )

            db.session.add_all(
                [
                    LearnProgressRecord(
                        progress_record_bid="entry-progress-a-1",
                        shifu_bid="course-a",
                        outline_item_bid="outline-1",
                        user_bid="learner-1",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    LearnProgressRecord(
                        progress_record_bid="entry-progress-a-2",
                        shifu_bid="course-a",
                        outline_item_bid="outline-1",
                        user_bid="learner-2",
                        status=LEARN_STATUS_NOT_STARTED,
                        block_position=0,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    LearnProgressRecord(
                        progress_record_bid="entry-progress-b-1",
                        shifu_bid="course-b",
                        outline_item_bid="outline-2",
                        user_bid="learner-3",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )

            db.session.add_all(
                [
                    Order(
                        order_bid="order-a-1",
                        shifu_bid="course-a",
                        user_bid="learner-1",
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    Order(
                        order_bid="order-a-2",
                        shifu_bid="course-a",
                        user_bid="learner-2",
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    Order(
                        order_bid="order-b-1",
                        shifu_bid="course-b",
                        user_bid="learner-3",
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )

            db.session.add_all(
                [
                    LearnGeneratedBlock(
                        generated_block_bid="entry-ask-a-1",
                        progress_record_bid="entry-progress-a-1",
                        user_bid="learner-1",
                        block_bid="",
                        outline_item_bid="outline-1",
                        shifu_bid="course-a",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=2,
                        generated_content="Q1",
                        position=1,
                        block_content_conf="",
                        liked=0,
                        deleted=0,
                        status=1,
                        created_at=now,
                        updated_at=now,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="entry-ask-a-2",
                        progress_record_bid="entry-progress-a-2",
                        user_bid="learner-2",
                        block_bid="",
                        outline_item_bid="outline-1",
                        shifu_bid="course-a",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=2,
                        generated_content="Q2",
                        position=1,
                        block_content_conf="",
                        liked=0,
                        deleted=0,
                        status=1,
                        created_at=now,
                        updated_at=now,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="entry-ask-b-1",
                        progress_record_bid="entry-progress-b-1",
                        user_bid="learner-3",
                        block_bid="",
                        outline_item_bid="outline-2",
                        shifu_bid="course-b",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=2,
                        generated_content="QB",
                        position=1,
                        block_content_conf="",
                        liked=0,
                        deleted=0,
                        status=1,
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )
            db.session.commit()

        resp = test_client.get("/api/dashboard/entry?page_index=1&page_size=20")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["course_count"] == 1
        assert payload["data"]["summary"]["learner_count"] == 2
        assert payload["data"]["summary"]["order_count"] == 2
        assert payload["data"]["summary"]["generation_count"] == 2
        assert payload["data"]["total"] == 1
        assert len(payload["data"]["items"]) == 1
        assert payload["data"]["items"][0]["shifu_bid"] == "course-a"

    def test_entry_keyword_and_date_range_filters(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        in_range = datetime(2025, 1, 10, 9, 0, 0)
        out_of_range = datetime(2024, 12, 20, 9, 0, 0)
        with app.app_context():
            self._seed_dashboard_course(shifu_bid="course-alg", title="Algebra 101")
            self._seed_dashboard_course(shifu_bid="course-bio", title="Biology 101")

            db.session.add_all(
                [
                    LearnProgressRecord(
                        progress_record_bid="entry-filter-progress-alg",
                        shifu_bid="course-alg",
                        outline_item_bid="outline-1",
                        user_bid="learner-a",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=in_range,
                        updated_at=in_range,
                    ),
                    LearnProgressRecord(
                        progress_record_bid="entry-filter-progress-bio",
                        shifu_bid="course-bio",
                        outline_item_bid="outline-2",
                        user_bid="learner-b",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=in_range,
                        updated_at=in_range,
                    ),
                ]
            )

            db.session.add_all(
                [
                    Order(
                        order_bid="entry-filter-order-in",
                        shifu_bid="course-alg",
                        user_bid="learner-a",
                        deleted=0,
                        created_at=in_range,
                        updated_at=in_range,
                    ),
                    Order(
                        order_bid="entry-filter-order-out",
                        shifu_bid="course-alg",
                        user_bid="learner-a",
                        deleted=0,
                        created_at=out_of_range,
                        updated_at=out_of_range,
                    ),
                ]
            )

            db.session.add_all(
                [
                    LearnGeneratedBlock(
                        generated_block_bid="entry-filter-ask-in",
                        progress_record_bid="entry-filter-progress-alg",
                        user_bid="learner-a",
                        block_bid="",
                        outline_item_bid="outline-1",
                        shifu_bid="course-alg",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=2,
                        generated_content="In range",
                        position=1,
                        block_content_conf="",
                        liked=0,
                        deleted=0,
                        status=1,
                        created_at=in_range,
                        updated_at=in_range,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="entry-filter-ask-out",
                        progress_record_bid="entry-filter-progress-alg",
                        user_bid="learner-a",
                        block_bid="",
                        outline_item_bid="outline-1",
                        shifu_bid="course-alg",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=2,
                        generated_content="Out range",
                        position=1,
                        block_content_conf="",
                        liked=0,
                        deleted=0,
                        status=1,
                        created_at=out_of_range,
                        updated_at=out_of_range,
                    ),
                ]
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/entry"
            "?keyword=alG"
            "&start_date=2025-01-01"
            "&end_date=2025-01-31"
            "&page_index=1&page_size=20"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["course_count"] == 1
        assert payload["data"]["summary"]["learner_count"] == 1
        assert payload["data"]["summary"]["order_count"] == 1
        assert payload["data"]["summary"]["generation_count"] == 1
        assert payload["data"]["items"][0]["shifu_bid"] == "course-alg"
        assert payload["data"]["items"][0]["order_count"] == 1
        assert payload["data"]["items"][0]["generation_count"] == 1

    def test_outlines_requires_permission(self, monkeypatch, test_client):
        self._mock_request_user(monkeypatch)
        self._allow_permission(monkeypatch, allowed=False)

        resp = test_client.get("/api/dashboard/shifus/course-1/outlines")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] != 0

    def test_outlines_returns_struct_order(self, monkeypatch, test_client, app):
        self._mock_request_user(monkeypatch)
        self._allow_permission(monkeypatch, allowed=True)

        with app.app_context():
            self._seed_published_struct(
                shifu_bid="course-1",
                outlines=[
                    _OutlineSeed(bid="o-1", title="Outline 1"),
                    _OutlineSeed(bid="o-2", title="Outline 2"),
                ],
            )

        resp = test_client.get("/api/dashboard/shifus/course-1/outlines")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert [item["outline_item_bid"] for item in payload["data"]] == ["o-1", "o-2"]

    def test_overview_excludes_hidden_and_uses_latest_progress(
        self, monkeypatch, test_client, app
    ):
        self._mock_request_user(monkeypatch)
        self._allow_permission(monkeypatch, allowed=True)

        with app.app_context():
            self._seed_published_struct(
                shifu_bid="course-2",
                outlines=[
                    _OutlineSeed(
                        bid="r-1", title="Required 1", type=UNIT_TYPE_VALUE_NORMAL
                    ),
                    _OutlineSeed(
                        bid="hidden-1",
                        title="Hidden required",
                        type=UNIT_TYPE_VALUE_NORMAL,
                        hidden=1,
                    ),
                    _OutlineSeed(
                        bid="guest-1",
                        title="Guest",
                        type=UNIT_TYPE_VALUE_GUEST,
                    ),
                ],
            )

            # Learner A: latest record is completed (older is not started)
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid="attend-a-1",
                    shifu_bid="course-2",
                    outline_item_bid="r-1",
                    user_bid="learner-a",
                    status=LEARN_STATUS_NOT_STARTED,
                    block_position=0,
                    deleted=0,
                    created_at=datetime.utcnow() - timedelta(days=2),
                    updated_at=datetime.utcnow() - timedelta(days=2),
                )
            )
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid="attend-a-2",
                    shifu_bid="course-2",
                    outline_item_bid="r-1",
                    user_bid="learner-a",
                    status=LEARN_STATUS_COMPLETED,
                    block_position=10,
                    deleted=0,
                    created_at=datetime.utcnow() - timedelta(days=1),
                    updated_at=datetime.utcnow() - timedelta(days=1),
                )
            )

            # Learner B: has only guest progress, still counts as a learner
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid="attend-b-1",
                    shifu_bid="course-2",
                    outline_item_bid="guest-1",
                    user_bid="learner-b",
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=1,
                    deleted=0,
                    created_at=datetime.utcnow() - timedelta(days=1),
                    updated_at=datetime.utcnow() - timedelta(days=1),
                )
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/shifus/course-2/overview?start_date=2025-01-01&end_date=2025-12-31"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["kpis"]["required_outline_total"] == 1
        assert payload["data"]["kpis"]["learner_count"] == 2
        assert payload["data"]["kpis"]["completion_count"] == 1

    def test_learners_pagination(self, monkeypatch, test_client, app):
        self._mock_request_user(monkeypatch)
        self._allow_permission(monkeypatch, allowed=True)

        with app.app_context():
            self._seed_published_struct(
                shifu_bid="course-3",
                outlines=[_OutlineSeed(bid="r-1", title="Required 1")],
            )
            for idx in range(3):
                db.session.add(
                    LearnProgressRecord(
                        progress_record_bid=f"attend-{idx}",
                        shifu_bid="course-3",
                        outline_item_bid="r-1",
                        user_bid=f"learner-{idx}",
                        status=LEARN_STATUS_NOT_STARTED,
                        block_position=0,
                        deleted=0,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/shifus/course-3/learners?page_index=1&page_size=2"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["total"] == 3
        assert payload["data"]["page_count"] == 2
        assert len(payload["data"]["items"]) == 2

    def test_followups_pairs_answer(self, monkeypatch, test_client, app):
        self._mock_request_user(monkeypatch)
        self._allow_permission(monkeypatch, allowed=True)

        now = datetime.utcnow()
        with app.app_context():
            self._seed_published_struct(
                shifu_bid="course-4",
                outlines=[_OutlineSeed(bid="r-1", title="Required 1")],
            )
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid="attend-1",
                    shifu_bid="course-4",
                    outline_item_bid="r-1",
                    user_bid="learner-1",
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=0,
                    deleted=0,
                    created_at=now,
                    updated_at=now,
                )
            )

            # Ask then answer
            db.session.add(
                LearnGeneratedBlock(
                    generated_block_bid="ask-1",
                    progress_record_bid="attend-1",
                    user_bid="learner-1",
                    block_bid="",
                    outline_item_bid="r-1",
                    shifu_bid="course-4",
                    type=BLOCK_TYPE_MDASK_VALUE,
                    role=2,
                    generated_content="Q1",
                    position=1,
                    block_content_conf="",
                    liked=0,
                    deleted=0,
                    status=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.session.add(
                LearnGeneratedBlock(
                    generated_block_bid="answer-1",
                    progress_record_bid="attend-1",
                    user_bid="learner-1",
                    block_bid="",
                    outline_item_bid="r-1",
                    shifu_bid="course-4",
                    type=BLOCK_TYPE_MDANSWER_VALUE,
                    role=1,
                    generated_content="A1",
                    position=1,
                    block_content_conf="",
                    liked=0,
                    deleted=0,
                    status=1,
                    created_at=now + timedelta(seconds=5),
                    updated_at=now + timedelta(seconds=5),
                )
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/shifus/course-4/learners/learner-1/followups"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["total"] == 1
        assert payload["data"]["items"][0]["question"] == "Q1"
        assert payload["data"]["items"][0]["answer"] == "A1"
