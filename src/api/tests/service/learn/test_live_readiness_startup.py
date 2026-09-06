"""Optional Live preparation must not block server startup or fill HTTP threads."""

import socket
import time
from contextlib import nullcontext
from threading import Event, Thread
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.config import funcs
from flaskr.service.learn import live_follow_up_admission as admission
from flaskr.service.learn import live_follow_up_config as config
from flaskr.service.learn import live_follow_up_routes as routes
from redis import Redis


def test_stalled_configuration_task_does_not_delay_http_or_duplicate_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_SHIFU_PRELOAD_MASTER", raising=False)
    started, release = Event(), Event()
    tasks = []

    def prepare(_app: Flask) -> bool:
        started.set()
        release.wait(5)
        return True

    def task(**kwargs: object) -> Thread:
        worker = Thread(**kwargs)
        tasks.append(worker)
        return worker

    monkeypatch.setattr(routes, "_prepare_live_follow_up", prepare)
    monkeypatch.setattr(routes, "Thread", task)
    app = Flask("nonblocking-live-startup")
    app.add_url_rule("/health", view_func=lambda: {"ok": True})
    try:
        before = time.monotonic()
        routes.init_live_follow_up_readiness(app)
        assert time.monotonic() - before < 1
        assert started.wait(1)
        routes.init_live_follow_up_readiness(app)
        assert len(tasks) == 1
        assert app.test_client().get("/health").status_code == 200
    finally:
        release.set()
        for worker in tasks:
            worker.join(timeout=2)


def test_unresponsive_redis_is_bounded_before_flag_lookup_and_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Accept TCP but never respond, reproducing an unlimited shared Redis read.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.1)
    stop = Event()
    accepted = []

    def blackhole() -> None:
        while not stop.is_set():
            try:
                connection, _address = listener.accept()
                accepted.append(connection)
            except TimeoutError:
                continue

    server = Thread(target=blackhole, daemon=True)
    server.start()
    source = Redis(
        host="127.0.0.1",
        port=listener.getsockname()[1],
        socket_timeout=None,
        socket_connect_timeout=None,
    )
    monkeypatch.setattr(admission, "_require_redis", lambda: source)
    monkeypatch.setattr(routes, "Thread", Mock())
    monkeypatch.setattr(routes, "has_explicit_env_override", lambda _: False)
    monkeypatch.setattr(funcs, "has_explicit_env_override", lambda _: False)
    shared = Mock()
    monkeypatch.setattr(funcs, "redis", shared)
    app = Flask("blackhole-live-readiness")
    app.config["REDIS_KEY_PREFIX"] = "bounded:"
    try:
        routes.register_live_follow_up_routes(app)
        before = time.monotonic()
        response = app.test_client().get("/api/learn/live-follow-up/readiness")
        assert response.get_json()["data"]["status"] == "unavailable"
        assert time.monotonic() - before < 3
        before = time.monotonic()
        assert routes._prepare_live_follow_up(app) is False
        assert time.monotonic() - before < 3
        shared.get.assert_not_called()
        assert source.connection_pool.connection_kwargs["socket_timeout"] is None
    finally:
        stop.set()
        server.join(timeout=2)
        listener.close()
        for connection in accepted:
            connection.close()
        source.close()


@pytest.mark.parametrize("cached", [None, '{"value":"true","is_encrypted":false}'])
def test_readiness_never_reenters_shared_config_or_database(
    monkeypatch: pytest.MonkeyPatch, cached: str | None
) -> None:
    monkeypatch.setattr(routes, "Thread", Mock())
    monkeypatch.setattr(routes, "has_explicit_env_override", lambda _: False)
    monkeypatch.setattr(funcs, "has_explicit_env_override", lambda _: False)
    client = Mock()
    client.get.return_value = cached
    monkeypatch.setattr(
        routes, "live_follow_up_readiness_client", lambda: nullcontext(client)
    )
    shared = Mock()
    monkeypatch.setattr(funcs, "redis", shared)
    monkeypatch.setattr(
        routes,
        "live_follow_up_readiness",
        lambda *_args, **_kwargs: {"status": "ready"},
    )
    # The actual flag resolver inside capability validation must use the
    # request-local resolved override, not shared Redis after its client closes.
    monkeypatch.setattr(
        routes,
        "is_live_follow_up_model_available",
        lambda _: config.is_gemini_live_enabled(),
    )
    app = Flask("cache-only-live-readiness")
    app.config["REDIS_KEY_PREFIX"] = ""
    routes.register_live_follow_up_routes(app)
    response = app.test_client().get("/api/learn/live-follow-up/readiness")
    assert response.get_json()["data"]["status"] == (
        "ready" if cached is not None else "unavailable"
    )
    client.get.assert_called_once()
    client.lock.assert_not_called()
    shared.get.assert_not_called()
