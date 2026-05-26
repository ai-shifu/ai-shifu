from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from flask import Flask

import flaskr.common.config as common_config


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


def test_shifu_publish_url_builder_uses_public_base():
    from flaskr.service.shifu.shifu_publish_funcs import _build_frontend_url

    assert (
        _build_frontend_url("https://example.com/", "/c/course-1")
        == "https://example.com/c/course-1"
    )
