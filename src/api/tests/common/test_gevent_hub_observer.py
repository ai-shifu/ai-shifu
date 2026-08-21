"""The hub error observer must mirror gevent hub failures into the app log.

A callback crashing inside the gevent hub (e.g. AssertionError in
AbstractLinkable._notify_links) bypasses every application except-block; the
observer wraps hub.handle_error so the failing context object is named in
the application log while the hub's original behavior is preserved.
"""

import logging

from flaskr.common.gevent_hub_observer import install_hub_error_observer


class _StubHub:
    def __init__(self) -> None:
        self.calls = []

        def _original(context, exc_type, value, tb):
            self.calls.append((context, exc_type, value, tb))
            return "original-result"

        self.handle_error = _original


def _fire(hub, context=None, exc=None):
    exc = exc if exc is not None else AssertionError("(None, <callback>)")
    return hub.handle_error(context, type(exc), exc, None)


def test_observer_logs_and_delegates(caplog):
    hub = _StubHub()
    logger = logging.getLogger("test-hub-observer")
    assert install_hub_error_observer(logger, hub=hub) is True

    class _FakeSemaphore:
        def __repr__(self) -> str:
            return "<FakeSemaphore links=3>"

    context = _FakeSemaphore()
    with caplog.at_level(logging.ERROR, logger="test-hub-observer"):
        result = _fire(hub, context=context)

    assert result == "original-result"
    assert len(hub.calls) == 1
    assert "gevent hub error" in caplog.text
    # The culprit primitive must be attributable: class name AND repr.
    assert "_FakeSemaphore" in caplog.text
    assert "<FakeSemaphore links=3>" in caplog.text
    assert "AssertionError" in caplog.text


def test_observer_installs_once(caplog):
    hub = _StubHub()
    logger = logging.getLogger("test-hub-observer-once")
    assert install_hub_error_observer(logger, hub=hub) is True
    assert install_hub_error_observer(logger, hub=hub) is True

    with caplog.at_level(logging.ERROR, logger="test-hub-observer-once"):
        _fire(hub)

    # Double install must not double-wrap: one delegate call, one log line.
    assert len(hub.calls) == 1
    assert caplog.text.count("gevent hub error") == 1


def test_logger_failure_never_blocks_the_original_handler():
    hub = _StubHub()

    class _BrokenLogger:
        def error(self, *args: object, **kwargs):
            _ = (args, kwargs)
            message = "logging backend down"
            raise RuntimeError(message)

    install_hub_error_observer(_BrokenLogger(), hub=hub)
    result = _fire(hub)

    assert result == "original-result"
    assert len(hub.calls) == 1


def test_unreprable_context_is_still_logged(caplog):
    hub = _StubHub()
    logger = logging.getLogger("test-hub-observer-badrepr")
    install_hub_error_observer(logger, hub=hub)

    class _BadRepr:
        def __repr__(self) -> str:
            message = "no repr for you"
            raise ValueError(message)

    with caplog.at_level(logging.ERROR, logger="test-hub-observer-badrepr"):
        _fire(hub, context=_BadRepr())

    assert "_BadRepr" in caplog.text
    assert "<repr failed>" in caplog.text
