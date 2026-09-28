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
