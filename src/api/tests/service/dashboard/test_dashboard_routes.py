from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from flaskr.dao import db
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
    ORDER_STATUS_SUCCESS,
    ORDER_STATUS_TO_BE_PAID,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import BLOCK_TYPE_CONTENT_VALUE, BLOCK_TYPE_MDASK_VALUE
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
    ShifuUserArchive,
)


def _clear_dashboard_tables() -> None:
    db.session.query(LearnGeneratedBlock).delete()
    db.session.query(Order).delete()
    db.session.query(LearnProgressRecord).delete()
    db.session.query(ShifuUserArchive).delete()
    db.session.query(AiCourseAuth).delete()
    db.session.query(PublishedOutlineItem).delete()
    db.session.query(DraftShifu).delete()
    db.session.query(PublishedShifu).delete()
    db.session.commit()
    db.session.remove()


@pytest.fixture(autouse=True)
def _isolate_dashboard_tables(app):
    if app is None:
        yield
        return

    with app.app_context():
        _clear_dashboard_tables()

    yield

    with app.app_context():
        _clear_dashboard_tables()


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

    def _seed_dashboard_course(
        self,
        *,
        shifu_bid: str,
        title: str,
        user_id: str = "teacher-1",
        created_at: datetime | None = None,
        published_created_at: datetime | None = None,
    ) -> None:
        draft_created_at = created_at or datetime.utcnow()
        publish_time = published_created_at or draft_created_at
        db.session.add(
            DraftShifu(
                shifu_bid=shifu_bid,
                title=title,
                keywords="",
                description="",
                avatar_res_bid="",
                llm="",
                llm_temperature=0,
                llm_system_prompt="",
                ask_enabled_status=0,
                ask_llm="",
                ask_llm_temperature=0,
                ask_llm_system_prompt="",
                ask_provider_config="{}",
                price=0,
                deleted=0,
                created_at=draft_created_at,
                created_user_bid=user_id,
                updated_at=publish_time,
                updated_user_bid=user_id,
            )
        )
        db.session.add(
            PublishedShifu(
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
                created_at=publish_time,
                created_user_bid=user_id,
                updated_at=publish_time,
                updated_user_bid=user_id,
            )
        )

    def _seed_outline_item(
        self,
        *,
        shifu_bid: str,
        outline_item_bid: str,
        title: str,
        parent_bid: str = "",
        position: str,
        hidden: int = 0,
        created_at: datetime | None = None,
    ) -> None:
        now = created_at or datetime.utcnow()
        db.session.add(
            PublishedOutlineItem(
                outline_item_bid=outline_item_bid,
                shifu_bid=shifu_bid,
                title=title,
                parent_bid=parent_bid,
                position=position,
                hidden=hidden,
                type=0,
                llm="",
                llm_temperature=0,
                llm_system_prompt="",
                ask_enabled_status=0,
                ask_llm="",
                ask_llm_temperature=0,
                ask_llm_system_prompt="",
                content="",
                deleted=0,
                created_at=now,
                created_user_bid="teacher-1",
                updated_at=now,
                updated_user_bid="teacher-1",
            )
        )

    def _seed_shared_course_auth(
        self,
        *,
        shifu_bid: str,
        user_id: str = "teacher-1",
        auth_type: str = '["view"]',
        status: int = 1,
    ) -> None:
        now = datetime.utcnow()
        db.session.add(
            AiCourseAuth(
                course_auth_id=f"auth-{user_id}-{shifu_bid}",
                course_id=shifu_bid,
                user_id=user_id,
                auth_type=auth_type,
                status=status,
                created_at=now,
                updated_at=now,
            )
        )

    def test_entry_summary_uses_owned_courses_only(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        now = datetime(2025, 1, 15, 10, 0, 0)
        with app.app_context():
            self._seed_dashboard_course(shifu_bid="course-a", title="Course A")
            self._seed_dashboard_course(
                shifu_bid="course-b",
                title="Course B",
                user_id="another-teacher",
            )
            self._seed_shared_course_auth(shifu_bid="course-b")
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
                        paid_price="10.00",
                        status=ORDER_STATUS_SUCCESS,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    Order(
                        order_bid="order-a-2",
                        shifu_bid="course-a",
                        user_bid="learner-2",
                        paid_price="20.50",
                        status=ORDER_STATUS_SUCCESS,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    Order(
                        order_bid="order-b-1",
                        shifu_bid="course-b",
                        user_bid="learner-3",
                        paid_price="30.00",
                        status=ORDER_STATUS_SUCCESS,
                        deleted=0,
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
        assert payload["data"]["summary"]["order_amount"] == "30.50"
        assert payload["data"]["total"] == 1
        assert len(payload["data"]["items"]) == 1
        assert {item["shifu_bid"] for item in payload["data"]["items"]} == {
            "course-a",
        }
        amount_map = {
            item["shifu_bid"]: item["order_amount"] for item in payload["data"]["items"]
        }
        assert amount_map["course-a"] == "30.50"

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
                    LearnProgressRecord(
                        progress_record_bid="entry-filter-progress-created-out",
                        shifu_bid="course-alg",
                        outline_item_bid="outline-3",
                        user_bid="learner-c",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=out_of_range,
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
                        paid_price="9.99",
                        status=ORDER_STATUS_SUCCESS,
                        deleted=0,
                        created_at=in_range,
                        updated_at=in_range,
                    ),
                    Order(
                        order_bid="entry-filter-order-out",
                        shifu_bid="course-alg",
                        user_bid="learner-a",
                        paid_price="100.00",
                        status=ORDER_STATUS_SUCCESS,
                        deleted=0,
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
        assert payload["data"]["summary"]["order_amount"] == "9.99"
        assert payload["data"]["items"][0]["shifu_bid"] == "course-alg"
        assert payload["data"]["items"][0]["learner_count"] == 1
        assert payload["data"]["items"][0]["order_count"] == 1
        assert payload["data"]["items"][0]["order_amount"] == "9.99"

    def test_entry_returns_timezone_adjusted_last_active_fields(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        try:
            ZoneInfo("Asia/Shanghai")
        except ZoneInfoNotFoundError:
            pytest.skip("Asia/Shanghai timezone is unavailable in test environment")

        self._mock_request_user(monkeypatch)
        with app.app_context():
            self._seed_dashboard_course(shifu_bid="course-timezone", title="Course TZ")
            app_tz = ZoneInfo(app.config.get("TZ", "UTC"))
            last_active = datetime(2026, 3, 6, 8, 0, 0, tzinfo=app_tz)
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid="entry-timezone-progress-1",
                    shifu_bid="course-timezone",
                    outline_item_bid="outline-1",
                    user_bid="learner-1",
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=0,
                    deleted=0,
                    created_at=last_active - timedelta(hours=1),
                    updated_at=last_active,
                )
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/entry?page_index=1&page_size=20&timezone=Asia/Shanghai"
        )
        payload = resp.get_json(force=True)

        expected = datetime(2026, 3, 6, 8, 0, 0, tzinfo=app_tz).astimezone(
            ZoneInfo("Asia/Shanghai")
        )
        item = payload["data"]["items"][0]

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert item["last_active_at"] == expected.isoformat()
        assert item["last_active_at_display"] == expected.strftime("%Y-%m-%d %H:%M:%S")

    def test_entry_course_count_respects_date_filter(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        in_range = datetime(2025, 2, 10, 9, 0, 0)
        out_of_range = datetime(2024, 11, 20, 9, 0, 0)
        with app.app_context():
            self._seed_dashboard_course(shifu_bid="course-a", title="Course A")
            self._seed_dashboard_course(shifu_bid="course-b", title="Course B")

            db.session.add(
                Order(
                    order_bid="entry-date-order-a",
                    shifu_bid="course-a",
                    user_bid="learner-a",
                    paid_price="5.00",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=in_range,
                    updated_at=in_range,
                )
            )
            db.session.add(
                Order(
                    order_bid="entry-date-order-b",
                    shifu_bid="course-b",
                    user_bid="learner-b",
                    paid_price="7.00",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=out_of_range,
                    updated_at=out_of_range,
                )
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/entry"
            "?start_date=2025-02-01"
            "&end_date=2025-02-28"
            "&page_index=1&page_size=20"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["course_count"] == 1
        assert payload["data"]["summary"]["order_count"] == 1
        assert payload["data"]["summary"]["order_amount"] == "5.00"
        assert payload["data"]["total"] == 1
        assert payload["data"]["items"][0]["shifu_bid"] == "course-a"
        assert payload["data"]["items"][0]["order_amount"] == "5.00"

    def test_entry_order_only_user_not_counted_as_learner(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        now = datetime(2025, 2, 10, 9, 0, 0)
        with app.app_context():
            self._seed_dashboard_course(shifu_bid="course-order", title="Order Course")
            db.session.add(
                Order(
                    order_bid="order-only-1",
                    shifu_bid="course-order",
                    user_bid="imported-user",
                    payment_channel="pingxx",
                    paid_price="88.80",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/entry"
            "?start_date=2025-02-01"
            "&end_date=2025-02-28"
            "&page_index=1&page_size=20"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["learner_count"] == 0
        assert payload["data"]["summary"]["order_count"] == 1
        assert payload["data"]["summary"]["order_amount"] == "88.80"
        assert payload["data"]["items"][0]["shifu_bid"] == "course-order"
        assert payload["data"]["items"][0]["learner_count"] == 0
        assert payload["data"]["items"][0]["order_count"] == 1
        assert payload["data"]["items"][0]["order_amount"] == "88.80"

    def test_entry_manual_import_user_counted_as_learner(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        now = datetime(2025, 2, 10, 9, 0, 0)
        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-import", title="Import Course"
            )
            db.session.add(
                Order(
                    order_bid="order-import-1",
                    shifu_bid="course-import",
                    user_bid="imported-user",
                    payment_channel="manual",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/entry"
            "?start_date=2025-02-01"
            "&end_date=2025-02-28"
            "&page_index=1&page_size=20"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["learner_count"] == 1
        assert payload["data"]["summary"]["order_count"] == 1
        assert payload["data"]["summary"]["order_amount"] == "0.00"
        assert payload["data"]["items"][0]["shifu_bid"] == "course-import"
        assert payload["data"]["items"][0]["learner_count"] == 1
        assert payload["data"]["items"][0]["order_count"] == 1
        assert payload["data"]["items"][0]["order_amount"] == "0.00"

    def test_entry_manual_non_zero_order_counted_in_order_metrics(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        now = datetime(2025, 2, 10, 9, 0, 0)
        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-manual-paid", title="Manual Paid Course"
            )
            db.session.add(
                Order(
                    order_bid="order-manual-paid-1",
                    shifu_bid="course-manual-paid",
                    user_bid="manual-paid-user",
                    payment_channel="manual",
                    paid_price="12.34",
                    status=ORDER_STATUS_SUCCESS,
                    deleted=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/entry"
            "?start_date=2025-02-01"
            "&end_date=2025-02-28"
            "&page_index=1&page_size=20"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["learner_count"] == 1
        assert payload["data"]["summary"]["order_count"] == 1
        assert payload["data"]["summary"]["order_amount"] == "12.34"
        assert payload["data"]["items"][0]["shifu_bid"] == "course-manual-paid"
        assert payload["data"]["items"][0]["order_count"] == 1
        assert payload["data"]["items"][0]["order_amount"] == "12.34"

    def test_entry_non_success_order_excluded_from_order_metrics(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        now = datetime(2025, 2, 10, 9, 0, 0)
        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-pending-order", title="Pending Order Course"
            )
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid="pending-order-progress-1",
                    shifu_bid="course-pending-order",
                    outline_item_bid="outline-pending-order-1",
                    user_bid="learner-pending",
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=0,
                    deleted=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.session.add(
                Order(
                    order_bid="order-pending-1",
                    shifu_bid="course-pending-order",
                    user_bid="learner-pending",
                    payment_channel="pingxx",
                    paid_price="66.66",
                    status=ORDER_STATUS_TO_BE_PAID,
                    deleted=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/entry"
            "?start_date=2025-02-01"
            "&end_date=2025-02-28"
            "&page_index=1&page_size=20"
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["course_count"] == 1
        assert payload["data"]["summary"]["learner_count"] == 1
        assert payload["data"]["summary"]["order_count"] == 0
        assert payload["data"]["summary"]["order_amount"] == "0.00"
        assert payload["data"]["items"][0]["shifu_bid"] == "course-pending-order"
        assert payload["data"]["items"][0]["order_count"] == 0
        assert payload["data"]["items"][0]["order_amount"] == "0.00"

    def test_entry_excludes_all_shared_courses(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-owned",
                title="Owned Course",
            )
            self._seed_dashboard_course(
                shifu_bid="course-view",
                title="Shared View",
                user_id="teacher-2",
            )
            self._seed_dashboard_course(
                shifu_bid="course-edit",
                title="Shared Edit",
                user_id="teacher-2",
            )
            self._seed_dashboard_course(
                shifu_bid="course-publish",
                title="Shared Publish",
                user_id="teacher-2",
            )
            self._seed_dashboard_course(
                shifu_bid="course-mixed",
                title="Shared Mixed",
                user_id="teacher-2",
            )
            self._seed_dashboard_course(
                shifu_bid="course-disabled",
                title="Shared Disabled",
                user_id="teacher-2",
            )
            self._seed_shared_course_auth(
                shifu_bid="course-view",
                auth_type='["view"]',
                status=1,
            )
            self._seed_shared_course_auth(
                shifu_bid="course-edit",
                auth_type='["edit"]',
                status=1,
            )
            self._seed_shared_course_auth(
                shifu_bid="course-publish",
                auth_type='["publish"]',
                status=1,
            )
            self._seed_shared_course_auth(
                shifu_bid="course-mixed",
                auth_type='["view","edit"]',
                status=1,
            )
            self._seed_shared_course_auth(
                shifu_bid="course-disabled",
                auth_type='["view"]',
                status=0,
            )
            self._seed_shared_course_auth(
                shifu_bid="course-view",
                auth_type='["view"]',
                status=1,
            )
            db.session.commit()

        resp = test_client.get("/api/dashboard/entry?page_index=1&page_size=20")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["course_count"] == 1
        assert payload["data"]["total"] == 1
        assert {item["shifu_bid"] for item in payload["data"]["items"]} == {
            "course-owned",
        }

    def test_entry_excludes_shared_courses_without_owned_copy(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)
        monkeypatch.setattr(
            "flaskr.service.dashboard.funcs.get_dynamic_config",
            lambda _key, default=None: default,
            raising=False,
        )

        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-live",
                title="Live Course",
            )
            self._seed_shared_course_auth(
                shifu_bid="course-stale",
                auth_type='["view"]',
                status=1,
            )
            db.session.commit()

        resp = test_client.get("/api/dashboard/entry?page_index=1&page_size=20")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["course_count"] == 1
        assert payload["data"]["total"] == 1
        assert payload["data"]["items"][0]["shifu_bid"] == "course-live"

    def test_entry_excludes_demo_courses(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)
        monkeypatch.setattr(
            "flaskr.service.shifu.demo_courses.get_dynamic_config",
            lambda key, default=None: (
                "course-demo" if key == "DEMO_SHIFU_BID" else default
            ),
            raising=False,
        )

        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-demo",
                title="Demo Course",
            )
            self._seed_dashboard_course(
                shifu_bid="course-live",
                title="Live Course",
            )
            db.session.commit()

        resp = test_client.get("/api/dashboard/entry?page_index=1&page_size=20")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["course_count"] == 1
        assert payload["data"]["total"] == 1
        assert payload["data"]["items"][0]["shifu_bid"] == "course-live"

    def test_entry_excludes_builtin_demo_titles_when_config_missing(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)
        monkeypatch.setattr(
            "flaskr.service.shifu.demo_courses.get_dynamic_config",
            lambda _key, default=None: default,
            raising=False,
        )

        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="e867343eaab44488ad792ec54d8b82b5",
                title="AI 师傅教学引导",
                user_id="system",
            )
            self._seed_dashboard_course(
                shifu_bid="b5d7844387e940ed9480a6f945a6db6a",
                title="AI-Shifu Creation Guide",
                user_id="system",
            )
            self._seed_dashboard_course(
                shifu_bid="course-live",
                title="Live Course",
            )
            db.session.commit()

        resp = test_client.get("/api/dashboard/entry?page_index=1&page_size=20")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["summary"]["course_count"] == 1
        assert payload["data"]["total"] == 1
        assert payload["data"]["items"][0]["shifu_bid"] == "course-live"

    def test_course_detail_returns_real_metrics(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        draft_created_at = datetime(2025, 1, 1, 8, 0, 0)
        published_created_at = datetime(2025, 2, 1, 9, 0, 0)
        recent_now = datetime.utcnow()
        old_activity = recent_now - timedelta(days=10)

        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-detail",
                title="Detail Course",
                created_at=draft_created_at,
                published_created_at=published_created_at,
            )
            self._seed_outline_item(
                shifu_bid="course-detail",
                outline_item_bid="chapter-1",
                title="Chapter 1",
                position="1",
            )
            self._seed_outline_item(
                shifu_bid="course-detail",
                outline_item_bid="lesson-1",
                title="Lesson 1",
                parent_bid="chapter-1",
                position="1.1",
            )
            self._seed_outline_item(
                shifu_bid="course-detail",
                outline_item_bid="lesson-2",
                title="Lesson 2",
                parent_bid="chapter-1",
                position="1.2",
            )
            self._seed_outline_item(
                shifu_bid="course-detail",
                outline_item_bid="chapter-2",
                title="Chapter 2",
                position="2",
            )
            self._seed_outline_item(
                shifu_bid="course-detail",
                outline_item_bid="lesson-3",
                title="Lesson 3",
                parent_bid="chapter-2",
                position="2.1",
            )

            db.session.add_all(
                [
                    LearnProgressRecord(
                        progress_record_bid="detail-progress-u1-l1",
                        shifu_bid="course-detail",
                        outline_item_bid="lesson-1",
                        user_bid="learner-1",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=recent_now - timedelta(hours=2),
                        updated_at=recent_now - timedelta(hours=1, minutes=30),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="detail-progress-u1-l2",
                        shifu_bid="course-detail",
                        outline_item_bid="lesson-2",
                        user_bid="learner-1",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=recent_now - timedelta(hours=1, minutes=50),
                        updated_at=recent_now - timedelta(hours=1),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="detail-progress-u1-l3",
                        shifu_bid="course-detail",
                        outline_item_bid="lesson-3",
                        user_bid="learner-1",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=recent_now - timedelta(hours=1, minutes=40),
                        updated_at=recent_now - timedelta(minutes=30),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="detail-progress-u2-l1",
                        shifu_bid="course-detail",
                        outline_item_bid="lesson-1",
                        user_bid="learner-2",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=old_activity - timedelta(minutes=25),
                        updated_at=old_activity - timedelta(minutes=5),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="detail-progress-u2-l2",
                        shifu_bid="course-detail",
                        outline_item_bid="lesson-2",
                        user_bid="learner-2",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=old_activity - timedelta(minutes=20),
                        updated_at=old_activity,
                    ),
                ]
            )
            db.session.add_all(
                [
                    Order(
                        order_bid="detail-order-1",
                        shifu_bid="course-detail",
                        user_bid="learner-1",
                        paid_price="10.00",
                        status=ORDER_STATUS_SUCCESS,
                        deleted=0,
                        created_at=recent_now,
                        updated_at=recent_now,
                    ),
                    Order(
                        order_bid="detail-order-2",
                        shifu_bid="course-detail",
                        user_bid="learner-2",
                        paid_price="20.00",
                        status=ORDER_STATUS_SUCCESS,
                        deleted=0,
                        created_at=recent_now,
                        updated_at=recent_now,
                    ),
                    Order(
                        order_bid="detail-order-3",
                        shifu_bid="course-detail",
                        user_bid="learner-3",
                        payment_channel="manual",
                        paid_price="30.00",
                        status=ORDER_STATUS_SUCCESS,
                        deleted=0,
                        created_at=recent_now,
                        updated_at=recent_now,
                    ),
                ]
            )
            db.session.add_all(
                [
                    LearnGeneratedBlock(
                        generated_block_bid="detail-ask-1",
                        progress_record_bid="detail-progress-u1-l1",
                        user_bid="learner-1",
                        block_bid="",
                        outline_item_bid="lesson-1",
                        shifu_bid="course-detail",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=ROLE_STUDENT,
                        generated_content="Question 1",
                        position=1,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=recent_now,
                        updated_at=recent_now,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="detail-ask-2",
                        progress_record_bid="detail-progress-u1-l2",
                        user_bid="learner-1",
                        block_bid="",
                        outline_item_bid="lesson-2",
                        shifu_bid="course-detail",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=ROLE_STUDENT,
                        generated_content="Question 2",
                        position=2,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=recent_now,
                        updated_at=recent_now,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="detail-ask-3",
                        progress_record_bid="detail-progress-u2-l1",
                        user_bid="learner-2",
                        block_bid="",
                        outline_item_bid="lesson-1",
                        shifu_bid="course-detail",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=ROLE_STUDENT,
                        generated_content="Question 3",
                        position=3,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=recent_now,
                        updated_at=recent_now,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="detail-ignore-teacher",
                        progress_record_bid="detail-progress-u2-l1",
                        user_bid="learner-2",
                        block_bid="",
                        outline_item_bid="lesson-1",
                        shifu_bid="course-detail",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=ROLE_TEACHER,
                        generated_content="Ignore",
                        position=4,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=recent_now,
                        updated_at=recent_now,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="detail-ignore-type",
                        progress_record_bid="detail-progress-u2-l2",
                        user_bid="learner-2",
                        block_bid="",
                        outline_item_bid="lesson-2",
                        shifu_bid="course-detail",
                        type=BLOCK_TYPE_CONTENT_VALUE,
                        role=ROLE_STUDENT,
                        generated_content="Ignore",
                        position=5,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=recent_now,
                        updated_at=recent_now,
                    ),
                ]
            )
            db.session.commit()

        resp = test_client.get("/api/dashboard/shifus/course-detail/detail")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["basic_info"] == {
            "shifu_bid": "course-detail",
            "course_name": "Detail Course",
            "created_at": "2025-01-01T08:00:00+00:00",
            "created_at_display": "2025-01-01 08:00:00",
            "chapter_count": 3,
            "learner_count": 3,
        }
        assert payload["data"]["metrics"] == {
            "order_count": 3,
            "order_amount": "60.00",
            "completed_learner_count": 1,
            "completion_rate": "33.33",
            "active_learner_count_last_7_days": 1,
            "total_follow_up_count": 3,
            "avg_follow_up_count_per_learner": "1.00",
            "avg_learning_duration_seconds": 2300,
        }

    def test_course_detail_returns_timezone_adjusted_created_at_fields(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        try:
            ZoneInfo("Asia/Shanghai")
        except ZoneInfoNotFoundError:
            pytest.skip("Asia/Shanghai timezone is unavailable in test environment")

        self._mock_request_user(monkeypatch)

        with app.app_context():
            created_at = datetime(2026, 3, 3, 0, 0, 0)
            self._seed_dashboard_course(
                shifu_bid="course-detail-tz",
                title="Detail TZ Course",
                created_at=created_at,
                published_created_at=created_at,
            )
            db.session.commit()

        resp = test_client.get(
            "/api/dashboard/shifus/course-detail-tz/detail?timezone=Asia/Shanghai"
        )
        payload = resp.get_json(force=True)

        app_tz = ZoneInfo(app.config.get("TZ", "UTC"))
        expected = datetime(2026, 3, 3, 0, 0, 0, tzinfo=app_tz).astimezone(
            ZoneInfo("Asia/Shanghai")
        )

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["basic_info"]["created_at"] == expected.isoformat()
        assert payload["data"]["basic_info"]["created_at_display"] == expected.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def test_course_detail_counts_restudy_learners_as_completed(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-restudy",
                title="Restudy Course",
            )
            self._seed_outline_item(
                shifu_bid="course-restudy",
                outline_item_bid="chapter-1",
                title="Chapter 1",
                position="1",
            )
            self._seed_outline_item(
                shifu_bid="course-restudy",
                outline_item_bid="lesson-1",
                title="Lesson 1",
                parent_bid="chapter-1",
                position="1.1",
            )
            self._seed_outline_item(
                shifu_bid="course-restudy",
                outline_item_bid="lesson-2",
                title="Lesson 2",
                parent_bid="chapter-1",
                position="1.2",
            )

            now = datetime.utcnow()
            db.session.add_all(
                [
                    LearnProgressRecord(
                        progress_record_bid="restudy-u1-l1-completed",
                        shifu_bid="course-restudy",
                        outline_item_bid="lesson-1",
                        user_bid="learner-1",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=now - timedelta(hours=4),
                        updated_at=now - timedelta(hours=4),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="restudy-u1-l2-completed",
                        shifu_bid="course-restudy",
                        outline_item_bid="lesson-2",
                        user_bid="learner-1",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=now - timedelta(hours=3),
                        updated_at=now - timedelta(hours=3),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="restudy-u2-l1-completed",
                        shifu_bid="course-restudy",
                        outline_item_bid="lesson-1",
                        user_bid="learner-2",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=now - timedelta(hours=4),
                        updated_at=now - timedelta(hours=4),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="restudy-u2-l2-reset",
                        shifu_bid="course-restudy",
                        outline_item_bid="lesson-2",
                        user_bid="learner-2",
                        status=LEARN_STATUS_RESET,
                        block_position=0,
                        deleted=0,
                        created_at=now - timedelta(hours=2),
                        updated_at=now - timedelta(hours=2),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="restudy-u2-l2-restudy",
                        shifu_bid="course-restudy",
                        outline_item_bid="lesson-2",
                        user_bid="learner-2",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=now - timedelta(hours=1),
                        updated_at=now - timedelta(hours=1),
                    ),
                    LearnProgressRecord(
                        progress_record_bid="restudy-u3-l1-completed",
                        shifu_bid="course-restudy",
                        outline_item_bid="lesson-1",
                        user_bid="learner-3",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=now - timedelta(minutes=50),
                        updated_at=now - timedelta(minutes=50),
                    ),
                ]
            )
            db.session.commit()

        resp = test_client.get("/api/dashboard/shifus/course-restudy/detail")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["basic_info"]["learner_count"] == 3
        assert payload["data"]["metrics"]["completed_learner_count"] == 2
        assert payload["data"]["metrics"]["completion_rate"] == "66.67"

    def test_course_detail_rejects_non_owned_course(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-shared",
                title="Shared Course",
                user_id="another-teacher",
            )
            self._seed_shared_course_auth(shifu_bid="course-shared")
            db.session.commit()

        resp = test_client.get("/api/dashboard/shifus/course-shared/detail")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] != 0
        assert payload["message"] == "Course not found"

    def test_course_detail_returns_section_learning_chart(
        self,
        monkeypatch,
        test_client,
        app,
    ):
        self._mock_request_user(monkeypatch)

        now = datetime.utcnow()
        with app.app_context():
            self._seed_dashboard_course(
                shifu_bid="course-section-chart",
                title="Section Chart Course",
            )
            self._seed_outline_item(
                shifu_bid="course-section-chart",
                outline_item_bid="chapter-1",
                title="Chapter 1",
                position="1",
            )
            self._seed_outline_item(
                shifu_bid="course-section-chart",
                outline_item_bid="lesson-1",
                title="Lesson 1",
                parent_bid="chapter-1",
                position="1.1",
            )
            self._seed_outline_item(
                shifu_bid="course-section-chart",
                outline_item_bid="lesson-2",
                title="Lesson 2",
                parent_bid="chapter-1",
                position="1.2",
            )
            self._seed_outline_item(
                shifu_bid="course-section-chart",
                outline_item_bid="lesson-hidden",
                title="Hidden Lesson",
                parent_bid="chapter-1",
                position="1.3",
                hidden=1,
            )

            # 2 learners with progress in lesson-1, 1 in lesson-2
            db.session.add_all(
                [
                    LearnProgressRecord(
                        progress_record_bid="sec-prog-1",
                        shifu_bid="course-section-chart",
                        outline_item_bid="lesson-1",
                        user_bid="learner-1",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    LearnProgressRecord(
                        progress_record_bid="sec-prog-2",
                        shifu_bid="course-section-chart",
                        outline_item_bid="lesson-1",
                        user_bid="learner-2",
                        status=LEARN_STATUS_COMPLETED,
                        block_position=0,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    LearnProgressRecord(
                        progress_record_bid="sec-prog-3",
                        shifu_bid="course-section-chart",
                        outline_item_bid="lesson-2",
                        user_bid="learner-1",
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=0,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )
            # Follow-up questions
            db.session.add_all(
                [
                    LearnGeneratedBlock(
                        generated_block_bid="sec-ask-1",
                        progress_record_bid="sec-prog-1",
                        user_bid="learner-1",
                        block_bid="",
                        outline_item_bid="lesson-1",
                        shifu_bid="course-section-chart",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=ROLE_STUDENT,
                        generated_content="Q1",
                        position=1,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="sec-ask-2",
                        progress_record_bid="sec-prog-2",
                        user_bid="learner-2",
                        block_bid="",
                        outline_item_bid="lesson-1",
                        shifu_bid="course-section-chart",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=ROLE_STUDENT,
                        generated_content="Q2",
                        position=2,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    LearnGeneratedBlock(
                        generated_block_bid="sec-ask-3",
                        progress_record_bid="sec-prog-2",
                        user_bid="learner-2",
                        block_bid="",
                        outline_item_bid="lesson-1",
                        shifu_bid="course-section-chart",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=ROLE_STUDENT,
                        generated_content="Q3",
                        position=3,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                    # Teacher role - should be excluded from follow-up counts
                    LearnGeneratedBlock(
                        generated_block_bid="sec-ask-teacher",
                        progress_record_bid="sec-prog-1",
                        user_bid="learner-1",
                        block_bid="",
                        outline_item_bid="lesson-1",
                        shifu_bid="course-section-chart",
                        type=BLOCK_TYPE_MDASK_VALUE,
                        role=ROLE_TEACHER,
                        generated_content="Ignore",
                        position=4,
                        block_content_conf="",
                        status=1,
                        deleted=0,
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )
            db.session.commit()

        resp = test_client.get("/api/dashboard/shifus/course-section-chart/detail")
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        sections = payload["data"]["charts"]["sections"]
        assert len(sections) == 2

        lesson1 = next(s for s in sections if s["section_outline_item_bid"] == "lesson-1")
        assert lesson1["section_title"] == "Lesson 1"
        assert lesson1["chapter_title"] == "Chapter 1"
        assert lesson1["learning_user_count"] == 2
        assert lesson1["learning_record_count"] == 2
        assert lesson1["follow_up_user_count"] == 2
        assert lesson1["follow_up_question_count"] == 3

        lesson2 = next(s for s in sections if s["section_outline_item_bid"] == "lesson-2")
        assert lesson2["section_title"] == "Lesson 2"
        assert lesson2["chapter_title"] == "Chapter 1"
        assert lesson2["learning_user_count"] == 1
        assert lesson2["learning_record_count"] == 1
        assert lesson2["follow_up_user_count"] == 0
        assert lesson2["follow_up_question_count"] == 0
