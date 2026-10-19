"""Authenticated browser-direct Gemini Live follow-up routes."""

from __future__ import annotations

import contextlib
import hmac
import math
import os
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from itertools import pairwise
from threading import Lock, Thread
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from flask import Flask, Response, request
from flaskr.api.langfuse import get_request_id
from flaskr.api.llm import is_live_follow_up_model_available
from flaskr.common.config import has_explicit_env_override
from flaskr.common.http import (
    make_common_response,  # noqa: F401  # re-exported public API
    sensitive_body,
)
from flaskr.common.shifu_context import with_shifu_context
from flaskr.i18n import get_current_language
from flaskr.service.common import raise_error
from flaskr.service.common.models import AppError, raise_param_error
from flaskr.service.config import (
    config_cache_client,
    config_overrides,
    get_cached_config,
    get_config,
    has_config_override,
)
from flaskr.service.learn.follow_up_context import (
    build_follow_up_conversation_context,
)
from flaskr.service.learn.gemini_live_token import (
    GEMINI_LIVE_CONSTRAINED_ENDPOINT,  # noqa: F401  # re-exported public API
    GEMINI_LIVE_TOKEN_CONNECT_SECONDS,  # noqa: F401  # re-exported public API
    GEMINI_LIVE_TOKEN_LIFETIME_SECONDS,  # noqa: F401  # re-exported public API
    GeminiLiveEphemeralToken,  # noqa: F401  # re-exported public API
    GeminiLiveHistoryTurn,
    GeminiLiveTokenError,
    GeminiLiveTokenTimeoutError,
    build_gemini_live_client_setup,  # noqa: F401  # re-exported public API
    build_gemini_live_history_message,  # noqa: F401  # re-exported public API
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
    discover_admission_owner,
    fail_admission,
    legacy_request_bid,
    live_follow_up_readiness,
    live_follow_up_readiness_client,
    request_timestamp_ms,  # noqa: F401  # re-exported public API
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
from flaskr.service.learn.live_follow_up_payloads import (
    _ALLOWED_LEARNING_MODES,
    _ALLOWED_SURFACES,
    _ERROR_DEADLINE_MISMATCH,
    _MAX_DIRECT_TURN_REPORT_BYTES,
    LIVE_FOLLOW_UP_SESSION_SECONDS,  # noqa: F401  # re-exported public API
    _admission_failure,
    _admission_request,
    _make_live_response,
    _new_session_binding,
    _normalize_origin,
    _read_bounded_turn_payload,
    _session_response,
    _validate_token_deadlines,
    _validate_turn_payload,
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
    LIVE_FOLLOW_UP_SESSION_HEARTBEAT_INTERVAL_SECONDS,  # noqa: F401  # re-exported public API
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
from flaskr.service.user.api import is_allowed_oauth_origin, load_user_aggregate
from flaskr.util.datetime import to_utc_iso
from flaskr.util.prompt_loader import load_prompt_template
from flaskr.util.uuid import generate_id
from sqlalchemy import or_

if TYPE_CHECKING:
    from collections.abc import Iterator

LIVE_FOLLOW_UP_WARNING_SECONDS = 14 * 60 + 30


class LiveFollowUpModelUnavailableError(RuntimeError):
    """Signal that Gemini no longer advertises the required Bidi capability."""


def _request_user_bid() -> str:
    user = getattr(request, "user", None)
    return str(getattr(user, "user_id", "") or "").strip()


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
        # Live conversations must not be forced into the interface language.
        use_learner_language=False,
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


@contextlib.contextmanager
def _bounded_live_config() -> Iterator[None]:
    key = "GEMINI_LIVE_ENABLED"
    if has_explicit_env_override(key) or has_config_override(key):
        yield
    else:
        with (
            live_follow_up_readiness_client() as client,
            config_cache_client(client, cache_absence=True),
        ):
            yield


def _cached_live_enabled() -> bool:
    with _bounded_live_config():
        value = get_cached_config("GEMINI_LIVE_ENABLED", default=False)
    with config_overrides({"GEMINI_LIVE_ENABLED": value}):
        return is_gemini_live_enabled()


def _prepare_live_follow_up(app: Flask) -> bool:
    """Return whether preparation is done or Live is explicitly disabled."""
    try:
        with app.app_context(), _bounded_live_config():
            enabled = is_gemini_live_enabled()
            if not enabled and has_explicit_env_override("GEMINI_LIVE_ENABLED"):
                return True
            if not enabled:
                # Only a confirmed cached value/DB absence can settle disabled;
                # a transient DB failure fallback has neither and keeps retrying.
                value = get_cached_config("GEMINI_LIVE_ENABLED", default=False)
                with config_overrides({"GEMINI_LIVE_ENABLED": value}):
                    enabled = is_gemini_live_enabled()
                if not enabled:
                    return True
            status = live_follow_up_readiness(app, enabled=enabled)["status"]
            # A warming marker is already initialized; no need to wait for its deadline.
            return status in {"ready", "warming"}
    except Exception:
        return False


@dataclass
class _LiveReadinessTask:
    lock: Lock = field(default_factory=Lock)
    active: bool = False
    next_start_at: float = 0


def _retry_live_follow_up_preparation(
    app: Flask, task: _LiveReadinessTask | None = None
) -> None:
    """Retry startup failures without learner traffic or unbounded task growth."""
    try:
        for attempt in range(21):
            if attempt:
                time.sleep(30)
            if _prepare_live_follow_up(app):
                return
        app.logger.warning("Live follow-up startup preparation still unavailable")
    finally:
        if task is not None:
            with task.lock:
                task.active = False
                task.next_start_at = time.monotonic() + 30


def init_live_follow_up_readiness(app: Flask, *, refresh: bool = False) -> None:
    """Prepare/refresh Live without overlapping tasks or preload-master I/O."""
    if os.environ.get("AI_SHIFU_PRELOAD_MASTER") or not app.extensions.get(
        "serving_http", True
    ):
        return
    # A PID-scoped key never acquires a lock inherited from another process.
    candidate = _LiveReadinessTask()
    task = app.extensions.setdefault(f"live_follow_up_startup:{os.getpid()}", candidate)
    if task is not candidate and not refresh:
        return
    # Even the first DB-backed config lookup belongs in this one task. Never
    # join it or create timeout-replacement threads if a dependency is stalled.
    with task.lock:
        if task.active or time.monotonic() < task.next_start_at:
            return
        task.active = True
        try:
            Thread(
                target=_retry_live_follow_up_preparation,
                args=(app, task),
                name="live-follow-up-startup",
                daemon=True,
            ).start()
        except Exception:
            task.active = False
            task.next_start_at = time.monotonic() + 30
            app.logger.warning("Live follow-up startup retry unavailable")


@dataclass(frozen=True)
class _LiveSessionDraft:
    """Validated course context gathered before any admission side effect."""

    user_bid: str
    origin: str
    api_key: str
    voice: str
    provisional_binding: LiveFollowUpSessionBinding
    system_instruction: str
    history: tuple[GeminiLiveHistoryTurn, ...]


def _draft_live_session(
    app: Flask, shifu_bid: str, outline_bid: str, payload: dict[str, object]
) -> _LiveSessionDraft:
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
    return _LiveSessionDraft(
        user_bid=user_bid,
        origin=origin,
        api_key=api_key,
        voice=voice,
        provisional_binding=provisional_binding,
        system_instruction=system_instruction,
        history=history,
    )


def _issue_live_session(
    app: Flask,
    draft: _LiveSessionDraft,
    *,
    shifu_bid: str,
    outline_bid: str,
    payload: dict[str, object],
) -> Response:
    provisional_binding = draft.provisional_binding
    session_bid = provisional_binding.session_bid
    user_bid = draft.user_bid
    origin = draft.origin
    voice = draft.voice
    history = draft.history
    legacy = "request_bid" not in payload
    rotation = is_gemini_live_rotation_enabled()
    admission: AdmissionResult | None = None
    admission_request: AdmissionRequest | None = None
    try:
        operation_bid = (
            legacy_request_bid() if legacy else str(payload.get("request_bid") or "")
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
            api_key=draft.api_key,
            api_base_url=str(get_config("GEMINI_API_URL", "") or "").strip(),
            model=provisional_binding.model,
            voice_name=voice,
            system_instruction=draft.system_instruction,
            include_initial_history=bool(history),
            current_time=issued_at,
        )
        _validate_token_deadlines(token, issued_at)
        binding = _new_session_binding(
            session_bid=session_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            anchor_element_bid=provisional_binding.anchor_element_bid,
            progress_record_bid=provisional_binding.progress_record_bid,
            preview_mode=provisional_binding.preview_mode,
            origin=origin,
            model=provisional_binding.model,
            voice_name=voice,
            language=provisional_binding.language,
            learning_mode=provisional_binding.learning_mode,
            expires_at_epoch=token.expires_at.timestamp(),
        )
        session = StoredLiveFollowUpSession(
            binding=binding,
            lease=admission.lease,
            admission=admission_request,
            admission_revision=str(admission.data["admission_revision"]),
        )
        _complete_session_admission(app, admission_request, admission, session)
        # Use the same Redis clock as credential issuance and risk leases,
        # not the HTTP worker's or learner device's wall clock.
        expires_in_ms = max(
            0, math.ceil((token.expires_at.timestamp() - admission_time()) * 1000)
        )
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
        expires_in_ms=expires_in_ms,
    )


def _require_direct_session(
    app: Flask,
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


def _touch_direct_session(
    app: Flask, session: StoredLiveFollowUpSession, *, finalizing: bool = False
) -> None:
    try:
        touch_live_follow_up_session(
            app,
            session_bid=session.binding.session_bid,
            finalizing=finalizing,
        )
    except (LiveFollowUpCapacityError, LiveFollowUpSessionStoreError):
        raise_param_error("live_follow_up_session")


def _require_retirement_receipt(
    app: Flask, session_bid: str
) -> dict[str, object] | None:
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


def _persist_reserved_turn(
    app: Flask,
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


def _turn_response(
    session_bid: str, turn_index: int, result: LiveTurnPersistenceResult
) -> Response:
    return _make_live_response(
        {
            "session_bid": session_bid,
            "turn_index": turn_index,
            "history_saved": result.history_saved,
            "ask_element_bid": result.ask_element_bid,
            "answer_element_bid": result.answer_element_bid,
        }
    )


def _persist_finalized_turns(
    app: Flask,
    session: StoredLiveFollowUpSession,
    *,
    session_bid: str,
    turns: list[LiveTurnPersistenceInput],
    admitted_at: float,
) -> None:
    with live_follow_up_persistence_lock(app, session.binding.progress_record_bid):
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
            touch_live_follow_up_session(app, session_bid=session_bid, finalizing=True)
            reservation = reserve_live_follow_up_turn(
                app,
                session_bid=session_bid,
                turn_index=turn.turn_index,
                recover_pending=True,
            )
            _persist_reserved_turn(app, bound_session, turn, reservation)
        latest_session = load_live_follow_up_session(
            app,
            session_bid=session_bid,
            current_time=admitted_at,
            allow_finalization=True,
        )
        _retire_session_admission(app, latest_session)
        consume_live_follow_up_session(app, session_bid=session_bid)


def register_live_follow_up_routes(
    app: Flask,
    path_prefix: str = "/api/learn",
) -> None:
    """Register the direct Live session, heartbeat, turn, and end endpoints."""
    # Preloaded deployments defer process-local work to post_fork; ordinary
    # app factories prepare here without waiting for a learner request.
    init_live_follow_up_readiness(app)
    _register_live_admission_routes(app, path_prefix)
    _register_live_direct_session_routes(app, path_prefix)


def _register_live_admission_routes(app: Flask, path_prefix: str) -> None:
    """Register readiness, session creation/status, and owner discovery."""

    @app.route(path_prefix + "/live-follow-up/readiness", methods=["GET"])
    def live_follow_up_readiness_api() -> Response:
        try:
            enabled = _cached_live_enabled()
            # Reuse the resolved flag so the capability check cannot re-enter
            # the shared unbounded config cache or its DB fallback.
            with config_overrides({"GEMINI_LIVE_ENABLED": enabled}):
                readiness = live_follow_up_readiness(app, enabled=enabled)
                if readiness["status"] in {"ready", "warming"} and not (
                    is_live_follow_up_model_available(GEMINI_LIVE_MODEL_ID)
                ):
                    readiness = {"status": "unavailable", "retry_after_ms": 30_000}
        except LookupError:
            # Expired DB-backed flags need repopulation even after successful
            # startup. This schedules at most one rate-limited background task.
            init_live_follow_up_readiness(app, refresh=True)
            readiness = {"status": "unavailable", "retry_after_ms": 30_000}
        except Exception:
            readiness = {"status": "unavailable", "retry_after_ms": 30_000}
        return _make_live_response(readiness)

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
        if operation_kind not in {"create", "takeover"}:
            raise_param_error("live_follow_up")
        return create_session_with_course_context(shifu_bid, outline_bid, payload)

    @app.route(path_prefix + "/live-follow-up/owner", methods=["POST"])
    @sensitive_body(max_bytes=_MAX_DIRECT_TURN_REPORT_BYTES)
    def discover_live_follow_up_owner_api() -> Response:
        user_bid = _request_user_bid()
        if not user_bid:
            raise_error("server.user.userNotLogin")
        origin = _require_allowed_origin(app)
        try:
            return _make_live_response(
                discover_admission_owner(
                    app,
                    user_bid=user_bid,
                    origin=origin,
                    rotation_enabled=is_gemini_live_rotation_enabled(),
                )
            )
        except LiveFollowUpCapacityError:
            return _make_live_response(
                {
                    "operation_status": "rejected",
                    "error_code": "admission_unavailable",
                }
            )

    @with_shifu_context()
    def create_session_with_course_context(
        shifu_bid: str, outline_bid: str, payload: dict[str, object]
    ) -> Response:
        draft = _draft_live_session(app, shifu_bid, outline_bid, payload)
        return _issue_live_session(
            app,
            draft,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            payload=payload,
        )


def _register_live_direct_session_routes(app: Flask, path_prefix: str) -> None:
    """Register the browser-direct session heartbeat, turn, finalize, and end."""

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/heartbeat",
        methods=["POST"],
    )
    @sensitive_body(max_bytes=_MAX_DIRECT_TURN_REPORT_BYTES)
    def heartbeat_live_follow_up_session_api(session_bid: str) -> Response:
        session = _require_direct_session(app, session_bid)
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
        _touch_direct_session(app, session)
        expires_at = datetime.fromtimestamp(
            session.binding.expires_at_epoch,
            tz=UTC,
        )
        return _make_live_response(
            {"session_bid": session_bid, "expires_at": to_utc_iso(expires_at)}
        )

    @app.route(
        path_prefix + "/live-follow-up/session/<session_bid>/turn",
        methods=["POST"],
    )
    @sensitive_body(max_bytes=_MAX_DIRECT_TURN_REPORT_BYTES)
    def commit_live_follow_up_turn_api(session_bid: str) -> Response:
        turn = _validate_turn_payload(_read_bounded_turn_payload())
        try:
            session = _require_direct_session(app, session_bid, allow_finalization=True)
        except AppError:
            receipt = _require_retirement_receipt(app, session_bid)
            if receipt is None or turn.turn_index > int(
                receipt["last_committed_index"]
            ):
                raise
            result = load_persisted_live_follow_up_turn(session_bid, turn.turn_index)
            return _turn_response(session_bid, turn.turn_index, result)
        _touch_direct_session(app, session, finalizing=True)
        try:
            with live_follow_up_persistence_lock(
                app, session.binding.progress_record_bid
            ):
                session = _require_direct_session(
                    app, session_bid, allow_finalization=True
                )
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
                    result = _persist_reserved_turn(app, session, turn, reservation)
        except (LiveFollowUpSessionStoreError, LiveFollowUpPersistenceError):
            raise_param_error("live_follow_up_turn")
        return _turn_response(session_bid, turn.turn_index, result)

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
            session = _require_direct_session(app, session_bid, allow_finalization=True)
        except AppError:
            receipt = _require_retirement_receipt(app, session_bid)
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
        _touch_direct_session(app, session, finalizing=True)
        try:
            _persist_finalized_turns(
                app,
                session,
                session_bid=session_bid,
                turns=turns,
                admitted_at=admitted_at,
            )
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
            session = _require_direct_session(app, session_bid, allow_finalization=True)
        except AppError:
            receipt = _require_retirement_receipt(app, session_bid)
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
            _touch_direct_session(app, session, finalizing=True)
        try:
            with live_follow_up_persistence_lock(
                app, session.binding.progress_record_bid
            ):
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
