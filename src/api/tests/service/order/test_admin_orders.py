from datetime import datetime
from unittest.mock import MagicMock, patch

from flask import Flask

from flaskr.service.common.dtos import PageNationDTO
from flaskr.service.order.admin import get_order_detail, list_orders
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
                    shifu_bids_mock.return_value = ["shifu-1"]
                    order_model_mock.query = query_mock
                    shifu_map_mock.return_value = {"shifu-1": DummyShifu()}
                    user_map_mock.return_value = {
                        "user-1": {"mobile": "18800001111", "nickname": "Tester"}
                    }

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
                                order_model_mock.query = query_mock
                                creator_mock.return_value = "user-1"
                                shifu_map_mock.return_value = {"shifu-1": DummyShifu()}
                                user_map_mock.return_value = {
                                    "user-1": {
                                        "mobile": "18800001111",
                                        "nickname": "Tester",
                                    }
                                }
                                activities_mock.return_value = []
                                coupons_mock.return_value = []
                                payment_mock.return_value = None

                                detail = get_order_detail(app, "user-1", "order-1")

    assert isinstance(detail, OrderAdminDetailDTO)
    assert isinstance(detail.order, OrderAdminSummaryDTO)
    assert detail.order.order_bid == "order-1"
