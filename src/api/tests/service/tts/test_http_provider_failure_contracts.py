"""Exercise HTTP TTS provider failures, byte limits and token refresh boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from flaskr.api.tts import baidu_provider as baidu
from flaskr.api.tts.base import VoiceSettings


@pytest.fixture
def baidu_http(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setattr(baidu, "get_config", lambda _key: "credential")
    monkeypatch.setattr(baidu, "_token_cache", {"access_token": None, "expires_at": 0})
    token = Mock(return_value="access-token")
    monkeypatch.setattr(baidu, "_get_access_token", token)
    response = Mock(
        headers={"Content-Type": "audio/mp3"}, content=b"x" * 160, text="bad response"
    )
    post = Mock(return_value=response)
    monkeypatch.setattr(baidu.requests, "post", post)
    return SimpleNamespace(
        provider=baidu.BaiduTTSProvider(), post=post, response=response, token=token
    )


@pytest.mark.parametrize(("setting", "expected"), [(-10, 0), (20, 15), (None, 5)])
def test_baidu_clamps_native_voice_settings_and_truncates_on_utf8_boundary(
    baidu_http: SimpleNamespace,
    setting: object,
    expected: int,
) -> None:
    voice = VoiceSettings(voice_id="0", speed=setting, pitch=setting, volume=setting)
    result = baidu_http.provider.synthesize("中" * 500, voice_settings=voice)
    payload = baidu_http.post.call_args.kwargs["params"]
    assert payload["tex"] == "中" * 341
    assert payload["spd"] == payload["pit"] == payload["vol"] == expected
    assert payload["tok"] == "access-token"
    assert result.word_count == 341
    assert result.duration_ms == 10


@pytest.mark.parametrize(
    "failure", ["json_error", "non_json", "transport", "credentials", "empty"]
)
def test_baidu_failure_does_not_return_false_success(
    baidu_http: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    expected = "Baidu TTS"
    if failure == "json_error":
        baidu_http.response.headers = {"Content-Type": "application/json"}
        baidu_http.response.json.return_value = {"err_no": 500, "err_msg": "quota"}
        expected = "API error 500: quota"
    elif failure == "non_json":
        baidu_http.response.headers = {}
        baidu_http.response.json.side_effect = ValueError("invalid")
    elif failure == "transport":
        baidu_http.post.side_effect = requests.Timeout("timeout")
    elif failure == "credentials":
        monkeypatch.setattr(baidu, "get_config", lambda _key: "")
        assert not baidu_http.provider.is_configured()
    else:
        expected = "Text cannot be empty"
    with pytest.raises(ValueError, match=expected):
        baidu_http.provider.synthesize(" " if failure == "empty" else "Hello")
    if failure in {"empty", "credentials"}:
        baidu_http.post.assert_not_called()


@pytest.mark.parametrize("remaining", [301, 300, 0])
def test_baidu_token_cache_refreshes_at_five_minute_boundary(
    monkeypatch: pytest.MonkeyPatch,
    remaining: int,
) -> None:
    cache = {"access_token": "cached", "expires_at": 1000 + remaining}
    monkeypatch.setattr(baidu, "_token_cache", cache)
    monkeypatch.setattr(baidu.time, "time", lambda: 1000)
    response = Mock()
    response.json.return_value = {"access_token": "new", "expires_in": 3600}
    post = Mock(return_value=response)
    monkeypatch.setattr(baidu.requests, "post", post)
    assert baidu._get_access_token("key", "secret") == (
        "cached" if remaining > 300 else "new"
    )
    assert post.call_count == (remaining <= 300)
    if remaining <= 300:
        assert cache["expires_at"] == 4600
        assert baidu._get_access_token("key", "secret") == "new"
        assert post.call_count == 1


@pytest.mark.parametrize("failure", ["missing_token", "transport"])
def test_baidu_token_failure_never_populates_cache(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    cache = {"access_token": None, "expires_at": 0}
    monkeypatch.setattr(baidu, "_token_cache", cache)
    response = Mock()
    response.json.return_value = {"error_description": "invalid credentials"}
    post = Mock(return_value=response)
    if failure == "transport":
        post.side_effect = requests.Timeout("timeout")
    monkeypatch.setattr(baidu.requests, "post", post)
    with pytest.raises(ValueError, match="Failed to get Baidu access token"):
        baidu._get_access_token("key", "secret")
    assert cache == {"access_token": None, "expires_at": 0}
