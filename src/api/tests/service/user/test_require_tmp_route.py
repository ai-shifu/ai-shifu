"""Verify require tmp HTTP route behavior."""

from __future__ import annotations

import json
import uuid

from flaskr.dao import db
from flaskr.service.user.models import UserToken
from flaskr.service.user.token_store import token_store


def test_require_tmp_passes_payload_source_to_temp_user(
    test_client: object, monkeypatch: object
) -> None:
    import flaskr.route.user as user_route

    calls: list[dict[str, str | None]] = []

    def fake_generate_temp_user(
        app: object,
        temp_id: object,
        source: object,
        wx_code: object = None,
        language: object = "en-US",
    ) -> object:
        _ = app
        calls.append(
            {
                "temp_id": temp_id,
                "source": source,
                "wx_code": wx_code,
                "language": language,
            }
        )
        return {"token": "guest-token", "userInfo": {"user_bid": "guest-user"}}

    monkeypatch.setattr(user_route, "generate_temp_user", fake_generate_temp_user)

    response = test_client.post(
        "/api/user/require_tmp",
        json={
            "temp_id": "guest-temp-id",
            "source": "shingler",
            "wxcode": "wx-code-1234",
            "language": "zh-CN",
        },
    )

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["code"] == 0
    assert calls == [
        {
            "temp_id": "guest-temp-id",
            "source": "shingler",
            "wx_code": "wx-code-1234",
            "language": "zh-CN",
        }
    ]


def test_require_tmp_token_remains_valid_in_the_next_request(
    app: object, test_client: object
) -> None:
    """A guest token must be durable before the issuing request ends."""
    response = test_client.post(
        "/api/user/require_tmp",
        json={
            "temp_id": f"guest-{uuid.uuid4().hex}",
            "source": "web",
            "language": "zh-CN",
        },
    )
    payload = json.loads(response.get_data(as_text=True))
    token = payload["data"]["token"]
    user_id = payload["data"]["userInfo"]["user_id"]

    # Prove authentication can fall back to the durable row instead of being
    # accidentally rescued by the cache populated during token creation.
    token_store._cache.delete(token_store._cache_key(app, token))
    db.session.remove()

    user_response = test_client.get(
        "/api/user/info",
        headers={"Token": token},
    )
    user_payload = json.loads(user_response.get_data(as_text=True))

    assert user_payload["code"] == 0
    assert user_payload["data"]["user_id"] == user_id
    assert UserToken.query.filter_by(token=token, user_id=user_id).count() == 1
