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

    handler = FeishuLogHandler("https://example.invalid/open-apis/bot/v2/hook/test")
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


def test_feishu_log_handler_surfaces_delivery_failure_without_recursion(
    monkeypatch, caplog
):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return _FailingResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    handler = FeishuLogHandler("https://example.invalid/open-apis/bot/v2/hook/test")
    handler.setFormatter(logging.Formatter("%(message)s"))
    # Attach the handler to a real logger so that reporting the delivery
    # failure would re-enter emit() if the re-entrancy guard were missing.
    logger = logging.getLogger("test_feishu_recursion")
    logger.handlers = [handler]
    logger.setLevel(logging.ERROR)
    logger.propagate = False

    with caplog.at_level(logging.WARNING, logger="flaskr.common.log"):
        logger.error("original application error")

    # The webhook is attempted exactly once: the delivery-failure report does
    # not loop back into the handler.
    assert len(calls) == 1
    # The failure is still visible in the standard logs, not silently dropped.
    assert "Failed to send log to Feishu webhook" in caplog.text


def test_feishu_log_handler_reentrancy_guard_blocks_nested_emit(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return type("Response", (), {"raise_for_status": lambda self: None})()

    monkeypatch.setattr(requests, "post", fake_post)

    handler = FeishuLogHandler("https://example.invalid/open-apis/bot/v2/hook/test")
    record = logging.LogRecord(
        name="app",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="nested emit",
        args=(),
        exc_info=None,
    )

    # Simulate being already inside emit() on this thread (as happens when the
    # delivery-failure report flows back through app.logger).
    handler._delivering.active = True
    handler.emit(record)

    assert calls == []


def test_feishu_log_handler_truncates_oversized_payload(monkeypatch):
    captured = {}

    def fake_post(_url, *, json, timeout):
        captured["payload"] = json
        captured["timeout"] = timeout
        return type("Response", (), {"raise_for_status": lambda self: None})()

    monkeypatch.setattr(requests, "post", fake_post)

    handler = FeishuLogHandler("https://example.invalid/open-apis/bot/v2/hook/test")
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
