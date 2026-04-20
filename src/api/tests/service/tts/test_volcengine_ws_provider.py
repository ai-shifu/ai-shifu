import flaskr.api.tts.volcengine_provider as volcengine_provider


def test_volcengine_ws_get_credentials_prefers_volcengine_tts_keys(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APP_KEY", "test-app")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_KEY", "test-access")
    monkeypatch.setenv("ARK_ACCESS_KEY_ID", "legacy-app")
    monkeypatch.setenv("ARK_SECRET_ACCESS_KEY", "legacy-access")

    provider = volcengine_provider.VolcengineTTSProvider()
    app_key, access_key, resource_id = provider._get_credentials("seed-tts-2.0")

    assert app_key == "test-app"
    assert access_key == "test-access"
    assert resource_id == "seed-tts-2.0"


def test_volcengine_ws_get_credentials_falls_back_to_ark_keys(monkeypatch):
    monkeypatch.delenv("VOLCENGINE_TTS_APP_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_TTS_ACCESS_KEY", raising=False)
    monkeypatch.setenv("ARK_ACCESS_KEY_ID", "legacy-app")
    monkeypatch.setenv("ARK_SECRET_ACCESS_KEY", "legacy-access")

    provider = volcengine_provider.VolcengineTTSProvider()
    app_key, access_key, resource_id = provider._get_credentials("")

    assert app_key == "legacy-app"
    assert access_key == "legacy-access"
    assert resource_id == "seed-tts-1.0"


def test_volcengine_ws_is_configured_uses_volcengine_tts_keys(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APP_KEY", "test-app")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_KEY", "test-access")
    monkeypatch.delenv("ARK_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ARK_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setattr(volcengine_provider, "WEBSOCKET_AVAILABLE", True)

    provider = volcengine_provider.VolcengineTTSProvider()
    assert provider.is_configured() is True
