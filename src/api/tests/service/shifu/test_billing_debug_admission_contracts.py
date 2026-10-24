"""Protect billing debug admission contracts."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
    CREDIT_BUCKET_CATEGORY_TOPUP,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_SOURCE_TYPE_MANUAL,
    CREDIT_SOURCE_TYPE_TOPUP,
)
from flaskr.service.billing.models import CreditWalletBucket
from flaskr.service.common.models import ERROR_CODE, raise_error
from flaskr.service.shifu.models import AiCourseAuth, DraftShifu
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
    assert "def _admit_creator_debug_usage(raw_shifu_bid: object) -> str:" in source
    assert (
        "def _admit_creator_preview_usage_for_shifu(shifu_bid: str) -> None:" in source
    )
    assert source.count('_admit_creator_debug_usage(json_data.get("shifu_bid"))') == 2
    assert "_admit_creator_preview_usage_for_shifu(shifu_bid)" in source
    assert "def ask_preview_api() -> str:" in source
    assert "def tts_preview_api() -> Response:" in source
    assert "@bypass_token_validation\n    def ask_preview_api():" not in source
    assert "@bypass_token_validation\n    def tts_preview_api():" not in source


def _seed_preview_course(
    app: object, course: str, owner: str, user: str, permission: str = "edit"
) -> None:
    with app.app_context(), unit_of_work():
        db.session.add(DraftShifu(shifu_bid=course, created_user_bid=owner))
        if permission:
            db.session.add(
                AiCourseAuth(
                    course_id=course,
                    user_id=user,
                    auth_type=json.dumps([permission]),
                    status=1,
                )
            )


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
    owner_bid = f"owner-{uuid4().hex}"
    course_bid = f"course-{uuid4().hex}"
    _seed_preview_course(test_client.application, course_bid, owner_bid, user_bid)
    # The caller's funds cannot override a rejected course owner.
    with test_client.application.app_context(), unit_of_work():
        db.session.add(
            CreditWalletBucket(
                wallet_bucket_bid=f"bucket-{user_bid}",
                wallet_bid=f"wallet-{user_bid}",
                creator_bid=user_bid,
                bucket_category=CREDIT_BUCKET_CATEGORY_SUBSCRIPTION,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                status=CREDIT_BUCKET_STATUS_ACTIVE,
                priority=20,
                available_credits=Decimal(100),
                effective_from=now_utc() - timedelta(days=1),
            )
        )
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
        assert creator_bid == owner_bid
        if error_key == "server.billing.debugDisabledBySoftLimit":
            raise_error(error_key)

    monkeypatch.setattr(
        "flaskr.service.shifu.route.assert_creator_debug_allowed", check_debug_limit
    )
    if error_key == "server.billing.subscriptionInactive":
        with test_client.application.app_context(), unit_of_work():
            db.session.add(
                CreditWalletBucket(
                    wallet_bucket_bid=f"bucket-{owner_bid}",
                    wallet_bid=f"wallet-{owner_bid}",
                    creator_bid=owner_bid,
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
        "shifu_bid": course_bid,
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


@pytest.mark.parametrize("preview", ["ask", "tts"])
@pytest.mark.parametrize(
    "course_input", [None, "", "   ", "foreign", "view_only", "query_mismatch"]
)
def test_settings_preview_requires_edit_permission_on_the_billed_course(
    monkeypatch: pytest.MonkeyPatch,
    test_client: object,
    preview: str,
    course_input: str | None,
) -> None:
    user_bid = f"actor-{uuid4().hex}"
    course_bid = f"course-{uuid4().hex}"
    permission = "view" if course_input == "view_only" else ""
    _seed_preview_course(
        test_client.application, course_bid, "other-owner", user_bid, permission
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda *_args: SimpleNamespace(
            user_id=user_bid, language="en-US", is_creator=True
        ),
    )

    def unexpected_call(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Unauthorized course must not reach billing or providers")

    for target in (
        "flaskr.service.shifu.route.assert_creator_debug_allowed",
        "flaskr.service.shifu.route.admit_creator_usage",
        "flaskr.api.llm.chat_llm",
        "flaskr.service.shifu.tts_preview.build_tts_preview_response",
    ):
        monkeypatch.setattr(target, unexpected_call)
    body_course = (
        course_bid
        if course_input in {"foreign", "view_only", "query_mismatch"}
        else course_input
    )
    url = f"/api/shifu/{preview}/preview"
    if course_input == "query_mismatch":
        own_course = f"owned-{uuid4().hex}"
        _seed_preview_course(test_client.application, own_course, user_bid, user_bid)
        url += f"?shifu_bid={own_course}"
    response = test_client.post(
        url,
        headers={"Token": "preview-token"},
        json={
            "shifu_bid": body_course,
            "query": "hello",
            "ask_model": "gpt-test",
            "creator_bid": user_bid,
            "billable": 0,
            "internal": True,
        },
    )
    expected = (
        "server.shifu.noPermission" if body_course else "server.common.paramsError"
    )
    if course_input == "   ":
        expected = "server.common.paramsError"
    assert response.get_json()["code"] == ERROR_CODE[expected]
