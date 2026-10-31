"""Parse the paid amount that Alipay and WeChat Pay report for a native trade."""

import pytest
from flaskr.service.common.native_payment_status import extract_native_paid_amount


@pytest.mark.parametrize(
    ("provider", "payload", "expected"),
    [
        ("alipay", {"trade": {"total_amount": "99.00"}}, 9900),
        ("alipay", {"trade": {"total_amount": "0.01"}}, 1),
        ("alipay", {"trade": {"total_amount": ""}}, None),
        ("alipay", {"trade": {"trade_status": "TRADE_SUCCESS"}}, None),
        # A WeChat-funded coupon lowers payer_total; total is the order amount.
        (
            "wechatpay",
            {"trade": {"amount": {"total": 9900, "payer_total": 9800}}},
            9900,
        ),
        ("wechatpay", {"trade": {"amount": {"payer_total": 9800}}}, 9800),
        # Webhook notifications carry the decrypted trade under "resource".
        ("wechatpay", {"resource": {"amount": {"total": 990}}}, 990),
        ("wechatpay", {"trade": {"amount": "990"}}, None),
        ("wechatpay", {"trade": {"trade_state": "SUCCESS"}}, None),
        ("pingxx", {"trade": {"total_amount": "99.00"}}, None),
    ],
)
def test_extract_native_paid_amount(
    provider: str, payload: dict[str, object], expected: int | None
) -> None:
    assert extract_native_paid_amount(provider, payload) == expected
