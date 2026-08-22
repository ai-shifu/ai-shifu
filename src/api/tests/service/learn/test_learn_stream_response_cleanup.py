"""Stream response helpers must discard the session connection on close.

Both SSE helpers wrap streaming generators consumed by WSGI; a client
walking away injects GeneratorExit (or its RuntimeError disguise) at the
yield point, which may have interrupted a DB exchange deeper in the stack.
The helpers must invalidate the session BEFORE the finally-remove would
otherwise roll back on a possibly desynced connection.
"""

import pytest
from flaskr.service.learn import routes as learn_routes
from sqlalchemy.exc import ResourceClosedError


@pytest.fixture
def invalidations(monkeypatch: object) -> object:
    calls = []

    def release_db_session(app: object, *, source: str) -> None:
        del app, source

    monkeypatch.setattr(
        learn_routes,
        "invalidate_session",
        lambda *, source, _session=None: calls.append(source) or True,
    )
    monkeypatch.setattr(learn_routes, "_release_db_session", release_db_session)
    return calls


def _iter_stream(app: object, helper: object, iter_factory: object):
    with app.test_request_context("/"):
        response = helper(
            app,
            message_iter_factory=iter_factory,
            close_log="closed",
            error_log="failed",
        )
        return response.response


def test_sse_close_invalidates_session(app: object, invalidations: object) -> None:
    def factory():
        yield {"type": "chunk"}
        yield {"type": "chunk2"}

    with app.test_request_context("/"):
        response = learn_routes._stream_sse_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
        )
        stream = iter(response.response)
        next(stream)
        stream.close()

    assert invalidations == ["learn stream_sse_response close"]


def test_sse_protocol_error_invalidates_session(
    app: object, invalidations: object
) -> None:
    def factory():
        yield {"type": "chunk"}
        message = "desynced"
        raise ResourceClosedError(message)

    with app.test_request_context("/"):
        response = learn_routes._stream_sse_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
        )
        stream = iter(response.response)
        next(stream)
        with pytest.raises(ResourceClosedError):
            next(stream)

    assert invalidations == ["learn stream_sse_response desync"]


def test_sse_business_error_does_not_invalidate(
    app: object, invalidations: object
) -> None:
    def factory():
        yield {"type": "chunk"}
        message = "business"
        raise ValueError(message)

    with app.test_request_context("/"):
        response = learn_routes._stream_sse_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
        )
        stream = iter(response.response)
        next(stream)
        with pytest.raises(ValueError, match="business"):
            next(stream)

    assert invalidations == []


def test_passthrough_close_invalidates_session(
    app: object, invalidations: object
) -> None:
    def factory():
        yield "data: 1\n\n"
        yield "data: 2\n\n"

    with app.test_request_context("/"):
        response = learn_routes._stream_passthrough_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
        )
        stream = iter(response.response)
        next(stream)
        stream.close()

    assert invalidations == ["learn stream_passthrough_response close"]


def test_passthrough_close_disguised_as_runtime_error(
    app: object, invalidations: object
) -> None:
    def factory():
        yield "data: 1\n\n"
        message = "generator ignored GeneratorExit"
        raise RuntimeError(message)

    with app.test_request_context("/"):
        response = learn_routes._stream_passthrough_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
        )
        stream = iter(response.response)
        next(stream)
        with pytest.raises(StopIteration):
            next(stream)

    assert invalidations == ["learn stream_passthrough_response close"]


def test_passthrough_normal_exhaustion_does_not_invalidate(
    app: object, invalidations: object
) -> None:
    def factory():
        yield "data: 1\n\n"

    with app.test_request_context("/"):
        response = learn_routes._stream_passthrough_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
        )
        assert list(response.response) == ["data: 1\n\n"]

    assert invalidations == []
