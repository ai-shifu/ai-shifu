"""Verify account-backed model gateway HTTP contracts."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.route.model_gateway import register_model_gateway_handler
from flaskr.service.billing.consts import (
    CREDIT_BUCKET_CATEGORY_FREE,
    CREDIT_BUCKET_STATUS_ACTIVE,
)
from flaskr.service.billing.models import CreditWallet, CreditWalletBucket


@pytest.fixture
def gateway_route_app(monkeypatch: pytest.MonkeyPatch) -> Flask:
    import flaskr.route.model_gateway as gateway

    app = Flask(__name__)
    app.testing = True
    monkeypatch.setattr(
        gateway,
        "validate_user",
        lambda _app, token: SimpleNamespace(
            user_id="gateway-user" if token == "valid-token" else "",
            name="Gateway User",
            language="zh-CN",
        ),
    )
    monkeypatch.setattr(
        gateway,
        "_account_payload",
        lambda _app, user: {
            "user": {"user_id": user.user_id},
            "wallet": {"available_credits": 10, "reserved_credits": 1},
            "billing_url": "https://example.test/admin/billing",
        },
    )
    monkeypatch.setattr(
        gateway,
        "_gateway_models",
        lambda _app: [
            {
                "id": "rated-model",
                "object": "model",
                "owned_by": "ai-shifu",
                "display_name": "Rated Model",
                "credit_multiplier": 2,
            }
        ],
    )
    register_model_gateway_handler(app)
    return app


def _headers(**extra: str) -> dict[str, str]:
    return {"Authorization": "Bearer valid-token", **extra}


def test_gateway_account_and_models_contracts(gateway_route_app: Flask) -> None:
    client = gateway_route_app.test_client()

    account = client.get("/api/gateway/account", headers=_headers())
    models = client.get("/api/gateway/v1/models", headers=_headers())

    assert account.status_code == 200
    assert json.loads(account.data)["data"]["wallet"] == {
        "available_credits": 10,
        "reserved_credits": 1,
    }
    assert models.status_code == 200
    assert models.get_json()["data"][0]["id"] == "rated-model"


def test_gateway_rejects_missing_bearer_token(gateway_route_app: Flask) -> None:
    response = gateway_route_app.test_client().get("/api/gateway/v1/models")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_token"


def test_gateway_non_stream_chat_dispatches_openai_payload(
    gateway_route_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.route.model_gateway as gateway

    captured: dict[str, object] = {}

    def prepare(
        _app: Flask,
        *,
        creator_bid: str,
        idempotency_key: str,
        payload: dict[str, object],
    ) -> object:
        captured.update(
            creator_bid=creator_bid,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        return SimpleNamespace(request_id=idempotency_key)

    monkeypatch.setattr(gateway, "prepare_gateway_chat_request", prepare)
    monkeypatch.setattr(
        gateway,
        "complete_gateway_chat_request",
        lambda _app, _reservation: {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hello"},
                    "finish_reason": "stop",
                }
            ],
        },
    )

    response = gateway_route_app.test_client().post(
        "/api/gateway/v1/chat/completions",
        headers=_headers(**{"Idempotency-Key": "request-1"}),
        json={
            "model": "rated-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["id"] == "chatcmpl-1"
    assert captured == {
        "creator_bid": "gateway-user",
        "idempotency_key": "request-1",
        "payload": {
            "model": "rated-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        },
    }


def test_gateway_stream_chat_emits_sse_and_done(
    gateway_route_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.route.model_gateway as gateway

    monkeypatch.setattr(
        gateway,
        "prepare_gateway_chat_request",
        lambda _app, **kwargs: SimpleNamespace(request_id=kwargs["idempotency_key"]),
    )
    monkeypatch.setattr(
        gateway,
        "stream_gateway_chat_request",
        lambda _app, _reservation: iter(
            [
                {
                    "id": "chatcmpl-stream",
                    "object": "chat.completion.chunk",
                    "choices": [{"index": 0, "delta": {"content": "hello"}}],
                }
            ]
        ),
    )

    response = gateway_route_app.test_client().post(
        "/api/gateway/v1/chat/completions",
        headers=_headers(**{"Idempotency-Key": "request-stream"}),
        json={
            "model": "rated-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert b'"content": "hello"' in response.data
    assert response.data.endswith(b"data: [DONE]\n\n")
    assert response.headers["X-AI-Shifu-Request-ID"] == "request-stream"


def test_gateway_maps_credit_error_to_http_402(
    gateway_route_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.route.model_gateway as gateway
    from flaskr.service.common.models import raise_error

    def reject(*_args: object, **_kwargs: object) -> object:
        raise_error("server.billing.creditInsufficient")

    monkeypatch.setattr(gateway, "prepare_gateway_chat_request", reject)
    monkeypatch.setattr(
        gateway,
        "build_public_url",
        lambda path: f"https://example.test{path}",
    )

    response = gateway_route_app.test_client().post(
        "/api/gateway/v1/chat/completions",
        headers=_headers(**{"Idempotency-Key": "request-credit"}),
        json={
            "model": "rated-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 402
    assert response.get_json()["error"]["code"] == "insufficient_credits"
    assert response.get_json()["error"]["billing_url"].endswith("/admin/billing")


def test_account_payload_accepts_non_creator_user_with_existing_wallet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flaskr.route.model_gateway as gateway

    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        wallet = CreditWallet(
            wallet_bid="wallet-learner",
            creator_bid="learner-user",
            available_credits=Decimal(8),
            reserved_credits=Decimal(2),
            lifetime_granted_credits=Decimal(10),
            lifetime_consumed_credits=Decimal(0),
            last_settled_usage_id=0,
            version=0,
        )
        bucket = CreditWalletBucket(
            wallet_bucket_bid="bucket-learner",
            wallet_bid=wallet.wallet_bid,
            creator_bid=wallet.creator_bid,
            bucket_category=CREDIT_BUCKET_CATEGORY_FREE,
            source_type=0,
            source_bid="source-learner",
            priority=10,
            original_credits=Decimal(10),
            available_credits=Decimal(8),
            reserved_credits=Decimal(2),
            consumed_credits=Decimal(0),
            expired_credits=Decimal(0),
            effective_from=datetime(2026, 1, 1),
            effective_to=None,
            status=CREDIT_BUCKET_STATUS_ACTIVE,
            metadata_json={},
        )
        dao.db.session.add_all([wallet, bucket])
        dao.db.session.commit()
        monkeypatch.setattr(
            gateway,
            "build_public_url",
            lambda path: f"https://example.test{path}",
        )

        payload = gateway._account_payload(
            app,
            SimpleNamespace(
                user_id="learner-user",
                name="Learner",
                language="zh-CN",
                is_creator=False,
            ),
        )

        assert payload["wallet"] == {
            "available_credits": 8,
            "reserved_credits": 2,
        }
        dao.db.session.remove()
        dao.db.drop_all()
