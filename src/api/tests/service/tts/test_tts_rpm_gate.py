"""Verify TTS rate-limit queues isolate credentials and models."""

from collections.abc import Callable, Iterator

import pytest
from flaskr.service.tts import rpm_gate


class _FakeRedisLock:
    def __init__(self) -> None:
        self.released = False

    def acquire(
        self, *, blocking: bool = True, blocking_timeout: object | None = None
    ) -> bool:
        _ = blocking, blocking_timeout
        return True

    def release(self) -> None:
        self.released = True


class _FakeRedis:
    def __init__(self) -> None:
        self.values = {}
        self.locks = []

    def get(self, key: object) -> object:
        return self.values.get(key)

    def set(self, key: object, value: object, ex: object | None = None) -> bool:
        _ = ex
        self.values[key] = str(value).encode("utf-8")
        return True

    def lock(
        self,
        key: object,
        timeout: object | None = None,
        blocking_timeout: object | None = None,
    ) -> object:
        _ = key, timeout, blocking_timeout
        lock = _FakeRedisLock()
        self.locks.append(lock)
        return lock


def _clock(
    start: float = 1000.0,
) -> tuple[Callable[..., object], Callable[..., object]]:
    now = {"value": float(start)}

    def now_fn() -> object:
        return now["value"]

    def sleep_fn(seconds: object) -> None:
        now["value"] += seconds

    return now_fn, sleep_fn


@pytest.fixture(autouse=True)
def _reset_gate_state() -> Iterator[None]:
    rpm_gate._LOCAL_STATE.clear()
    rpm_gate._FALLBACK_WARNING_KEYS.clear()
    yield
    rpm_gate._LOCAL_STATE.clear()
    rpm_gate._FALLBACK_WARNING_KEYS.clear()


def test_rpm_gate_smooths_same_provider_and_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(rpm_gate, "_get_redis_client", lambda: fake_redis)
    now_fn, sleep_fn = _clock()

    first = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )
    second = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )

    assert first.waited_seconds == 0
    assert second.waited_seconds == pytest.approx(1.0)


def test_rpm_gate_uses_independent_queues_for_different_api_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(rpm_gate, "_get_redis_client", lambda: fake_redis)
    now_fn, sleep_fn = _clock()

    first = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )
    second = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-b",
        rpm_limit=60,
        max_wait_seconds=10,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )

    assert first.waited_seconds == 0
    assert second.waited_seconds == 0


def test_rpm_gate_uses_independent_queues_for_different_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(rpm_gate, "_get_redis_client", lambda: fake_redis)
    now_fn, sleep_fn = _clock()

    first = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        model="speech-2.8-turbo",
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )
    second = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        model="speech-2.8-hd",
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )

    # Per-model quotas: different models smooth against independent queues.
    assert first.waited_seconds == 0
    assert second.waited_seconds == 0


def test_rpm_gate_smooths_same_model(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(rpm_gate, "_get_redis_client", lambda: fake_redis)
    now_fn, sleep_fn = _clock()

    first = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        model="speech-2.8-hd",
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )
    second = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        model="speech-2.8-hd",
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )

    assert first.waited_seconds == 0
    assert second.waited_seconds == pytest.approx(1.0)


def test_rpm_gate_times_out_when_queue_exceeds_max_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(rpm_gate, "_get_redis_client", lambda: fake_redis)
    now_fn, sleep_fn = _clock()

    rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=6,
        max_wait_seconds=10,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )

    with pytest.raises(rpm_gate.TTSRpmQueueTimeoutError):
        rpm_gate.acquire_tts_rpm_slot(
            provider="minimax",
            api_key="api-key-a",
            rpm_limit=6,
            max_wait_seconds=5,
            now_fn=now_fn,
            sleep_fn=sleep_fn,
        )


def test_rpm_gate_falls_back_to_process_local_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rpm_gate,
        "_get_redis_client",
        lambda: (_ for _ in ()).throw(RuntimeError("redis down")),
    )
    now_fn, sleep_fn = _clock()

    first = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )
    second = rpm_gate.acquire_tts_rpm_slot(
        provider="minimax",
        api_key="api-key-a",
        rpm_limit=60,
        max_wait_seconds=10,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
    )

    assert first.waited_seconds == 0
    assert second.waited_seconds == pytest.approx(1.0)
