from __future__ import annotations

from pathlib import Path

from flaskr.service.billing.consts import (
    BILLING_TRIAL_PRODUCT_BID,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
    BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT,
    BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS,
)

_API_ROOT = Path(__file__).resolve().parents[3]


def test_billing_trial_product_contract_stays_runtime_defined_without_branch_migration() -> (
    None
):
    assert BILLING_TRIAL_PRODUCT_BID == "bill-product-plan-trial"
    assert BILLING_TRIAL_PRODUCT_CODE == "creator-plan-trial"
    assert BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG == "public_trial_offer"
    assert BILLING_TRIAL_PRODUCT_METADATA_VALID_DAYS == "trial_valid_days"
    assert BILLING_TRIAL_PRODUCT_METADATA_STARTS_ON_FIRST_GRANT == (
        "starts_on_first_grant"
    )
    assert not (
        _API_ROOT / "migrations/versions/d2b9a5c4f8e1_productize_creator_trial_plan.py"
    ).exists()
