from types import SimpleNamespace


def test_ask_config_route_localizes_response_by_user_language(monkeypatch, test_client):
    monkeypatch.setattr(
        "flaskr.service.shifu.route.validate_user",
        lambda _app, _token: SimpleNamespace(language="zh-CN"),
        raising=False,
    )

    resp = test_client.get(
        "/api/shifu/ask/config",
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0

    providers = {
        item["provider"]: item for item in payload["data"].get("providers", [])
    }
    assert providers["volc_knowledge"]["title"] == "火山引擎知识库"
    assert "base_url" not in providers["coze"]["json_schema"]["properties"]
    assert (
        providers["coze"]["json_schema"]["properties"]["bot_id"]["description"]
        == "Coze Bot 标识。"
    )
