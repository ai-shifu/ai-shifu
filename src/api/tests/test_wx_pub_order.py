from decimal import Decimal
from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.order.consts import ORDER_STATUS_INIT
from flaskr.service.order.funs import BuyRecordDTO, generate_charge
from flaskr.service.order.models import Order


def test_generate_charge_uses_pingxx_channel(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    order_bid = "order-wx-pub-1"
    course_bid = "course-wx-pub-1"
    user_bid = "user-wx-pub-1"

    with app.app_context():
        order = Order(
            order_bid=order_bid,
            shifu_bid=course_bid,
            user_bid=user_bid,
            payable_price=Decimal("10.00"),
            paid_price=Decimal("10.00"),
            status=ORDER_STATUS_INIT,
        )
        db.session.add(order)
        db.session.commit()

    monkeypatch.setattr(order_funs, "get_shifu_creator_bid", lambda _app, _bid: "u1")
    monkeypatch.setattr(order_funs, "set_shifu_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        order_funs,
        "get_shifu_info",
        lambda _app, _bid, _preview: SimpleNamespace(
            title="Course", description="Desc"
        ),
    )

    captured = {}

    def fake_generate_pingxx_charge(**kwargs):
        captured.update(kwargs)
        return BuyRecordDTO(
            kwargs["buy_record"].order_bid,
            kwargs["buy_record"].user_bid,
            kwargs["buy_record"].paid_price,
            kwargs["channel"],
            "qr-url",
            payment_channel="pingxx",
        )

    monkeypatch.setattr(
        order_funs, "_generate_pingxx_charge", fake_generate_pingxx_charge
    )

    result = generate_charge(app, order_bid, "wx_wap", "127.0.0.1")
    assert result.channel == "wx_wap"
    assert result.payment_channel == "pingxx"
    assert captured["channel"] == "wx_wap"
