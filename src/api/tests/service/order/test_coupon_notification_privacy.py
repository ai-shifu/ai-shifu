"""Verify coupon notifications disclose only masked correlation fields."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from flaskr.service.order import coupon_funcs


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("13812348000", "138****8000"),
        ("123456", "1****6"),
        ("1234", "****"),
        ("", "****"),
    ],
)
def test_coupon_notification_mobile_mask(value: str, expected: str) -> None:
    assert coupon_funcs._mask_coupon_notification_mobile(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PRIVATE-COUPON-7890", "****7890"),
        ("ABCD", "****"),
        ("", "****"),
    ],
)
def test_coupon_notification_code_mask(value: str, expected: str) -> None:
    assert coupon_funcs._mask_coupon_notification_code(value) == expected


def test_coupon_notification_omits_full_identity_and_promotion_details(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        coupon_funcs,
        "load_user_aggregate",
        lambda _user_id: SimpleNamespace(
            mobile="13812348000",
            name="Private Learner Name",
        ),
    )
    monkeypatch.setattr(
        coupon_funcs,
        "send_notify",
        lambda _app, title, messages: captured.update(
            {"title": title, "messages": messages}
        ),
    )

    coupon_funcs.send_feishu_coupon_code(
        app,
        "private-user-id",
        "PRIVATE-COUPON-7890",
    )

    assert captured == {
        "title": "优惠码通知",
        "messages": ["手机号：138****8000", "优惠码：****7890"],
    }
    notification = str(captured)
    for private_value in (
        "13812348000",
        "Private Learner Name",
        "PRIVATE-COUPON-7890",
        "private-user-id",
    ):
        assert private_value not in notification


def test_missing_coupon_notification_user_does_not_log_identifier(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user_id = "private-missing-user-id"
    monkeypatch.setattr(coupon_funcs, "load_user_aggregate", lambda _user_id: None)
    monkeypatch.setattr(
        coupon_funcs,
        "send_notify",
        lambda *_args: pytest.fail("notification should not be sent"),
    )
    app.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING):
            coupon_funcs.send_feishu_coupon_code(app, user_id, "PRIVATE-CODE")
    finally:
        app.logger.removeHandler(caplog.handler)

    assert "feishu coupon notify skipped" in caplog.text
    assert user_id not in caplog.text
