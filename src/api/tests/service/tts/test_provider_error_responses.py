"""Error-branch tests for the Baidu and Aliyun TTS HTTP responses."""

import pytest
import requests
from flaskr.api.tts import aliyun_provider as aliyun_mod
from flaskr.api.tts import baidu_provider as baidu_mod
from flaskr.api.tts.aliyun_provider import AliyunTTSProvider
from flaskr.api.tts.baidu_provider import BaiduTTSProvider


class _Response:
    def __init__(self, payload: object, text: object) -> None:
        self.headers = {"Content-Type": "application/json"}
        self.status_code = 200
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            message = "no json"
            raise ValueError(message)
        return self._payload


@pytest.fixture
def baidu(monkeypatch: object) -> object:
    monkeypatch.setattr(baidu_mod, "_get_access_token", lambda *_args: "token")
    provider = BaiduTTSProvider()
    monkeypatch.setattr(provider, "_get_credentials", lambda: ("key", "secret"))
    return provider


@pytest.fixture
def aliyun(monkeypatch: object) -> object:
    monkeypatch.setattr(aliyun_mod, "get_aliyun_nls_token", lambda: "token")
    provider = AliyunTTSProvider()
    monkeypatch.setattr(provider, "_get_settings", lambda: ("appkey", "shanghai"))
    return provider


def test_baidu_reports_the_json_error_payload(
    baidu: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_args, **_kwargs: _Response({"err_no": 502, "err_msg": "bad"}, "{}"),
    )

    with pytest.raises(ValueError, match=r"Baidu TTS API error 502: bad"):
        baidu.synthesize("hello")


def test_baidu_reports_the_raw_body_when_json_is_malformed(
    baidu: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_args, **_kwargs: _Response(None, "<html>oops</html>"),
    )

    with pytest.raises(ValueError, match=r"Baidu TTS API error: <html>oops</html>"):
        baidu.synthesize("hello")


def test_aliyun_reports_the_json_error_payload(
    aliyun: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_args, **_kwargs: _Response(
            {"status": 40000000, "message": "denied", "task_id": "t-1"},
            "{}",
        ),
    )

    with pytest.raises(
        ValueError,
        match=r"Aliyun TTS API error 40000000: denied \(task_id: t-1\)",
    ):
        aliyun.synthesize("hello")


def test_aliyun_reports_the_raw_body_when_json_is_malformed(
    aliyun: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_args, **_kwargs: _Response(None, "<html>oops</html>"),
    )

    with pytest.raises(ValueError, match=r"Aliyun TTS API error: <html>oops</html>"):
        aliyun.synthesize("hello")
