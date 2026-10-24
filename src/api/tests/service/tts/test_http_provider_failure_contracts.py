"""Exercise HTTP TTS provider failures, byte limits and token refresh boundaries."""

import base64
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from flaskr.api.tts import baidu_provider as baidu
from flaskr.api.tts import volcengine_http_provider as volc
from flaskr.api.tts.base import AudioSettings, VoiceSettings


@pytest.fixture
def volc_http(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    values = {
        "VOLCENGINE_TTS_APP_KEY": "app",
        "VOLCENGINE_TTS_ACCESS_KEY": "token",
        "VOLCENGINE_TTS_CLUSTER_ID": "cluster",
    }
    monkeypatch.setattr(volc, "get_config", values.get)
    monkeypatch.setattr(volc, "get_explicit_env_override", lambda _key: None)
    response = Mock(
        status_code=200,
        url=volc.VOLCENGINE_HTTP_TTS_URL,
        headers={"Content-Type": "application/json"},
        text="response",
        reason="error",
    )
    response.json.return_value = {
        "code": 3000,
        "data": base64.b64encode(b"audio").decode(),
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(volc.requests, "post", post)
    return SimpleNamespace(
        provider=volc.VolcengineHttpTTSProvider(),
        post=post,
        response=response,
        values=values,
    )


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"code": 4000, "message": "quota exhausted"}, "error 4000: quota exhausted"),
        ({"code": 3000}, "No audio data"),
        ({"code": 3000, "data": "a"}, "Invalid base64 audio"),
    ],
)
def test_volcengine_invalid_provider_payload_is_not_returned_as_audio(
    volc_http: SimpleNamespace,
    payload: dict,
    error: str,
) -> None:
    volc_http.response.json.return_value = payload
    with pytest.raises(ValueError, match=error):
        volc_http.provider.synthesize("Hello")


@pytest.mark.parametrize("failure", ["transport", "http", "json"])
def test_volcengine_http_failures_have_stable_provider_errors(
    volc_http: SimpleNamespace,
    failure: str,
) -> None:
    if failure == "transport":
        volc_http.post.side_effect = requests.Timeout("timed out")
        expected = "request failed"
    elif failure == "http":
        volc_http.response.status_code = 429
        volc_http.response.raise_for_status.side_effect = requests.HTTPError("quota")
        expected = "HTTP 429"
    else:
        volc_http.response.json.side_effect = ValueError("invalid")
        expected = "not valid JSON"
    with pytest.raises(ValueError, match=expected):
        volc_http.provider.synthesize("Hello")


@pytest.mark.parametrize("text", ["", " "])
def test_volcengine_empty_text_never_calls_provider(
    volc_http: SimpleNamespace, text: str
) -> None:
    with pytest.raises(ValueError, match="Text cannot be empty"):
        volc_http.provider.synthesize(text)
    volc_http.post.assert_not_called()


def test_volcengine_incomplete_credentials_never_calls_provider(
    volc_http: SimpleNamespace,
) -> None:
    volc_http.values.pop("VOLCENGINE_TTS_ACCESS_KEY")
    assert not volc_http.provider.is_configured()
    with pytest.raises(ValueError, match="not configured"):
        volc_http.provider.synthesize("Hello")
    volc_http.post.assert_not_called()


@pytest.mark.parametrize(
    ("duration", "expected"), [("12.75", 12), ("invalid", 0), (None, 0)]
)
def test_volcengine_duration_metadata_and_unsupported_audio_settings_degrade_safely(
    volc_http: SimpleNamespace,
    duration: object,
    expected: int,
) -> None:
    volc_http.response.json.return_value["addition"] = {"duration": duration}
    result = volc_http.provider.synthesize(
        "Hello", audio_settings=AudioSettings(format="unsupported", sample_rate=123)
    )
    assert result.audio_data == b"audio"
    assert result.duration_ms == expected
    assert result.format == "mp3"
    assert result.sample_rate == 24000


@pytest.mark.parametrize(
    ("pitch", "expected"), [(None, 1.0), ("bad", 1.0), (-5, 0.1), (99, 3.0)]
)
def test_volcengine_pitch_conversion_is_bounded(pitch: object, expected: float) -> None:
    assert volc.VolcengineHttpTTSProvider()._resolve_pitch_ratio(pitch) == expected


def test_volcengine_http_error_logs_allowlisted_headers_and_bounded_body(
    volc_http: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = Mock()
    monkeypatch.setattr(volc.logger, "error", error)
    volc_http.response.headers = {
        "X-Request-Id": "request",
        "Authorization": "private-secret",
    }
    volc_http.response.text = "x" * 3000
    volc_http.provider._log_http_error_response(
        volc_http.response, "req", "cluster", "voice", "mp3", 24000, 5
    )
    assert error.call_args.args[-2] == {"X-Request-Id": "request"}
    assert error.call_args.args[-1] == "x" * 2000
    assert "private-secret" not in str(error.call_args)


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
