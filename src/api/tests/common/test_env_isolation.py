"""Keep registered config env vars from leaking between non-app tests."""

import os

import pytest
from flaskr.common.config import ENV_VARS

from tests.common.fixtures.env_isolation import clear_registered_env

pytest_plugins = ["pytester"]


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


_INNER_TESTS = """
import os


def test_writes_registered_keys_directly():
    os.environ["REDIS_HOST"] = "written-by-the-test"
    os.environ["SECRET_KEY"] = "written-by-the-test"


def test_next_test_starts_isolated_again():
    assert "REDIS_HOST" not in os.environ
    assert "SECRET_KEY" not in os.environ
"""


@pytest.mark.parametrize("early_monkeypatch", [False, True])
def test_autouse_isolation_restores_env_between_tests(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    early_monkeypatch: bool,
) -> None:
    """Run the real autouse fixture across two tests and check the outer env."""
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.setenv("SECRET_KEY", "outer-secret")
    early = (
        "@pytest.fixture(autouse=True)\n"
        "def _earlier_monkeypatch(monkeypatch):\n"
        "    del monkeypatch\n\n\n"
        if early_monkeypatch
        else ""
    )
    pytester.makeconftest(
        "import pytest\n"
        "from tests.conftest import isolate_env_for_non_app_tests  # noqa: F401\n\n\n"
        + early
    )
    pytester.makepyfile(test_inner=_INNER_TESTS)

    result = pytester.runpytest("-p", "no:xdist", "-p", "no:cacheprovider")

    result.assert_outcomes(passed=2)
    assert "REDIS_HOST" not in os.environ
    assert os.environ["SECRET_KEY"] == "outer-secret"
