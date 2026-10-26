"""Verify temporary speech-token validation and lock-safe refresh failures."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from flaskr.api.tts import aliyun_nls_token as nls
from flaskr.common.cache_provider import InMemoryCacheProvider


@pytest.mark.parametrize(
    "raw",
    [
        None,
        b"",
        " ",
        "not JSON",
        123,
        "null",
        "[]",
        {},
        '{"token":"","expire_time":200}',
        '{"token":"test","expire_time":"bad"}',
        '{"token":"test","expire_time":0}',
    ],
)
def test_invalid_cache_entries_do_not_become_usable_tokens(raw: object) -> None:
    assert nls._decode_cache_value(raw) is None


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (
            {
                "ALIYUN_AK_ID": "dedicated",
                "ALIYUN_AK_SECRET": "secret",
                "ALIBABA_CLOUD_OSS_ACCESS_KEY_ID": "fallback",
                "ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET": "fallback-secret",
            },
            ("dedicated", "secret"),
        ),
        (
            {
                "ALIYUN_AK_ID": "incomplete",
                "ALIBABA_CLOUD_OSS_ACCESS_KEY_ID": "fallback",
                "ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET": "fallback-secret",
            },
            ("fallback", "fallback-secret"),
        ),
        ({"ALIYUN_AK_ID": "incomplete"}, ("", "")),
    ],
)
def test_access_keys_use_complete_pairs_without_mixing_profiles(
    monkeypatch: pytest.MonkeyPatch, settings: dict, expected: tuple
) -> None:
    monkeypatch.setattr(nls, "get_config", settings.get)
    assert nls._get_access_keys() == expected
    assert nls.is_aliyun_nls_token_configured() is bool(expected[0])


@pytest.mark.parametrize(
    ("status", "payload", "error", "expected"),
    [
        (503, {}, None, "HTTP 503"),
        (200, {}, ValueError("invalid JSON"), "not valid JSON"),
        (
            200,
            {"RequestId": "request"},
            None,
            "missing Token.Id or Token.ExpireTime.*request_id=request",
        ),
        (200, {"Token": {"Id": "test"}}, None, "missing Token.Id or Token.ExpireTime"),
        (
            200,
            {"Token": {"Id": "test", "ExpireTime": "invalid"}},
            None,
            "invalid ExpireTime",
        ),
    ],
)
def test_provider_token_response_errors_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    payload: dict,
    error: Exception | None,
    expected: str,
) -> None:
    response = Mock(status_code=status, text="provider response")
    response.json.return_value = payload
    response.json.side_effect = error
    monkeypatch.setattr(nls.requests, "get", Mock(return_value=response))
    with pytest.raises(ValueError, match=expected):
        nls._request_new_token("test-id", "test-secret")


def test_request_failure_preserves_original_network_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = requests.ConnectionError("offline")
    monkeypatch.setattr(nls.requests, "get", Mock(side_effect=failure))
    with pytest.raises(ValueError, match="token request failed") as caught:
        nls._request_new_token("test-id", "test-secret")
    assert caught.value.__cause__ is failure


@pytest.fixture
def refresh(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    config = {"ALIYUN_AK_ID": "test-id", "ALIYUN_AK_SECRET": "test-secret"}
    monkeypatch.setattr(
        nls, "get_config", lambda key, default=None: config.get(key, default)
    )
    monkeypatch.setattr(nls, "time", SimpleNamespace(time=lambda: 100))
    cache = Mock()
    cache.get.return_value = None
    cache.lock.return_value.acquire.return_value = True
    request = Mock(return_value=nls.AliyunNlsToken("fresh", 500))
    monkeypatch.setattr(nls, "cache", cache)
    monkeypatch.setattr(nls, "_request_new_token", request)
    return SimpleNamespace(cache=cache, request=request, config=config)


def test_refresh_rechecks_cache_under_lock_and_reuses_another_workers_token(
    refresh: SimpleNamespace,
) -> None:
    refresh.cache.get.side_effect = [
        None,
        json.dumps({"token": "other-worker", "expire_time": 500}),
    ]
    assert nls.get_aliyun_nls_token() == "other-worker"
    refresh.request.assert_not_called()
    refresh.cache.lock.return_value.release.assert_called_once()


def test_force_refresh_ignores_cached_value_and_persists_new_expiry(
    refresh: SimpleNamespace,
) -> None:
    assert nls.get_aliyun_nls_token(force_refresh=True) == "fresh"
    refresh.cache.get.assert_not_called()
    refresh.request.assert_called_once_with("test-id", "test-secret")
    args, kwargs = refresh.cache.set.call_args
    assert json.loads(args[1]) == {"token": "fresh", "expire_time": 500}
    assert kwargs == {"ex": 400}
    refresh.cache.lock.return_value.release.assert_called_once()


def test_refresh_without_lock_ownership_does_not_release_another_workers_lock(
    refresh: SimpleNamespace,
) -> None:
    refresh.cache.lock.return_value.acquire.return_value = False
    assert nls.get_aliyun_nls_token() == "fresh"
    refresh.cache.lock.return_value.release.assert_not_called()


def test_expired_cache_cannot_mask_refresh_failure(refresh: SimpleNamespace) -> None:
    refresh.cache.get.return_value = json.dumps({"token": "expired", "expire_time": 99})
    refresh.request.side_effect = ValueError("provider unavailable")
    with pytest.raises(ValueError, match="provider unavailable"):
        nls.get_aliyun_nls_token()
    refresh.cache.lock.return_value.release.assert_called_once()
    refresh.cache.set.assert_not_called()


def test_release_failure_does_not_discard_successful_refresh(
    refresh: SimpleNamespace,
) -> None:
    refresh.cache.lock.return_value.release.side_effect = RuntimeError("lock expired")
    assert nls.get_aliyun_nls_token() == "fresh"


def test_missing_access_keys_fail_without_lock_or_network(
    refresh: SimpleNamespace,
) -> None:
    refresh.config.clear()
    with pytest.raises(ValueError, match="token is not configured"):
        nls.get_aliyun_nls_token()
    refresh.cache.lock.assert_not_called()
    refresh.request.assert_not_called()


def test_expired_token_cache_uses_minimum_positive_ttl(
    refresh: SimpleNamespace,
) -> None:
    nls._store_cache_value(nls.AliyunNlsToken("expired", 99))
    assert refresh.cache.set.call_args.kwargs == {"ex": 1}
    token = nls.AliyunNlsToken("expired", 99)
    assert token.expires_in_seconds == 0
    assert token.is_expired()
    assert nls._percent_encode(None) == ""


@pytest.mark.parametrize(
    "token", [None, False, True, 0, 1, 1.25, [], ["token"], {}, {"Id": "token"}]
)
def test_cached_token_requires_a_string_before_whitespace_normalization(
    token: object,
) -> None:
    assert (
        nls._decode_cache_value(json.dumps({"token": token, "expire_time": 500}))
        is None
    )


@pytest.mark.parametrize("corrupt_after_lock", [False, True])
def test_malformed_cached_token_is_refreshed_and_replaced_with_a_usable_value(
    monkeypatch: pytest.MonkeyPatch,
    corrupt_after_lock: bool,
) -> None:
    cache = InMemoryCacheProvider()
    monkeypatch.setattr(nls, "cache", cache)
    settings = {"ALIYUN_AK_ID": "test-key", "ALIYUN_AK_SECRET": "test-secret"}
    monkeypatch.setattr(
        nls, "get_config", lambda name, default=None: settings.get(name, default)
    )
    monkeypatch.setattr(nls.time, "time", lambda: 100)
    key = nls._get_cache_key()
    corrupt = json.dumps({"token": {"Id": "invalid"}, "expire_time": 500})
    cache.set(key, corrupt, ex=60)
    if corrupt_after_lock:
        original_get = cache.get
        reads = 0

        def read(key: str) -> object:
            nonlocal reads
            reads += 1
            return None if reads == 1 else original_get(key)

        monkeypatch.setattr(cache, "get", read)
    fetch = Mock(return_value=nls.AliyunNlsToken("replacement", 500))
    monkeypatch.setattr(nls, "_request_new_token", fetch)
    assert nls.get_aliyun_nls_token() == "replacement"
    assert nls.get_aliyun_nls_token() == "replacement"
    fetch.assert_called_once_with("test-key", "test-secret")
    assert json.loads(cache.get(key)) == {"token": "replacement", "expire_time": 500}
    lock = cache.lock(nls._get_lock_key(), timeout=15, blocking_timeout=0)
    assert lock.acquire(blocking=False)
    lock.release()


def test_cached_string_token_keeps_whitespace_trimming() -> None:
    assert nls._decode_cache_value(
        '{"token":"  usable  ","expire_time":500}'
    ) == nls.AliyunNlsToken("usable", 500)
