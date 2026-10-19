"""Request validation and response shaping for direct Gemini Live routes.

These helpers have no Redis, database, or provider side effects; the routes in
``live_follow_up_routes`` keep every collaborator that tests patch there.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from flask import Response, request
from flaskr.common.http import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.gemini_live_token import (
    GEMINI_LIVE_CONSTRAINED_ENDPOINT,
    GEMINI_LIVE_TOKEN_CONNECT_SECONDS,
    GEMINI_LIVE_TOKEN_LIFETIME_SECONDS,
    GeminiLiveEphemeralToken,
    GeminiLiveHistoryTurn,
    GeminiLiveTokenError,
    build_gemini_live_client_setup,
    build_gemini_live_history_message,
)
from flaskr.service.learn.live_follow_up_admission import (
    AdmissionRequest,
    AdmissionResult,
    request_timestamp_ms,
)
from flaskr.service.learn.live_follow_up_persistence import LiveTurnPersistenceInput
from flaskr.service.learn.live_follow_up_session_store import (
    LIVE_FOLLOW_UP_MAX_TURNS,
    LIVE_FOLLOW_UP_SESSION_HEARTBEAT_INTERVAL_SECONDS,
    LiveFollowUpSessionBinding,
)
from flaskr.util.datetime import to_utc_iso

LIVE_FOLLOW_UP_SESSION_SECONDS = 15 * 60
_ALLOWED_LEARNING_MODES = frozenset({"read", "listen"})
_ALLOWED_SURFACES = frozenset({"read_content", "listen_player", "teacher_preview"})
_MAX_DIRECT_TRANSCRIPT_CHARS = 32_000
_MAX_DIRECT_USAGE_BYTES = 64 * 1024
_MAX_DIRECT_TURN_REPORT_BYTES = 60 * 1024
_ERROR_DEADLINE_MISMATCH = "token_deadline_mismatch"


def _make_live_response(data: dict[str, object]) -> Response:
    serialized = make_common_response(data)
    return Response(
        serialized,
        mimetype="application/json",
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _validate_token_deadlines(
    token: GeminiLiveEphemeralToken, issued_at: datetime
) -> None:
    if token.expires_at != issued_at + timedelta(
        seconds=GEMINI_LIVE_TOKEN_LIFETIME_SECONDS
    ) or token.new_session_expires_at != issued_at + timedelta(
        seconds=GEMINI_LIVE_TOKEN_CONNECT_SECONDS
    ):
        raise GeminiLiveTokenError(_ERROR_DEADLINE_MISMATCH)


def _normalize_origin(value: object) -> str:
    raw = str(value or "").strip().rstrip("/")
    try:
        parsed = urlsplit(raw)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return ""
        return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    except ValueError:
        return ""


def _new_session_binding(
    *,
    session_bid: str,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    anchor_element_bid: str,
    progress_record_bid: str,
    preview_mode: bool,
    origin: str,
    model: str,
    voice_name: str,
    language: str,
    learning_mode: str,
    expires_at_epoch: float,
) -> LiveFollowUpSessionBinding:
    return LiveFollowUpSessionBinding(
        session_bid=session_bid,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        anchor_element_bid=anchor_element_bid,
        progress_record_bid=progress_record_bid,
        preview_mode=preview_mode,
        origin=origin,
        model=model,
        voice_name=voice_name,
        language=language,
        learning_mode=learning_mode,
        expires_at_epoch=expires_at_epoch,
    )


def _read_bounded_turn_payload() -> object:
    if not request.is_json or (
        request.content_length is not None
        and request.content_length > _MAX_DIRECT_TURN_REPORT_BYTES
    ):
        raise_param_error("live_follow_up_turn")
    configured_limit = request.max_content_length
    request.max_content_length = min(
        configured_limit or _MAX_DIRECT_TURN_REPORT_BYTES + 1,
        _MAX_DIRECT_TURN_REPORT_BYTES + 1,
    )
    raw = request.get_data(cache=True)
    if len(raw) > _MAX_DIRECT_TURN_REPORT_BYTES:
        raise_param_error("live_follow_up_turn")
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise_param_error("live_follow_up_turn")


def _validate_turn_payload(payload: object) -> LiveTurnPersistenceInput:
    if not isinstance(payload, dict):
        raise_param_error("live_follow_up_turn")
    turn_index = payload.get("turn_index")
    user_transcript = payload.get("user_transcript")
    answer_transcript = payload.get("played_answer_transcript")
    interrupted = payload.get("interrupted")
    usage_metadata = payload.get("usage_metadata")
    latency_ms = payload.get("latency_ms", 0)
    if (
        type(turn_index) is not int
        or not 1 <= turn_index <= LIVE_FOLLOW_UP_MAX_TURNS
        or not isinstance(user_transcript, str)
        or len(user_transcript) > _MAX_DIRECT_TRANSCRIPT_CHARS
        or not isinstance(answer_transcript, str)
        or len(answer_transcript) > _MAX_DIRECT_TRANSCRIPT_CHARS
        or type(interrupted) is not bool
        or type(latency_ms) is not int
        or not 0 <= latency_ms <= LIVE_FOLLOW_UP_SESSION_SECONDS * 1000
        or (usage_metadata is not None and not isinstance(usage_metadata, dict))
    ):
        raise_param_error("live_follow_up_turn")
    if usage_metadata is not None:
        try:
            usage_size = len(
                json.dumps(
                    usage_metadata,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
        except (TypeError, ValueError):
            raise_param_error("live_follow_up_turn")
        if usage_size > _MAX_DIRECT_USAGE_BYTES:
            raise_param_error("live_follow_up_turn")
    return LiveTurnPersistenceInput(
        turn_index=turn_index,
        user_transcript=user_transcript.strip(),
        played_answer_transcript=answer_transcript.strip(),
        interrupted=interrupted,
        usage_metadata=dict(usage_metadata) if usage_metadata else None,
        latency_ms=latency_ms,
    )


def _session_response(
    *,
    binding: LiveFollowUpSessionBinding,
    token: GeminiLiveEphemeralToken,
    history: tuple[GeminiLiveHistoryTurn, ...],
    admission: AdmissionResult,
    rotation_enabled: bool,
    expires_in_ms: int,
) -> Response:
    return _make_live_response(
        {
            "session_bid": binding.session_bid,
            "request_bid": admission.data["request_bid"],
            "admission_revision": admission.data["admission_revision"],
            "operation_status": "issued",
            "rotation_enabled": rotation_enabled,
            "ephemeral_token": token.token,
            "websocket_url": GEMINI_LIVE_CONSTRAINED_ENDPOINT,
            "setup": build_gemini_live_client_setup(
                model=binding.model,
                voice_name=binding.voice_name,
                include_initial_history=bool(history),
            ),
            "history": build_gemini_live_history_message(history),
            "expires_at": to_utc_iso(token.expires_at),
            "expires_in_ms": expires_in_ms,
            "ownership_timeout_ms": 10_000,
            "new_session_expires_at": to_utc_iso(token.new_session_expires_at),
            "heartbeat_interval_ms": (
                LIVE_FOLLOW_UP_SESSION_HEARTBEAT_INTERVAL_SECONDS * 1000
            ),
        }
    )


def _admission_request(
    payload: dict[str, object],
    *,
    request_bid: str,
    user_bid: str,
    origin: str,
    shifu_bid: str,
    outline_bid: str,
) -> AdmissionRequest:
    """Validate the exact content-free operation target before Redis access."""
    anchor = str(payload.get("anchor_element_bid") or "").strip()
    preview = payload.get("preview_mode", False)
    mode = str(payload.get("learning_mode") or "").strip().lower()
    surface = str(payload.get("surface") or "").strip().lower()
    predecessor = str(payload.get("replace_session_bid") or "").strip()
    revision = str(payload.get("expected_admission_revision") or "").strip()
    takeover = payload.get("operation") == "takeover"
    if (
        not anchor
        or len(anchor) > 64
        or type(preview) is not bool
        or mode not in _ALLOWED_LEARNING_MODES
        or surface not in _ALLOWED_SURFACES
        or (preview and surface != "teacher_preview")
        or (not preview and surface == "teacher_preview")
        or len(predecessor) > 64
        or len(revision) > 128
        or (not takeover and bool(predecessor) != bool(revision))
        or (takeover and (predecessor or "expected_admission_revision" not in payload))
    ):
        raise_param_error("live_follow_up")
    try:
        request_timestamp_ms(request_bid)
    except ValueError:
        raise_param_error("live_follow_up")
    return AdmissionRequest(
        request_bid=request_bid,
        user_bid=user_bid,
        origin=origin,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        anchor_element_bid=anchor,
        preview_mode=preview,
        learning_mode=mode,
        surface=surface,
        replace_session_bid=predecessor,
        expected_admission_revision=revision,
        takeover=takeover,
    )


def _admission_failure(request_bid: str, *, rotation_enabled: bool) -> Response:
    return _make_live_response(
        {
            "request_bid": request_bid,
            "operation_status": "rejected",
            "error_code": "admission_unavailable",
            "rotation_enabled": rotation_enabled,
        }
    )
