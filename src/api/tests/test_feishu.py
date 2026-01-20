from types import SimpleNamespace


def test_send_order_feishu_formats_notification(app, monkeypatch):
    from flaskr.service.order import funs as order_funs

    price_item = SimpleNamespace(
        name="Coupon",
        price_name="Discount",
        price="10",
        is_discount=True,
        discount_code="CODE10",
    )
    order_info = SimpleNamespace(
        user_id="user-1",
        course_id="course-1",
        price="99.00",
        price_item=[price_item],
    )
    aggregate = SimpleNamespace(mobile="13800000000", name="Tester")
    shifu_info = SimpleNamespace(title="Test Course")

    monkeypatch.setattr(order_funs, "query_buy_record", lambda _app, _id: order_info)
    monkeypatch.setattr(order_funs, "load_user_aggregate", lambda _id: aggregate)
    monkeypatch.setattr(order_funs, "get_shifu_info", lambda _app, _cid, _p: shifu_info)

    class FakeQuery:
        def __init__(self, first_value=None, count_value=0):
            self._first_value = first_value
            self._count_value = count_value

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self._first_value

        def count(self):
            return self._count_value

    class FakeColumn:
        def __eq__(self, other):
            return True

        def __ge__(self, other):
            return True

    class FakeUserConversion:
        user_id = FakeColumn()
        query = FakeQuery(first_value=SimpleNamespace(conversion_source="ads"))

    class FakeUserEntity:
        state = FakeColumn()
        deleted = FakeColumn()
        query = FakeQuery(count_value=3)

    monkeypatch.setattr(order_funs, "UserConversion", FakeUserConversion)
    monkeypatch.setattr(order_funs, "UserEntity", FakeUserEntity)

    captured = {}

    def fake_send_notify(_app, title, msgs):
        captured["title"] = title
        captured["msgs"] = msgs

    monkeypatch.setattr(order_funs, "send_notify", fake_send_notify)

    with app.app_context():
        order_funs.send_order_feishu(app, "order-1")

    assert isinstance(captured.get("title"), str)
    assert captured["title"]
    assert any("13800000000" in msg for msg in captured["msgs"])
    assert any("Tester" in msg for msg in captured["msgs"])
    assert any("Test Course" in msg for msg in captured["msgs"])
    assert any("ads" in msg for msg in captured["msgs"])
    assert any("CODE10" in msg for msg in captured["msgs"])
