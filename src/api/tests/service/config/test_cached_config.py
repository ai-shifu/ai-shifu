"""Exercise cache-only configuration reads and caller-local cache isolation."""

from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.config import (
    config_cache_client,
    config_overrides,
    funcs,
    get_cached_config,
)


@pytest.mark.parametrize("encrypted", [False, True])
def test_cached_config_preserves_decoding_without_database_fallback(
    monkeypatch: pytest.MonkeyPatch, encrypted: bool
) -> None:
    app = Flask("cache-only-config")
    app.config.update(SECRET_KEY="test-secret", REDIS_KEY_PREFIX="isolated:")
    monkeypatch.setattr(funcs, "has_explicit_env_override", lambda _: False)
    shared = Mock()
    monkeypatch.setattr(funcs, "redis", shared)
    client = Mock()
    with app.app_context():
        value = funcs._encrypt_config(app, "true") if encrypted else "true"
        client.get.return_value = funcs.ConfigCache(
            is_encrypted=encrypted, value=value
        ).model_dump_json()
        with config_cache_client(client):
            assert get_cached_config("GEMINI_LIVE_ENABLED") == "true"
            assert funcs.get_config("GEMINI_LIVE_ENABLED") == "true"
        client.get.assert_called_with("isolated:sys:config:GEMINI_LIVE_ENABLED")
        client.get.return_value = None
        with config_cache_client(client), pytest.raises(LookupError):
            get_cached_config("GEMINI_LIVE_ENABLED")
    client.lock.assert_not_called()
    shared.get.assert_not_called()


def test_cached_config_overrides_and_env_do_not_touch_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    monkeypatch.setattr(funcs, "has_explicit_env_override", lambda _: True)
    monkeypatch.setattr(funcs, "get_config_from_common", lambda *_args: "false")
    with config_cache_client(client):
        with config_overrides({"GEMINI_LIVE_ENABLED": "true"}):
            assert get_cached_config("GEMINI_LIVE_ENABLED") == "true"
        assert get_cached_config("GEMINI_LIVE_ENABLED") == "false"
    client.get.assert_not_called()


def test_config_cache_client_restores_nested_and_shared_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Flask("config-cache-restore")
    app.config["REDIS_KEY_PREFIX"] = ""
    monkeypatch.setattr(funcs, "has_explicit_env_override", lambda _: False)
    shared, outer, inner = (Mock() for _ in range(3))
    for client, value in ((shared, "shared"), (outer, "outer"), (inner, "inner")):
        client.get.return_value = funcs.ConfigCache(value=value).model_dump_json()
    monkeypatch.setattr(funcs, "redis", shared)
    with app.app_context():
        with config_cache_client(outer):
            assert get_cached_config("key") == "outer"
            with config_cache_client(inner):
                assert get_cached_config("key") == "inner"
            assert get_cached_config("key") == "outer"
        assert get_cached_config("key") == "shared"
