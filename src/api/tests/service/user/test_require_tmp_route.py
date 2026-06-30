from __future__ import annotations

import json


def test_require_tmp_passes_payload_source_to_temp_user(test_client, monkeypatch):
    import flaskr.route.user as user_route

    calls: list[dict[str, str | None]] = []

    def fake_generate_temp_user(app, temp_id, source, wx_code=None, language="en-US"):
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
