import json

from flask import Flask


def test_list_records_builds_request(monkeypatch):
    from flaskr.api.doc import feishu

    captured = {}

    def fake_post(url, headers=None, data=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data

        class Response:
            def json(self):
                return {"data": {"items": []}}

        return Response()

    monkeypatch.setattr(
        feishu, "get_tenant_token", lambda app, app_id=None, app_secret=None: "token"
    )
    monkeypatch.setattr(feishu.requests, "post", fake_post)

    app = Flask("contract-feishu")
    with app.app_context():
        result = feishu.list_records(
            app,
            app_token="app123",
            table_id="table456",
            view_id="view789",
            page_token="page-token",
            page_size=50,
        )

    assert result == {"data": {"items": []}}
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert "page_token=page-token" in captured["url"]
    assert "page_size=50" in captured["url"]

    body = json.loads(captured["data"])
    assert body["automatic_fields"] is True
    assert body["view_id"] == "view789"
