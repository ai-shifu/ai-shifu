"""Exercise Live credential admission against an isolated real Redis server."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao
from flaskr.service.learn import live_follow_up_admission as admission
from flaskr.service.learn import live_follow_up_capacity as capacity
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import BinaryIO


class RedisHarness:
    """Own one disposable Redis process, socket, and database for a test."""

    def __init__(self, binary: str, directory: Path) -> None:
        """Keep all process state inside the explicitly created directory."""
        self.binary = binary
        self.directory = directory
        self.socket = directory / "redis.sock"
        self.log_path = directory / "redis.log"
        self.process: subprocess.Popen[bytes] | None = None
        self.log: BinaryIO | None = None
        self.client = Redis(
            unix_socket_path=str(self.socket),
            socket_timeout=2,
            socket_connect_timeout=2,
            decode_responses=True,
        )

    def start(self) -> None:
        self.log = self.log_path.open("ab")
        self.process = subprocess.Popen(
            [
                self.binary,
                "--port",
                "0",
                "--unixsocket",
                str(self.socket),
                "--unixsocketperm",
                "700",
                "--save",
                "",
                "--appendonly",
                "no",
                "--maxmemory-policy",
                "noeviction",
                "--dir",
                str(self.directory),
            ],
            stdout=self.log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                pytest.fail(f"Isolated Redis exited: {self.log_path.read_text()}")
            try:
                if self.client.ping():
                    return
            except RedisConnectionError:
                time.sleep(0.01)
        pytest.fail(f"Isolated Redis did not start: {self.log_path.read_text()}")

    def stop(self) -> None:
        self.client.connection_pool.disconnect()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log is not None:
            self.log.close()
            self.log = None


@pytest.fixture
def real_redis() -> Iterator[RedisHarness]:
    configured = os.environ.get("GEMINI_LIVE_TEST_REDIS_SERVER")
    binary = configured or shutil.which("redis-server")
    if not binary:
        if os.environ.get("GEMINI_LIVE_REQUIRE_REAL_REDIS") == "1":
            pytest.fail("Real Redis is required for Live admission tests")
        pytest.skip("Set GEMINI_LIVE_TEST_REDIS_SERVER or install redis-server")
    # Keep Unix socket paths short enough for both macOS and Linux.
    with tempfile.TemporaryDirectory(prefix="live-admission-", dir="/tmp") as temporary:
        harness = RedisHarness(binary, Path(temporary))
        try:
            harness.start()
            yield harness
        finally:
            harness.stop()


@pytest.fixture
def admission_app(real_redis: RedisHarness, monkeypatch: pytest.MonkeyPatch) -> Flask:
    application = Flask(__name__)
    application.config["REDIS_KEY_PREFIX"] = "live-admission-test:"
    monkeypatch.setattr(dao._redis_state, "client", real_redis.client)
    return application


def test_real_redis_lua_exposes_instance_generation_and_eviction_policy(
    real_redis: RedisHarness,
) -> None:
    result = real_redis.client.eval(
        """
        local server = redis.call('INFO', 'server')
        local memory = redis.call('INFO', 'memory')
        return {
            string.match(server, 'run_id:([^\\r\\n]+)'),
            string.match(memory, 'maxmemory_policy:([^\\r\\n]+)')
        }
        """,
        0,
    )
    assert result == [real_redis.client.info("server")["run_id"], "noeviction"]


def test_real_redis_restart_changes_instance_generation(
    real_redis: RedisHarness,
) -> None:
    original = real_redis.client.info("server")["run_id"]
    real_redis.stop()
    real_redis.start()
    assert real_redis.client.info("server")["run_id"] != original


def _now_ms(client: Redis) -> int:
    seconds, micros = client.time()
    return seconds * 1000 + micros // 1000


def _request_id(timestamp_ms: int) -> str:
    random = uuid.uuid4().int
    value = (
        (timestamp_ms << 80)
        | (7 << 76)
        | (((random >> 64) & 0xFFF) << 64)
        | (2 << 62)
        | (random & ((1 << 62) - 1))
    )
    return str(uuid.UUID(int=value))


def _request(client: Redis, **changes: object) -> admission.AdmissionRequest:
    request = admission.AdmissionRequest(
        request_bid=_request_id(_now_ms(client)),
        user_bid="user-1",
        origin="https://learning.example",
        shifu_bid="course-1",
        outline_bid="outline-1",
        anchor_element_bid="anchor-1",
        preview_mode=False,
        learning_mode="listen",
        surface="listen_panel",
    )
    return replace(request, **changes)


def _begin(
    application: Flask,
    request: admission.AdmissionRequest,
    *,
    worker: str = "worker-1",
    rotation: bool = True,
    legacy: bool = False,
) -> admission.AdmissionResult:
    return admission.begin_admission(
        application,
        request,
        session_bid=uuid.uuid4().hex,
        rotation_enabled=rotation,
        legacy=legacy,
        worker_id=worker,
    )


def _keys(
    application: Flask,
    request: admission.AdmissionRequest,
    result: admission.AdmissionResult | None = None,
    *,
    worker: str = "worker-1",
) -> tuple[str, ...]:
    return admission._keys(
        application,
        request,
        worker_id=worker,
        session_bid=str(result.data["session_bid"]) if result else "fixture-session",
    )


def _read_json(client: Redis, key: str) -> dict[str, object]:
    raw = client.get(key)
    assert raw is not None
    return json.loads(raw)


def _successor(
    client: Redis,
    request: admission.AdmissionRequest,
    result: admission.AdmissionResult,
    **changes: object,
) -> admission.AdmissionRequest:
    return replace(
        request,
        request_bid=_request_id(_now_ms(client)),
        replace_session_bid=str(result.data["session_bid"]),
        expected_admission_revision=str(result.data["admission_revision"]),
        **changes,
    )


def _complete(
    application: Flask,
    request: admission.AdmissionRequest,
    result: admission.AdmissionResult,
) -> None:
    assert result.lease is not None
    assert admission.complete_admission(
        application, request, result, session_payload='{"fixture_binding": true}'
    )


def _retire(
    application: Flask,
    request: admission.AdmissionRequest,
    result: admission.AdmissionResult,
    *,
    last_committed_index: int = 1,
) -> None:
    admission.retire_admission(
        application,
        request,
        session_bid=str(result.data["session_bid"]),
        admission_revision=str(result.data["admission_revision"]),
        expires_at_ms=result.issued_at_ms + 900_000,
        last_committed_index=last_committed_index,
    )


@pytest.fixture
def ready_app(admission_app: Flask, real_redis: RedisHarness) -> Flask:
    request = _request(real_redis.client)
    result = _begin(admission_app, request)
    assert result.data["error_code"] == "admission_unavailable"
    marker_key = _keys(admission_app, request)[7]
    marker = _read_json(real_redis.client, marker_key)
    marker["safe_after_ms"] = 0
    real_redis.client.set(marker_key, json.dumps(marker))
    return admission_app


def test_missing_accounting_marker_quarantines_before_any_reservation(
    admission_app: Flask,
    real_redis: RedisHarness,
) -> None:
    request = _request(real_redis.client)
    result = _begin(admission_app, request)
    assert result.lease is None
    assert result.data["error_code"] == "admission_unavailable"
    assert 899_000 <= result.data["retry_after_ms"] <= 900_000
    keys = _keys(admission_app, request)
    assert real_redis.client.exists(*keys[:7]) == 0
    marker = _read_json(real_redis.client, keys[7])
    assert marker["generation"] == real_redis.client.info("server")["run_id"]


def test_reservation_uses_redis_time_and_exact_credential_deadline(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    before = _now_ms(client)
    result = _begin(ready_app, request)
    after = _now_ms(client)
    assert result.lease is not None
    assert before <= result.issued_at_ms <= after
    assert result.deadline_ms == result.issued_at_ms + 15_000
    keys = _keys(ready_app, request, result)
    for key in keys[:3]:
        assert (
            client.zscore(key, result.lease.lease_id)
            == (result.issued_at_ms + 900_000) / 1000
        )
    assert 1_199_000 <= client.pttl(keys[4]) <= 1_200_000
    assert client.get(keys[9]) is None
    _complete(ready_app, request, result)
    assert client.get(keys[9]) == '{"fixture_binding": true}'


def test_exact_idempotent_duplicate_returns_metadata_without_new_risk_or_rate(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    first = _begin(ready_app, request)
    second = _begin(ready_app, request, worker="another-worker")
    assert second.lease is None
    assert second.data == first.data
    _complete(ready_app, request, first)
    third = _begin(ready_app, request)
    assert third.lease is None
    assert third.data["operation_status"] == "issued"
    assert third.data["session_bid"] == first.data["session_bid"]
    assert set(third.data) == {
        "request_bid",
        "operation_status",
        "session_bid",
        "admission_revision",
        "ownership_current",
        "rotation_enabled",
    }
    keys = _keys(ready_app, request, first)
    assert [client.zcard(keys[index]) for index in (0, 1, 2, 5, 6)] == [1] * 5


@pytest.mark.parametrize(
    "changes",
    [
        {"origin": "https://another.example"},
        {"shifu_bid": "another-course"},
        {"outline_bid": "another-outline"},
        {"anchor_element_bid": "another-anchor"},
        {"preview_mode": True},
        {"learning_mode": "read"},
        {"expected_admission_revision": "mutated-revision"},
    ],
)
def test_same_request_id_rejects_mutated_immutable_binding(
    ready_app: Flask,
    real_redis: RedisHarness,
    changes: dict[str, object],
) -> None:
    request = _request(real_redis.client)
    _begin(ready_app, request)
    result = _begin(ready_app, replace(request, **changes))
    assert result.lease is None
    assert result.data["error_code"] == "operation_conflict"


def test_concurrent_initial_requests_have_one_logical_owner(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    requests = [_request(real_redis.client) for _ in range(12)]
    with ThreadPoolExecutor(max_workers=12) as workers:
        results = list(
            workers.map(lambda request: _begin(ready_app, request), requests)
        )
    assert sum(result.lease is not None for result in results) == 1
    assert all(
        result.lease is not None or result.data["error_code"] == "ownership_conflict"
        for result in results
    )


def test_concurrent_predecessor_cas_has_one_winner_across_workers(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original)
    _complete(ready_app, original, first)
    requests = [_successor(client, original, first) for _ in range(10)]
    with ThreadPoolExecutor(max_workers=10) as workers:
        results = list(
            workers.map(
                lambda pair: _begin(ready_app, pair[1], worker=f"worker-{pair[0]}"),
                enumerate(requests),
            )
        )
    assert sum(result.lease is not None for result in results) == 1
    assert all(
        result.lease is not None or result.data["error_code"] == "ownership_conflict"
        for result in results
    )
    assert client.zcard(_keys(ready_app, original, first)[0]) == 2


def test_three_credentials_per_user_remain_counted_after_retirement(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    first = None
    for index in range(3):
        result = _begin(ready_app, request, worker=f"worker-{index}")
        _complete(ready_app, request, result)
        _retire(ready_app, request, result)
        first = first or result
        request = _successor(client, request, result)
    rejected = _begin(ready_app, request, worker="worker-new")
    assert rejected.lease is None
    assert rejected.data["error_code"] == "capacity_exceeded"
    assert 899_000 <= rejected.data["retry_after_ms"] <= 900_000
    assert first is not None
    assert client.zcard(_keys(ready_app, request, first)[2]) == 3


def test_worker_limit_is_six_outstanding_credentials(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    for index in range(6):
        assert _begin(ready_app, _request(client, user_bid=f"user-{index}")).lease
    rejected = _begin(ready_app, _request(client, user_bid="overflow-user"))
    assert rejected.lease is None
    assert rejected.data["error_code"] == "capacity_exceeded"


def test_global_limit_is_twenty_four_outstanding_credentials(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    for index in range(24):
        result = _begin(
            ready_app,
            _request(client, user_bid=f"user-{index}"),
            worker=f"worker-{index // 6}",
        )
        assert result.lease is not None
    rejected = _begin(
        ready_app,
        _request(client, user_bid="overflow-user"),
        worker="new-worker",
    )
    assert rejected.lease is None
    assert rejected.data["error_code"] == "capacity_exceeded"


def test_undisclosed_failure_frees_only_its_risk_not_rolling_mint_rate(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    first = _begin(ready_app, request)
    _complete(ready_app, request, first)
    second_request = _successor(client, request, first)
    second = _begin(ready_app, second_request)
    admission.fail_admission(ready_app, second_request, second, undisclosed=True)
    keys = _keys(ready_app, second_request, second)
    assert [client.zcard(keys[index]) for index in (0, 1, 2)] == [1, 1, 1]
    assert client.zscore(keys[0], first.lease.lease_id) is not None
    assert [client.zcard(keys[index]) for index in (5, 6)] == [2, 2]


def test_uncertain_issuance_keeps_risk_for_full_credential_lifetime(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    request = _request(real_redis.client)
    result = _begin(ready_app, request)
    admission.fail_admission(ready_app, request, result, undisclosed=False)
    keys = _keys(ready_app, request, result)
    assert [real_redis.client.zcard(keys[index]) for index in (0, 1, 2, 5, 6)] == [
        1
    ] * 5


def test_user_rolling_rate_is_four_even_when_all_tokens_were_undisclosed(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    for _ in range(4):
        result = _begin(ready_app, request)
        assert result.lease is not None
        admission.fail_admission(ready_app, request, result, undisclosed=True)
        request = _successor(client, request, result)
    rejected = _begin(ready_app, request)
    assert rejected.lease is None
    assert rejected.data["error_code"] == "capacity_exceeded"
    assert 59_000 <= rejected.data["retry_after_ms"] <= 60_000


def test_global_rolling_rate_is_twenty_four_across_users_and_workers(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    for index in range(24):
        request = _request(client, user_bid=f"user-{index}")
        result = _begin(ready_app, request, worker=f"worker-{index}")
        assert result.lease is not None
        admission.fail_admission(ready_app, request, result, undisclosed=True)
    rejected = _begin(
        ready_app, _request(client, user_bid="new-user"), worker="new-worker"
    )
    assert rejected.lease is None
    assert rejected.data["error_code"] == "capacity_exceeded"
    assert 59_000 <= rejected.data["retry_after_ms"] <= 60_000


def test_old_end_cannot_retire_successor_or_release_either_risk(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original)
    _complete(ready_app, original, first)
    successor = _successor(client, original, first, anchor_element_bid="new-anchor")
    second = _begin(ready_app, successor)
    _complete(ready_app, successor, second)
    _retire(ready_app, original, first)
    assert admission.current_admission(
        ready_app,
        successor,
        session_bid=str(second.data["session_bid"]),
        admission_revision=str(second.data["admission_revision"]),
    )
    assert client.zcard(_keys(ready_app, original, first)[0]) == 2


def test_retired_pending_operation_cannot_be_resurrected_by_late_completion(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    request = _request(real_redis.client)
    result = _begin(ready_app, request)
    _retire(ready_app, request, result)
    assert (
        admission.complete_admission(
            ready_app,
            request,
            result,
            session_payload='{"late": true}',
        )
        is False
    )
    assert real_redis.client.get(_keys(ready_app, request, result)[9]) is None


def test_predecessor_replay_is_rejected_even_after_successor_also_ends(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original)
    _complete(ready_app, original, first)
    _retire(ready_app, original, first)
    successor = _successor(client, original, first)
    second = _begin(ready_app, successor)
    _complete(ready_app, successor, second)
    _retire(ready_app, successor, second)
    replay = _begin(ready_app, _successor(client, original, first))
    assert replay.lease is None
    assert replay.data["error_code"] == "ownership_conflict"


@pytest.mark.parametrize("offset_ms", [-1_200_001, -120_001, 31_000])
def test_stale_or_future_request_id_never_reserves_or_recreates_tombstone(
    ready_app: Flask,
    real_redis: RedisHarness,
    offset_ms: int,
) -> None:
    client = real_redis.client
    request = _request(client, request_bid=_request_id(_now_ms(client) + offset_ms))
    result = _begin(ready_app, request)
    assert result.lease is None
    assert result.data["error_code"] == "stale_request"
    assert str(result.data["server_time"]).endswith("Z")
    keys = _keys(ready_app, request)
    assert client.exists(*keys[:7]) == 0


@pytest.mark.parametrize("offset_ms", [-119_000, 29_000])
def test_request_id_within_accepted_clock_window_can_reserve(
    ready_app: Flask,
    real_redis: RedisHarness,
    offset_ms: int,
) -> None:
    request = _request(
        real_redis.client,
        request_bid=_request_id(_now_ms(real_redis.client) + offset_ms),
    )
    assert _begin(ready_app, request).lease is not None


def test_expired_id_status_recovers_original_metadata_without_new_mint(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    result = _begin(ready_app, request)
    _complete(ready_app, request, result)
    # Move the same completed fixture to an already-aged ID without waiting
    # two minutes. Its immutable target explicitly excludes request_bid.
    aged = replace(request, request_bid=_request_id(_now_ms(client) - 121_000))
    old_keys = _keys(ready_app, request, result)
    aged_keys = _keys(ready_app, aged, result)
    client.rename(old_keys[4], aged_keys[4])
    snapshot = {key: client.dump(key) for key in client.scan_iter()}
    status = admission.admission_status(ready_app, aged, rotation_enabled=True)
    assert status["operation_status"] == "issued"
    assert status["session_bid"] == result.data["session_bid"]
    assert status["ownership_current"] is True
    assert set(status) == {
        "request_bid",
        "operation_status",
        "session_bid",
        "admission_revision",
        "ownership_current",
        "rotation_enabled",
    }
    assert {key: client.dump(key) for key in client.scan_iter()} == snapshot


def test_missing_status_lookup_is_read_only_and_cannot_create_an_operation(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    snapshot = {key: client.dump(key) for key in client.scan_iter()}
    status = admission.admission_status(ready_app, request, rotation_enabled=True)
    assert status == {
        "request_bid": request.request_bid,
        "operation_status": "missing",
        "ownership_current": False,
        "rotation_enabled": True,
    }
    assert {key: client.dump(key) for key in client.scan_iter()} == snapshot


def test_stale_operation_status_does_not_reveal_successor_identity(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original)
    _complete(ready_app, original, first)
    successor = _successor(client, original, first)
    second = _begin(ready_app, successor)
    status = admission.admission_status(ready_app, original, rotation_enabled=True)
    assert status["ownership_current"] is False
    assert status["session_bid"] == first.data["session_bid"]
    assert str(second.data["session_bid"]) not in json.dumps(status)
    assert str(second.data["admission_revision"]) not in json.dumps(status)


def test_expired_pending_issuance_cannot_complete_but_explicit_successor_can_start(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original)
    keys = _keys(ready_app, original, first)
    for index in (3, 4):
        record = _read_json(client, keys[index])
        record["deadline_ms"] = _now_ms(client) - 1
        client.set(keys[index], json.dumps(record), keepttl=True)
    status = admission.admission_status(ready_app, original, rotation_enabled=True)
    assert status["operation_status"] == "cancelled"
    assert (
        admission.complete_admission(
            ready_app,
            original,
            first,
            session_payload='{"late": true}',
        )
        is False
    )
    successor = _successor(client, original, first)
    second = _begin(ready_app, successor)
    assert second.lease is not None
    assert client.zcard(keys[0]) == 2


def test_still_pending_operation_rejects_distinct_successor_before_deadline(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    original = _request(real_redis.client)
    first = _begin(ready_app, original)
    second = _begin(ready_app, _successor(real_redis.client, original, first))
    assert second.lease is None
    assert second.data["error_code"] == "ownership_conflict"


def test_rotation_disabled_keeps_current_single_credential_contract(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    original = _request(real_redis.client)
    first = _begin(ready_app, original, rotation=False)
    _complete(ready_app, original, first)
    _retire(ready_app, original, first)
    second = _begin(
        ready_app,
        _successor(real_redis.client, original, first),
        rotation=False,
    )
    assert second.lease is None
    assert second.data["error_code"] == "capacity_exceeded"
    assert second.data["rotation_enabled"] is False


def test_rotation_disabled_still_counts_all_previously_issued_v2_risk(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    for _ in range(3):
        result = _begin(ready_app, request)
        _complete(ready_app, request, result)
        request = _successor(client, request, result)
    keys = _keys(ready_app, request)
    rejected = _begin(ready_app, request, rotation=False)
    assert rejected.data["error_code"] == "capacity_exceeded"
    assert [client.zcard(keys[index]) for index in (0, 1, 2)] == [3] * 3


def test_old_client_cannot_use_rotation_to_bypass_single_credential_guard(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original, legacy=True)
    _complete(ready_app, original, first)
    second = _begin(ready_app, _successor(client, original, first), legacy=True)
    assert second.lease is None
    assert second.data["error_code"] == "capacity_exceeded"


def test_existing_legacy_credential_blocks_v2_admission_for_same_user(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    capacity.acquire_live_follow_up_capacity(
        ready_app,
        user_bid=request.user_bid,
        worker_id="legacy-worker",
        now=_now_ms(client) / 1000,
    )
    result = _begin(ready_app, request)
    assert result.lease is None
    assert result.data["error_code"] == "capacity_exceeded"
    assert client.zcard(_keys(ready_app, request)[0]) == 1


def test_legacy_and_v2_share_existing_worker_and_global_risk_sets(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    for index in range(6):
        capacity.acquire_live_follow_up_capacity(
            ready_app,
            user_bid=f"legacy-user-{index}",
            worker_id="shared-worker",
            now=_now_ms(client) / 1000,
        )
    result = _begin(ready_app, _request(client), worker="shared-worker")
    assert result.lease is None
    assert result.data["error_code"] == "capacity_exceeded"


def test_rolling_window_prunes_exactly_expired_attempts_before_admission(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    keys = _keys(ready_app, request)
    expired_at = _now_ms(client) - 60_000
    client.zadd(
        keys[5], {f"past-user-attempt-{index}": expired_at for index in range(4)}
    )
    client.zadd(
        keys[6], {f"past-global-attempt-{index}": expired_at for index in range(24)}
    )
    result = _begin(ready_app, request)
    assert result.lease is not None
    assert client.zcard(keys[5]) == client.zcard(keys[6]) == 1


def test_busy_delay_accounts_for_every_blocking_risk_and_rate_quota(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    keys = _keys(ready_app, request)
    now = _now_ms(client)
    client.zadd(
        keys[0], {f"global-risk-{index}": (now + 90_000) / 1000 for index in range(24)}
    )
    client.zadd(
        keys[2], {f"user-risk-{index}": (now + 120_000) / 1000 for index in range(3)}
    )
    client.zadd(keys[5], {f"user-attempt-{index}": now for index in range(4)})
    result = _begin(ready_app, request)
    assert result.lease is None
    assert result.data["error_code"] == "capacity_exceeded"
    assert 119_000 <= result.data["retry_after_ms"] <= 120_000


def test_retirement_receipt_survives_consumed_history_binding_and_keeps_cursor(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    result = _begin(ready_app, request)
    _complete(ready_app, request, result)
    keys = _keys(ready_app, request, result)
    _retire(ready_app, request, result, last_committed_index=8)
    client.delete(keys[9])
    _retire(ready_app, request, result, last_committed_index=3)
    receipt = _read_json(client, keys[10])
    assert receipt["last_committed_index"] == 8
    assert receipt["session_bid"] == result.data["session_bid"]
    assert (
        client.pttl(keys[10]) >= result.issued_at_ms + 1_200_000 - _now_ms(client) - 10
    )
    assert client.pttl(keys[3]) >= client.pttl(keys[10])
    assert "fixture_binding" not in json.dumps(receipt)
    replacement = _begin(ready_app, _successor(client, request, result))
    assert replacement.lease is not None


def test_missing_marker_after_prior_issuance_never_means_empty_risk(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    result = _begin(ready_app, request)
    _complete(ready_app, request, result)
    keys = _keys(ready_app, request, result)
    client.delete(keys[7])
    replacement = _begin(ready_app, _successor(client, request, result))
    assert replacement.lease is None
    assert replacement.data["error_code"] == "admission_unavailable"
    assert client.zcard(keys[0]) == 1
    assert replacement.data["retry_after_ms"] > 899_000


def test_total_accounting_loss_quarantines_even_if_no_risk_keys_survive(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    _begin(ready_app, _request(client))
    client.flushdb()
    result = _begin(ready_app, _request(client))
    assert result.lease is None
    assert result.data["error_code"] == "admission_unavailable"
    assert result.data["retry_after_ms"] > 899_000


def test_surviving_old_marker_after_redis_restart_triggers_generation_quarantine(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    result = _begin(ready_app, request)
    keys = _keys(ready_app, request, result)
    marker = client.get(keys[7])
    old_generation = client.info("server")["run_id"]
    real_redis.stop()
    real_redis.start()
    client.set(keys[7], marker)
    replacement = _begin(ready_app, _request(client))
    assert replacement.lease is None
    assert replacement.data["error_code"] == "admission_unavailable"
    restored = _read_json(client, keys[7])
    assert restored["generation"] != old_generation
    assert restored["safe_after_ms"] > _now_ms(client) + 899_000


def test_evicting_redis_policy_is_rejected_without_mutating_capacity(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    client.config_set("maxmemory-policy", "allkeys-lru")
    request = _request(client)
    result = _begin(ready_app, request)
    assert result.lease is None
    assert result.data["error_code"] == "admission_unavailable"
    assert client.exists(*_keys(ready_app, request)[:7]) == 0


def test_redis_unavailability_fails_closed_before_issuance(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    request = _request(real_redis.client)
    real_redis.stop()
    with pytest.raises(capacity.LiveFollowUpCapacityUnavailableError):
        _begin(ready_app, request)


def test_fresh_initial_after_retirement_advances_head_and_invalidates_old_receipt(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original)
    _complete(ready_app, original, first)
    _retire(ready_app, original, first)
    fresh = _request(client, anchor_element_bid="new-anchor")
    second = _begin(ready_app, fresh)
    _complete(ready_app, fresh, second)
    assert second.data["admission_revision"] != first.data["admission_revision"]
    assert client.zcard(_keys(ready_app, fresh, second)[0]) == 2
    replay = _begin(ready_app, _successor(client, original, first))
    assert replay.lease is None
    assert replay.data["error_code"] == "ownership_conflict"


def test_expired_pending_head_allows_fresh_initial_without_lost_response_metadata(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original)
    keys = _keys(ready_app, original, first)
    for index in (3, 4):
        record = _read_json(client, keys[index])
        record["deadline_ms"] = _now_ms(client) - 1
        client.set(keys[index], json.dumps(record), keepttl=True)
    fresh = _begin(ready_app, _request(client))
    assert fresh.lease is not None
    assert fresh.data["session_bid"] != first.data["session_bid"]
    assert client.zcard(keys[0]) == 2


@pytest.mark.parametrize(
    ("rotation", "legacy"), [(False, False), (False, True), (True, True)]
)
def test_recovery_gate_also_protects_flag_off_and_legacy_admission(
    admission_app: Flask,
    real_redis: RedisHarness,
    *,
    rotation: bool,
    legacy: bool,
) -> None:
    request = _request(real_redis.client)
    result = _begin(admission_app, request, rotation=rotation, legacy=legacy)
    assert result.lease is None
    assert result.data["error_code"] == "admission_unavailable"
    assert real_redis.client.exists(*_keys(admission_app, request)[:7]) == 0


@pytest.mark.parametrize("limit", [6, 24])
def test_concurrent_workers_cannot_overshoot_risk_and_mint_limits(
    ready_app: Flask,
    real_redis: RedisHarness,
    limit: int,
) -> None:
    client = real_redis.client
    requests = [
        _request(client, user_bid=f"user-{index}") for index in range(limit + 12)
    ]
    with ThreadPoolExecutor(max_workers=12) as workers:
        results = list(
            workers.map(
                lambda pair: _begin(
                    ready_app,
                    pair[1],
                    worker="shared-worker" if limit == 6 else f"worker-{pair[0]}",
                ),
                enumerate(requests),
            )
        )
    assert sum(result.lease is not None for result in results) == limit
    assert all(
        result.lease is not None or result.data["error_code"] == "capacity_exceeded"
        for result in results
    )
    keys = _keys(ready_app, requests[0], worker="shared-worker")
    assert client.zcard(keys[0]) == limit
    assert client.zcard(keys[6]) == limit
    if limit == 6:
        assert client.zcard(keys[1]) == limit


def test_expired_risk_and_legacy_guard_allow_fresh_initial_without_old_receipt(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    original = _request(client)
    first = _begin(ready_app, original)
    _complete(ready_app, original, first)
    keys = _keys(ready_app, original, first)
    expired_at = _now_ms(client) - 1
    for key in keys[:3]:
        client.zadd(key, {first.lease.lease_id: expired_at / 1000})
    head = _read_json(client, keys[3])
    head["expires_at_ms"] = expired_at
    client.set(keys[3], json.dumps(head), keepttl=True)
    client.pexpireat(keys[8], expired_at)
    second = _begin(ready_app, _request(client), rotation=False)
    assert second.lease is not None
    assert client.zcard(keys[0]) == 1
    assert client.zscore(keys[0], first.lease.lease_id) is None


def test_corrupt_accounting_marker_fails_closed_without_capacity_side_effects(
    ready_app: Flask,
    real_redis: RedisHarness,
) -> None:
    client = real_redis.client
    request = _request(client)
    keys = _keys(ready_app, request)
    client.set(keys[7], "malformed fixture accounting")
    with pytest.raises(capacity.LiveFollowUpCapacityUnavailableError):
        _begin(ready_app, request)
    assert client.exists(*keys[:7]) == 0
