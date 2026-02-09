import json
import time

import requests

from flaskr.api.tts.aliyun_nls_token import get_aliyun_nls_token
from flaskr.api.tts.aliyun_provider import AliyunTTSProvider


def test_get_aliyun_nls_token_uses_override_when_configured(monkeypatch):
    monkeypatch.setenv("ALIYUN_TTS_TOKEN", "override-token")

    def fake_get(*args, **kwargs):
        raise AssertionError(
            "requests.get should not be called when override token exists"
        )

    monkeypatch.setattr(requests, "get", fake_get)

    assert get_aliyun_nls_token() == "override-token"


def test_get_aliyun_nls_token_fetches_and_caches(monkeypatch):
    monkeypatch.setenv("REDIS_KEY_PREFIX", "test:aliyun:nls-token:")
    monkeypatch.delenv("ALIYUN_TTS_TOKEN", raising=False)
    monkeypatch.setenv("ALIYUN_AK_ID", "my_access_key_id")
    monkeypatch.setenv("ALIYUN_AK_SECRET", "my_access_key_secret")

    from flaskr.api.tts import aliyun_nls_token as token_mod

    monkeypatch.setattr(token_mod, "_iso8601_utc_now", lambda: "2019-04-18T08:32:31Z")
    monkeypatch.setattr(
        token_mod,
        "_generate_nonce",
        lambda: "b924c8c3-6d03-4c5d-ad36-d984d3116788",
    )

    captured = {"calls": 0}

    class DummyResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"Token": {"Id": "tok-1", "ExpireTime": int(time.time()) + 3600}}

    def fake_get(url, headers=None, timeout=None):
        captured["calls"] += 1
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    token1 = get_aliyun_nls_token()
    token2 = get_aliyun_nls_token()

    assert token1 == "tok-1"
    assert token2 == "tok-1"
    assert captured["calls"] == 1

    # Signature check uses the official Aliyun doc "quick test" sample.
    assert (
        "Signature=hHq4yNsPitlfDJ2L0nQPdugdEzM%3D&"
        "AccessKeyId=my_access_key_id&Action=CreateToken&Format=JSON&"
        "RegionId=cn-shanghai&SignatureMethod=HMAC-SHA1&"
        "SignatureNonce=b924c8c3-6d03-4c5d-ad36-d984d3116788&"
        "SignatureVersion=1.0&Timestamp=2019-04-18T08%3A32%3A31Z&"
        "Version=2019-02-28" in captured["url"]
    )


def test_get_aliyun_nls_token_refresh_falls_back_to_cached_token(monkeypatch):
    monkeypatch.setenv("REDIS_KEY_PREFIX", "test:aliyun:nls-token:fallback:")
    monkeypatch.delenv("ALIYUN_TTS_TOKEN", raising=False)
    monkeypatch.setenv("ALIYUN_AK_ID", "my_access_key_id")
    monkeypatch.setenv("ALIYUN_AK_SECRET", "my_access_key_secret")

    from flaskr.api.tts import aliyun_nls_token as token_mod
    from flaskr.common.cache_provider import cache

    # Seed a near-expiry token in cache (still valid, but inside refresh leeway).
    cache_key = token_mod._get_cache_key()
    expire_time = int(time.time()) + 10
    cache.set(
        cache_key,
        json.dumps({"token": "cached-token", "expire_time": expire_time}),
        ex=30,
    )

    captured = {"calls": 0}

    def fake_get(*args, **kwargs):
        captured["calls"] += 1
        raise requests.RequestException("network down")

    monkeypatch.setattr(requests, "get", fake_get)

    assert get_aliyun_nls_token() == "cached-token"
    assert captured["calls"] == 1


def test_aliyun_provider_is_configured_with_access_keys(monkeypatch):
    monkeypatch.setenv("ALIYUN_TTS_APPKEY", "appkey")
    monkeypatch.delenv("ALIYUN_TTS_TOKEN", raising=False)
    monkeypatch.setenv("ALIYUN_AK_ID", "ak")
    monkeypatch.setenv("ALIYUN_AK_SECRET", "secret")

    provider = AliyunTTSProvider()
    assert provider.is_configured() is True


def test_aliyun_provider_synthesize_uses_dynamic_token(monkeypatch):
    monkeypatch.setenv("ALIYUN_TTS_APPKEY", "appkey")
    monkeypatch.setenv("ALIYUN_TTS_REGION", "shanghai")
    monkeypatch.delenv("ALIYUN_TTS_TOKEN", raising=False)

    from flaskr.api.tts import aliyun_provider as provider_mod

    monkeypatch.setattr(provider_mod, "get_aliyun_nls_token", lambda: "dyn-token")

    captured = {}

    class DummyResponse:
        status_code = 200
        headers = {"Content-Type": "audio/mpeg"}
        content = b"audio-bytes"

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    provider = AliyunTTSProvider()
    result = provider.synthesize("Hello")

    assert result.audio_data == b"audio-bytes"
    assert captured["json"]["appkey"] == "appkey"
    assert captured["json"]["token"] == "dyn-token"
    assert captured["headers"]["X-NLS-Token"] == "dyn-token"
