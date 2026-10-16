"""Attribute allowlisted Skill API requests without inspecting business input."""

from __future__ import annotations

import re
from dataclasses import dataclass
from time import monotonic

from flask import Flask, Response, g, has_request_context, request
from flaskr.service.common.server_analytics import track_skill_request_event

SKILL_ID = "ai-shifu-course-creator"
CALLER_AGENTS = frozenset(
    {
        "codex",
        "claude_code",
        "cursor",
        "hermes",
        "openclaw",
        "workbuddy",
        "qoderwork",
        "grok_bot",
        "unknown",
    }
)
_RELEASE_VERSION = re.compile(
    r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)

# Keys are Flask endpoints and HTTP methods, never request paths or payloads.
SKILL_API_OPERATIONS = {
    ("get_shifu_list_api", "GET"): "course_list",
    ("create_shifu_api", "PUT"): "course_create",
    ("get_shifu_detail_api", "GET"): "course_get",
    ("save_shifu_detail_api", "POST"): "course_update",
    ("archive_shifu_api", "POST"): "course_archive",
    ("unarchive_shifu_api", "POST"): "course_unarchive",
    ("publish_shifu_api", "POST"): "course_publish",
    ("export_shifu_api", "GET"): "course_export",
    ("get_outline_tree_api", "GET"): "outline_list",
    ("get_unit_info_api", "GET"): "outline_get",
    ("create_outline_api", "PUT"): "outline_create",
    ("modify_outline_api", "POST"): "outline_update",
    ("delete_unit_api", "DELETE"): "outline_delete",
    ("update_chapter_order_api", "PATCH"): "outline_reorder",
    ("get_mdflow_api", "GET"): "content_get",
    ("save_mdflow_api", "POST"): "content_save",
    ("get_mdflow_history_api", "GET"): "content_history_list",
    ("get_mdflow_history_version_detail_api", "GET"): "content_history_get",
    ("get_draft_meta_api", "GET"): "draft_meta_get",
    ("upfile_api", "POST"): "asset_upload",
    ("upload_url_api", "POST"): "asset_url_upload",
    ("creator_analytics_query", "POST"): "analytics_query",
    ("creator_analytics_credit_detail", "POST"): "analytics_credit_detail",
}


@dataclass(frozen=True, slots=True)
class _SkillRequest:
    version: str
    caller_agent: str
    operation: str
    started_at: float


def has_skill_request_analytics() -> bool:
    """Return whether this request uses the new validated telemetry contract."""
    return has_request_context() and isinstance(
        getattr(g, "skill_request_analytics", None), _SkillRequest
    )


def _request_metadata() -> _SkillRequest | None:
    operation = SKILL_API_OPERATIONS.get((request.endpoint, request.method))
    if operation is None or request.headers.get("X-AI-Shifu-Skill") != SKILL_ID:
        return None
    version = request.headers.get("X-AI-Shifu-Skill-Version", "")
    caller_agent = request.headers.get("X-AI-Shifu-Caller-Agent", "")
    if (
        len(version) > 64
        or _RELEASE_VERSION.fullmatch(version) is None
        or caller_agent not in CALLER_AGENTS
    ):
        return None
    return _SkillRequest(version, caller_agent, operation, monotonic())


def _request_outcome(response: Response, operation: str) -> str:
    if not 200 <= response.status_code < 300:
        return "failure"
    # Export's JSON file is a download, not the API envelope. Never read its
    # iterable: doing so can buffer a file, exhaust a stream, or run user work.
    if (
        operation == "course_export"
        and response.direct_passthrough
        and response.mimetype == "application/json"
        and response.headers.get("Content-Disposition", "").startswith("attachment;")
    ):
        return "success"
    if response.is_streamed or response.direct_passthrough:
        return "failure"
    envelope = response.get_json(force=True, silent=True)
    if isinstance(envelope, dict) and type(envelope.get("code")) is int:
        return "success" if envelope["code"] == 0 else "failure"
    return "failure"


def register_skill_request_analytics(app: Flask) -> None:
    """Install fail-open observation before authentication and after routing."""

    @app.before_request
    def begin_skill_request_analytics() -> None:
        try:
            g.skill_request_analytics = _request_metadata()
        except Exception:
            # Telemetry must never change authentication or business handling.
            g.skill_request_analytics = None

    @app.after_request
    def finish_skill_request_analytics(response: Response) -> Response:
        try:
            # Flask may process a replacement error response after another
            # response hook fails. Consume the observation exactly once.
            metadata = g.pop("skill_request_analytics", None)
            user = getattr(request, "user", None)
            user_id = getattr(user, "user_id", None)
            if (
                isinstance(metadata, _SkillRequest)
                and user_id
                and getattr(g, "authenticated_session_attribution", None)
            ):
                track_skill_request_event(
                    app,
                    user_id=str(user_id),
                    skill_version=metadata.version,
                    caller_agent=metadata.caller_agent,
                    operation=metadata.operation,
                    outcome=_request_outcome(response, metadata.operation),
                    duration_ms=max(0, int((monotonic() - metadata.started_at) * 1000)),
                )
        except Exception:
            # Includes malformed response envelopes and sender/queue failures.
            return response
        return response
