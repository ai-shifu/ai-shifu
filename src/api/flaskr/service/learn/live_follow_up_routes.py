"""Authenticated browser-to-Gemini Live WebSocket proxy routes."""

from __future__ import annotations

import contextlib
import json
import queue
import socket
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, Response, make_response, request
from flask_sock import Sock
from flaskr.api.langfuse import get_request_id
from flaskr.api.llm import is_live_follow_up_model_available
from flaskr.common.http import bypass_token_validation, make_common_response
from flaskr.common.shifu_context import with_shifu_context
from flaskr.dao import db
from flaskr.i18n import get_current_language
from flaskr.service.common import raise_error
from flaskr.service.common.models import raise_param_error
from flaskr.service.config import get_config
from flaskr.service.learn.follow_up_context import (
    build_follow_up_conversation_context,
    resolve_course_system_prompt,
)
from flaskr.service.learn.gemini_live_provider import (
    GEMINI_LIVE_MAX_INPUT_FRAME_BYTES,
    GeminiLiveConnectionError,
    GeminiLiveHistoryTurn,
    GeminiLiveProtocolError,
    GeminiLiveProvider,
    GeminiLiveProviderError,
)
from flaskr.service.learn.learn_dtos import (
    LearnOutlineItemInfoDTO,
    OutlineType,
)
from flaskr.service.learn.learn_funcs import get_outline_item_tree
from flaskr.service.learn.live_follow_up_capacity import (
    LIVE_FOLLOW_UP_LEASE_RENEW_INTERVAL_SECONDS,
    LiveFollowUpCapacityError,
    LiveFollowUpCapacityLease,
    LiveFollowUpCapacityLeaseLostError,
    LiveFollowUpCapacityLimitError,
    acquire_live_follow_up_capacity,
    release_live_follow_up_capacity,
    renew_live_follow_up_capacity,
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
from flaskr.service.learn.live_follow_up_security import (
    LIVE_FOLLOW_UP_TICKET_COOKIE_NAME,
    IssuedLiveFollowUpTicket,
    LiveFollowUpSecurityError,
    LiveFollowUpTicketBinding,
    consume_live_follow_up_ticket,
    issue_live_follow_up_ticket,
)
from flaskr.service.learn.live_follow_up_trace import LiveFollowUpTrace
from flaskr.service.learn.live_follow_up_turns import (
    LiveTranscriptUpdate,
    LiveTurnAccumulator,
    LiveTurnCommit,
)
from flaskr.service.learn.models import LearnGeneratedElement
from flaskr.service.learn.preview_permissions import (
    require_shifu_preview_permission,
)
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
_BROWSER_RECEIVE_TIMEOUT_SECONDS = 0.25
_PCM16_BYTES_PER_SECOND = 16_000 * 2
_PCM_INPUT_BURST_BYTES = _PCM16_BYTES_PER_SECOND * 2
_UPSTREAM_QUEUE_MAX_BYTES = _PCM16_BYTES_PER_SECOND * 4
_UPSTREAM_QUEUE_MAX_FRAMES = 128
_BROWSER_QUEUE_MAX_BYTES = 256 * 1024
_BROWSER_QUEUE_MAX_FRAMES = 256
_BROWSER_SEND_TIMEOUT_SECONDS = 5.0
_WRITER_DRAIN_TIMEOUT_SECONDS = 1.0
_PERSISTENCE_QUEUE_MAX_TURNS = 32
_ALLOWED_LEARNING_MODES = frozenset({"read", "listen"})
_ALLOWED_SURFACES = frozenset({"read_content", "listen_player", "teacher_preview"})


@dataclass(frozen=True)
class _ReaderFailure:
    code: str
    retryable: bool


class LiveFollowUpModelUnavailableError(RuntimeError):
    """Signal that Gemini no longer advertises the required Bidi capability."""


class _PcmInputRateLimiter:
    """Bound browser PCM to the declared 16 kHz mono PCM16 byte rate."""

    def __init__(
        self,
        *,
        bytes_per_second: int = _PCM16_BYTES_PER_SECOND,
        burst_bytes: int = _PCM_INPUT_BURST_BYTES,
    ) -> None:
        self._bytes_per_second = max(1, int(bytes_per_second))
        self._burst_bytes = max(1, int(burst_bytes))
        self._tokens = float(self._burst_bytes)
        self._updated_at = time.monotonic()

    def allow(self, frame_bytes: int, *, now: float | None = None) -> bool:
        amount = max(0, int(frame_bytes))
        current = time.monotonic() if now is None else float(now)
        elapsed = max(0.0, current - self._updated_at)
        self._tokens = min(
            float(self._burst_bytes),
            self._tokens + elapsed * self._bytes_per_second,
        )
        self._updated_at = current
        if amount > self._tokens:
            return False
        self._tokens -= amount
        return True


class _BrowserSender:
    """Deliver browser frames on one bounded, cancellable writer thread."""

    _SENTINEL = object()

    def __init__(
        self,
        ws: object,
        *,
        max_queue_bytes: int = _BROWSER_QUEUE_MAX_BYTES,
        max_queue_frames: int = _BROWSER_QUEUE_MAX_FRAMES,
        send_timeout_seconds: float = _BROWSER_SEND_TIMEOUT_SECONDS,
    ) -> None:
        self._ws = ws
        self._max_queue_bytes = max(1, int(max_queue_bytes))
        self._queue: queue.Queue[tuple[str | bytes, int] | object] = queue.Queue(
            maxsize=max(1, int(max_queue_frames))
        )
        self._state_lock = threading.Lock()
        self._pending_bytes = 0
        self._pending_frames = 0
        self._inflight_started_at: float | None = None
        self._send_timeout_seconds = max(0.01, float(send_timeout_seconds))
        self._accepting = True
        self._failed = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._thread = threading.Thread(
            target=self._run,
            name="gemini-live-browser-writer",
            daemon=True,
        )
        self._thread.start()

    @property
    def failed(self) -> bool:
        with self._state_lock:
            inflight_started_at = self._inflight_started_at
        if (
            not self._failed.is_set()
            and inflight_started_at is not None
            and time.monotonic() - inflight_started_at >= self._send_timeout_seconds
        ):
            self._fail()
        return self._failed.is_set()

    def json(self, payload: dict[str, object]) -> bool:
        return self._send(json.dumps(payload, separators=(",", ":")))

    def binary(self, payload: bytes) -> bool:
        return self._send(payload)

    def _send(self, payload: str | bytes) -> bool:
        size = (
            len(payload) if isinstance(payload, bytes) else len(payload.encode("utf-8"))
        )
        with self._state_lock:
            if (
                not self._accepting
                or self._failed.is_set()
                or self._pending_bytes + size > self._max_queue_bytes
            ):
                accepted = False
            else:
                self._pending_bytes += size
                self._pending_frames += 1
                self._idle.clear()
                accepted = True
        if not accepted:
            self._fail()
            return False
        try:
            self._queue.put_nowait((payload, size))
        except queue.Full:
            self._finish_frame(size)
            self._fail()
            return False
        return True

    def close(
        self,
        *,
        drain: bool = True,
        timeout: float = _WRITER_DRAIN_TIMEOUT_SECONDS,
    ) -> None:
        """Stop accepting frames and finish without waiting indefinitely."""
        with self._state_lock:
            self._accepting = False
        bounded_timeout = max(0.0, float(timeout))
        if drain and not self._failed.is_set():
            self._idle.wait(timeout=bounded_timeout)
        if not self._idle.is_set():
            self._fail()
        self._discard_queued_frames()
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(self._SENTINEL)
        self._thread.join(timeout=bounded_timeout)
        if self._thread.is_alive():
            self._abort_socket()
            self._thread.join(timeout=0.25)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is self._SENTINEL:
                self._queue.task_done()
                return
            payload, size = item
            try:
                with self._state_lock:
                    self._inflight_started_at = time.monotonic()
                self._ws.send(payload)
            except Exception:
                self._finish_frame(size, inflight=True)
                self._queue.task_done()
                self._fail()
                return
            self._finish_frame(size, inflight=True)
            self._queue.task_done()

    def _finish_frame(self, size: int, *, inflight: bool = False) -> None:
        with self._state_lock:
            if inflight:
                self._inflight_started_at = None
            self._pending_bytes = max(0, self._pending_bytes - size)
            self._pending_frames = max(0, self._pending_frames - 1)
            if self._pending_frames == 0:
                self._idle.set()

    def _fail(self) -> None:
        with self._state_lock:
            self._accepting = False
            self._failed.set()
        self._discard_queued_frames()
        self._abort_socket()

    def _discard_queued_frames(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is not self._SENTINEL:
                _payload, size = item
                self._finish_frame(size)
            self._queue.task_done()

    def _abort_socket(self) -> None:
        raw_socket = getattr(self._ws, "sock", None)
        shutdown = getattr(raw_socket, "shutdown", None)
        if callable(shutdown):
            with contextlib.suppress(Exception):
                shutdown(socket.SHUT_RDWR)


@dataclass(frozen=True)
class _UpstreamWrite:
    kind: str
    payload: bytes = b""


class _UpstreamWriter:
    """Keep Gemini writes off the lease/deadline loop with bounded backlog."""

    _SENTINEL = object()

    def __init__(
        self,
        *,
        provider: GeminiLiveProvider,
        upstream_ready: threading.Event,
        upstream_connection_lock: threading.Lock,
        session_stop: threading.Event,
        failures: queue.SimpleQueue[_ReaderFailure],
        max_queue_bytes: int = _UPSTREAM_QUEUE_MAX_BYTES,
        max_queue_frames: int = _UPSTREAM_QUEUE_MAX_FRAMES,
    ) -> None:
        self._provider = provider
        self._upstream_ready = upstream_ready
        self._upstream_connection_lock = upstream_connection_lock
        self._session_stop = session_stop
        self._failures = failures
        self._max_queue_bytes = max(1, int(max_queue_bytes))
        self._queue: queue.Queue[_UpstreamWrite | object] = queue.Queue(
            maxsize=max(1, int(max_queue_frames))
        )
        self._state_lock = threading.Lock()
        self._pending_bytes = 0
        self._pending_writes = 0
        self._accepting = True
        self._closing = threading.Event()
        self._failed = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._thread = threading.Thread(
            target=self._run,
            name="gemini-live-upstream-writer",
            daemon=True,
        )
        self._thread.start()

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    def enqueue_audio(self, frame: bytes) -> bool:
        return self._enqueue(_UpstreamWrite(kind="audio", payload=frame))

    def enqueue_audio_stream_end(self) -> bool:
        return self._enqueue(_UpstreamWrite(kind="audio_stream_end"))

    def close(
        self,
        *,
        drain: bool,
        timeout: float = _WRITER_DRAIN_TIMEOUT_SECONDS,
    ) -> None:
        with self._state_lock:
            self._accepting = False
        bounded_timeout = max(0.0, float(timeout))
        if drain and not self._failed.is_set():
            self._idle.wait(timeout=bounded_timeout)
        self._closing.set()
        if not self._idle.is_set():
            self._discard_queued_writes()
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(self._SENTINEL)
        self._thread.join(timeout=bounded_timeout)

    def wait_closed(self, *, timeout: float = 0.25) -> None:
        self._thread.join(timeout=max(0.0, float(timeout)))

    def _enqueue(self, item: _UpstreamWrite) -> bool:
        size = len(item.payload)
        with self._state_lock:
            if (
                not self._accepting
                or self._failed.is_set()
                or self._pending_bytes + size > self._max_queue_bytes
            ):
                return False
            self._pending_bytes += size
            self._pending_writes += 1
            self._idle.clear()
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._finish_write(size)
            return False
        return True

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is self._SENTINEL:
                self._queue.task_done()
                return
            try:
                if not self._wait_until_ready():
                    continue
                if not self._acquire_connection_lock():
                    continue
                try:
                    if item.kind == "audio":
                        self._provider.send_audio(item.payload)
                    else:
                        self._provider.send_audio_stream_end()
                finally:
                    self._upstream_connection_lock.release()
            except (GeminiLiveConnectionError, GeminiLiveProtocolError):
                self._record_failure()
                return
            finally:
                self._finish_write(len(item.payload))
                self._queue.task_done()

    def _wait_until_ready(self) -> bool:
        while not self._closing.is_set():
            if self._upstream_ready.wait(timeout=0.1):
                return True
        return False

    def _acquire_connection_lock(self) -> bool:
        while not self._closing.is_set():
            if self._upstream_connection_lock.acquire(timeout=0.1):
                return True
        return False

    def _record_failure(self) -> None:
        if self._failed.is_set():
            return
        self._failed.set()
        with self._state_lock:
            self._accepting = False
        self._failures.put(_ReaderFailure(code="upstream_unavailable", retryable=True))
        self._session_stop.set()
        self._discard_queued_writes()

    def _finish_write(self, size: int) -> None:
        with self._state_lock:
            self._pending_bytes = max(0, self._pending_bytes - size)
            self._pending_writes = max(0, self._pending_writes - 1)
            if self._pending_writes == 0:
                self._idle.set()

    def _discard_queued_writes(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is not self._SENTINEL:
                self._finish_write(len(item.payload))
            self._queue.task_done()


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
    # The browser controls neither the request URL's Host header nor the
    # reverse proxy's Host rewrite, while a direct client can spoof an
    # X-Forwarded-Host header. Use Flask's resolved request host here so a
    # forged forwarded header cannot make an attacker Origin look same-site.
    request_host = str(request.host or "").strip()
    return _normalize_origin(f"{forwarded_proto}://{request_host}")


def _require_allowed_origin(app: Flask) -> str:
    origin = _normalize_origin(request.headers.get("Origin"))
    if not origin:
        raise_param_error("origin")
    if origin == _request_transport_origin():
        return origin
    if is_allowed_oauth_origin(app, origin):
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


def _is_secure_cookie(app: Flask) -> bool:
    if str(app.config.get("ENV", "production") or "").lower() != "development":
        return True
    forwarded_proto = str(request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[
        0
    ]
    return bool(request.is_secure or forwarded_proto.strip().lower() == "https")


def _session_response(
    app: Flask,
    *,
    session_bid: str,
    ws_path: str,
    ticket: IssuedLiveFollowUpTicket,
) -> Response:
    response = make_response(
        make_common_response(
            {
                "session_bid": session_bid,
                "ws_path": ws_path,
                "expires_at": to_utc_iso(ticket.expires_at),
            }
        )
    )
    response.mimetype = "application/json"
    response.set_cookie(
        LIVE_FOLLOW_UP_TICKET_COOKIE_NAME,
        ticket.token,
        expires=ticket.expires_at,
        httponly=True,
        secure=_is_secure_cookie(app),
        samesite="Strict",
        path=ws_path,
    )
    return response


def _send_state(
    sender: _BrowserSender,
    state: str,
    *,
    turn_index: int | None = None,
) -> bool:
    payload: dict[str, object] = {"type": "state", "state": state}
    if turn_index is not None:
        payload["turn_index"] = int(turn_index)
    return sender.json(payload)


def _send_error(
    sender: _BrowserSender,
    *,
    code: str,
    retryable: bool,
) -> bool:
    return sender.json({"type": "error", "code": code, "retryable": bool(retryable)})


def _send_transcript(
    sender: _BrowserSender,
    update: LiveTranscriptUpdate,
) -> bool:
    return sender.json(
        {
            "type": "transcript",
            "role": update.role,
            "turn_index": int(update.turn_index),
            "text": update.text,
            "final": bool(update.final),
        }
    )


def _build_conversation(
    app: Flask,
    *,
    binding: LiveFollowUpTicketBinding,
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
        # Ten completed exchanges are at most twenty ASK/ANSWER messages.
        max_history_messages=20,
    )
    history = tuple(
        GeminiLiveHistoryTurn(role=item["role"], text=item["content"])
        for item in conversation.llm_messages
        if item.get("role") in {"user", "assistant"}
        and str(item.get("content") or "").strip()
    )
    return conversation.system_instruction, history


def _turn_input(
    commit: LiveTurnCommit,
    *,
    started_at: float | None,
) -> LiveTurnPersistenceInput:
    latency_ms = 0
    if started_at is not None:
        latency_ms = max(0, round((time.monotonic() - started_at) * 1000))
    return LiveTurnPersistenceInput(
        turn_index=commit.turn_index,
        user_transcript=commit.user_transcript,
        played_answer_transcript=commit.answer_transcript,
        interrupted=commit.interrupted,
        usage_metadata=(
            dict(commit.usage_metadata) if commit.usage_metadata is not None else None
        ),
        latency_ms=latency_ms,
    )


def _ensure_session_config_unchanged(
    binding: LiveFollowUpTicketBinding,
    *,
    current_voice: str,
) -> None:
    if binding.model == GEMINI_LIVE_MODEL_ID and binding.voice_name == current_voice:
        return
    message = "Live follow-up configuration changed before connection"
    raise RuntimeError(message)


def _commit_turns(
    app: Flask,
    *,
    commits: list[LiveTurnCommit],
    persistence_context: LiveTurnPersistenceContext,
    trace: LiveFollowUpTrace,
    sender: _BrowserSender,
    turn_started_at: dict[int, float],
    turn_started_lock: threading.Lock,
    notify_persistence_failure: bool = True,
) -> bool:
    for commit in commits:
        with turn_started_lock:
            started_at = turn_started_at.get(commit.turn_index)
        turn_input = _turn_input(
            commit,
            started_at=started_at,
        )
        try:
            result = persist_live_follow_up_turn(
                app,
                persistence_context,
                turn_input,
            )
        except Exception:
            # Do not attach the database exception here: SQLAlchemy errors can
            # include bound transcript values. The stable identifiers are
            # sufficient for operators to correlate the failed write.
            app.logger.error(  # noqa: TRY400 - never log the caught provider error
                "Gemini Live turn persistence failed session=%s turn=%s",
                persistence_context.session_bid,
                commit.turn_index,
            )
            if notify_persistence_failure:
                _send_error(sender, code="persistence_failed", retryable=True)
            return False
        finally:
            # The usage idempotence read runs in the request session while the
            # recorder writes in its own app context. Do not retain that read
            # transaction for the remainder of a 15-minute socket.
            with contextlib.suppress(Exception):
                db.session.remove()
        with turn_started_lock:
            turn_started_at.pop(commit.turn_index, None)
        with contextlib.suppress(Exception):
            trace.record_turn(turn_input, result)
        if not sender.json(
            {"type": "turn_committed", "turn_index": int(commit.turn_index)}
        ):
            return False
    return True


def _commit_pending_turns(
    app: Flask,
    *,
    commits: list[LiveTurnCommit],
    persistence_context: LiveTurnPersistenceContext,
    trace: LiveFollowUpTrace,
    sender: _BrowserSender,
    turn_started_at: dict[int, float],
    turn_started_lock: threading.Lock,
    attempts: int = 2,
) -> bool:
    """Persist queued turns in order and retain the first failed turn for retry."""
    bounded_attempts = max(1, min(int(attempts), 3))
    while commits:
        committed = False
        for _attempt in range(bounded_attempts):
            if _commit_turns(
                app,
                commits=[commits[0]],
                persistence_context=persistence_context,
                trace=trace,
                sender=sender,
                turn_started_at=turn_started_at,
                turn_started_lock=turn_started_lock,
                notify_persistence_failure=False,
            ):
                committed = True
                break
        if not committed:
            _send_error(sender, code="persistence_failed", retryable=True)
            return False
        commits.pop(0)
    return True


class _TurnPersistenceWorker:
    """Persist completed turns without pausing browser socket reads."""

    _SENTINEL = object()

    def __init__(
        self,
        app: Flask,
        *,
        persistence_context: LiveTurnPersistenceContext,
        trace: LiveFollowUpTrace,
        sender: _BrowserSender,
        turn_started_at: dict[int, float],
        turn_started_lock: threading.Lock,
    ) -> None:
        self._app = app
        self._persistence_context = persistence_context
        self._trace = trace
        self._sender = sender
        self._turn_started_at = turn_started_at
        self._turn_started_lock = turn_started_lock
        self._queue: queue.Queue[LiveTurnCommit | object] = queue.Queue(
            maxsize=_PERSISTENCE_QUEUE_MAX_TURNS
        )
        self._accepting = True
        self._failed = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"gemini-live-persistence-{persistence_context.session_bid[:8]}",
            daemon=True,
        )
        self._thread.start()

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    def enqueue(self, commits: list[LiveTurnCommit]) -> bool:
        if not self._accepting or self.failed:
            return False
        for commit in commits:
            try:
                self._queue.put_nowait(commit)
            except queue.Full:
                self._failed.set()
                _send_error(self._sender, code="persistence_failed", retryable=True)
                return False
        return True

    def close(self, *, drain: bool) -> bool:
        self._accepting = False
        if not drain:
            self._discard_queued_turns()
        if self._thread.is_alive():
            self._queue.put(self._SENTINEL)
            # Persistence already had to finish synchronously before this
            # worker existed. Keep that durability guarantee at shutdown,
            # while leaving the active browser receive loop non-blocking.
            self._thread.join()
        return not self.failed

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is self._SENTINEL:
                    return
                commits = [item]
                if not _commit_pending_turns(
                    self._app,
                    commits=commits,
                    persistence_context=self._persistence_context,
                    trace=self._trace,
                    sender=self._sender,
                    turn_started_at=self._turn_started_at,
                    turn_started_lock=self._turn_started_lock,
                ):
                    self._failed.set()
                    self._discard_queued_turns()
                    return
            finally:
                self._queue.task_done()

    def _discard_queued_turns(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return
            self._queue.task_done()


def _process_control_message(
    raw_message: str,
    *,
    accumulator: LiveTurnAccumulator,
) -> str:
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError:
        return "invalid"
    if not isinstance(message, dict):
        return "invalid"
    message_type = message.get("type")
    if message_type == "playback_progress":
        turn_index = message.get("turn_index")
        played_bytes = message.get("played_bytes")
        if (
            not isinstance(turn_index, int)
            or isinstance(turn_index, bool)
            or turn_index < 0
            or not isinstance(played_bytes, int)
            or isinstance(played_bytes, bool)
            or played_bytes < 0
        ):
            return "invalid"
        accumulator.record_playback_progress(turn_index, played_bytes)
        return "continue"
    if message_type == "playback_complete":
        turn_index = message.get("turn_index")
        if (
            not isinstance(turn_index, int)
            or isinstance(turn_index, bool)
            or turn_index < 0
        ):
            return "invalid"
        accumulator.mark_playback_complete(turn_index)
        return "continue"
    if message_type == "audio_stream_end":
        return "audio_stream_end"
    if message_type == "end":
        return "end"
    return "invalid"


def _abort_provider(provider: GeminiLiveProvider) -> None:
    """Cancel provider I/O without waiting on a writer-held connection lock."""
    abort = getattr(provider, "abort", None)
    if callable(abort):
        abort()
        return
    provider.close()


def _reader_loop(
    *,
    provider: GeminiLiveProvider,
    accumulator: LiveTurnAccumulator,
    sender: _BrowserSender,
    stop_event: threading.Event,
    upstream_ready: threading.Event,
    upstream_connection_lock: threading.Lock,
    failures: queue.SimpleQueue[_ReaderFailure],
    turn_started_at: dict[int, float],
    turn_started_lock: threading.Lock,
) -> None:
    try:
        while not stop_event.is_set():
            event = provider.receive()
            if event.upstream_error:
                failures.put(
                    _ReaderFailure(code="upstream_unavailable", retryable=True)
                )
                stop_event.set()
                return
            result = accumulator.process_event(event)
            now = time.monotonic()
            touched_turns = {update.turn_index for update in result.transcript_updates}
            if result.audio_turn_index is not None:
                touched_turns.add(result.audio_turn_index)
            with turn_started_lock:
                for turn_index in touched_turns:
                    turn_started_at.setdefault(turn_index, now)
            for update in result.transcript_updates:
                if not _send_transcript(sender, update):
                    stop_event.set()
                    return

            if result.interrupted_turn_index is not None and not sender.json(
                {
                    "type": "interrupted",
                    "turn_index": int(result.interrupted_turn_index),
                }
            ):
                stop_event.set()
                return

            if result.audio_chunks and result.audio_turn_index is not None:
                if not _send_state(
                    sender,
                    "speaking",
                    turn_index=result.audio_turn_index,
                ):
                    stop_event.set()
                    return
                for chunk in result.audio_chunks:
                    if not sender.binary(chunk):
                        stop_event.set()
                        return
                    accumulator.record_audio_sent(
                        result.audio_turn_index,
                        len(chunk),
                    )
                accumulator.finish_audio_event(result.audio_turn_index)

            if result.terminal_turn_index is not None and not _send_state(
                sender, "listening"
            ):
                stop_event.set()
                return

            # GoAway messages can carry the final usage/transcript fields for
            # the old socket. Reconcile the entire envelope before replacing
            # the connection or ending the browser session.
            if event.go_away:
                if not provider.can_resume_after(event):
                    failures.put(_ReaderFailure(code="upstream_ended", retryable=True))
                    stop_event.set()
                    return
                upstream_ready.clear()
                if not _send_state(sender, "reconnecting"):
                    stop_event.set()
                    return
                # Keep connection replacement atomic with browser audio sends.
                # A frame already holding the lock may finish on the old socket;
                # later frames wait and continue on the resumed connection.
                with upstream_connection_lock:
                    if stop_event.is_set():
                        return
                    provider.reconnect_with_resumption()
                    upstream_ready.set()
                if not _send_state(sender, "listening"):
                    stop_event.set()
                    return
    except (GeminiLiveProviderError, OSError):
        if not stop_event.is_set():
            failures.put(_ReaderFailure(code="upstream_unavailable", retryable=True))
            stop_event.set()
    except Exception:
        if not stop_event.is_set():
            failures.put(_ReaderFailure(code="service_unavailable", retryable=True))
            stop_event.set()


def _run_live_websocket(
    app: Flask,
    ws: object,
    *,
    binding: LiveFollowUpTicketBinding,
) -> None:
    sender = _BrowserSender(ws)
    lease: LiveFollowUpCapacityLease | None = None
    provider: GeminiLiveProvider | None = None
    reader: threading.Thread | None = None
    upstream_writer: _UpstreamWriter | None = None
    persistence_worker: _TurnPersistenceWorker | None = None
    stop_event = threading.Event()
    upstream_ready = threading.Event()
    upstream_connection_lock = threading.Lock()
    failures: queue.SimpleQueue[_ReaderFailure] = queue.SimpleQueue()
    accumulator = LiveTurnAccumulator(binding.session_bid)
    turn_started_at: dict[int, float] = {}
    turn_started_lock = threading.Lock()
    end_reason = "service_error"
    trace: LiveFollowUpTrace | None = None
    input_rate_limiter = _PcmInputRateLimiter()

    try:
        lease = acquire_live_follow_up_capacity(app, user_bid=binding.user_bid)
    except LiveFollowUpCapacityLimitError:
        _send_error(sender, code="capacity_reached", retryable=True)
        _send_state(sender, "ended")
        sender.json({"type": "session_end", "reason": "capacity_reached"})
        sender.close()
        return
    except LiveFollowUpCapacityError:
        _send_error(sender, code="service_unavailable", retryable=True)
        _send_state(sender, "ended")
        sender.json({"type": "session_end", "reason": "service_error"})
        sender.close()
        return

    try:
        follow_up_info, current_voice = _resolve_live_config(
            app,
            shifu_bid=binding.shifu_bid,
            outline_bid=binding.outline_bid,
            progress_record_bid=binding.progress_record_bid,
            preview_mode=binding.preview_mode,
        )
        _ensure_session_config_unchanged(binding, current_voice=current_voice)
        system_instruction, history = _build_conversation(
            app,
            binding=binding,
            follow_up_info=follow_up_info,
        )
        # All query results needed by the session are now immutable values.
        # Release the request's read transaction before opening a long socket.
        db.session.remove()
        api_key = str(get_config("GEMINI_API_KEY", "") or "").strip()
        provider = GeminiLiveProvider(
            api_key=api_key,
            model=binding.model,
            voice_name=binding.voice_name,
            system_instruction=system_instruction,
            history=history,
        )
        if not _send_state(sender, "connecting"):
            return
        provider.connect()
        upstream_ready.set()
        upstream_writer = _UpstreamWriter(
            provider=provider,
            upstream_ready=upstream_ready,
            upstream_connection_lock=upstream_connection_lock,
            session_stop=stop_event,
            failures=failures,
        )
        if not _send_state(sender, "listening"):
            return

        trace = LiveFollowUpTrace(
            app,
            session_bid=binding.session_bid,
            user_bid=binding.user_bid,
            shifu_bid=binding.shifu_bid,
            outline_item_bid=binding.outline_bid,
        )
        persistence_context = LiveTurnPersistenceContext(
            session_bid=binding.session_bid,
            user_bid=binding.user_bid,
            shifu_bid=binding.shifu_bid,
            outline_item_bid=binding.outline_bid,
            progress_record_bid=binding.progress_record_bid,
            anchor_element_bid=binding.anchor_element_bid,
            preview_mode=binding.preview_mode,
            learning_mode=binding.learning_mode,
            request_id=get_request_id(),
            trace_id=trace.trace_id,
        )
        persistence_worker = _TurnPersistenceWorker(
            app,
            persistence_context=persistence_context,
            trace=trace,
            sender=sender,
            turn_started_at=turn_started_at,
            turn_started_lock=turn_started_lock,
        )
        reader = threading.Thread(
            target=_reader_loop,
            kwargs={
                "provider": provider,
                "accumulator": accumulator,
                "sender": sender,
                "stop_event": stop_event,
                "upstream_ready": upstream_ready,
                "upstream_connection_lock": upstream_connection_lock,
                "failures": failures,
                "turn_started_at": turn_started_at,
                "turn_started_lock": turn_started_lock,
            },
            name=f"gemini-live-reader-{binding.session_bid[:8]}",
            daemon=True,
        )
        reader.start()

        started_at = time.monotonic()
        deadline = started_at + LIVE_FOLLOW_UP_SESSION_SECONDS
        next_lease_renewal = started_at + LIVE_FOLLOW_UP_LEASE_RENEW_INTERVAL_SECONDS
        while True:
            now = time.monotonic()
            if now >= deadline:
                end_reason = "timeout"
                break
            if sender.failed:
                end_reason = "client_disconnected"
                break
            if persistence_worker.failed:
                end_reason = "service_error"
                break
            if stop_event.is_set():
                failure = (
                    failures.get_nowait()
                    if not failures.empty()
                    else _ReaderFailure(code="connection_lost", retryable=True)
                )
                _send_error(
                    sender,
                    code=failure.code,
                    retryable=failure.retryable,
                )
                end_reason = "service_error"
                break
            if now >= next_lease_renewal:
                try:
                    renew_live_follow_up_capacity(app, lease=lease)
                except LiveFollowUpCapacityLeaseLostError:
                    _send_error(sender, code="lease_lost", retryable=True)
                    end_reason = "lease_lost"
                    break
                except LiveFollowUpCapacityError:
                    _send_error(sender, code="service_unavailable", retryable=True)
                    end_reason = "service_error"
                    break
                next_lease_renewal = now + LIVE_FOLLOW_UP_LEASE_RENEW_INTERVAL_SECONDS

            if not persistence_worker.enqueue(accumulator.pop_ready(now=now)):
                end_reason = "service_error"
                break

            try:
                incoming = ws.receive(timeout=_BROWSER_RECEIVE_TIMEOUT_SECONDS)
            except Exception:
                end_reason = "client_disconnected"
                break
            if incoming is None:
                if not bool(getattr(ws, "connected", True)):
                    end_reason = "client_disconnected"
                    break
                continue
            if isinstance(incoming, bytes):
                if (
                    not incoming
                    or len(incoming) > GEMINI_LIVE_MAX_INPUT_FRAME_BYTES
                    or len(incoming) % 2 != 0
                ):
                    _send_error(sender, code="invalid_audio", retryable=False)
                    end_reason = "invalid_request"
                    break
                if not input_rate_limiter.allow(len(incoming)):
                    _send_error(sender, code="audio_rate_exceeded", retryable=False)
                    end_reason = "invalid_request"
                    break
                if not upstream_writer.enqueue_audio(incoming):
                    code = (
                        "upstream_unavailable"
                        if upstream_writer.failed
                        else "upstream_backpressure"
                    )
                    _send_error(sender, code=code, retryable=True)
                    end_reason = "service_error"
                    break
                continue
            if not isinstance(incoming, str):
                _send_error(sender, code="invalid_control", retryable=False)
                end_reason = "invalid_request"
                break
            control_result = _process_control_message(
                incoming,
                accumulator=accumulator,
            )
            if control_result == "end":
                end_reason = "ended_by_user"
                break
            if control_result == "audio_stream_end":
                if not upstream_writer.enqueue_audio_stream_end():
                    code = (
                        "upstream_unavailable"
                        if upstream_writer.failed
                        else "upstream_backpressure"
                    )
                    _send_error(sender, code=code, retryable=True)
                    end_reason = "service_error"
                    break
                continue
            if control_result == "invalid":
                _send_error(sender, code="invalid_control", retryable=False)
                end_reason = "invalid_request"
                break

        stop_event.set()
        upstream_writer.close(drain=end_reason == "ended_by_user")
        _abort_provider(provider)
        upstream_writer.wait_closed()
        if reader is not None:
            reader.join(timeout=2)
        final_commit_succeeded = persistence_worker.enqueue(
            accumulator.finish_session()
        ) and persistence_worker.close(drain=True)
        persistence_worker = None
        if not final_commit_succeeded:
            end_reason = "service_error"
        if end_reason != "client_disconnected":
            _send_state(sender, "ended")
            sender.json({"type": "session_end", "reason": end_reason})
    except LiveFollowUpModelUnavailableError:
        _send_error(sender, code="model_unavailable", retryable=True)
        _send_state(sender, "ended")
        sender.json({"type": "session_end", "reason": "model_unavailable"})
    except (GeminiLiveProviderError, LiveFollowUpSecurityError):
        _send_error(sender, code="upstream_unavailable", retryable=True)
        _send_state(sender, "ended")
        sender.json({"type": "session_end", "reason": "service_error"})
    except Exception:
        # Upstream and persistence exceptions may carry API URLs, provider
        # details, or transcript values. Keep operational logging bounded.
        app.logger.error(  # noqa: TRY400 - never log the caught provider error
            "Gemini Live session failed session=%s",
            binding.session_bid,
        )
        _send_error(sender, code="service_unavailable", retryable=True)
        _send_state(sender, "ended")
        sender.json({"type": "session_end", "reason": "service_error"})
    finally:
        stop_event.set()
        if upstream_writer is not None:
            upstream_writer.close(drain=False)
        if persistence_worker is not None:
            persistence_worker.close(drain=False)
        if provider is not None:
            _abort_provider(provider)
        if upstream_writer is not None:
            upstream_writer.wait_closed()
        if reader is not None and reader.is_alive():
            reader.join(timeout=2)
        if trace is not None:
            with contextlib.suppress(Exception):
                trace.close(end_reason=end_reason)
        if lease is not None:
            with contextlib.suppress(Exception):
                release_live_follow_up_capacity(app, lease=lease)
        with contextlib.suppress(Exception):
            db.session.remove()
        sender.close()


def register_live_follow_up_routes(
    app: Flask,
    path_prefix: str = "/api/learn",
) -> None:
    """Register the authenticated POST ticket and WebSocket endpoints."""
    app.config.setdefault("SOCK_SERVER_OPTIONS", {})
    app.config["SOCK_SERVER_OPTIONS"].setdefault("ping_interval", 25)
    app.config["SOCK_SERVER_OPTIONS"].setdefault(
        "max_message_size", GEMINI_LIVE_MAX_INPUT_FRAME_BYTES
    )
    sock = Sock(app)

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
        if not str(get_config("GEMINI_API_KEY", "") or "").strip():
            raise_param_error("live_follow_up")
        session_bid = generate_id(app)
        ws_path = f"{path_prefix}/live-follow-up/ws/{session_bid}"
        language = str(get_current_language() or "en-US").strip() or "en-US"
        try:
            issued = issue_live_follow_up_ticket(
                app,
                binding=LiveFollowUpTicketBinding(
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
                ),
            )
        except LiveFollowUpSecurityError:
            raise_param_error("live_follow_up")
        return _session_response(
            app,
            session_bid=session_bid,
            ws_path=ws_path,
            ticket=issued,
        )

    @sock.route(path_prefix + "/live-follow-up/ws/<session_bid>")
    @bypass_token_validation
    def live_follow_up_ws(ws: object, session_bid: str) -> None:
        sender = _BrowserSender(ws)
        if not is_gemini_live_enabled():
            _send_error(sender, code="feature_disabled", retryable=True)
            sender.close()
            return
        try:
            binding = consume_live_follow_up_ticket(
                app,
                session_bid=session_bid,
                token=request.cookies.get(LIVE_FOLLOW_UP_TICKET_COOKIE_NAME),
                origin=request.headers.get("Origin"),
            )
        except LiveFollowUpSecurityError:
            _send_error(sender, code="auth_failed", retryable=False)
            sender.close()
            return
        # Browser WebSocket APIs cannot attach the ordinary Token header. The
        # authenticated POST minted this exact-path, one-time, Origin-bound
        # HttpOnly credential, so the consumed binding is the WS identity.
        sender.close(drain=False)
        _run_live_websocket(app, ws, binding=binding)
