"""Unit-of-work behavior for operator promotion writes (B1 migration)."""

from __future__ import annotations

import pytest
from flaskr import dao
from flaskr.service.promo import admin as promo_admin
from flaskr.service.promo.consts import (
    COUPON_APPLY_TYPE_SPECIFIC,
    COUPON_TYPE_FIXED,
)
from flaskr.service.promo.models import Coupon

_PAYLOAD = {
    "name": "UOW specific batch",
    "usage_type": COUPON_APPLY_TYPE_SPECIFIC,
    "discount_type": COUPON_TYPE_FIXED,
    "value": "20",
    "total_count": 3,
    "scope_type": "all_courses",
    "start_at": "2026-04-24 10:00:00",
    "end_at": "2026-05-24 10:00:00",
    "enabled": True,
}


def _committed_coupon_count(app: object, name: str) -> int:
    with app.app_context(), dao.db.engine.connect() as connection:
        rows = connection.execute(
            Coupon.__table__.select().where(Coupon.name == name)
        ).fetchall()
    return len(rows)


def test_create_coupon_rolls_back_when_the_usage_batch_fails(
    app: object, monkeypatch: object
) -> None:
    """A failure after the header write must leave no coupon behind.

    Pre-migration the header was flushed and the commit never ran, but nothing
    guaranteed a rollback either.
    """

    def failing_batch(*_args: object, **_kwargs: object) -> list[object]:
        message = "usage batch boom"
        raise RuntimeError(message)

    monkeypatch.setattr(promo_admin, "_build_specific_coupon_usages", failing_batch)

    with app.app_context(), pytest.raises(RuntimeError, match="usage batch boom"):
        promo_admin.create_operator_promotion_coupon(app, "operator-uow", _PAYLOAD)

    assert _committed_coupon_count(app, _PAYLOAD["name"]) == 0


def test_create_coupon_commits_header_and_usages_together(app: object) -> None:
    payload = {**_PAYLOAD, "name": "UOW specific batch ok"}

    with app.app_context():
        result = promo_admin.create_operator_promotion_coupon(
            app, "operator-uow", payload
        )

    assert result["coupon_bid"]
    assert _committed_coupon_count(app, payload["name"]) == 1
