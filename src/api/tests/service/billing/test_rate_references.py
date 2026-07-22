from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_METRIC_LLM_OUTPUT_TOKENS,
    CREDIT_ROUNDING_MODE_CEIL,
    CREDIT_USAGE_RATE_STATUS_ACTIVE,
)
from flaskr.service.billing.models import CreditUsageRate
from flaskr.service.billing import rate_references
from flaskr.service.common import credit_rate_references
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD, BILL_USAGE_TYPE_LLM


def _rate(
    rate_bid: str, credits_per_unit: str, effective_from: datetime
) -> CreditUsageRate:
    return CreditUsageRate(
        rate_bid=rate_bid,
        usage_type=BILL_USAGE_TYPE_LLM,
        provider="qwen",
        model="deepseek-v4-flash",
        usage_scene=BILL_USAGE_SCENE_PROD,
        billing_metric=BILLING_METRIC_LLM_OUTPUT_TOKENS,
        unit_size=1,
        credits_per_unit=Decimal(credits_per_unit),
        rounding_mode=CREDIT_ROUNDING_MODE_CEIL,
        effective_from=effective_from,
        effective_to=None,
        status=CREDIT_USAGE_RATE_STATUS_ACTIVE,
    )


def test_llm_credit_1x_unit_cost_uses_fixed_config(monkeypatch, app):
    values = {
        "LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS": "0.066667",
        "DEFAULT_LLM_MODEL": "qwen/deepseek-v4-flash",
    }
    monkeypatch.setattr(
        credit_rate_references,
        "get_config",
        lambda key, default=None: values.get(key, default),
    )

    with app.app_context():
        db.session.query(CreditUsageRate).delete()
        db.session.add_all(
            [
                _rate("old-default-rate", "0.000066667", datetime(2026, 1, 1, 0, 0, 0)),
                _rate("new-default-rate", "0.000466669", datetime(2026, 2, 1, 0, 0, 0)),
            ]
        )
        db.session.commit()

        assert rate_references.load_llm_credit_1x_unit_cost() == Decimal("0.000066667")

        values["DEFAULT_LLM_MODEL"] = "ark/doubao-seed-2-0-lite-260428"
        assert rate_references.load_llm_credit_1x_unit_cost() == Decimal("0.000066667")

        db.session.query(CreditUsageRate).delete()
        db.session.commit()
        assert rate_references.load_llm_credit_1x_unit_cost() == Decimal("0.000066667")


def test_llm_credit_1x_unit_cost_rejects_missing_or_invalid_config(monkeypatch):
    for raw_value in [None, "", "bad", "0", "-1"]:
        monkeypatch.setattr(
            credit_rate_references,
            "get_config",
            lambda key, default=None, raw_value=raw_value: (
                raw_value if key == "LLM_CREDIT_1X_PER_1000_OUTPUT_TOKENS" else default
            ),
        )

        assert rate_references.load_llm_credit_1x_unit_cost() is None
