import logging

import requests

from flaskr.common.log import FeishuLogHandler


class _FailingResponse:
    def raise_for_status(self):
        raise requests.exceptions.HTTPError("400 Client Error")


def test_feishu_log_handler_does_not_reemit_webhook_failures(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return _FailingResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    handler = FeishuLogHandler("https://open.feishu.cn/open-apis/bot/v2/hook/test")
    record = logging.LogRecord(
        name="app",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="original application error",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    assert len(calls) == 1
    assert calls[0][1]["timeout"] == 5


def test_feishu_log_handler_truncates_oversized_payload(monkeypatch):
    captured = {}

    def fake_post(_url, *, json, timeout):
        captured["payload"] = json
        captured["timeout"] = timeout
        return type("Response", (), {"raise_for_status": lambda self: None})()

    monkeypatch.setattr(requests, "post", fake_post)

    handler = FeishuLogHandler("https://open.feishu.cn/open-apis/bot/v2/hook/test")
    record = logging.LogRecord(
        name="app",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="x" * (handler.MAX_TEXT_LENGTH + 1000),
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    text = captured["payload"]["content"]["text"]
    assert len(text) <= handler.MAX_TEXT_LENGTH
    assert "truncated" in text
    assert captured["timeout"] == 5
