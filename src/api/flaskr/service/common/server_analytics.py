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
_CLI_UA_AGENT_NAMES = {
    "Claude Code": "Claude-Code",
    # "Hermes Agent" matches Umami's bot filter; the OS keeps the full label.
    "Hermes Agent": "Hermes",
    # "Grok-Bot" matches Umami's bot filter; the OS retains the full label.
    "Grok Bot": "Grok",
    "Grok Build": "Grok-Build",
    "Unknown Agent": "Unknown",
}


def _cli_user_agent(skill_version: str, caller_agent_name: str) -> str:
    """Render a validated CLI release and display name for the collector."""
    agent_name = _CLI_UA_AGENT_NAMES.get(caller_agent_name, caller_agent_name)
    return f"Mozilla/5.0 AI-Shifu-CLI/{skill_version} ({agent_name})"


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
            # Umami's bot filter matches "server" in user agents. Use a fixed
            # application identity without forwarding the client's user agent.
            headers={"User-Agent": "Mozilla/5.0 AI-Shifu-Backend/1.0"},
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
    _queue_event(
        event_name,
        {
            "host_platform": attribution.host_platform,
            "skill_id": attribution.skill_id,
            "skill_version_major": _version_bucket(attribution.skill_version),
        },
    )


def track_cli_request_pageview(
    _app: Flask,
    *,
    user_id: str,
    skill_version: str,
    caller_agent: str,
    caller_agent_name: str,
    operation: str,
    outcome: str,
    duration_ms: int,
    route_template: str,
    method: str,
    timestamp: int,
) -> None:
    """Queue one identify/pageview pair under the authenticated account ID."""
    from flaskr.service.common.skill_request_analytics import (
        SKILL_API_OPERATIONS,
        SKILL_API_ROUTE_TEMPLATES,
        SKILL_ID,
        _is_caller_agent_metadata,
        _is_cli_version,
    )

    if (
        not user_id
        or not _is_cli_version(skill_version)
        or not _is_caller_agent_metadata(caller_agent, caller_agent_name)
        or operation not in SKILL_API_OPERATIONS.values()
        or outcome not in {"success", "failure"}
        or type(duration_ms) is not int
        or duration_ms < 0
        or type(timestamp) is not int
        or timestamp < 0
        or not any(
            operation == allowed_operation and method == allowed_method
            for (_, allowed_method), allowed_operation in SKILL_API_OPERATIONS.items()
        )
        or route_template != SKILL_API_ROUTE_TEMPLATES.get(operation)
    ):
        return
    try:
        collector_url = _collector_url(get_config("ANALYTICS_UMAMI_SCRIPT", ""))
        website_id = str(get_config("ANALYTICS_UMAMI_SITE_ID", "") or "").strip()
    except Exception:
        return
    if not collector_url or not website_id or not _CAPACITY.acquire(blocking=False):
        return
    user_agent = _cli_user_agent(skill_version, caller_agent_name)
    identity: dict[str, object] = {
        "website": website_id,
        "id": user_id,
        "timestamp": timestamp,
        "browser": "AI-Shifu CLI",
        "os": caller_agent_name,
        "device": "desktop",
    }
    pageview = {
        **identity,
        "hostname": "server.ai-shifu",
        "url": route_template,
        "tag": "skill_api_request_v2",
        "data": {
            "skill_id": SKILL_ID,
            "skill_version_major": _version_bucket(skill_version),
            "caller_agent": caller_agent,
            "operation": operation,
            "method": method,
            "outcome": outcome,
            "duration_ms": duration_ms,
        },
    }
    try:
        future = _EXECUTOR.submit(
            _deliver_skill_request, collector_url, identity, pageview, user_agent
        )
    except Exception:
        _CAPACITY.release()
        return
    future.add_done_callback(lambda _future: _CAPACITY.release())


def _send_skill_payload(
    url: str, event_type: str, payload: dict[str, object], user_agent: str
) -> bool:
    """Recognize collector acknowledgements without claiming stored identity."""
    try:
        response = requests.post(
            url,
            json={"type": event_type, "payload": payload},
            headers={"User-Agent": user_agent},
            timeout=(0.25, 0.5),
        )
        if not 200 <= response.status_code < 300:
            return False
        acknowledgement = response.json()
        if (
            not isinstance(acknowledgement, dict)
            or acknowledgement.get("beep") == "boop"
        ):
            return False
        # No cache is retained or sent. A collector acknowledgement alone does
        # not prove the event or session_link can be read back from storage.
        return isinstance(acknowledgement.get("cache"), str) and bool(
            acknowledgement["cache"]
        )
    except Exception:
        return False


def _deliver_skill_request(
    url: str,
    identity: dict[str, object],
    pageview: dict[str, object],
    user_agent: str,
) -> None:
    # _send_skill_payload isolates each failure; identify never suppresses the
    # pageview attempt. Each request has its own UA-bound identity and no cache.
    _send_skill_payload(url, "identify", identity, user_agent)
    _send_skill_payload(url, "event", pageview, user_agent)


def _queue_event(
    event_name: str,
    data: dict[str, object],
    *,
    user_id: str | None = None,
) -> None:
    """Share the bounded, nonblocking delivery path across backend events."""
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
        "url": "/backend/skill" if user_id is not None else "/backend/external-client",
        "name": event_name,
        "data": data,
    }
    if user_id is not None:
        # Umami's Distinct ID matches the browser's umami.identify(user_id).
        payload["id"] = user_id
    try:
        future = _EXECUTOR.submit(_deliver, collector_url, payload)
    except Exception:
        _CAPACITY.release()
        return
    future.add_done_callback(lambda _future: _CAPACITY.release())
