from __future__ import annotations

from types import SimpleNamespace

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
