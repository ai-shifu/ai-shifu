"""Authenticated browser-direct Gemini Live follow-up routes."""

from __future__ import annotations

import contextlib
import hmac
import json
import math
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, Response, request
from flaskr.api.langfuse import get_request_id
from flaskr.api.llm import is_live_follow_up_model_available
from flaskr.common.http import make_common_response, sensitive_body
from flaskr.common.shifu_context import with_shifu_context
from flaskr.i18n import get_current_language
from flaskr.service.common import raise_error
from flaskr.service.common.models import AppError, raise_param_error
from flaskr.service.config import get_config
from flaskr.service.learn.follow_up_context import (
    build_follow_up_conversation_context,
)
from flaskr.service.learn.gemini_live_token import (
    GEMINI_LIVE_CONSTRAINED_ENDPOINT,
    GEMINI_LIVE_TOKEN_CONNECT_SECONDS,
    GEMINI_LIVE_TOKEN_LIFETIME_SECONDS,
    GeminiLiveEphemeralToken,
    GeminiLiveHistoryTurn,
    GeminiLiveTokenError,
    GeminiLiveTokenTimeoutError,
    build_gemini_live_client_setup,
    build_gemini_live_history_message,
    mint_gemini_live_ephemeral_token,
)
from flaskr.service.learn.learn_dtos import LearnOutlineItemInfoDTO, OutlineType
from flaskr.service.learn.learn_funcs import get_outline_item_tree
from flaskr.service.learn.live_follow_up_admission import (
    AdmissionRequest,
    AdmissionResult,
    admission_status,
    admission_time,
    begin_admission,
    complete_admission,
    current_admission,
    fail_admission,
    legacy_request_bid,
    request_timestamp_ms,
    retire_admission,
    retirement_receipt,
)
from flaskr.service.learn.live_follow_up_capacity import (
    LiveFollowUpCapacityError,
)
from flaskr.service.learn.live_follow_up_config import (
    DEFAULT_GEMINI_LIVE_VOICE,
    GEMINI_LIVE_MODEL_ID,
    is_gemini_live_enabled,
    is_gemini_live_rotation_enabled,
    is_live_follow_up_model,
    normalize_live_follow_up_provider_config,
)
from flaskr.service.learn.live_follow_up_persistence import (
    LiveFollowUpPersistenceError,
    LiveTurnPersistenceContext,
    LiveTurnPersistenceInput,
    LiveTurnPersistenceResult,
    live_follow_up_persistence_lock,
    load_persisted_live_follow_up_turn,
    persist_live_follow_up_turn,
)
from flaskr.service.learn.live_follow_up_session_store import (
    LIVE_FOLLOW_UP_MAX_TURNS,
    LIVE_FOLLOW_UP_SESSION_HEARTBEAT_INTERVAL_SECONDS,
    LiveFollowUpSessionBinding,
    LiveFollowUpSessionRejectedError,
    LiveFollowUpSessionStoreError,
    LiveFollowUpTurnReservation,
    StoredLiveFollowUpSession,
    commit_live_follow_up_turn_reservation,
    consume_live_follow_up_session,
    load_live_follow_up_session,
    release_live_follow_up_turn_reservation,
    reserve_live_follow_up_turn,
    serialize_live_follow_up_session,
    touch_live_follow_up_session,
)
from flaskr.service.learn.live_follow_up_trace import LiveFollowUpTrace
from flaskr.service.learn.models import LearnGeneratedElement
from flaskr.service.learn.preview_permissions import require_shifu_preview_permission
from flaskr.service.learn.utils_v2 import get_follow_up_info_v2
from flaskr.service.shifu.api import get_effective_ask_provider_config
from flaskr.service.shifu.consts import ASK_MODE_DISABLE
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.api import is_allowed_oauth_origin, load_user_aggregate
from flaskr.util.datetime import to_utc_iso
from flaskr.util.prompt_loader import load_prompt_template
from flaskr.util.uuid import generate_id
from sqlalchemy import or_

LIVE_FOLLOW_UP_SESSION_SECONDS = 15 * 60
LIVE_FOLLOW_UP_WARNING_SECONDS = 14 * 60 + 30
_ALLOWED_LEARNING_MODES = frozenset({"read", "listen"})
_ALLOWED_SURFACES = frozenset({"read_content", "listen_player", "teacher_preview"})
_MAX_DIRECT_TRANSCRIPT_CHARS = 32_000
_MAX_DIRECT_USAGE_BYTES = 64 * 1024
_MAX_DIRECT_TURN_REPORT_BYTES = 60 * 1024
_ERROR_DEADLINE_MISMATCH = "token_deadline_mismatch"


class LiveFollowUpModelUnavailableError(RuntimeError):
    """Signal that Gemini no longer advertises the required Bidi capability."""


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


def _request_user_bid() -> str:
    user = getattr(request, "user", None)
    return str(getattr(user, "user_id", "") or "").strip()


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


def _request_transport_origin() -> str:
    forwarded_proto = (
        str(request.headers.get("X-Forwarded-Proto") or request.scheme or "")
        .split(",", 1)[0]
        .strip()
    )
    return _normalize_origin(f"{forwarded_proto}://{str(request.host or '').strip()}")


def _require_allowed_origin(app: Flask) -> str:
    origin = _normalize_origin(request.headers.get("Origin"))
    if not origin:
        raise_param_error("origin")
    if origin == _request_transport_origin() or is_allowed_oauth_origin(app, origin):
        return origin
    if str(app.config.get("ENV", "production") or "").lower() == "development":
        parsed = urlsplit(origin)
        if parsed.hostname in {"localhost", "127.0.0.1", "[::1]", "::1"}:
            return origin
    raise_param_error("origin")
    return origin


def _find_outline_item(
    items: list[LearnOutlineItemInfoDTO], outline_bid: str
) -> LearnOutlineItemInfoDTO | None:
    for item in items:
        if item.bid == outline_bid:
            return item
        found = _find_outline_item(list(item.children or []), outline_bid)
        if found is not None:
            return found
    return None


def _require_course_access(
    app: Flask,
    *,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    preview_mode: bool,
) -> None:
    if preview_mode:
        require_shifu_preview_permission(app, user_bid, shifu_bid)
    tree = get_outline_item_tree(app, shifu_bid, user_bid, preview_mode)
    item = _find_outline_item(list(tree.outline_items or []), outline_bid)
    if item is None:
        raise_error("server.shifu.lessonNotFoundInCourse")
    if (
        not preview_mode
        and not item.is_paid
        and item.type not in {OutlineType.TRIAL, OutlineType.GUEST}
    ):
        raise_error("server.order.courseNotPaid")


def _load_anchor(
    *,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    anchor_element_bid: str,
) -> LearnGeneratedElement:
    row = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.shifu_bid == shifu_bid,
            LearnGeneratedElement.outline_item_bid == outline_bid,
            LearnGeneratedElement.user_bid == user_bid,
            LearnGeneratedElement.event_type == "element",
            or_(
                LearnGeneratedElement.element_bid == anchor_element_bid,
                LearnGeneratedElement.target_element_bid == anchor_element_bid,
            ),
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        )
        .order_by(
            LearnGeneratedElement.sequence_number.desc(),
            LearnGeneratedElement.run_event_seq.desc(),
            LearnGeneratedElement.id.desc(),
        )
        .first()
    )
    if row is None or not str(row.progress_record_bid or "").strip():
        raise_param_error("anchor_element_bid")
    return row


def _resolve_live_config(
    app: Flask,
    *,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    preview_mode: bool,
) -> tuple[object, str]:
    follow_up_info = get_follow_up_info_v2(
        app,
        shifu_bid,
        outline_bid,
        progress_record_bid,
        preview_mode,
    )
    if follow_up_info.ask_mode == ASK_MODE_DISABLE:
        raise_param_error("follow_up")
    if not is_live_follow_up_model(follow_up_info.ask_model):
        raise_param_error("follow_up_model")
    if not is_live_follow_up_model_available(follow_up_info.ask_model):
        raise LiveFollowUpModelUnavailableError
    provider_config = get_effective_ask_provider_config(
        follow_up_info.ask_provider_config
    )
    normalized, invalid_field = normalize_live_follow_up_provider_config(
        follow_up_info.ask_model,
        provider_config,
    )
    if invalid_field is not None:
        raise_param_error(invalid_field)
    config = normalized.get("config")
    voice = (
        str(config.get("live_voice") or DEFAULT_GEMINI_LIVE_VOICE)
        if isinstance(config, dict)
        else DEFAULT_GEMINI_LIVE_VOICE
    )
    return follow_up_info, voice


def _load_use_learner_language(*, shifu_bid: str, preview_mode: bool) -> bool:
    model = DraftShifu if preview_mode else PublishedShifu
    row = (
        model.query.filter(model.shifu_bid == shifu_bid, model.deleted == 0)
        .order_by(model.id.desc())
        .first()
    )
    return bool(getattr(row, "use_learner_language", 0))


def _build_conversation(
    app: Flask,
    *,
    binding: LiveFollowUpSessionBinding,
    follow_up_info: object,
) -> tuple[str, tuple[GeminiLiveHistoryTurn, ...]]:
    user = load_user_aggregate(binding.user_bid)
    if user is None:
        message = "Live user is unavailable"
        raise RuntimeError(message)
    conversation = build_follow_up_conversation_context(
        app,
        user_info=user,
        shifu_bid=binding.shifu_bid,
        outline_item_bid=binding.outline_bid,
        progress_record_bid=binding.progress_record_bid,
        follow_up_info=follow_up_info,
        # Live must not inherit the course's text-output and formatting rules.
        course_system_prompt=None,
        fallback_system_prompt=load_prompt_template("live_follow_up"),
        use_learner_language=_load_use_learner_language(
            shifu_bid=binding.shifu_bid,
            preview_mode=binding.preview_mode,
        ),
        runtime_language=binding.language,
        anchor_element_bid=binding.anchor_element_bid,
        max_history_messages=20,
    )
    history = tuple(
        GeminiLiveHistoryTurn(role=item["role"], text=item["content"])
        for item in conversation.llm_messages
        if item.get("role") in {"user", "assistant"}
        and str(item.get("content") or "").strip()
    )
    return conversation.system_instruction, history


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
        or bool(predecessor) != bool(revision)
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


def _status_response(
    app: Flask, *, payload: dict[str, object], shifu_bid: str, outline_bid: str
) -> Response:
    """Recover only this user's original metadata, never old course content."""
    user_bid = _request_user_bid()
    if not user_bid:
        raise_error("server.user.userNotLogin")
    origin = _require_allowed_origin(app)
    target = payload.get("target")
    if not isinstance(target, dict) or "anchor_element_bid" in payload:
        raise_param_error("live_follow_up")
    operation = _admission_request(
        target,
        request_bid=str(payload.get("request_bid") or ""),
        user_bid=user_bid,
        origin=origin,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
    )
    rotation = is_gemini_live_rotation_enabled()
    try:
        return _make_live_response(
            admission_status(app, operation, rotation_enabled=rotation)
        )
    except LiveFollowUpCapacityError:
        return _admission_failure(operation.request_bid, rotation_enabled=rotation)


def _retire_session_admission(app: Flask, session: StoredLiveFollowUpSession) -> None:
    if session.admission and session.admission_revision:
        retire_admission(
            app,
            session.admission,
            session_bid=session.binding.session_bid,
            admission_revision=session.admission_revision,
            expires_at_ms=math.ceil(session.binding.expires_at_epoch * 1000),
            last_committed_index=session.turn_state.last_committed_index,
        )


def _complete_session_admission(
    app: Flask,
    operation: AdmissionRequest,
    result: AdmissionResult,
    session: StoredLiveFollowUpSession,
) -> None:
    if not complete_admission(
        app,
        operation,
        result,
        session_payload=serialize_live_follow_up_session(session),
    ):
        raise GeminiLiveTokenError(_ERROR_DEADLINE_MISMATCH)


def _failed_operation_response(
    app: Flask, operation: AdmissionRequest | None, *, rotation_enabled: bool
) -> Response:
    """Never mislabel an advanced or uncertain ownership head as pre-admission.

    A generic transport/business failure keeps the original request ID for a
    later non-minting lookup when Redis cannot establish the operation status.
    """
    if operation is not None:
        try:
            status = admission_status(app, operation, rotation_enabled=rotation_enabled)
        except LiveFollowUpCapacityError:
            raise_param_error("live_follow_up")
        if status.get("operation_status") in {
            "pending",
            "issued",
            "failed",
            "cancelled",
        }:
            return _make_live_response(status)
    return raise_param_error("live_follow_up")


def register_live_follow_up_routes(
    app: Flask,
    path_prefix: str = "/api/learn",
) -> None:
    """Register the direct Live session, heartbeat, turn, and end endpoints."""

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/live-follow-up/<outline_bid>/session",
        methods=["POST"],
    )
    @sensitive_body(max_bytes=_MAX_DIRECT_TURN_REPORT_BYTES)
    def create_live_follow_up_session_api(
        shifu_bid: str,
        outline_bid: str,
    ) -> Response:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("live_follow_up")
        operation_kind = payload.get("operation", "create")
        if operation_kind == "status":
            return _status_response(
                app, payload=payload, shifu_bid=shifu_bid, outline_bid=outline_bid
            )
        if operation_kind != "create":
            raise_param_error("live_follow_up")
        return create_session_with_course_context(shifu_bid, outline_bid, payload)

    @with_shifu_context()
    def create_session_with_course_context(
        shifu_bid: str, outline_bid: str, payload: dict[str, object]
    ) -> Response:
        # Non-minting status recovery deliberately bypasses this course-context
        # resolver: an old course's later removal cannot strand owned metadata.
        if not is_gemini_live_enabled():
            raise_param_error("live_follow_up")
        if not is_live_follow_up_model_available(GEMINI_LIVE_MODEL_ID):
            raise_param_error("follow_up_model")
        user_bid = _request_user_bid()
        if not user_bid:
            raise_error("server.user.userNotLogin")
        anchor_element_bid = str(payload.get("anchor_element_bid") or "").strip()
        preview_mode = payload.get("preview_mode", False)
        learning_mode = str(payload.get("learning_mode") or "").strip().lower()
        surface = str(payload.get("surface") or "").strip().lower()
        if (
            not anchor_element_bid
            or len(anchor_element_bid) > 64
            or type(preview_mode) is not bool
            or learning_mode not in _ALLOWED_LEARNING_MODES
            or surface not in _ALLOWED_SURFACES
            or (preview_mode and surface != "teacher_preview")
            or (not preview_mode and surface == "teacher_preview")
        ):
            raise_param_error("live_follow_up")

        origin = _require_allowed_origin(app)
        _require_course_access(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=preview_mode,
        )
        anchor = _load_anchor(
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            anchor_element_bid=anchor_element_bid,
        )
        follow_up_info, voice = _resolve_live_config(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            progress_record_bid=anchor.progress_record_bid,
            preview_mode=preview_mode,
        )
        api_key = str(get_config("GEMINI_API_KEY", "") or "").strip()
        if not api_key:
            raise_param_error("live_follow_up")

        session_bid = generate_id(app)
        language = str(get_current_language() or "en-US").strip() or "en-US"
        provisional_binding = _new_session_binding(
            session_bid=session_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            anchor_element_bid=anchor_element_bid,
            progress_record_bid=anchor.progress_record_bid,
            preview_mode=preview_mode,
            origin=origin,
            model=str(follow_up_info.ask_model),
            voice_name=voice,
            language=language,
            learning_mode=learning_mode,
            expires_at_epoch=0,
        )
        system_instruction, history = _build_conversation(
            app,
            binding=provisional_binding,
            follow_up_info=follow_up_info,
        )

        legacy = "request_bid" not in payload
        rotation = is_gemini_live_rotation_enabled()
        admission: AdmissionResult | None = None
        admission_request: AdmissionRequest | None = None
        try:
            operation_bid = (
                legacy_request_bid()
                if legacy
                else str(payload.get("request_bid") or "")
            )
            admission_request = _admission_request(
                payload,
                request_bid=operation_bid,
                user_bid=user_bid,
                origin=origin,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
            )
            admission = begin_admission(
                app,
                admission_request,
                session_bid=session_bid,
                rotation_enabled=rotation,
                legacy=legacy,
            )
            if admission.lease is None:
                if legacy:
                    if admission.data.get("error_code") in {
                        "capacity_exceeded",
                        "ownership_conflict",
                    }:
                        raise_error("server.learn.liveFollowUpCapacityExceeded")
                    raise_param_error("live_follow_up")
                return _make_live_response(admission.data)
            # The atomic Redis TIME epoch bounds token and every capacity scope.
            issued_at = datetime.fromtimestamp(admission.issued_at_ms / 1000, tz=UTC)
            token = mint_gemini_live_ephemeral_token(
                api_key=api_key,
                api_base_url=str(get_config("GEMINI_API_URL", "") or "").strip(),
                model=provisional_binding.model,
                voice_name=voice,
                system_instruction=system_instruction,
                include_initial_history=bool(history),
                current_time=issued_at,
            )
            _validate_token_deadlines(token, issued_at)
            binding = _new_session_binding(
                session_bid=session_bid,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                anchor_element_bid=anchor_element_bid,
                progress_record_bid=anchor.progress_record_bid,
                preview_mode=preview_mode,
                origin=origin,
                model=provisional_binding.model,
                voice_name=voice,
                language=language,
                learning_mode=learning_mode,
                expires_at_epoch=token.expires_at.timestamp(),
            )
            session = StoredLiveFollowUpSession(
                binding=binding,
                lease=admission.lease,
                admission=admission_request,
                admission_revision=str(admission.data["admission_revision"]),
            )
            _complete_session_admission(app, admission_request, admission, session)
        except (LiveFollowUpCapacityError, LiveFollowUpSessionStoreError):
            if admission is not None and admission_request is not None:
                with contextlib.suppress(Exception):
                    fail_admission(app, admission_request, admission)
            if not legacy:
                return _failed_operation_response(
                    app, admission_request, rotation_enabled=rotation
                )
            raise_param_error("live_follow_up")
        except GeminiLiveTokenError as exc:
            if admission is not None and admission_request is not None:
                with contextlib.suppress(Exception):
                    fail_admission(
                        app,
                        admission_request,
                        admission,
                        undisclosed=not isinstance(exc, GeminiLiveTokenTimeoutError),
                    )
            app.logger.error(  # noqa: TRY400 - never log provider response details
                "Gemini Live token provisioning failed session=%s",
                session_bid,
            )
            if not legacy:
                return _failed_operation_response(
                    app, admission_request, rotation_enabled=rotation
                )
            raise_param_error("live_follow_up")
        return _session_response(
            binding=binding,
            token=token,
            history=history,
            admission=admission,
            rotation_enabled=rotation,
        )

    def require_direct_session(
        session_bid: str,
        *,
        allow_finalization: bool = False,
    ) -> StoredLiveFollowUpSession:
        if not session_bid or len(session_bid) > 64:
            raise_param_error("live_follow_up_session")
        user_bid = _request_user_bid()
        if not user_bid:
            raise_error("server.user.userNotLogin")
        origin = _require_allowed_origin(app)
        try:
            session = load_live_follow_up_session(
                app,
                session_bid=session_bid,
                allow_finalization=allow_finalization,
            )
        except LiveFollowUpSessionStoreError:
            raise_param_error("live_follow_up_session")
        if not hmac.compare_digest(
            session.binding.user_bid, user_bid
        ) or not hmac.compare_digest(session.binding.origin, origin):
            raise_param_error("live_follow_up_session")
        return session

    def touch_direct_session(
        session: StoredLiveFollowUpSession, *, finalizing: bool = False
    ) -> None:
        try:
            touch_live_follow_up_session(
                app,
                session_bid=session.binding.session_bid,
                finalizing=finalizing,
            )
        except (LiveFollowUpCapacityError, LiveFollowUpSessionStoreError):
            raise_param_error("live_follow_up_session")

    def require_retirement_receipt(session_bid: str) -> dict[str, object] | None:
        user_bid = _request_user_bid()
        if not user_bid:
            raise_error("server.user.userNotLogin")
        origin = _require_allowed_origin(app)
        try:
            return retirement_receipt(
                app, user_bid=user_bid, origin=origin, session_bid=session_bid
            )
        except LiveFollowUpCapacityError:
            raise_param_error("live_follow_up_session")

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/heartbeat",
        methods=["POST"],
    )
    @sensitive_body(max_bytes=_MAX_DIRECT_TURN_REPORT_BYTES)
    def heartbeat_live_follow_up_session_api(session_bid: str) -> Response:
        session = require_direct_session(session_bid)
        if session.admission:
            try:
                current = current_admission(
                    app,
                    session.admission,
                    session_bid=session_bid,
                    admission_revision=session.admission_revision,
                )
            except LiveFollowUpCapacityError:
                return _make_live_response(
                    {
                        "session_bid": session_bid,
                        "operation_status": "rejected",
                        "error_code": "admission_unavailable",
                    }
                )
            if not current:
                return _make_live_response(
                    {
                        "session_bid": session_bid,
                        "operation_status": "rejected",
                        "error_code": "ownership_conflict",
                    }
                )
        touch_direct_session(session)
        expires_at = datetime.fromtimestamp(
            session.binding.expires_at_epoch,
            tz=UTC,
        )
        return _make_live_response(
            {"session_bid": session_bid, "expires_at": to_utc_iso(expires_at)}
        )

    def persist_reserved_turn(
        session: StoredLiveFollowUpSession,
        turn: LiveTurnPersistenceInput,
        reservation: LiveFollowUpTurnReservation,
    ) -> LiveTurnPersistenceResult:
        binding = session.binding
        session_bid = binding.session_bid
        trace: LiveFollowUpTrace | None = None
        try:
            trace = LiveFollowUpTrace(
                app,
                session_bid=binding.session_bid,
                user_bid=binding.user_bid,
                shifu_bid=binding.shifu_bid,
                outline_item_bid=binding.outline_bid,
            )
            result = persist_live_follow_up_turn(
                app,
                LiveTurnPersistenceContext(
                    session_bid=session_bid,
                    user_bid=binding.user_bid,
                    shifu_bid=binding.shifu_bid,
                    outline_item_bid=binding.outline_bid,
                    progress_record_bid=binding.progress_record_bid,
                    anchor_element_bid=binding.anchor_element_bid,
                    preview_mode=binding.preview_mode,
                    learning_mode=binding.learning_mode,
                    request_id=get_request_id(),
                    trace_id=trace.trace_id,
                ),
                turn,
            )
            commit_live_follow_up_turn_reservation(
                app,
                reservation=reservation,
            )
            with contextlib.suppress(Exception):
                trace.record_turn(turn, result)
        except Exception:
            with contextlib.suppress(Exception):
                release_live_follow_up_turn_reservation(
                    app,
                    reservation=reservation,
                )
            app.logger.error(  # noqa: TRY400 - never log transcript values
                "Gemini Live direct turn persistence failed session=%s turn=%s",
                session_bid,
                turn.turn_index,
            )
            raise_param_error("live_follow_up_turn")
        finally:
            if trace is not None:
                with contextlib.suppress(Exception):
                    trace.close(end_reason="turn_committed")
        return result

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/turn",
        methods=["POST"],
    )
    @sensitive_body(max_bytes=_MAX_DIRECT_TURN_REPORT_BYTES)
    def commit_live_follow_up_turn_api(session_bid: str) -> Response:
        turn = _validate_turn_payload(_read_bounded_turn_payload())
        try:
            session = require_direct_session(session_bid, allow_finalization=True)
        except AppError:
            receipt = require_retirement_receipt(session_bid)
            if receipt is None or turn.turn_index > int(
                receipt["last_committed_index"]
            ):
                raise
            result = load_persisted_live_follow_up_turn(session_bid, turn.turn_index)
            return _make_live_response(
                {
                    "session_bid": session_bid,
                    "turn_index": turn.turn_index,
                    "history_saved": result.history_saved,
                    "ask_element_bid": result.ask_element_bid,
                    "answer_element_bid": result.answer_element_bid,
                }
            )
        touch_direct_session(session, finalizing=True)
        try:
            with live_follow_up_persistence_lock(app, session_bid):
                session = require_direct_session(session_bid, allow_finalization=True)
                if turn.turn_index <= session.turn_state.last_committed_index:
                    result = load_persisted_live_follow_up_turn(
                        session_bid, turn.turn_index
                    )
                else:
                    reservation = reserve_live_follow_up_turn(
                        app,
                        session_bid=session_bid,
                        turn_index=turn.turn_index,
                        recover_pending=True,
                    )
                    result = persist_reserved_turn(session, turn, reservation)
        except (LiveFollowUpSessionStoreError, LiveFollowUpPersistenceError):
            raise_param_error("live_follow_up_turn")
        return _make_live_response(
            {
                "session_bid": session_bid,
                "turn_index": turn.turn_index,
                "history_saved": result.history_saved,
                "ask_element_bid": result.ask_element_bid,
                "answer_element_bid": result.answer_element_bid,
            }
        )

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/finalize",
        methods=["POST"],
    )
    @sensitive_body(max_bytes=_MAX_DIRECT_TURN_REPORT_BYTES)
    def finalize_live_follow_up_session_api(session_bid: str) -> Response:
        admitted_at = time.time()
        payload = _read_bounded_turn_payload()
        if not isinstance(payload, dict):
            raise_param_error("live_follow_up_turn")
        reports = payload.get("turns")
        if not isinstance(reports, list) or len(reports) > LIVE_FOLLOW_UP_MAX_TURNS:
            raise_param_error("live_follow_up_turn")
        turns = [_validate_turn_payload(item) for item in reports]
        if any(
            following.turn_index != previous.turn_index + 1
            for previous, following in pairwise(turns)
        ):
            raise_param_error("live_follow_up_turn")
        try:
            session = require_direct_session(session_bid, allow_finalization=True)
        except AppError:
            receipt = require_retirement_receipt(session_bid)
            if receipt is None or any(
                turn.turn_index > int(receipt["last_committed_index"]) for turn in turns
            ):
                raise
            return _make_live_response(
                {
                    "session_bid": session_bid,
                    "turn_indices": [turn.turn_index for turn in turns],
                    "admission_revision": receipt["admission_revision"],
                }
            )
        if session.admission:
            admitted_at = admission_time()
        # An admitted batch may wait for the DB lock across the grace deadline.
        # Retain its binding now, without granting any later request admission.
        touch_direct_session(session, finalizing=True)
        try:
            with live_follow_up_persistence_lock(app, session_bid):
                # Admission applies to this already-validated, bounded batch.
                # Reload its cursor under the DB lock using the admission time,
                # not a new deadline check after each potentially slow write.
                bound_session = load_live_follow_up_session(
                    app,
                    session_bid=session_bid,
                    current_time=admitted_at,
                    allow_finalization=True,
                )
                # Redis Lua serializes epoch seconds at 14 significant digits.
                # Allow only that rounding noise; all other binding fields match
                # exactly and the stored admission deadline stays unchanged.
                if replace(
                    bound_session.binding,
                    expires_at_epoch=session.binding.expires_at_epoch,
                ) != session.binding or not math.isclose(
                    bound_session.binding.expires_at_epoch,
                    session.binding.expires_at_epoch,
                    rel_tol=0,
                    abs_tol=0.0001,
                ):
                    raise LiveFollowUpSessionRejectedError
                for turn in turns:
                    if turn.turn_index <= bound_session.turn_state.last_committed_index:
                        continue
                    touch_live_follow_up_session(
                        app, session_bid=session_bid, finalizing=True
                    )
                    reservation = reserve_live_follow_up_turn(
                        app,
                        session_bid=session_bid,
                        turn_index=turn.turn_index,
                        recover_pending=True,
                    )
                    persist_reserved_turn(bound_session, turn, reservation)
                latest_session = load_live_follow_up_session(
                    app,
                    session_bid=session_bid,
                    current_time=admitted_at,
                    allow_finalization=True,
                )
                _retire_session_admission(app, latest_session)
                consume_live_follow_up_session(app, session_bid=session_bid)
        except (
            LiveFollowUpSessionStoreError,
            LiveFollowUpPersistenceError,
            LiveFollowUpCapacityError,
        ):
            raise_param_error("live_follow_up_turn")
        return _make_live_response(
            {
                "session_bid": session_bid,
                "turn_indices": [turn.turn_index for turn in turns],
            }
        )

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/end",
        methods=["POST"],
    )
    @sensitive_body(max_bytes=_MAX_DIRECT_TURN_REPORT_BYTES)
    def end_live_follow_up_session_api(session_bid: str) -> Response:
        admitted_at = time.time()
        try:
            session = require_direct_session(session_bid, allow_finalization=True)
        except AppError:
            receipt = require_retirement_receipt(session_bid)
            if receipt is None:
                raise
            return _make_live_response(
                {
                    "session_bid": session_bid,
                    "reason": "ended_by_user",
                    "admission_revision": receipt["admission_revision"],
                }
            )
        payload = request.get_json(silent=True) or {}
        end_reason = str(payload.get("reason") or "ended_by_user").strip()
        if end_reason not in {
            "ended_by_user",
            "client_disconnected",
            "connection_error",
            "lesson_changed",
            "page_hidden",
            "replaced",
            "timeout",
        }:
            end_reason = "connection_error"
        if session.admission:
            admitted_at = admission_time()
            touch_direct_session(session, finalizing=True)
        try:
            with live_follow_up_persistence_lock(app, session_bid):
                if session.admission:
                    session = load_live_follow_up_session(
                        app,
                        session_bid=session_bid,
                        current_time=admitted_at,
                        allow_finalization=True,
                    )
                _retire_session_admission(app, session)
                consume_live_follow_up_session(app, session_bid=session_bid)
        except LiveFollowUpSessionRejectedError:
            pass
        except (
            LiveFollowUpSessionStoreError,
            LiveFollowUpPersistenceError,
            LiveFollowUpCapacityError,
        ):
            raise_param_error("live_follow_up_session")
        # The browser has already received a credential that Gemini accepts
        # until its fixed expireTime. Gemini exposes no revoke operation, so
        # only logical ownership is retired here. Its independent credential
        # reservation expires naturally and continues counting toward 24/6/3.
        data: dict[str, object] = {"session_bid": session_bid, "reason": end_reason}
        if session.admission_revision:
            data["admission_revision"] = session.admission_revision
        return _make_live_response(data)
