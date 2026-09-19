"""Protect billing debug admission contracts."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import CreditWalletBucket
from flaskr.service.common.models import ERROR_CODE, raise_error
from flaskr.util.datetime import now_utc

_API_ROOT = Path(__file__).resolve().parents[3]


def test_shifu_preview_routes_gate_creator_debug_usage_with_billing_admission() -> None:
    source = (_API_ROOT / "flaskr/service/shifu/route.py").read_text(encoding="utf-8")
    billing_source = (_API_ROOT / "flaskr/service/billing/api.py").read_text(
        encoding="utf-8"
    )

    assert "from flaskr.service.billing.admission import admit_creator_usage" in source
    assert "admit_creator_preview_usage" in source
    assert "reserve_creator_runtime_slot" not in source
    assert "usage_scene=BILL_USAGE_SCENE_DEBUG" in source
    assert "usage_scene=BILL_USAGE_SCENE_PREVIEW" in billing_source
    assert "assert_creator_debug_allowed(app, creator_bid)" in billing_source
    assert "def _admit_creator_debug_usage() -> None:" in source
    assert (
        "def _admit_creator_preview_usage_for_shifu(shifu_bid: str) -> None:" in source
    )
    assert source.count("_admit_creator_debug_usage()") >= 3
    assert "_admit_creator_preview_usage_for_shifu(shifu_bid)" in source
    assert "def ask_preview_api() -> str:" in source
    assert "def tts_preview_api() -> Response:" in source
    assert "@bypass_token_validation\n    def ask_preview_api():" not in source
    assert "@bypass_token_validation\n    def tts_preview_api():" not in source


@pytest.mark.parametrize("is_creator", [True, False])
@pytest.mark.parametrize("preview", ["ask", "provider_only", "tts"])
@pytest.mark.parametrize(
    "error_key",
    [
        "server.billing.creditInsufficient",
        "server.billing.subscriptionInactive",
        "server.billing.debugDisabledBySoftLimit",
    ],
)
def test_external_previews_reject_unavailable_billing_before_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
    test_client: object,
    is_creator: bool,
    preview: str,
    error_key: str,
) -> None:
    """Use real wallet admission, including paid credits without a subscription."""
    user_bid = f"preview-{uuid4().hex}"
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id=user_bid, language="en-US", is_creator=is_creator
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.billing.admission.is_billing_enabled", lambda: True
    )

    def check_debug_limit(_app: object, creator_bid: str) -> None:
        assert creator_bid == user_bid
        if error_key == "server.billing.debugDisabledBySoftLimit":
            raise_error(error_key)

    monkeypatch.setattr(
        "flaskr.service.shifu.route.assert_creator_debug_allowed", check_debug_limit
    )
    if error_key == "server.billing.subscriptionInactive":
        with test_client.application.app_context(), unit_of_work():
            db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid=f"bucket-{user_bid}",
                    wallet_bid=f"wallet-{user_bid}",
                    creator_bid=user_bid,
                    bucket_category=CREDIT_BUCKET_CATEGORY_TOPUP,
                    status=CREDIT_BUCKET_STATUS_ACTIVE,
                    source_type=CREDIT_SOURCE_TYPE_TOPUP,
                    priority=30,
                    available_credits=Decimal(10),
                    effective_from=now_utc() - timedelta(days=1),
                )
            )

    def unexpected_provider_call(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Rejected previews must not invoke providers or start tracing")

    for target in (
        "flaskr.api.llm.chat_llm",
        "flaskr.service.learn.ask_provider_adapters.stream_ask_provider_response",
        "flaskr.service.shifu.route.get_langfuse_client",
        "flaskr.service.shifu.tts_preview.synthesize_text",
        "flaskr.service.shifu.tts_preview.build_tts_preview_response",
    ):
        monkeypatch.setattr(target, unexpected_provider_call)

    payload = {
        "query": "hello",
        "ask_model": "gpt-test",
        "billable": 0,
        "internal": True,
        "user_bid": "unrelated-user",
        "creator_bid": "unrelated-owner",
        "shifu_bid": "unrelated-course",
    }
    if preview == "provider_only":
        payload["ask_provider_config"] = {
            "provider": "dify",
            "mode": "provider_only",
            "config": {
                "base_url": "https://api.example.com/v1",
                "api_key": "test-api-key",
            },
        }
    endpoint = "tts" if preview == "tts" else "ask"
    response = test_client.post(
        f"/api/shifu/{endpoint}/preview",
        headers={"Token": "preview-token", "X-Internal-Request": "true"},
        json=payload,
    )
    assert response.mimetype == "application/json"
    assert response.get_json()["code"] == ERROR_CODE[error_key]


@pytest.mark.parametrize("preview", ["ask", "tts"])
def test_external_previews_require_an_authenticated_payer(
    monkeypatch: pytest.MonkeyPatch, test_client: object, preview: str
) -> None:
    def reject_auth(_app: object, _token: str) -> None:
        raise_error("server.user.userNotLogin")

    monkeypatch.setattr("flaskr.route.user.validate_user", reject_auth)
    response = test_client.post(
        f"/api/shifu/{preview}/preview",
        json={"query": "hello", "ask_model": "gpt-test", "internal": True},
    )
    assert response.get_json()["code"] == ERROR_CODE["server.user.userNotLogin"]


def test_shifu_ask_preview_routes_pass_debug_usage_context_into_chat_llm() -> None:
    source = (_API_ROOT / "flaskr/service/shifu/route.py").read_text(encoding="utf-8")

    assert "from flaskr.service.metering import UsageContext" in source
    assert 'generation_name="ask_provider_preview"' in source
    assert "usage_context=UsageContext(" in source
    assert source.count("usage_scene=BILL_USAGE_SCENE_DEBUG") >= 2


def test_shifu_tts_preview_helper_records_debug_metering() -> None:
    source = (_API_ROOT / "flaskr/service/shifu/tts_preview.py").read_text(
        encoding="utf-8"
    )

    assert (
        "from flaskr.service.metering import UsageContext, record_tts_usage" in source
    )
    assert source.count("record_tts_usage(") >= 2
    assert "usage_scene=BILL_USAGE_SCENE_DEBUG" in source
