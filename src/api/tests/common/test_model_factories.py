"""The test row factories fill column defaults and let callers override them."""

from flask import Flask

from tests.common.fixtures.model_factories import (
    make_billing_order,
    make_generated_element,
)


def test_factory_rows_carry_column_defaults_before_flush(app: Flask) -> None:
    with app.app_context():
        element = make_generated_element(element_bid="e1", is_final=1)

    assert element.element_bid == "e1"
    assert element.is_final == 1
    # Unset fields hold the column defaults, not None, before any flush.
    assert element.event_type == "element"
    assert element.role == "teacher"
    assert element.status == 1
    assert element.audio_segments == "[]"
    # Callable defaults such as timestamps are left to the database insert.
    assert element.created_at is None


def test_billing_order_factory_round_trips(app: Flask) -> None:
    from flaskr.dao import db
    from flaskr.service.billing.models import BillingOrder

    with app.app_context():
        order = make_billing_order(bill_order_bid="factory-order-1")
        db.session.add(order)
        db.session.flush()
        stored = BillingOrder.query.filter_by(bill_order_bid="factory-order-1").one()
        assert stored is order
        db.session.rollback()
