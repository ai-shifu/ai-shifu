"""Authenticated browser-direct Gemini Live follow-up routes."""

from __future__ import annotations

import contextlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, Response, request
from flaskr.api.langfuse import get_request_id
from flaskr.api.llm import is_live_follow_up_model_available
from flaskr.common.http import make_common_response
from flaskr.common.shifu_context import with_shifu_context
from flaskr.i18n import get_current_language
from flaskr.service.common import raise_error
from flaskr.service.common.models import raise_param_error
from flaskr.service.config import get_config
from flaskr.service.learn.follow_up_context import (
    build_follow_up_conversation_context,
    resolve_course_system_prompt,
)
from flaskr.service.learn.gemini_live_token import (
    GEMINI_LIVE_CONSTRAINED_ENDPOINT,
    GeminiLiveEphemeralToken,
    GeminiLiveHistoryTurn,
    GeminiLiveTokenError,
    build_gemini_live_client_setup,
    build_gemini_live_history_message,
    mint_gemini_live_ephemeral_token,
)
from flaskr.service.learn.learn_dtos import LearnOutlineItemInfoDTO, OutlineType
from flaskr.service.learn.learn_funcs import get_outline_item_tree
from flaskr.service.learn.live_follow_up_capacity import (
    LiveFollowUpCapacityError,
    LiveFollowUpCapacityLease,
    LiveFollowUpCapacityLimitError,
    acquire_live_follow_up_capacity,
    release_live_follow_up_capacity,
)
from flaskr.service.learn.live_follow_up_config import (
    DEFAULT_GEMINI_LIVE_VOICE,
    GEMINI_LIVE_MODEL_ID,
    is_gemini_live_enabled,
    is_live_follow_up_model,
    normalize_live_follow_up_provider_config,
)
from flaskr.service.learn.live_follow_up_persistence import (
    LiveTurnPersistenceContext,
    LiveTurnPersistenceInput,
    persist_live_follow_up_turn,
)
from flaskr.service.learn.live_follow_up_session_store import (
    LIVE_FOLLOW_UP_MAX_TURNS,
    LIVE_FOLLOW_UP_SESSION_HEARTBEAT_INTERVAL_SECONDS,
    LiveFollowUpSessionBinding,
    LiveFollowUpSessionRejectedError,
    LiveFollowUpSessionStoreError,
    StoredLiveFollowUpSession,
    commit_live_follow_up_turn_reservation,
    consume_live_follow_up_session,
    load_live_follow_up_session,
    release_live_follow_up_turn_reservation,
    reserve_live_follow_up_turn,
    store_live_follow_up_session,
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
from flaskr.util.uuid import generate_id
from sqlalchemy import or_

LIVE_FOLLOW_UP_SESSION_SECONDS = 15 * 60
LIVE_FOLLOW_UP_WARNING_SECONDS = 14 * 60 + 30
_ALLOWED_LEARNING_MODES = frozenset({"read", "listen"})
_ALLOWED_SURFACES = frozenset({"read_content", "listen_player", "teacher_preview"})
_MAX_DIRECT_TRANSCRIPT_CHARS = 32_000
_MAX_DIRECT_USAGE_BYTES = 64 * 1024
_MAX_DIRECT_TURN_REPORT_BYTES = 60 * 1024


class LiveFollowUpModelUnavailableError(RuntimeError):
    """Signal that Gemini no longer advertises the required Bidi capability."""


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
        course_system_prompt=resolve_course_system_prompt(
            app,
            shifu_bid=binding.shifu_bid,
            outline_item_bid=binding.outline_bid,
            preview_mode=binding.preview_mode,
        ),
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
) -> Response:
    return make_common_response(
        {
            "session_bid": binding.session_bid,
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


def register_live_follow_up_routes(
    app: Flask,
    path_prefix: str = "/api/learn",
) -> None:
    """Register the direct Live session, heartbeat, turn, and end endpoints."""

    @app.route(
        path_prefix + "/shifu/<shifu_bid>/live-follow-up/<outline_bid>/session",
        methods=["POST"],
    )
    @with_shifu_context()
    def create_live_follow_up_session_api(
        shifu_bid: str,
        outline_bid: str,
    ) -> Response:
        if not is_gemini_live_enabled():
            raise_param_error("live_follow_up")
        if not is_live_follow_up_model_available(GEMINI_LIVE_MODEL_ID):
            raise_param_error("follow_up_model")
        user_bid = _request_user_bid()
        if not user_bid:
            raise_error("server.user.userNotLogin")
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise_param_error("live_follow_up")
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

        lease: LiveFollowUpCapacityLease | None = None
        try:
            lease = acquire_live_follow_up_capacity(app, user_bid=user_bid)
            token = mint_gemini_live_ephemeral_token(
                api_key=api_key,
                model=provisional_binding.model,
                voice_name=voice,
                system_instruction=system_instruction,
                include_initial_history=bool(history),
            )
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
            store_live_follow_up_session(
                app,
                session=StoredLiveFollowUpSession(binding=binding, lease=lease),
            )
        except LiveFollowUpCapacityLimitError:
            raise_param_error("live_follow_up_capacity")
        except (LiveFollowUpCapacityError, LiveFollowUpSessionStoreError):
            if lease is not None:
                with contextlib.suppress(Exception):
                    release_live_follow_up_capacity(app, lease=lease)
            raise_param_error("live_follow_up")
        except GeminiLiveTokenError:
            if lease is not None:
                with contextlib.suppress(Exception):
                    release_live_follow_up_capacity(app, lease=lease)
            app.logger.error(  # noqa: TRY400 - never log provider response details
                "Gemini Live token provisioning failed session=%s",
                session_bid,
            )
            raise_param_error("live_follow_up")
        return _session_response(binding=binding, token=token, history=history)

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

    def touch_direct_session(session: StoredLiveFollowUpSession) -> None:
        try:
            touch_live_follow_up_session(
                app,
                session_bid=session.binding.session_bid,
            )
        except (LiveFollowUpCapacityError, LiveFollowUpSessionStoreError):
            raise_param_error("live_follow_up_session")

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/heartbeat",
        methods=["POST"],
    )
    def heartbeat_live_follow_up_session_api(session_bid: str) -> Response:
        session = require_direct_session(session_bid)
        touch_direct_session(session)
        expires_at = datetime.fromtimestamp(
            session.binding.expires_at_epoch,
            tz=UTC,
        )
        return make_common_response(
            {"session_bid": session_bid, "expires_at": to_utc_iso(expires_at)}
        )

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/turn",
        methods=["POST"],
    )
    def commit_live_follow_up_turn_api(session_bid: str) -> Response:
        session = require_direct_session(session_bid, allow_finalization=True)
        if len(request.get_data(cache=True)) > _MAX_DIRECT_TURN_REPORT_BYTES:
            raise_param_error("live_follow_up_turn")
        turn = _validate_turn_payload(request.get_json(silent=True) or {})
        touch_direct_session(session)
        try:
            reservation = reserve_live_follow_up_turn(
                app,
                session_bid=session_bid,
                turn_index=turn.turn_index,
            )
        except LiveFollowUpSessionStoreError:
            raise_param_error("live_follow_up_turn")
        binding = session.binding
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
        return make_common_response(
            {
                "session_bid": session_bid,
                "turn_index": turn.turn_index,
                "history_saved": result.history_saved,
                "ask_element_bid": result.ask_element_bid,
                "answer_element_bid": result.answer_element_bid,
            }
        )

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/end",
        methods=["POST"],
    )
    def end_live_follow_up_session_api(session_bid: str) -> Response:
        require_direct_session(session_bid, allow_finalization=True)
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
        try:
            consume_live_follow_up_session(app, session_bid=session_bid)
        except LiveFollowUpSessionRejectedError:
            pass
        except LiveFollowUpSessionStoreError:
            raise_param_error("live_follow_up_session")
        # The browser has already received a credential that Gemini accepts
        # until its fixed expireTime. Gemini exposes no revoke operation, so
        # releasing admission here would let one user keep the old socket and
        # mint another token outside the 24/6/1 capacity bounds. The Redis
        # reservation therefore expires naturally with the token.
        return make_common_response({"session_bid": session_bid, "reason": end_reason})
