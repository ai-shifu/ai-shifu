from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.order.admin import (
    ORDER_SOURCE_COUPON_REDEEM,
    ORDER_SOURCE_IMPORT_ACTIVATION,
    ORDER_SOURCE_OPEN_API,
    ORDER_SOURCE_USER_PURCHASE,
    get_operator_order_detail,
    get_order_detail,
    list_operator_orders,
    list_orders,
    _resolve_order_source,
)
from flaskr.service.order.admin_dtos import OrderAdminDetailDTO, OrderAdminSummaryDTO


class DummyOrder:
    def __init__(self):
        self.order_bid = "order-1"
        self.shifu_bid = "shifu-1"
        self.user_bid = "user-1"
        self.payable_price = "100.00"
        self.paid_price = "80.00"
        self.payment_channel = "stripe"
        self.status = 502
        self.deleted = 0
        self.created_at = datetime(2025, 1, 1, 12, 0, 0)
        self.updated_at = datetime(2025, 1, 2, 12, 0, 0)


class DummyShifu:
    def __init__(self):
        self.title = "Demo Course"


def _mock_operator(
    monkeypatch,
    user_id: str = "operator-1",
    *,
    is_operator: bool = True,
) -> None:
    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_operator=is_operator,
        is_creator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )


def test_list_orders_returns_page_dto():
    app = Flask(__name__)
    order = DummyOrder()

    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.count.return_value = 1
    query_mock.order_by.return_value = query_mock
    query_mock.offset.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.all.return_value = [order]

    with patch(
        "flaskr.service.order.admin.get_user_created_shifu_bids"
    ) as shifu_bids_mock:
        with patch("flaskr.service.order.admin.Order") as order_model_mock:
            with patch("flaskr.service.order.admin._load_shifu_map") as shifu_map_mock:
                with patch(
                    "flaskr.service.order.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.order.admin._load_coupon_code_map"
                    ) as coupon_map_mock:
                        shifu_bids_mock.return_value = ["shifu-1"]
                        order_model_mock.query = query_mock
                        shifu_map_mock.return_value = {"shifu-1": DummyShifu()}
                        user_map_mock.return_value = {
                            "user-1": {"mobile": "18800001111", "nickname": "Tester"}
                        }
                        coupon_map_mock.return_value = {}

                        result = list_orders(app, "user-1", 1, 20, {})

    assert isinstance(result, PageNationDTO)
    assert result.total == 1
    assert len(result.data) == 1
    assert isinstance(result.data[0], OrderAdminSummaryDTO)


def test_get_order_detail_returns_detail_dto():
    app = Flask(__name__)
    order = DummyOrder()

    query_mock = MagicMock()
    query_mock.filter.return_value.first.return_value = order

    with patch("flaskr.service.order.admin.Order") as order_model_mock:
        with patch("flaskr.service.order.admin.get_shifu_creator_bid") as creator_mock:
            with patch("flaskr.service.order.admin._load_shifu_map") as shifu_map_mock:
                with patch(
                    "flaskr.service.order.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.order.admin._load_order_activities"
                    ) as activities_mock:
                        with patch(
                            "flaskr.service.order.admin._load_order_coupons"
                        ) as coupons_mock:
                            with patch(
                                "flaskr.service.order.admin._load_payment_detail"
                            ) as payment_mock:
                                with patch(
                                    "flaskr.service.order.admin._load_coupon_code_map"
                                ) as coupon_map_mock:
                                    order_model_mock.query = query_mock
                                    creator_mock.return_value = "user-1"
                                    shifu_map_mock.return_value = {
                                        "shifu-1": DummyShifu()
                                    }
                                    user_map_mock.return_value = {
                                        "user-1": {
                                            "mobile": "18800001111",
                                            "nickname": "Tester",
                                        }
                                    }
                                    activities_mock.return_value = []
                                    coupons_mock.return_value = []
                                    payment_mock.return_value = None
                                    coupon_map_mock.return_value = {}

                                    detail = get_order_detail(app, "user-1", "order-1")

    assert isinstance(detail, OrderAdminDetailDTO)
    assert isinstance(detail.order, OrderAdminSummaryDTO)
    assert detail.order.order_bid == "order-1"


def test_list_operator_orders_returns_page_dto():
    app = Flask(__name__)
    order = DummyOrder()

    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.count.return_value = 1
    query_mock.order_by.return_value = query_mock
    query_mock.offset.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.all.return_value = [order]

    with patch("flaskr.service.order.admin.Order") as order_model_mock:
        with patch("flaskr.service.order.admin._load_shifu_map") as shifu_map_mock:
            with patch("flaskr.service.order.admin._load_user_map") as user_map_mock:
                with patch(
                    "flaskr.service.order.admin._load_coupon_code_map"
                ) as coupon_map_mock:
                    order_model_mock.query = query_mock
                    shifu_map_mock.return_value = {"shifu-1": DummyShifu()}
                    user_map_mock.return_value = {
                        "user-1": {
                            "mobile": "18800001111",
                            "email": "",
                            "nickname": "Tester",
                        }
                    }
                    coupon_map_mock.return_value = {}

                    result = list_operator_orders(app, 1, 20, {})

    assert isinstance(result, PageNationDTO)
    assert result.total == 1
    assert len(result.data) == 1
    assert isinstance(result.data[0], OrderAdminSummaryDTO)


def test_list_operator_orders_returns_derived_source_and_coupon_codes():
    app = Flask(__name__)
    order = DummyOrder()
    order.payment_channel = "pingxx"
    order.paid_price = "0"

    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.count.return_value = 1
    query_mock.order_by.return_value = query_mock
    query_mock.offset.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.all.return_value = [order]

    with patch("flaskr.service.order.admin.Order") as order_model_mock:
        with patch("flaskr.service.order.admin._load_shifu_map") as shifu_map_mock:
            with patch("flaskr.service.order.admin._load_user_map") as user_map_mock:
                with patch(
                    "flaskr.service.order.admin._load_coupon_code_map"
                ) as coupon_map_mock:
                    order_model_mock.query = query_mock
                    shifu_map_mock.return_value = {"shifu-1": DummyShifu()}
                    user_map_mock.return_value = {
                        "user-1": {
                            "mobile": "18800001111",
                            "email": "",
                            "nickname": "Tester",
                        }
                    }
                    coupon_map_mock.return_value = {"order-1": ["FREE100"]}

                    result = list_operator_orders(app, 1, 20, {})

    assert result.total == 1
    assert result.data[0].order_source == ORDER_SOURCE_COUPON_REDEEM
    assert (
        result.data[0].order_source_key == "module.operationsOrder.source.couponRedeem"
    )
    assert result.data[0].coupon_codes == ["FREE100"]


def test_list_operator_orders_applies_order_source_filter():
    app = Flask(__name__)
    order = DummyOrder()

    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.count.return_value = 1
    query_mock.order_by.return_value = query_mock
    query_mock.offset.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.all.return_value = [order]

    with patch("flaskr.service.order.admin.Order") as order_model_mock:
        with patch(
            "flaskr.service.order.admin._apply_order_source_filter"
        ) as apply_order_source_filter_mock:
            with patch("flaskr.service.order.admin._load_shifu_map") as shifu_map_mock:
                with patch(
                    "flaskr.service.order.admin._load_user_map"
                ) as user_map_mock:
                    with patch(
                        "flaskr.service.order.admin._load_coupon_code_map"
                    ) as coupon_map_mock:
                        order_model_mock.query = query_mock
                        apply_order_source_filter_mock.return_value = query_mock
                        shifu_map_mock.return_value = {"shifu-1": DummyShifu()}
                        user_map_mock.return_value = {
                            "user-1": {
                                "mobile": "18800001111",
                                "email": "",
                                "nickname": "Tester",
                            }
                        }
                        coupon_map_mock.return_value = {}

                        result = list_operator_orders(
                            app,
                            1,
                            20,
                            {"order_source": ORDER_SOURCE_COUPON_REDEEM},
                        )

    apply_order_source_filter_mock.assert_called_once_with(
        query_mock, ORDER_SOURCE_COUPON_REDEEM
    )
    assert isinstance(result, PageNationDTO)


def test_get_operator_order_detail_returns_detail_dto():
    app = Flask(__name__)
    order = DummyOrder()

    query_mock = MagicMock()
    query_mock.filter.return_value.first.return_value = order

    with patch("flaskr.service.order.admin.Order") as order_model_mock:
        with patch("flaskr.service.order.admin._load_shifu_map") as shifu_map_mock:
            with patch("flaskr.service.order.admin._load_user_map") as user_map_mock:
                with patch(
                    "flaskr.service.order.admin._load_order_activities"
                ) as activities_mock:
                    with patch(
                        "flaskr.service.order.admin._load_order_coupons"
                    ) as coupons_mock:
                        with patch(
                            "flaskr.service.order.admin._load_payment_detail"
                        ) as payment_mock:
                            with patch(
                                "flaskr.service.order.admin._load_coupon_code_map"
                            ) as coupon_map_mock:
                                order_model_mock.query = query_mock
                                shifu_map_mock.return_value = {"shifu-1": DummyShifu()}
                                user_map_mock.return_value = {
                                    "user-1": {
                                        "mobile": "18800001111",
                                        "email": "",
                                        "nickname": "Tester",
                                    }
                                }
                                activities_mock.return_value = []
                                coupons_mock.return_value = []
                                payment_mock.return_value = None
                                coupon_map_mock.return_value = {}

                                detail = get_operator_order_detail(app, "order-1")

    assert isinstance(detail, OrderAdminDetailDTO)
    assert isinstance(detail.order, OrderAdminSummaryDTO)
    assert detail.order.order_bid == "order-1"


def test_admin_operation_orders_route_requires_operator(
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch, is_operator=False)

    response = test_client.get(
        "/api/shifu/admin/operations/orders",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_admin_operation_order_detail_route_requires_operator(
    test_client,
    monkeypatch,
):
    _mock_operator(monkeypatch, is_operator=False)

    response = test_client.get(
        "/api/shifu/admin/operations/orders/order-1/detail",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_resolve_order_source_prefers_manual_open_api_and_coupon():
    source, _ = _resolve_order_source(
        payment_channel="manual",
        coupon_codes=[],
        paid_price="0",
    )
    assert source == ORDER_SOURCE_IMPORT_ACTIVATION

    source, _ = _resolve_order_source(
        payment_channel="open_api",
        coupon_codes=[],
        paid_price="0",
    )
    assert source == ORDER_SOURCE_OPEN_API

    source, _ = _resolve_order_source(
        payment_channel="pingxx",
        coupon_codes=["FREE100"],
        paid_price="0",
    )
    assert source == ORDER_SOURCE_COUPON_REDEEM

    source, _ = _resolve_order_source(
        payment_channel="pingxx",
        coupon_codes=[],
        paid_price="0.5",
    )
    assert source == ORDER_SOURCE_USER_PURCHASE
