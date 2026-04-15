from __future__ import annotations

from types import SimpleNamespace

import requests

from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.common import umami_client


def _mock_config(monkeypatch, values: dict[str, object]) -> None:
    monkeypatch.setattr(
        umami_client,
        "get_config",
        lambda key: values.get(key, ""),
    )


def test_get_course_visit_count_30d_counts_all_metric_pages(app, monkeypatch):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_SITE_ID": "site-1",
            "ANALYTICS_UMAMI_API_KEY": "api-key",
            "ANALYTICS_UMAMI_API_URL": "",
            "ANALYTICS_UMAMI_CACHE_EXPIRE_SECONDS": 900,
            "ANALYTICS_UMAMI_TIMEOUT_SECONDS": 10,
            "REDIS_KEY_PREFIX": "test:",
        },
    )
    monkeypatch.setattr(umami_client, "cache", InMemoryCacheProvider())

    calls: list[dict[str, object]] = []

    def _fake_get(url, params=None, headers=None, timeout=None):
        calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        offset = int((params or {}).get("offset", 0))
        size = 500 if offset == 0 else 2
        rows = [{"x": f"user-{offset + i}", "y": 1} for i in range(size)]
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: rows,
        )

    monkeypatch.setattr(umami_client.requests, "get", _fake_get)

    with app.app_context():
        assert umami_client.get_course_visit_count_30d(app, "course-1") == 502

    assert len(calls) == 2
    assert calls[0]["url"] == "https://api.umami.is/v1/websites/site-1/metrics"
    assert calls[0]["params"]["type"] == "distinctId"
    assert calls[0]["params"]["event"] == "course_visit_course-1"
    assert calls[0]["headers"]["x-umami-api-key"] == "api-key"


def test_get_course_visit_count_30d_uses_cached_value(app, monkeypatch):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_SITE_ID": "site-1",
            "ANALYTICS_UMAMI_API_KEY": "api-key",
            "ANALYTICS_UMAMI_API_URL": "",
            "ANALYTICS_UMAMI_CACHE_EXPIRE_SECONDS": 900,
            "ANALYTICS_UMAMI_TIMEOUT_SECONDS": 10,
            "REDIS_KEY_PREFIX": "test:",
        },
    )
    monkeypatch.setattr(umami_client, "cache", InMemoryCacheProvider())

    request_count = {"value": 0}

    def _fake_get(url, params=None, headers=None, timeout=None):
        request_count["value"] += 1
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: [{"x": "user-1", "y": 1}],
        )

    monkeypatch.setattr(umami_client.requests, "get", _fake_get)

    with app.app_context():
        assert umami_client.get_course_visit_count_30d(app, "course-1") == 1
        assert umami_client.get_course_visit_count_30d(app, "course-1") == 1

    assert request_count["value"] == 1


def test_get_course_visit_count_30d_returns_zero_without_required_config(
    app, monkeypatch
):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_SITE_ID": "",
            "ANALYTICS_UMAMI_API_KEY": "",
            "ANALYTICS_UMAMI_API_URL": "",
            "ANALYTICS_UMAMI_SCRIPT": "",
            "REDIS_KEY_PREFIX": "test:",
        },
    )
    monkeypatch.setattr(umami_client, "cache", InMemoryCacheProvider())

    with app.app_context():
        assert umami_client.get_course_visit_count_30d(app, "course-1") == 0


def test_build_course_visit_event_name_normalizes_non_ascii_to_match_frontend():
    assert umami_client.build_course_visit_event_name("课程-1") == "course_visit___-1"


def test_get_course_visit_count_30d_caches_failures_briefly(app, monkeypatch):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_SITE_ID": "site-1",
            "ANALYTICS_UMAMI_API_KEY": "api-key",
            "ANALYTICS_UMAMI_API_URL": "",
            "ANALYTICS_UMAMI_CACHE_EXPIRE_SECONDS": 900,
            "ANALYTICS_UMAMI_TIMEOUT_SECONDS": 10,
            "REDIS_KEY_PREFIX": "test:",
        },
    )
    monkeypatch.setattr(umami_client, "cache", InMemoryCacheProvider())

    request_count = {"value": 0}

    def _fake_get(url, params=None, headers=None, timeout=None):
        request_count["value"] += 1
        raise requests.RequestException("umami unavailable")

    monkeypatch.setattr(umami_client.requests, "get", _fake_get)

    with app.app_context():
        assert umami_client.get_course_visit_count_30d(app, "course-1") == 0
        assert umami_client.get_course_visit_count_30d(app, "course-1") == 0

    assert request_count["value"] == 1


def test_get_course_visit_count_30d_uses_event_name_cache_key(app, monkeypatch):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_SITE_ID": "site-1",
            "ANALYTICS_UMAMI_API_KEY": "api-key",
            "ANALYTICS_UMAMI_API_URL": "",
            "ANALYTICS_UMAMI_CACHE_EXPIRE_SECONDS": 900,
            "ANALYTICS_UMAMI_TIMEOUT_SECONDS": 10,
            "REDIS_KEY_PREFIX": "test:",
        },
    )
    cache_provider = InMemoryCacheProvider()
    monkeypatch.setattr(umami_client, "cache", cache_provider)
    cache_provider.setex(
        "test:analytics:umami:course-visits:30d:course_visit___-1", 60, 9
    )

    with app.app_context():
        assert umami_client.get_course_visit_count_30d(app, "课程-1") == 9


def test_get_course_visit_count_30d_returns_fetched_value_when_cache_write_fails(
    app, monkeypatch
):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_SITE_ID": "site-1",
            "ANALYTICS_UMAMI_API_KEY": "api-key",
            "ANALYTICS_UMAMI_API_URL": "",
            "ANALYTICS_UMAMI_CACHE_EXPIRE_SECONDS": 900,
            "ANALYTICS_UMAMI_TIMEOUT_SECONDS": 10,
            "REDIS_KEY_PREFIX": "test:",
        },
    )

    class CacheWrapper:
        def __init__(self):
            self._cache = InMemoryCacheProvider()

        def get(self, key):
            return self._cache.get(key)

        def delete(self, *keys):
            return self._cache.delete(*keys)

        def setex(self, key, ttl, value):
            raise RuntimeError("cache unavailable")

        def lock(self, key, timeout=None, blocking_timeout=None):
            return self._cache.lock(
                key, timeout=timeout, blocking_timeout=blocking_timeout
            )

    monkeypatch.setattr(umami_client, "cache", CacheWrapper())
    monkeypatch.setattr(
        umami_client,
        "_fetch_distinct_ids_for_event",
        lambda **kwargs: 7,
    )

    with app.app_context():
        assert umami_client.get_course_visit_count_30d(app, "course-1") == 7


def test_get_course_visit_count_30d_returns_zero_when_failure_cache_write_fails(
    app, monkeypatch
):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_SITE_ID": "site-1",
            "ANALYTICS_UMAMI_API_KEY": "api-key",
            "ANALYTICS_UMAMI_API_URL": "",
            "ANALYTICS_UMAMI_CACHE_EXPIRE_SECONDS": 900,
            "ANALYTICS_UMAMI_TIMEOUT_SECONDS": 10,
            "REDIS_KEY_PREFIX": "test:",
        },
    )

    class CacheWrapper:
        def __init__(self):
            self._cache = InMemoryCacheProvider()

        def get(self, key):
            return self._cache.get(key)

        def delete(self, *keys):
            return self._cache.delete(*keys)

        def setex(self, key, ttl, value):
            raise RuntimeError("cache unavailable")

        def lock(self, key, timeout=None, blocking_timeout=None):
            return self._cache.lock(
                key, timeout=timeout, blocking_timeout=blocking_timeout
            )

    monkeypatch.setattr(umami_client, "cache", CacheWrapper())
    monkeypatch.setattr(
        umami_client,
        "_fetch_distinct_ids_for_event",
        lambda **kwargs: (_ for _ in ()).throw(
            requests.RequestException("umami unavailable")
        ),
    )

    with app.app_context():
        assert umami_client.get_course_visit_count_30d(app, "course-1") == 0


def test_login_for_access_token_rechecks_cache_when_lock_is_busy(monkeypatch):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_API_USERNAME": "user",
            "ANALYTICS_UMAMI_API_PASSWORD": "pass",
            "REDIS_KEY_PREFIX": "test:",
        },
    )

    class BusyLock:
        def acquire(self, blocking=True, blocking_timeout=None):
            return False

        def release(self):
            return None

    cache_provider = InMemoryCacheProvider()
    cache_provider.setex("test:analytics:umami:access-token", 60, "fresh-token")

    class CacheWrapper:
        def get(self, key):
            return cache_provider.get(key)

        def setex(self, key, ttl, value):
            return cache_provider.setex(key, ttl, value)

        def lock(self, key, timeout=None, blocking_timeout=None):
            return BusyLock()

    monkeypatch.setattr(umami_client, "cache", CacheWrapper())

    assert (
        umami_client._login_for_access_token("https://api.umami.is/v1", 10)
        == "fresh-token"
    )


def test_login_for_access_token_returns_token_when_cache_write_fails(monkeypatch):
    _mock_config(
        monkeypatch,
        {
            "ANALYTICS_UMAMI_API_USERNAME": "user",
            "ANALYTICS_UMAMI_API_PASSWORD": "pass",
            "REDIS_KEY_PREFIX": "test:",
        },
    )

    class CacheWrapper:
        def __init__(self):
            self._cache = InMemoryCacheProvider()

        def get(self, key):
            return self._cache.get(key)

        def setex(self, key, ttl, value):
            raise RuntimeError("cache unavailable")

        def lock(self, key, timeout=None, blocking_timeout=None):
            return self._cache.lock(
                key, timeout=timeout, blocking_timeout=blocking_timeout
            )

    monkeypatch.setattr(umami_client, "cache", CacheWrapper())
    monkeypatch.setattr(
        umami_client.requests,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"token": "fresh-token"},
        ),
    )

    assert (
        umami_client._login_for_access_token("https://api.umami.is/v1", 10)
        == "fresh-token"
    )
