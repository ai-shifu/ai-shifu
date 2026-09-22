"""Verify Redis ask-slot concurrency and recoverable runtime status failures."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.learn import learn_funcs as learn
from flaskr.service.learn import runscript_v2 as run

from tests.service.learn import test_live_follow_up_admission as admission_tests

# Reuse the isolated Redis process and its existing opt-in contract.
real_redis = admission_tests.real_redis


@pytest.fixture
def runtime_app() -> Flask:
    app = Flask(__name__)
    app.config.update(REDIS_KEY_PREFIX="runtime-contract", MAX_PARALLEL_ASK_COUNT=3)
    return app


def test_real_redis_ask_slots_are_atomic_and_scoped_to_learner_and_outline(
    runtime_app: Flask, real_redis: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(dao._redis_state, "client", real_redis.client)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(
            pool.map(
                lambda _: run._ask_sem_acquire(runtime_app, "user", "outline"),
                range(24),
            )
        )
    assert sum(results) == 3
    key = run._get_ask_sem_key(runtime_app, "user", "outline")
    assert real_redis.client.get(key) == "3"
    assert 0 < real_redis.client.ttl(key) <= run.RUN_SCRIPT_TIMEOUT_SECONDS
    assert run._ask_sem_acquire(runtime_app, "other-user", "outline") is True
    assert run._ask_sem_acquire(runtime_app, "user", "other-outline") is True
    run._ask_sem_release(runtime_app, "user", "outline")
    assert run._ask_sem_acquire(runtime_app, "user", "outline") is True
    assert run._ask_sem_acquire(runtime_app, "user", "outline") is False


def test_real_redis_duplicate_release_never_makes_ask_slots_negative(
    runtime_app: Flask, real_redis: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(dao._redis_state, "client", real_redis.client)
    assert run._ask_sem_acquire(runtime_app, "user", "outline") is True
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda _: run._ask_sem_release(runtime_app, "user", "outline"),
                range(16),
            )
        )
    assert (
        real_redis.client.get(run._get_ask_sem_key(runtime_app, "user", "outline"))
        == "0"
    )
    run._ask_sem_release(runtime_app, "missing", "outline")
    assert (
        real_redis.client.exists(
            run._get_ask_sem_key(runtime_app, "missing", "outline")
        )
        == 0
    )


@pytest.mark.parametrize("unavailable", [None, "connection-error"])
def test_ask_slot_backend_outage_preserves_fail_open_contract(
    runtime_app: Flask, monkeypatch: object, unavailable: str | None
) -> None:
    redis = (
        None
        if unavailable is None
        else Mock(eval=Mock(side_effect=ConnectionError("unavailable")))
    )
    monkeypatch.setattr(dao._redis_state, "client", redis)
    assert run._ask_sem_acquire(runtime_app, "user", "outline") is True
    run._ask_sem_release(runtime_app, "user", "outline")
    if redis is not None:
        assert redis.eval.call_count == 2


@pytest.mark.parametrize("configured", [None, "invalid", {}, 5, "7"])
def test_ask_limit_configuration_handles_malformed_values(
    runtime_app: Flask, configured: object
) -> None:
    runtime_app.config["MAX_PARALLEL_ASK_COUNT"] = configured
    expected = (
        int(configured)
        if isinstance(configured, int) or configured == "7"
        else run.DEFAULT_MAX_PARALLEL_ASK_COUNT
    )
    assert run._get_max_parallel_ask_count(runtime_app) == expected


@pytest.mark.parametrize("raw", [b"123", "456", b"bad\xff", [], None])
def test_run_status_decodes_timestamps_and_ignores_corrupt_cache_entries(
    runtime_app: Flask, monkeypatch: object, raw: object
) -> None:
    cache = Mock(get=Mock(return_value=raw))
    monkeypatch.setattr(run, "cache_provider", cache)
    expected = (
        {b"123": 123, "456": 456}.get(raw) if isinstance(raw, (bytes, str)) else None
    )
    assert run._get_run_script_started_at(runtime_app, "user", "outline") == expected
    cache.get.assert_called_once_with(
        "runtime-contract:run_script:user:outline:running"
    )


def test_run_status_cache_outage_does_not_interrupt_start_or_cleanup(
    runtime_app: Flask, monkeypatch: object
) -> None:
    cache = Mock()
    for method in (cache.setex, cache.delete, cache.get):
        method.side_effect = ConnectionError("status unavailable")
    monkeypatch.setattr(run, "cache_provider", cache)
    run._set_run_script_status(runtime_app, "user", "outline", 123)
    run._clear_run_script_status(runtime_app, "user", "outline")
    assert run._get_run_script_started_at(runtime_app, "user", "outline") is None
    cache.setex.assert_called_once_with(
        "runtime-contract:run_script:user:outline:running",
        run.RUN_SCRIPT_TIMEOUT_SECONDS,
        "123",
    )
    cache.delete.assert_called_once()


def test_real_redis_tts_slots_are_atomic_and_release_without_negative_counts(
    runtime_app: Flask, real_redis: object, monkeypatch: object
) -> None:
    runtime_app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = 3
    monkeypatch.setattr(dao._redis_state, "client", real_redis.client)
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(
            pool.map(
                lambda _: learn._tts_synth_sem_acquire(runtime_app, "user", "outline"),
                range(24),
            )
        )
    assert outcomes.count(learn._TTS_SLOT_ACQUIRED) == 3
    assert outcomes.count(learn._TTS_SLOT_FULL) == 21
    key = learn._get_tts_synth_sem_key(runtime_app, "user", "outline")
    assert real_redis.client.get(key) == "3"
    assert 0 < real_redis.client.ttl(key) <= learn.TTS_SYNTH_SEM_TTL_SECONDS
    assert (
        learn._tts_synth_sem_acquire(runtime_app, "other", "outline")
        == learn._TTS_SLOT_ACQUIRED
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda _: learn._tts_synth_sem_release(runtime_app, "user", "outline"),
                range(16),
            )
        )
    assert real_redis.client.get(key) == "0"
    assert (
        learn._tts_synth_sem_acquire(runtime_app, "user", "outline")
        == learn._TTS_SLOT_ACQUIRED
    )


@pytest.mark.parametrize("unavailable", [None, "connection-error"])
def test_tts_slot_backend_outage_distinguishes_bypass_from_reserved_slot(
    runtime_app: Flask, monkeypatch: object, unavailable: str | None
) -> None:
    redis = (
        None
        if unavailable is None
        else Mock(eval=Mock(side_effect=ConnectionError("unavailable")))
    )
    monkeypatch.setattr(dao._redis_state, "client", redis)
    assert (
        learn._tts_synth_sem_acquire(runtime_app, "user", "outline")
        == learn._TTS_SLOT_BYPASS
    )
    learn._tts_synth_sem_release(runtime_app, "user", "outline")
    if redis is not None:
        assert redis.eval.call_count == 2


@pytest.mark.parametrize("configured", [None, "invalid", {}])
def test_tts_limit_uses_default_for_malformed_configuration(
    runtime_app: Flask, configured: object
) -> None:
    runtime_app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = configured
    assert (
        learn._get_max_parallel_tts_synth_count(runtime_app)
        == learn.DEFAULT_MAX_PARALLEL_TTS_SYNTH_COUNT
    )


@pytest.mark.parametrize(
    ("user", "outline", "cap"),
    [("", "outline", 3), ("user", "", 3), ("user", "outline", 0)],
)
def test_disabled_or_unscoped_tts_limiter_never_touches_redis(
    runtime_app: Flask, monkeypatch: object, user: str, outline: str, cap: int
) -> None:
    runtime_app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = cap
    redis = Mock()
    monkeypatch.setattr(dao._redis_state, "client", redis)
    assert (
        learn._tts_synth_sem_acquire(runtime_app, user, outline)
        == learn._TTS_SLOT_BYPASS
    )
    learn._tts_synth_sem_release(runtime_app, user, outline)
    redis.eval.assert_not_called()
