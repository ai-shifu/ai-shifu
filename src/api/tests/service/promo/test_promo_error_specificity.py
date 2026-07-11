from __future__ import annotations

from decimal import Decimal

import pytest

import flaskr.service.promo.admin as promo_admin
from flaskr.dao import db
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.promo.consts import COUPON_STATUS_ACTIVE, COUPON_TYPE_FIXED
from flaskr.service.promo.models import Coupon, CouponUsage


@pytest.fixture(autouse=True)
def _isolate_coupon_tables(app):
    with app.app_context():
        CouponUsage.query.delete()
        Coupon.query.delete()
        db.session.commit()
    yield
    with app.app_context():
        CouponUsage.query.delete()
        Coupon.query.delete()
        db.session.commit()


def test_generate_unique_coupon_code_failure_returns_specific_error(app, monkeypatch):
    monkeypatch.setattr(
        promo_admin, "_generate_random_coupon_code", lambda: "DUPLICATE"
    )

    with app.app_context():
        db.session.add(
            Coupon(
                coupon_bid="coupon-duplicate",
                code="DUPLICATE",
                name="Duplicate Coupon",
                discount_type=COUPON_TYPE_FIXED,
                value=1,
                status=COUPON_STATUS_ACTIVE,
                filter="{}",
                total_count=1,
                used_count=0,
                deleted=0,
            )
        )
        db.session.commit()

        with pytest.raises(AppException) as exc_info:
            promo_admin._generate_unique_coupon_code()

    assert (
        exc_info.value.code == ERROR_CODE["server.discount.couponCodeGenerationFailed"]
    )


def test_generate_unique_coupon_codes_failure_returns_specific_error(app, monkeypatch):
    generated_codes = [f"DUP{i:03d}" for i in range(400)]
    code_iter = iter(generated_codes)
    monkeypatch.setattr(
        promo_admin, "_generate_random_coupon_code", lambda: next(code_iter)
    )

    with app.app_context():
        db.session.bulk_save_objects(
            [
                CouponUsage(
                    coupon_usage_bid=f"usage-duplicate-{idx}",
                    coupon_bid="coupon-specific",
                    code=code,
                    name="Duplicate Usage",
                    discount_type=COUPON_TYPE_FIXED,
                    value=Decimal("1"),
                    status=COUPON_STATUS_ACTIVE,
                    deleted=0,
                )
                for idx, code in enumerate(generated_codes)
            ]
        )
        db.session.commit()

        with pytest.raises(AppException) as exc_info:
            promo_admin._generate_unique_coupon_codes(1)

    assert (
        exc_info.value.code == ERROR_CODE["server.discount.couponCodeGenerationFailed"]
    )
