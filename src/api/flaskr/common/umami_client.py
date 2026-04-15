from __future__ import annotations
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
from urllib.parse import urlparse

import requests
from flask import Flask

from flaskr.common.cache_provider import cache
from flaskr.common.config import get_config

UMAMI_CLOUD_API_BASE_URL = "https://api.umami.is/v1"
UMAMI_ACCESS_TOKEN_CACHE_SUFFIX = "analytics:umami:access-token"
UMAMI_COURSE_VISIT_CACHE_PREFIX = "analytics:umami:course-visits:30d"
UMAMI_METRICS_PAGE_SIZE = 500
COURSE_VISIT_EVENT_PREFIX = "course_visit_"
UMAMI_FAILURE_CACHE_TTL_SECONDS = 60
logger = logging.getLogger(__name__)


def build_course_visit_event_name(shifu_bid: str) -> str:
    normalized = "".join(
        ch
        if ("0" <= ch <= "9")
        or ("A" <= ch <= "Z")
        or ("a" <= ch <= "z")
        or ch in ("_", "-")
        else "_"
        for ch in str(shifu_bid or "").strip()
    )
    if not normalized:
        return COURSE_VISIT_EVENT_PREFIX.rstrip("_")
    suffix_limit = max(1, 50 - len(COURSE_VISIT_EVENT_PREFIX))
    return COURSE_VISIT_EVENT_PREFIX + normalized[:suffix_limit]


def _decode_cache_bytes(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


def _get_cache_prefix() -> str:
    return str(get_config("REDIS_KEY_PREFIX") or "")


def _derive_umami_api_base_url() -> str:
    configured = str(get_config("ANALYTICS_UMAMI_API_URL") or "").strip()
    if configured:
        return configured.rstrip("/")

    api_key = str(get_config("ANALYTICS_UMAMI_API_KEY") or "").strip()
    if api_key:
        return UMAMI_CLOUD_API_BASE_URL

    script_src = str(get_config("ANALYTICS_UMAMI_SCRIPT") or "").strip()
    if not script_src:
        return ""

    parsed = urlparse(script_src)
    if not parsed.scheme or not parsed.netloc:
        return ""

    origin = f"{parsed.scheme}://{parsed.netloc}"
    script_path = parsed.path or ""
    if script_path.endswith("/script.js"):
        base_path = script_path[: -len("/script.js")]
    elif script_path.endswith("script.js"):
        base_path = script_path[: -len("script.js")]
    else:
        base_path = script_path
    base_path = base_path.rstrip("/")
    if base_path.endswith("/api"):
        return f"{origin}{base_path}".rstrip("/")
    return f"{origin}{base_path}/api".rstrip("/")


def _get_request_timeout_seconds() -> int:
    timeout = int(get_config("ANALYTICS_UMAMI_TIMEOUT_SECONDS") or 10)
    return max(1, timeout)


def _get_course_visit_cache_ttl_seconds() -> int:
    ttl = int(get_config("ANALYTICS_UMAMI_CACHE_EXPIRE_SECONDS") or 900)
    return max(60, ttl)


def _get_access_token_cache_key() -> str:
    return f"{_get_cache_prefix()}{UMAMI_ACCESS_TOKEN_CACHE_SUFFIX}"


def _cache_setex_best_effort(
    cache_key: str,
    ttl_seconds: int,
    value: Any,
    *,
    operation: str,
) -> None:
    try:
        cache.setex(cache_key, ttl_seconds, value)
    except Exception as exc:
        logger.warning(
            "Failed to cache Umami %s for %s: %s",
            operation,
            cache_key,
            exc,
        )


def _read_cached_int(cache_key: str) -> int | None:
    cached = _decode_cache_bytes(cache.get(cache_key))
    if not cached:
        return None
    try:
        return max(0, int(cached))
    except ValueError:
        cache.delete(cache_key)
        return None


def _login_for_access_token(base_url: str, timeout_seconds: int) -> str:
    username = str(get_config("ANALYTICS_UMAMI_API_USERNAME") or "").strip()
    password = str(get_config("ANALYTICS_UMAMI_API_PASSWORD") or "").strip()
    if not username or not password:
        return ""

    cache_key = _get_access_token_cache_key()
    cached = _decode_cache_bytes(cache.get(cache_key))
    if cached:
        return cached

    lock = cache.lock(f"{cache_key}:lock", timeout=10, blocking_timeout=2)
    if lock.acquire(blocking=True, blocking_timeout=2):
        try:
            cached = _decode_cache_bytes(cache.get(cache_key))
            if cached:
                return cached

            response = requests.post(
                f"{base_url.rstrip('/')}/auth/login",
                json={"username": username, "password": password},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            token = str(
                payload.get("token")
                or payload.get("access_token")
                or (payload.get("data") or {}).get("token")
                or ""
            ).strip()
            if token:
                _cache_setex_best_effort(
                    cache_key,
                    3600,
                    token,
                    operation="access token",
                )
            return token
        finally:
            lock.release()

    return _decode_cache_bytes(cache.get(cache_key))


def _build_umami_headers(base_url: str, timeout_seconds: int) -> dict[str, str]:
    api_key = str(get_config("ANALYTICS_UMAMI_API_KEY") or "").strip()
    if api_key:
        return {
            "Accept": "application/json",
            "x-umami-api-key": api_key,
        }

    access_token = _login_for_access_token(base_url, timeout_seconds)
    if not access_token:
        return {"Accept": "application/json"}

    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }


def _fetch_distinct_ids_for_event(
    *,
    base_url: str,
    website_id: str,
    event_name: str,
    timeout_seconds: int,
) -> int:
    headers = _build_umami_headers(base_url, timeout_seconds)
    if "x-umami-api-key" not in headers and "Authorization" not in headers:
        return 0

    now = datetime.now(timezone.utc)
    start_at = int((now - timedelta(days=30)).timestamp() * 1000)
    end_at = int(now.timestamp() * 1000)

    total = 0
    offset = 0

    while True:
        response = requests.get(
            f"{base_url.rstrip('/')}/websites/{website_id}/metrics",
            params={
                "type": "distinctId",
                "event": event_name,
                "startAt": start_at,
                "endAt": end_at,
                "limit": UMAMI_METRICS_PAGE_SIZE,
                "offset": offset,
            },
            headers=headers,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            return total

        total += len(rows)
        if len(rows) < UMAMI_METRICS_PAGE_SIZE:
            return total
        offset += UMAMI_METRICS_PAGE_SIZE


def get_course_visit_count_30d(app: Flask, shifu_bid: str) -> int:
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_shifu_bid:
        return 0

    website_id = str(get_config("ANALYTICS_UMAMI_SITE_ID") or "").strip()
    base_url = _derive_umami_api_base_url()
    if not website_id or not base_url:
        return 0

    event_name = build_course_visit_event_name(normalized_shifu_bid)
    cache_key = f"{_get_cache_prefix()}{UMAMI_COURSE_VISIT_CACHE_PREFIX}:{event_name}"
    cached_value = _read_cached_int(cache_key)
    if cached_value is not None:
        return cached_value

    lock = cache.lock(f"{cache_key}:lock", timeout=10, blocking_timeout=2)
    if lock.acquire(blocking=True, blocking_timeout=2):
        try:
            cached_value = _read_cached_int(cache_key)
            if cached_value is not None:
                return cached_value

            visit_count = _fetch_distinct_ids_for_event(
                base_url=base_url,
                website_id=website_id,
                event_name=event_name,
                timeout_seconds=_get_request_timeout_seconds(),
            )
            _cache_setex_best_effort(
                cache_key,
                _get_course_visit_cache_ttl_seconds(),
                visit_count,
                operation="course visit count",
            )
            return max(0, int(visit_count))
        except Exception as exc:
            app.logger.warning(
                "Failed to fetch Umami course visit count for %s: %s",
                normalized_shifu_bid,
                exc,
            )
            _cache_setex_best_effort(
                cache_key,
                UMAMI_FAILURE_CACHE_TTL_SECONDS,
                0,
                operation="failure marker",
            )
            return 0
        finally:
            lock.release()

    cached_value = _read_cached_int(cache_key)
    if cached_value is not None:
        return cached_value
    return 0
