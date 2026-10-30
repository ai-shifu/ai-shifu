"""Keep registered config env vars from leaking between non-app tests."""

import os

import pytest
from flaskr.common.config import ENV_VARS

from tests.common.fixtures.env_isolation import clear_registered_env


@pytest.mark.parametrize("initial", [None, "original-value"])
def test_registered_env_is_restored_after_direct_writes(
    initial: str | None,
) -> None:
    key = "REDIS_HOST"
    assert key in ENV_VARS
    saved = os.environ.get(key)
    try:
        if initial is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = initial
        patcher = pytest.MonkeyPatch()
        clear_registered_env(patcher)
        assert key not in os.environ
        # Config.__setitem__ writes straight to os.environ, outside monkeypatch.
        os.environ[key] = "written-by-the-test"
        patcher.undo()
        assert os.environ.get(key) == initial
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved


def test_env_restores_when_the_test_patched_the_same_key_later() -> None:
    key = "SECRET_KEY"
    saved = os.environ.get(key)
    try:
        os.environ[key] = "session-secret"
        patcher = pytest.MonkeyPatch()
        clear_registered_env(patcher)
        patcher.setenv(key, "test-secret")
        patcher.delenv(key)
        patcher.undo()
        assert os.environ.get(key) == "session-secret"
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved
