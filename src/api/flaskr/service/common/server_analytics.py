"""Send privacy-bounded backend product events to Umami without blocking users."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

import requests
from flaskr.service.config.funcs import get_config

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.common.skill_attribution import SkillIdentityInput

_ALLOWED_EVENTS = frozenset(
    {
        "external_device_authorization_requested",
        "external_device_authorization_approved",
        "external_device_authorization_denied",
        "external_device_token_collected",
        "external_course_creation_started",
        "external_course_creation_completed",
        "external_course_creation_failed",
        "external_course_publish_started",
        "external_course_publish_completed",
        "external_course_publish_failed",
    }
)
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="umami-backend")
_CAPACITY = BoundedSemaphore(32)
_VERSION_MAJOR = re.compile(r"^[vV]?([0-9]+)(?:\.|$)")


def _collector_url(script_url: object) -> str:
    """Derive Umami's event collector from the configured browser script origin."""
    try:
        parsed = urlsplit(str(script_url or "").strip())
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "/api/send", "", ""))


def _version_bucket(raw_version: str) -> str:
    match = _VERSION_MAJOR.match(str(raw_version or "").strip())
    if match is None:
        return "unknown"
    major = match.group(1)
    return f"v{major}" if len(major) == 1 else "unknown"


def _deliver(url: str, payload: dict[str, object]) -> None:
    try:
        requests.post(
            url,
            json={"type": "event", "payload": payload},
            headers={"User-Agent": "Mozilla/5.0 AIShifuServer/1.0"},
            timeout=(0.25, 0.5),
        )
    except Exception:
        # Product analytics is deliberately fail-open.
        return


def track_external_client_event(
    _app: Flask,
    *,
    event_name: str,
    attribution: SkillIdentityInput | None,
) -> None:
    """Queue one allowlisted event without exposing business or credential data."""
    if event_name not in _ALLOWED_EVENTS or attribution is None:
        return
    try:
        collector_url = _collector_url(get_config("ANALYTICS_UMAMI_SCRIPT", ""))
        website_id = str(get_config("ANALYTICS_UMAMI_SITE_ID", "") or "").strip()
    except Exception:
        return
    if not collector_url or not website_id or not _CAPACITY.acquire(blocking=False):
        return

    payload: dict[str, object] = {
        "website": website_id,
        "hostname": "server.ai-shifu",
        "url": "/backend/external-client",
        "name": event_name,
        "data": {
            "host_platform": attribution.host_platform,
            "skill_id": attribution.skill_id,
            "skill_version_major": _version_bucket(attribution.skill_version),
        },
    }
    try:
        future = _EXECUTOR.submit(_deliver, collector_url, payload)
    except Exception:
        _CAPACITY.release()
        return
    future.add_done_callback(lambda _future: _CAPACITY.release())


def _deliver_server_event(
    app: Flask, event_name: str, route: str, data: dict[str, str | int | float | bool]
) -> None:
    """Read server configuration on a worker, without retaining a request context."""
    from flaskr.dao.uow import app_context_scope

    try:
        with app_context_scope(app):
            collector_url = _collector_url(get_config("ANALYTICS_UMAMI_SCRIPT", ""))
            website_id = str(get_config("ANALYTICS_UMAMI_SITE_ID", "") or "").strip()
        if collector_url and website_id:
            _deliver(
                collector_url,
                {
                    "website": website_id,
                    "hostname": "server.ai-shifu",
                    "url": route,
                    "name": event_name,
                    "data": data,
                },
            )
    except Exception:
        # Configuration, context and delivery failures remain best-effort.
        return


def queue_server_event(
    app: Flask,
    *,
    event_name: str,
    route: str,
    data: dict[str, str | int | float | bool],
) -> None:
    """Queue a feature-owned scalar contract without config or network work inline.

    Callers own privacy allowlists and stable event semantics. The transport
    rejects malformed/oversized fields instead of truncating their meaning.
    Routes must be fixed backend paths; never pass request URLs or business IDs.
    """
    import json
    import math

    if not isinstance(event_name, str) or not re.fullmatch(
        r"[a-z][a-z0-9_]{0,49}", event_name
    ):
        return
    if (
        not isinstance(route, str)
        or not re.fullmatch(r"/backend/[a-z/-]{1,80}", route)
        or not isinstance(data, dict)
        or len(data) > 30
    ):
        return
    for key, value in data.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key):
            return
        if type(value) not in {str, int, float, bool}:
            return
        if isinstance(value, str) and len(value) > 240:
            return
        if isinstance(value, float) and not math.isfinite(value):
            return
    try:
        if len(json.dumps(data, ensure_ascii=False, allow_nan=False)) > 1024:
            return
    except (TypeError, ValueError):
        return
    if not _CAPACITY.acquire(blocking=False):
        return
    try:
        future = _EXECUTOR.submit(
            _deliver_server_event, app, event_name, route, dict(data)
        )
    except Exception:
        _CAPACITY.release()
        return
    future.add_done_callback(lambda _future: _CAPACITY.release())
