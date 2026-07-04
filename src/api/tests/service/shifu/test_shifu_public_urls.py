from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flask import Flask

import flaskr.dao as dao
import flaskr.common.config as common_config
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PREVIEW


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)  # noqa: SLF001


@pytest.fixture(autouse=True)
def clear_public_url_config_cache():
    _reset_config_cache("HOST_URL")
    yield
    _reset_config_cache("HOST_URL")


def _make_draft(shifu_bid: str = "course-1") -> SimpleNamespace:
    return SimpleNamespace(
        shifu_bid=shifu_bid,
        title="Test Course",
        description="desc",
        avatar_res_bid="avatar-1",
        keywords="test",
        llm="gpt-test",
        llm_temperature=Decimal("0.30"),
        price=Decimal("1.00"),
        llm_system_prompt="",
        created_user_bid="owner-1",
        tts_enabled=False,
        tts_provider="",
        tts_model="",
        tts_voice_id="",
        tts_speed=None,
        tts_pitch=0,
        tts_emotion="",
        use_learner_language=0,
        ask_enabled_status=5101,
        ask_llm="",
        ask_llm_temperature=Decimal("0.00"),
        ask_llm_system_prompt="",
        ask_provider_config="{}",
    )


def _seed_preview_route_course(
    app,
    *,
    shifu_bid: str,
    owner_bid: str,
    collaborator_bid: str,
) -> None:
    from flaskr.service.shifu.models import AiCourseAuth, DraftShifu

    with app.app_context():
        AiCourseAuth.query.filter_by(course_id=shifu_bid).delete()
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        dao.db.session.add(
            DraftShifu(
                shifu_bid=shifu_bid,
                title="Preview Route Course",
                description="desc",
                avatar_res_bid="avatar-1",
                keywords="test",
                llm="gpt-test",
                llm_temperature=Decimal("0"),
                llm_system_prompt="",
                price=Decimal("0"),
                created_user_bid=owner_bid,
                updated_user_bid=owner_bid,
            )
        )
        dao.db.session.add(
            AiCourseAuth(
                course_auth_id=f"auth-{shifu_bid}-{collaborator_bid}",
                course_id=shifu_bid,
                user_id=collaborator_bid,
                auth_type=json.dumps(["view"]),
                status=1,
            )
        )
        dao.db.session.commit()


def _build_detail_for_base_url(monkeypatch, base_url: str):
    from flaskr.service.shifu import shifu_draft_funcs

    monkeypatch.setattr(
        shifu_draft_funcs,
        "get_shifu_res_url",
        lambda _resource_bid: "",
        raising=False,
    )
    return shifu_draft_funcs.return_shifu_draft_dto(
        _make_draft(),
        base_url,
        readonly=False,
    )


def test_shifu_detail_urls_prefer_host_url(monkeypatch):
    from flaskr.service.shifu.route import _get_request_base_url

    monkeypatch.setenv("HOST_URL", "https://example.com/")
    _reset_config_cache("HOST_URL")

    app = Flask(__name__)
    with app.test_request_context(
        "/api/shifu/shifus/course-1/detail",
        base_url="http://internal.local",
    ):
        detail = _build_detail_for_base_url(monkeypatch, _get_request_base_url())

    assert detail.url == "https://example.com/c/course-1"
    assert detail.preview_url == "https://example.com/c/course-1?preview=true"


def test_shifu_detail_urls_use_forwarded_https_origin(monkeypatch):
    from flaskr.service.shifu.route import _get_request_base_url

    monkeypatch.delenv("HOST_URL", raising=False)
    _reset_config_cache("HOST_URL")

    app = Flask(__name__)
    with app.test_request_context(
        "/api/shifu/shifus/course-1/detail",
        base_url="http://internal.local",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "forwarded.example.com",
        },
    ):
        detail = _build_detail_for_base_url(monkeypatch, _get_request_base_url())

    assert detail.url == "https://forwarded.example.com/c/course-1"
    assert detail.preview_url == "https://forwarded.example.com/c/course-1?preview=true"


def test_shifu_preview_endpoint_url_uses_public_base(monkeypatch):
    from flaskr.service.shifu import shifu_publish_funcs
    from flaskr.service.shifu.route import _get_request_base_url

    monkeypatch.delenv("HOST_URL", raising=False)
    _reset_config_cache("HOST_URL")
    monkeypatch.setattr(
        shifu_publish_funcs,
        "get_latest_shifu_draft",
        lambda _shifu_id: _make_draft(_shifu_id),
        raising=False,
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/shifu/shifus/course-1/preview",
        method="POST",
        base_url="http://internal.local",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "forwarded.example.com",
        },
    ):
        preview_url = shifu_publish_funcs.preview_shifu_draft(
            app,
            "user-1",
            "course-1",
            {},
            _get_request_base_url(),
        )

    assert preview_url == "https://forwarded.example.com/c/course-1?preview=true"


def test_shifu_preview_endpoint_admits_course_owner_usage_for_collaborator(
    monkeypatch,
    test_client,
    app,
):
    shifu_bid = "preview-route-owner-admission"
    owner_bid = "owner-preview-route-admission"
    collaborator_bid = "collaborator-preview-route-admission"
    captured: dict[str, object] = {}
    _seed_preview_route_course(
        app,
        shifu_bid=shifu_bid,
        owner_bid=owner_bid,
        collaborator_bid=collaborator_bid,
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id=collaborator_bid,
            is_creator=True,
            is_operator=False,
            language="en-US",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.service.shifu.route.admit_creator_usage",
        lambda _app, **kwargs: captured.setdefault("admission", kwargs),
        raising=False,
    )

    resp = test_client.post(
        f"/api/shifu/shifus/{shifu_bid}/preview",
        headers={"Token": "test-token"},
        json={"variables": {}},
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"].endswith(f"/c/{shifu_bid}?preview=true")
    assert captured["admission"] == {
        "shifu_bid": shifu_bid,
        "usage_scene": BILL_USAGE_SCENE_PREVIEW,
    }


def test_shifu_publish_url_builder_uses_public_base():
    from flaskr.service.shifu.shifu_publish_funcs import _build_frontend_url

    assert (
        _build_frontend_url("https://example.com/", "/c/course-1")
        == "https://example.com/c/course-1"
    )


def _seed_white_label(
    app,
    *,
    creator_bid: str,
    host: str,
    custom_domain_enabled: bool = True,
    binding_status: int | None = None,
) -> None:
    from datetime import datetime, timedelta

    from flaskr.service.billing.consts import (
        BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
        BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
        CREDIT_SOURCE_TYPE_MANUAL,
    )
    from flaskr.service.billing.models import (
        BillingDomainBinding,
        BillingEntitlement,
    )

    status = (
        binding_status
        if binding_status is not None
        else BILLING_DOMAIN_BINDING_STATUS_VERIFIED
    )
    with app.app_context():
        BillingDomainBinding.query.filter_by(creator_bid=creator_bid).delete()
        BillingEntitlement.query.filter_by(creator_bid=creator_bid).delete()
        now = datetime.now()
        dao.db.session.add(
            BillingEntitlement(
                entitlement_bid=f"ent-{creator_bid}",
                creator_bid=creator_bid,
                source_type=CREDIT_SOURCE_TYPE_MANUAL,
                source_bid="",
                branding_enabled=1,
                custom_domain_enabled=1 if custom_domain_enabled else 0,
                effective_from=now - timedelta(days=1),
                effective_to=None,
            )
        )
        dao.db.session.add(
            BillingDomainBinding(
                domain_binding_bid=f"bind-{creator_bid}",
                creator_bid=creator_bid,
                host=host,
                status=status,
                verification_method=BILLING_DOMAIN_VERIFICATION_METHOD_DNS_TXT,
                verification_token="token-test",
            )
        )
        dao.db.session.commit()


def test_resolve_effective_custom_origin_returns_verified_host(app):
    from flaskr.service.billing.domains import resolve_effective_custom_origin

    creator_bid = "wl-owner-verified"
    _seed_white_label(app, creator_bid=creator_bid, host="learn.acme.test")

    assert (
        resolve_effective_custom_origin(app, creator_bid) == "https://learn.acme.test"
    )


def test_resolve_effective_custom_origin_none_when_entitlement_disabled(app):
    from flaskr.service.billing.domains import resolve_effective_custom_origin

    creator_bid = "wl-owner-disabled"
    _seed_white_label(
        app,
        creator_bid=creator_bid,
        host="disabled.acme.test",
        custom_domain_enabled=False,
    )

    assert resolve_effective_custom_origin(app, creator_bid) is None


def test_resolve_effective_custom_origin_none_when_binding_pending(app):
    from flaskr.service.billing.consts import (
        BILLING_DOMAIN_BINDING_STATUS_PENDING,
    )
    from flaskr.service.billing.domains import resolve_effective_custom_origin

    creator_bid = "wl-owner-pending"
    _seed_white_label(
        app,
        creator_bid=creator_bid,
        host="pending.acme.test",
        binding_status=BILLING_DOMAIN_BINDING_STATUS_PENDING,
    )

    assert resolve_effective_custom_origin(app, creator_bid) is None


def test_publish_base_url_prefers_custom_domain(app, monkeypatch):
    from flaskr.common.shifu_context import clear_shifu_context, set_shifu_context
    from flaskr.service.shifu.route import _resolve_publish_base_url

    creator_bid = "wl-owner-publish"
    _seed_white_label(app, creator_bid=creator_bid, host="pub.acme.test")
    monkeypatch.setenv("HOST_URL", "https://example.com/")
    _reset_config_cache("HOST_URL")

    set_shifu_context("course-x", creator_bid)
    try:
        with app.app_context():
            assert _resolve_publish_base_url(app) == "https://pub.acme.test"
    finally:
        clear_shifu_context()


def test_publish_base_url_falls_back_without_custom_domain(app, monkeypatch):
    from flaskr.common.shifu_context import clear_shifu_context, set_shifu_context
    from flaskr.service.shifu.route import _resolve_publish_base_url

    monkeypatch.setenv("HOST_URL", "https://example.com/")
    _reset_config_cache("HOST_URL")

    set_shifu_context("course-y", "wl-owner-without-domain")
    try:
        with app.app_context():
            assert _resolve_publish_base_url(app) == "https://example.com"
    finally:
        clear_shifu_context()
