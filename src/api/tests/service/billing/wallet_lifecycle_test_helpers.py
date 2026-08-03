from __future__ import annotations

from decimal import Decimal

from flaskr.service.billing.models import BillingProduct


def _create_monthly_plan_product(
    product_bid: str,
    *,
    credit_amount: Decimal = Decimal("1000.0000000000"),
) -> BillingProduct:
    return BillingProduct(
        product_bid=product_bid,
        product_code=product_bid,
        product_type=1,
        display_name_i18n_key=f"billing.product.{product_bid}",
        description_i18n_key=f"billing.product.{product_bid}.description",
        status=1,
        billing_mode=2,
        billing_interval=2,
        billing_interval_count=1,
        credit_amount=credit_amount,
        currency="CNY",
        price_amount=0,
        allocation_interval=2,
        auto_renew_enabled=1,
    )
