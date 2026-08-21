"""Verify Feishu delivery metadata and failure handling."""

import requests
from flaskr.api.doc import feishu


class _Logger:
    def __init__(self) -> None:
        self.infos = []
        self.warnings = []
        self.exceptions = []

    def info(self, *args: object, **kwargs):
        _ = kwargs
        self.infos.append(args)

    def warning(self, *args: object, **kwargs):
        _ = kwargs
        self.warnings.append(args)

    def exception(self, *args: object, **kwargs):
        _ = kwargs
        self.exceptions.append(args)


class _App:
    def __init__(self) -> None:
        self.logger = _Logger()


class _Response:
    def __init__(
        self, status_code=200, text="", json_value=None, json_exc=None
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._json_value = json_value
        self._json_exc = json_exc

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_value


def test_send_notify_returns_metadata_for_successful_non_json_response(monkeypatch):
    app = _App()
    monkeypatch.setattr(
        feishu,
        "get_config",
        lambda key, default=None: "https://example.test/webhook",  # noqa: ARG005 -- preserve get_config keyword contract
    )
    monkeypatch.setattr(
        feishu.requests,
        "post",
        lambda *_args, **_kwargs: _Response(
            status_code=200, text="ok", json_exc=ValueError("not json")
        ),
    )

    result = feishu.send_notify(app, "标题", ["消息"])

    assert result == {"status_code": 200, "text": "ok"}
    assert app.logger.warnings == []


def test_send_notify_returns_none_for_non_2xx_response(monkeypatch):
    app = _App()
    monkeypatch.setattr(
        feishu,
        "get_config",
        lambda key, default=None: "https://example.test/webhook",  # noqa: ARG005 -- preserve get_config keyword contract
    )
    monkeypatch.setattr(
        feishu.requests,
        "post",
        lambda *_args, **_kwargs: _Response(status_code=400, text="bad request"),
    )

    result = feishu.send_notify(app, "标题", ["消息"])

    assert result is None
    assert app.logger.warnings


def test_send_notify_returns_none_for_request_error(monkeypatch):
    app = _App()
    monkeypatch.setattr(
        feishu,
        "get_config",
        lambda key, default=None: "https://example.test/webhook",  # noqa: ARG005 -- preserve get_config keyword contract
    )

    def _raise(*args: object, **kwargs):
        _ = (args, kwargs)
        message = "network down"
        raise requests.RequestException(message)

    monkeypatch.setattr(feishu.requests, "post", _raise)

    result = feishu.send_notify(app, "标题", ["消息"])

    assert result is None
    assert app.logger.exceptions
