"""Verify temporary speech-token validation and lock-safe refresh failures."""

import json
from unittest.mock import Mock

import pytest
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
