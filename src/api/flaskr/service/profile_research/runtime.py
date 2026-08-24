"""Standalone MarkdownFlow runtime for learner-profile research."""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Callable, Generator, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from flask import Flask, Response, stream_with_context
from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
    get_request_trace_id,
)
from flaskr.api.llm import chat_llm
from flaskr.common.cache_provider import CacheLock, CacheProvider, redis_cache
from flaskr.common.i18n_utils import resolve_markdownflow_output_language
from flaskr.dao import (
    invalidate_session,
    is_protocol_interrupt_error,
    release_session_classified,
)
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.util import generate_id
from flaskr.util.prompt_loader import load_prompt_template
from markdown_flow import (
    USER_ANSWER_CONTEXT_KEY,
    BlockType,
    InteractionParser,
    LLMProvider,
    LLMResult,
    MarkdownFlow,
    ProcessMode,
)

PROFILE_ONBOARDING_PURPOSE = "profile-onboarding"
PROFILE_ONBOARDING_PREVIEW_PURPOSE = "profile-onboarding-preview"
_ALLOWED_PURPOSES = frozenset(
    {PROFILE_ONBOARDING_PURPOSE, PROFILE_ONBOARDING_PREVIEW_PURPOSE}
)

PROFILE_RESEARCH_SESSION_TTL_SECONDS = 30 * 60
# All supported API entrypoints configure a 300-second Gunicorn worker timeout.
# Leave one minute of headroom without making a hard-killed run keep its session
# busy for the rest of the conversation lifetime.
PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS = 6 * 60
_SESSION_SCHEMA_VERSION = 1
_MAX_DOCUMENT_CODEPOINTS = 100_000
_MAX_BLOCK_COUNT = 100
_MAX_INPUT_KEY_CODEPOINTS = 256
_MAX_INPUT_KEY_COUNT = 100
_MAX_INPUT_VALUES_PER_KEY = 100
_MAX_INPUT_VALUE_COUNT = 100
_MAX_INPUT_VALUE_CODEPOINTS = 4_000
_MAX_INPUT_TOTAL_CODEPOINTS = 10_000
_REPLAY_DELTA_MARKER = "_profile_replay_delta"


class ProfileResearchError(ValueError):
    """Base error with a response-safe code."""

    public_code = "transient_markdownflow_error"


class ProfileResearchValidationError(ProfileResearchError):
    """Signal invalid documents, runtime configuration, or learner input."""

    public_code = "transient_markdownflow_invalid"


class ProfileResearchSessionNotFoundError(ProfileResearchError):
    """Signal a missing, expired, or unauthorized research session."""

    public_code = "transient_markdownflow_session_not_found"


class ProfileResearchSessionBusyError(ProfileResearchError):
    """Signal concurrent work on the same owner-scoped research session."""

    public_code = "transient_markdownflow_session_busy"


ProfileResearchSessionNotFound = ProfileResearchSessionNotFoundError
ProfileResearchSessionBusy = ProfileResearchSessionBusyError


def _acquire_profile_research_lock(lock: CacheLock) -> None:
    if not bool(lock.acquire(blocking=False)):
        msg = "session is busy"
        raise ProfileResearchSessionBusy(msg)


@contextlib.contextmanager
def _hold_profile_research_lock(
    lock: CacheLock | None,
) -> Generator[None, None, None]:
    if lock is None:
        yield
        return
    if not bool(lock.acquire(blocking=False)):
        msg = "session is busy"
        raise ProfileResearchSessionBusy(msg)
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            lock.release()


def _normalize_variables(raw: object) -> dict[str, str | list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        msg = "invalid session variables"
        raise ProfileResearchSessionNotFound(msg)
    variables: dict[str, str | list[str]] = {}
    for raw_key, raw_value in raw.items():
        key = str(raw_key)
        if isinstance(raw_value, list):
            variables[key] = [str(value) for value in raw_value]
        elif raw_value is not None:
            variables[key] = str(raw_value)
    return variables


def _normalize_context(raw: object) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        msg = "invalid session context"
        raise ProfileResearchSessionNotFound(msg)
    context: list[dict[str, str]] = []
    for raw_message in raw:
        if not isinstance(raw_message, Mapping):
            continue
        role = str(raw_message.get("role") or "").strip()
        content = str(raw_message.get("content") or "")
        if not role or not content.strip():
            continue
        message = {"role": role, "content": content}
        if USER_ANSWER_CONTEXT_KEY in raw_message:
            message[USER_ANSWER_CONTEXT_KEY] = str(
                raw_message.get(USER_ANSWER_CONTEXT_KEY) or ""
            )
        context.append(message)
    return context


def _normalize_user_input(
    raw: Mapping[str, Any] | None,
) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        msg = "user_input must be an object"
        raise ProfileResearchValidationError(msg)
    if len(raw) > _MAX_INPUT_KEY_COUNT:
        msg = "user_input has too many keys"
        raise ProfileResearchValidationError(msg)
    normalized: dict[str, list[str]] = {}
    total_value_count = 0
    total_length = 0
    for raw_key, raw_values in raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            msg = "user_input key is invalid"
            raise ProfileResearchValidationError(msg)
        if len(raw_key) > _MAX_INPUT_KEY_CODEPOINTS:
            msg = "user_input key is too long"
            raise ProfileResearchValidationError(msg)
        if (
            not isinstance(raw_values, list)
            or not raw_values
            or len(raw_values) > _MAX_INPUT_VALUES_PER_KEY
        ):
            msg = "user_input values are invalid"
            raise ProfileResearchValidationError(msg)
        total_value_count += len(raw_values)
        if total_value_count > _MAX_INPUT_VALUE_COUNT:
            msg = "user_input has too many values"
            raise ProfileResearchValidationError(msg)
        values: list[str] = []
        for raw_value in raw_values:
            if not isinstance(raw_value, str):
                msg = "user_input values must be strings"
                raise ProfileResearchValidationError(msg)
            if not raw_value.strip():
                msg = "user_input values must not be blank"
                raise ProfileResearchValidationError(msg)
            if len(raw_value) > _MAX_INPUT_VALUE_CODEPOINTS:
                msg = "user_input value is too long"
                raise ProfileResearchValidationError(msg)
            total_length += len(raw_value)
            values.append(raw_value)
        normalized[raw_key] = values
    if total_length > _MAX_INPUT_TOTAL_CODEPOINTS:
        msg = "user_input is too long"
        raise ProfileResearchValidationError(msg)
    return normalized


@dataclass
class _ProfileResearchSession:
    session_id: str
    user_bid: str
    purpose: str
    document: str
    model: str
    temperature: float
    output_language: str
    config_revision: int
    block_index: int
    block_count: int
    profile_draft_block_index: int
    variables: dict[str, str | list[str]] = field(default_factory=dict)
    context: list[dict[str, str]] = field(default_factory=list)
    awaiting_input: bool = False
    done: bool = False
    profile_draft: str = ""
    last_request_id: str = ""
    last_expected_block_index: int | None = None
    last_user_input: dict[str, list[str]] = field(default_factory=dict)
    last_events: list[dict[str, Any]] = field(default_factory=list)

    def to_cache_payload(self) -> dict[str, Any]:
        return {
            "schema_version": _SESSION_SCHEMA_VERSION,
            "session_id": self.session_id,
            "user_bid": self.user_bid,
            "purpose": self.purpose,
            "document": self.document,
            "model": self.model,
            "temperature": self.temperature,
            "output_language": self.output_language,
            "config_revision": self.config_revision,
            "block_index": self.block_index,
            "block_count": self.block_count,
            "profile_draft_block_index": self.profile_draft_block_index,
            "variables": self.variables,
            "context": self.context,
            "awaiting_input": self.awaiting_input,
            "done": self.done,
            "profile_draft": self.profile_draft,
            "last_request_id": self.last_request_id,
            "last_expected_block_index": self.last_expected_block_index,
            "last_user_input": self.last_user_input,
            "last_events": self.last_events,
        }

    @classmethod
    def from_cache_payload(cls, payload: Mapping[str, Any]) -> _ProfileResearchSession:
        if int(payload.get("schema_version") or 0) != _SESSION_SCHEMA_VERSION:
            msg = "session schema mismatch"
            raise ProfileResearchSessionNotFound(msg)
        try:
            raw_events = payload.get("last_events")
            if raw_events is None:
                events: list[dict[str, Any]] = []
            elif isinstance(raw_events, list):
                events = [
                    dict(event) for event in raw_events if isinstance(event, Mapping)
                ]
            else:
                msg = "invalid replay events"
                raise ProfileResearchSessionNotFound(msg)
            last_expected_block_index = payload.get("last_expected_block_index")
            return cls(
                session_id=str(payload["session_id"]),
                user_bid=str(payload["user_bid"]),
                purpose=str(payload["purpose"]),
                document=str(payload["document"]),
                model=str(payload["model"]),
                temperature=float(payload["temperature"]),
                output_language=str(payload.get("output_language") or ""),
                config_revision=int(payload.get("config_revision") or 0),
                block_index=int(payload["block_index"]),
                block_count=int(payload["block_count"]),
                profile_draft_block_index=int(payload["profile_draft_block_index"]),
                variables=_normalize_variables(payload.get("variables")),
                context=_normalize_context(payload.get("context")),
                awaiting_input=bool(payload.get("awaiting_input", False)),
                done=bool(payload.get("done", False)),
                profile_draft=str(payload.get("profile_draft") or ""),
                last_request_id=str(payload.get("last_request_id") or ""),
                last_expected_block_index=(
                    int(last_expected_block_index)
                    if last_expected_block_index is not None
                    else None
                ),
                last_user_input=_normalize_user_input(
                    payload.get("last_user_input") or None
                ),
                last_events=events,
            )
        except ProfileResearchError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            msg = "invalid session payload"
            raise ProfileResearchSessionNotFound(msg) from exc

    def to_view(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "purpose": self.purpose,
            "block_index": self.block_index,
            "block_count": self.block_count,
            "profile_draft_block_index": self.profile_draft_block_index,
            "awaiting_input": self.awaiting_input,
            "done": self.done,
            "expires_in": PROFILE_RESEARCH_SESSION_TTL_SECONDS,
            "config_revision": self.config_revision,
        }


class _ProfileResearchSessionStore:
    def __init__(
        self,
        app: Flask,
        *,
        cache: CacheProvider = redis_cache,
        ttl_seconds: int = PROFILE_RESEARCH_SESSION_TTL_SECONDS,
    ) -> None:
        prefix = str(app.config.get("REDIS_KEY_PREFIX", "") or "")
        self._key_prefix = f"{prefix}profile_research:"
        self._cache = cache
        self._ttl_seconds = int(ttl_seconds)

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}{session_id}"

    def _active_key(self, user_bid: str, purpose: str) -> str:
        owner = str(user_bid or "").strip().encode("utf-8")
        owner_digest = hashlib.sha256(owner).hexdigest()
        return f"{self._key_prefix}active:{str(purpose).strip()}:{owner_digest}"

    def save(self, session: _ProfileResearchSession) -> None:
        self._cache.setex(
            self._key(session.session_id),
            self._ttl_seconds,
            json.dumps(session.to_cache_payload(), ensure_ascii=False),
        )
        self.refresh_active(session)

    def load(self, session_id: str) -> _ProfileResearchSession:
        raw = self._cache.get(self._key(session_id))
        if raw is None:
            msg = "session not found"
            raise ProfileResearchSessionNotFound(msg)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            payload = json.loads(str(raw))
        except (TypeError, ValueError) as exc:
            msg = "invalid session payload"
            raise ProfileResearchSessionNotFound(msg) from exc
        if not isinstance(payload, Mapping):
            msg = "invalid session payload"
            raise ProfileResearchSessionNotFound(msg)
        return _ProfileResearchSession.from_cache_payload(payload)

    def delete(self, session_id: str) -> None:
        self._cache.delete(self._key(session_id))

    def active_session_id(self, *, user_bid: str, purpose: str) -> str | None:
        raw = self._cache.get(self._active_key(user_bid, purpose))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        normalized = str(raw).strip()
        return normalized or None

    def refresh_active(self, session: _ProfileResearchSession) -> None:
        self._cache.setex(
            self._active_key(session.user_bid, session.purpose),
            self._ttl_seconds,
            session.session_id,
        )

    def clear_active(self, session: _ProfileResearchSession) -> None:
        active_session_id = self.active_session_id(
            user_bid=session.user_bid,
            purpose=session.purpose,
        )
        if active_session_id == session.session_id:
            self._cache.delete(self._active_key(session.user_bid, session.purpose))

    def lock(self, session_id: str) -> CacheLock:
        return self._cache.lock(
            f"{self._key(session_id)}:lock",
            timeout=PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS,
            blocking_timeout=0,
        )

    def owner_lock(self, *, user_bid: str, purpose: str) -> CacheLock:
        return self._cache.lock(
            f"{self._active_key(user_bid, purpose)}:lock",
            timeout=PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS,
            blocking_timeout=0,
        )


class _ProfileResearchLLMProvider(LLMProvider):
    """Thin adapter that keeps MarkdownFlow on the shared LLM route."""

    def __init__(
        self, app: Flask, session: _ProfileResearchSession, span: object
    ) -> None:
        self._app = app
        self._session = session
        self._span = span
        self.output_chunks: list[str] = []

    def _invoke(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None,
        temperature: float | None,
        stream: bool,
    ) -> Generator[str, None, None]:
        if not messages:
            msg = "No messages provided"
            raise ValueError(msg)
        actual_model = model or self._session.model
        actual_temperature = (
            temperature if temperature is not None else self._session.temperature
        )
        responses = chat_llm(
            self._app,
            self._session.user_bid,
            self._span,
            model=actual_model,
            messages=messages,
            stream=stream,
            generation_name="profile_research_markdownflow",
            temperature=actual_temperature,
            usage_context=UsageContext(
                user_bid=self._session.user_bid,
                usage_scene=BILL_USAGE_SCENE_DEBUG,
                billable=0,
            ),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        )
        for response in responses:
            if response.result:
                self.output_chunks.append(response.result)
                yield response.result

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        return "".join(
            self._invoke(
                messages,
                model=model,
                temperature=temperature,
                stream=False,
            )
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Generator[str, None, None]:
        yield from self._invoke(
            messages,
            model=model,
            temperature=temperature,
            stream=True,
        )


@dataclass
class _StepOutcome:
    content: str = ""
    prompt: str = ""
    variable_updates: dict[str, str | list[str]] = field(default_factory=dict)
    input_accepted: bool = False
    answer_values: list[str] = field(default_factory=list)


def _iter_results(
    result: LLMResult | Iterable[LLMResult],
) -> Iterable[LLMResult]:
    if isinstance(result, LLMResult):
        return (result,)
    return result


def _event(
    event_type: str,
    content: object,
    *,
    generated_block_bid: str | None = None,
    run_session_bid: str | None = None,
    is_terminal: bool | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": event_type,
        "event_type": event_type,
        "content": content,
    }
    if generated_block_bid is not None:
        event["generated_block_bid"] = generated_block_bid
    if run_session_bid is not None:
        event["run_session_bid"] = run_session_bid
    if is_terminal is not None:
        event["is_terminal"] = is_terminal
    return event


def _replay_stream_key(event: Mapping[str, Any]) -> tuple[str, str, str] | None:
    content = event.get("content")
    event_type = str(event.get("event_type") or "")
    if (
        not isinstance(content, str)
        or event.get("is_terminal")
        or event_type not in {"content", "interaction"}
    ):
        return None
    return (
        event_type,
        str(event.get("generated_block_bid") or ""),
        str(event.get("run_session_bid") or ""),
    )


def _compact_replay_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Store cumulative stream events as deltas without changing replay output."""
    previous_content: dict[tuple[str, str, str], str] = {}
    compacted: list[dict[str, Any]] = []
    for event in events:
        stored_event = dict(event)
        stream_key = _replay_stream_key(stored_event)
        if stream_key is not None:
            content = str(stored_event["content"])
            previous = previous_content.get(stream_key, "")
            if content.startswith(previous):
                stored_event["content"] = content[len(previous) :]
                stored_event[_REPLAY_DELTA_MARKER] = True
            previous_content[stream_key] = content
        compacted.append(stored_event)
    return compacted


def _expand_replay_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cumulative_content: dict[tuple[str, str, str], str] = {}
    expanded: list[dict[str, Any]] = []
    for event in events:
        replay_event = dict(event)
        is_delta = bool(replay_event.pop(_REPLAY_DELTA_MARKER, False))
        stream_key = _replay_stream_key(replay_event)
        if stream_key is not None:
            content = str(replay_event["content"])
            if is_delta:
                content = cumulative_content.get(stream_key, "") + content
                replay_event["content"] = content
            cumulative_content[stream_key] = content
        expanded.append(replay_event)
    return expanded


def _append_profile_summary(document: str) -> str:
    summary_prompt = load_prompt_template("profile_research_summary").strip()
    return f"{document.rstrip()}\n\n---\n\n{summary_prompt}"


def validate_profile_research_document(document: str) -> dict[str, Any]:
    """Validate the configured document with MarkdownFlow's own parser."""
    if not isinstance(document, str) or not document.strip():
        msg = "document is empty"
        raise ProfileResearchValidationError(msg)
    if len(document) > _MAX_DOCUMENT_CODEPOINTS:
        msg = "document is too long"
        raise ProfileResearchValidationError(msg)
    flow = MarkdownFlow(document=document)
    blocks = flow.get_all_blocks()
    if not blocks:
        msg = "document has no blocks"
        raise ProfileResearchValidationError(msg)
    if len(blocks) >= _MAX_BLOCK_COUNT:
        msg = "document has too many blocks"
        raise ProfileResearchValidationError(msg)
    interaction_count = sum(
        block.block_type == BlockType.INTERACTION for block in blocks
    )
    if interaction_count == 0:
        msg = "document must contain an interaction"
        raise ProfileResearchValidationError(msg)
    interaction_parser = InteractionParser()
    for block in blocks:
        if block.block_type != BlockType.INTERACTION:
            continue
        parsed_interaction = interaction_parser.parse(block.content)
        variable_name = parsed_interaction.get("variable")
        if (
            isinstance(variable_name, str)
            and len(variable_name) > _MAX_INPUT_KEY_CODEPOINTS
        ):
            msg = "interaction variable name is too long"
            raise ProfileResearchValidationError(msg)
        question = parsed_interaction.get("question")
        has_question = isinstance(question, str) and bool(question.strip())
        buttons = parsed_interaction.get("buttons")
        button_values: list[str] = []
        if isinstance(buttons, list):
            if len(buttons) > _MAX_INPUT_VALUE_COUNT:
                msg = "interaction options exceed runtime input limits"
                raise ProfileResearchValidationError(msg)
            for button in buttons:
                display = button.get("display") if isinstance(button, dict) else None
                value = button.get("value") if isinstance(button, dict) else None
                if (
                    not isinstance(display, str)
                    or not display.strip()
                    or not isinstance(value, str)
                    or not value.strip()
                ):
                    msg = "interaction has no answerable input"
                    raise ProfileResearchValidationError(msg)
                if len(value) > _MAX_INPUT_VALUE_CODEPOINTS:
                    msg = "interaction options exceed runtime input limits"
                    raise ProfileResearchValidationError(msg)
                button_values.append(value)
            if (
                parsed_interaction.get("is_multi_select")
                and sum(len(value) for value in button_values)
                > _MAX_INPUT_TOTAL_CODEPOINTS
            ):
                msg = "interaction options exceed runtime input limits"
                raise ProfileResearchValidationError(msg)
        has_usable_button = bool(button_values)
        if not has_question and not has_usable_button:
            msg = "interaction has no answerable input"
            raise ProfileResearchValidationError(msg)
    return {
        "block_count": len(blocks),
        "interaction_block_count": interaction_count,
        "content_block_count": len(blocks) - interaction_count,
        "variables": list(flow.extract_variables()),
    }


class ProfileResearchRuntime:
    """Run owner-scoped guided profile collection on shared Redis state."""

    def __init__(
        self,
        app: Flask,
        *,
        store: _ProfileResearchSessionStore | None = None,
        provider_factory: Callable[
            [Flask, _ProfileResearchSession, object], LLMProvider
        ] = _ProfileResearchLLMProvider,
    ) -> None:
        """Initialize the runtime with shared storage and provider adapters."""
        self.app = app
        self.store = store or _ProfileResearchSessionStore(app)
        self._provider_factory = provider_factory

    def start_session(
        self,
        *,
        user_bid: str,
        document: str,
        purpose: str,
        config_revision: int,
        output_language: str | None,
    ) -> dict[str, Any]:
        """Validate the document and create one owner-purpose session."""
        normalized_user_bid = str(user_bid or "").strip()
        normalized_purpose = str(purpose or "").strip()
        if not normalized_user_bid:
            msg = "user_bid is required"
            raise ProfileResearchValidationError(msg)
        if normalized_purpose not in _ALLOWED_PURPOSES:
            msg = "purpose is invalid"
            raise ProfileResearchValidationError(msg)
        validate_profile_research_document(document)

        normalized_output_language = str(output_language or "").strip()
        snapshotted_document = _append_profile_summary(document)
        flow = MarkdownFlow(snapshotted_document)
        blocks = flow.get_all_blocks()
        if not blocks or blocks[-1].block_type != BlockType.CONTENT:
            msg = "profile summary block is invalid"
            raise ProfileResearchValidationError(msg)
        if len(blocks) > _MAX_BLOCK_COUNT:
            msg = "document has too many blocks"
            raise ProfileResearchValidationError(msg)

        model = str(self.app.config.get("DEFAULT_LLM_MODEL", "") or "").strip()
        if not model:
            msg = "LLM model is not configured"
            raise ProfileResearchValidationError(msg)
        try:
            temperature = float(self.app.config.get("DEFAULT_LLM_TEMPERATURE", 0.3))
            revision = max(int(config_revision or 0), 0)
        except (TypeError, ValueError) as exc:
            msg = "runtime config is invalid"
            raise ProfileResearchValidationError(msg) from exc
        if temperature < 0 or temperature > 2:
            msg = "LLM temperature is invalid"
            raise ProfileResearchValidationError(msg)

        session = _ProfileResearchSession(
            session_id=generate_id(self.app),
            user_bid=normalized_user_bid,
            purpose=normalized_purpose,
            document=snapshotted_document,
            model=model,
            temperature=temperature,
            output_language=normalized_output_language,
            config_revision=revision,
            block_index=0,
            block_count=len(blocks),
            profile_draft_block_index=len(blocks) - 1,
        )
        owner_lock = self.store.owner_lock(
            user_bid=session.user_bid,
            purpose=session.purpose,
        )
        with _hold_profile_research_lock(owner_lock):
            previous_session_id = self.store.active_session_id(
                user_bid=session.user_bid,
                purpose=session.purpose,
            )
            previous_lock = (
                self.store.lock(previous_session_id) if previous_session_id else None
            )
            with _hold_profile_research_lock(previous_lock):
                previous_session = None
                if previous_session_id:
                    with contextlib.suppress(ProfileResearchSessionNotFound):
                        previous_session = self.store.load(previous_session_id)
                self.store.save(session)
                if (
                    previous_session
                    and previous_session.session_id != session.session_id
                    and (previous_session.user_bid, previous_session.purpose)
                    == (session.user_bid, session.purpose)
                ):
                    self.store.delete(previous_session.session_id)
        return session.to_view()

    def _resolve_existing_session_purpose(
        self,
        *,
        user_bid: str,
        session_id: str,
        expected_purpose: str | None,
    ) -> str:
        normalized_purpose = str(expected_purpose or "").strip()
        if not normalized_purpose:
            normalized_purpose = self._load_authorized_session(
                user_bid=user_bid,
                session_id=session_id,
                expected_purpose=None,
            ).purpose
        if normalized_purpose not in _ALLOWED_PURPOSES:
            msg = "session not found"
            raise ProfileResearchSessionNotFound(msg)
        return normalized_purpose

    def _load_authorized_session(
        self,
        *,
        user_bid: str,
        session_id: str,
        expected_purpose: str | None,
    ) -> _ProfileResearchSession:
        session = self.store.load(str(session_id or "").strip())
        if session.user_bid != str(user_bid or "").strip():
            msg = "session not found"
            raise ProfileResearchSessionNotFound(msg)
        if (
            expected_purpose is not None
            and session.purpose != str(expected_purpose).strip()
        ):
            msg = "session not found"
            raise ProfileResearchSessionNotFound(msg)
        return session

    def delete_session(
        self,
        *,
        user_bid: str,
        session_id: str,
        expected_purpose: str | None,
    ) -> None:
        """Delete an authorized session and its matching active pointer."""
        normalized_session_id = str(session_id or "").strip()
        normalized_user_bid = str(user_bid or "").strip()
        normalized_purpose = self._resolve_existing_session_purpose(
            user_bid=normalized_user_bid,
            session_id=normalized_session_id,
            expected_purpose=expected_purpose,
        )
        owner_lock = self.store.owner_lock(
            user_bid=normalized_user_bid,
            purpose=normalized_purpose,
        )
        with _hold_profile_research_lock(owner_lock):
            session_lock = self.store.lock(normalized_session_id)
            with _hold_profile_research_lock(session_lock):
                session = self._load_authorized_session(
                    user_bid=normalized_user_bid,
                    session_id=normalized_session_id,
                    expected_purpose=normalized_purpose,
                )
                self.store.delete(session.session_id)
                self.store.clear_active(session)

    def delete_active_session(self, *, user_bid: str, purpose: str) -> None:
        """Delete the current owner-purpose session when one exists."""
        normalized_user_bid = str(user_bid or "").strip()
        normalized_purpose = str(purpose or "").strip()
        if not normalized_user_bid or normalized_purpose not in _ALLOWED_PURPOSES:
            msg = "session not found"
            raise ProfileResearchSessionNotFound(msg)
        owner_lock = self.store.owner_lock(
            user_bid=normalized_user_bid,
            purpose=normalized_purpose,
        )
        with _hold_profile_research_lock(owner_lock):
            session_id = self.store.active_session_id(
                user_bid=normalized_user_bid,
                purpose=normalized_purpose,
            )
            if session_id is None:
                return
            session_lock = self.store.lock(session_id)
            with _hold_profile_research_lock(session_lock):
                session = self._load_authorized_session(
                    user_bid=normalized_user_bid,
                    session_id=session_id,
                    expected_purpose=normalized_purpose,
                )
                self.store.delete(session.session_id)
                self.store.clear_active(session)

    def _build_flow(
        self,
        session: _ProfileResearchSession,
        provider: LLMProvider,
    ) -> MarkdownFlow:
        flow = MarkdownFlow(
            document=session.document,
            llm_provider=provider,
        )
        flow.set_model(session.model)
        flow.set_temperature(session.temperature)
        if session.output_language:
            flow.set_output_language(
                resolve_markdownflow_output_language(session.output_language)
            )
        return flow

    def _summary(
        self,
        session: _ProfileResearchSession,
        *,
        processed_block_index: int,
        advanced: bool,
    ) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "block_index": processed_block_index,
            "next_block_index": session.block_index,
            "block_count": session.block_count,
            "profile_draft_block_index": session.profile_draft_block_index,
            "advanced": advanced,
            "awaiting_input": session.awaiting_input,
            "done": session.done,
            "profile_draft": session.profile_draft if session.done else None,
            "config_revision": session.config_revision,
        }

    @staticmethod
    def _remember_request(
        session: _ProfileResearchSession,
        *,
        request_id: str | None,
        expected_block_index: int | None,
        user_input: dict[str, list[str]],
        events: list[dict[str, Any]],
    ) -> None:
        session.last_request_id = request_id or ""
        session.last_expected_block_index = expected_block_index
        session.last_user_input = user_input if request_id else {}
        session.last_events = _compact_replay_events(events) if request_id else []

    @staticmethod
    def _replay_or_validate_request(
        session: _ProfileResearchSession,
        *,
        request_id: str | None,
        expected_block_index: int | None,
        user_input: dict[str, list[str]],
    ) -> list[dict[str, Any]] | None:
        if request_id is None and expected_block_index is None:
            return None
        if request_id is None or expected_block_index is None:
            msg = "expected_block_index and request_id must be provided together"
            raise ProfileResearchValidationError(msg)
        normalized_request_id = str(request_id).strip()
        if not normalized_request_id or len(normalized_request_id) > 128:
            msg = "request_id is invalid"
            raise ProfileResearchValidationError(msg)
        if normalized_request_id == session.last_request_id:
            if (
                expected_block_index == session.last_expected_block_index
                and user_input == session.last_user_input
                and session.last_events
            ):
                return _expand_replay_events(session.last_events)
            msg = "request_id was reused with different run input"
            raise ProfileResearchValidationError(msg)
        if expected_block_index != session.block_index:
            msg = "expected_block_index does not match the session cursor"
            raise ProfileResearchValidationError(msg)
        return None

    def _update_context(
        self,
        session: _ProfileResearchSession,
        *,
        current_block: object,
        user_input: dict[str, list[str]],
        outcome: _StepOutcome,
    ) -> None:
        if current_block.block_type == BlockType.INTERACTION:
            answer_values = outcome.answer_values or [
                value for values in user_input.values() for value in values
            ]
            interaction_context = {
                "role": "assistant",
                "content": str(current_block.content or ""),
            }
            if not outcome.variable_updates:
                interaction_context[USER_ANSWER_CONTEXT_KEY] = ", ".join(answer_values)
            session.context.append(interaction_context)
            return
        if current_block.block_type == BlockType.PRESERVED_CONTENT:
            if outcome.content.strip():
                session.context.append(
                    {"role": "assistant", "content": outcome.content.strip()}
                )
            return
        prompt = outcome.prompt or str(current_block.content or "")
        if prompt.strip():
            session.context.append({"role": "user", "content": prompt})
        if outcome.content.strip():
            session.context.append(
                {"role": "assistant", "content": outcome.content.strip()}
            )

    def stream_session(
        self,
        *,
        user_bid: str,
        session_id: str,
        user_input: Mapping[str, Any] | None,
        expected_purpose: str | None,
        expected_block_index: int | None = None,
        request_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Run one idempotent cursor step and stream public events."""
        normalized_session_id = str(session_id or "").strip()
        normalized_user_bid = str(user_bid or "").strip()
        normalized_purpose = self._resolve_existing_session_purpose(
            user_bid=normalized_user_bid,
            session_id=normalized_session_id,
            expected_purpose=expected_purpose,
        )
        owner_lock = self.store.owner_lock(
            user_bid=normalized_user_bid,
            purpose=normalized_purpose,
        )
        if not bool(owner_lock.acquire(blocking=False)):
            msg = "session is busy"
            raise ProfileResearchSessionBusy(msg)
        try:
            lock = self.store.lock(normalized_session_id)
            _acquire_profile_research_lock(lock)
        except BaseException:
            with contextlib.suppress(Exception):
                owner_lock.release()
            raise
        try:
            session = self._load_authorized_session(
                user_bid=normalized_user_bid,
                session_id=normalized_session_id,
                expected_purpose=normalized_purpose,
            )
            active_session_id = self.store.active_session_id(
                user_bid=session.user_bid,
                purpose=session.purpose,
            )
            if active_session_id is None:
                # Sessions created by old workers do not have an active pointer.
                # Claim them on first run while holding the owner-purpose lock.
                self.store.refresh_active(session)
            elif active_session_id != session.session_id:
                msg = "session not found"
                raise ProfileResearchSessionNotFound(msg)
            normalized_user_input = _normalize_user_input(user_input)
            replay = self._replay_or_validate_request(
                session,
                request_id=request_id,
                expected_block_index=expected_block_index,
                user_input=normalized_user_input,
            )
            if replay is not None:
                self.store.save(session)
                yield from replay
                return
            if session.done:
                yield _event(
                    "done",
                    self._summary(
                        session,
                        processed_block_index=max(session.block_index - 1, 0),
                        advanced=False,
                    ),
                    run_session_bid=session.session_id,
                    is_terminal=True,
                )
                return

            request_trace_id = get_request_trace_id()
            trace, root_span = create_trace_with_root_span(
                client=get_langfuse_client(),
                trace_payload={
                    "id": request_trace_id,
                    "name": "profile_research_markdownflow",
                    "user_id": session.user_bid,
                    "session_id": session.session_id,
                    "metadata": {
                        "purpose": session.purpose,
                        "config_revision": session.config_revision,
                        "block_index": session.block_index,
                    },
                },
                root_span_payload={"name": "profile_research_step"},
            )
            provider = self._provider_factory(self.app, session, root_span)
            events: list[dict[str, Any]] = []
            outcome = _StepOutcome()
            rerendered_interaction = ""
            try:
                flow = self._build_flow(session, provider)
                blocks = flow.get_all_blocks()
                if len(blocks) != session.block_count:
                    msg = "session document changed"
                    raise ProfileResearchSessionNotFound(msg)
                if session.block_index < 0 or session.block_index >= len(blocks):
                    msg = "invalid session cursor"
                    raise ProfileResearchSessionNotFound(msg)
                processed_block_index = session.block_index
                current_block = blocks[processed_block_index]
                is_profile_draft_block = (
                    processed_block_index == session.profile_draft_block_index
                )
                has_user_input = bool(normalized_user_input)
                if current_block.block_type != BlockType.INTERACTION and has_user_input:
                    msg = "user_input is not expected for this block"
                    raise ProfileResearchValidationError(msg)
                rendering_interaction = (
                    current_block.block_type == BlockType.INTERACTION
                    and not has_user_input
                )
                result = flow.process(
                    block_index=processed_block_index,
                    mode=(
                        ProcessMode.COMPLETE
                        if rendering_interaction
                        else ProcessMode.STREAM
                    ),
                    context=session.context or None,
                    variables=session.variables,
                    user_input=normalized_user_input or None,
                )
                generated_block_bid = (
                    f"profile-research:{session.session_id}:{processed_block_index}"
                )
                event_bid = (
                    f"{generated_block_bid}:feedback"
                    if current_block.block_type == BlockType.INTERACTION
                    and has_user_input
                    else generated_block_bid
                )
                for llm_result in _iter_results(result):
                    variables = getattr(llm_result, "variables", None)
                    if variables is not None:
                        outcome.input_accepted = True
                        outcome.variable_updates.update(_normalize_variables(variables))
                    metadata = getattr(llm_result, "metadata", None)
                    if isinstance(metadata, Mapping):
                        raw_answer = metadata.get("answer")
                        if isinstance(raw_answer, list):
                            outcome.answer_values = [str(value) for value in raw_answer]
                    prompt = str(getattr(llm_result, "prompt", "") or "")
                    if prompt and not outcome.prompt:
                        outcome.prompt = prompt
                    content = str(getattr(llm_result, "content", "") or "")
                    if not content:
                        continue
                    outcome.content += content
                    if is_profile_draft_block:
                        # The generated profile is a structured terminal result,
                        # not part of the learner-visible MarkdownFlow transcript.
                        continue
                    next_event = _event(
                        "interaction" if rendering_interaction else "content",
                        outcome.content,
                        generated_block_bid=event_bid,
                        run_session_bid=session.session_id,
                        is_terminal=False,
                    )
                    events.append(next_event)
                    yield next_event
                if rendering_interaction and not outcome.content.strip():
                    msg = "MarkdownFlow returned an empty interaction"
                    raise ProfileResearchError(msg)
                if (
                    current_block.block_type == BlockType.INTERACTION
                    and has_user_input
                    and not outcome.input_accepted
                ):
                    rerendered = flow.process(
                        block_index=processed_block_index,
                        mode=ProcessMode.COMPLETE,
                        context=session.context or None,
                        variables=session.variables,
                        user_input=None,
                    )
                    rerendered_interaction = "".join(
                        str(getattr(item, "content", "") or "")
                        for item in _iter_results(rerendered)
                    )
                    if not rerendered_interaction:
                        msg = "MarkdownFlow returned an empty interaction"
                        raise ProfileResearchError(msg)
            finally:
                finalize_langfuse_trace(
                    trace=trace,
                    root_span=root_span,
                    trace_payload={
                        "output": "".join(getattr(provider, "output_chunks", []))
                    },
                    root_span_payload={
                        "output": "".join(getattr(provider, "output_chunks", []))
                    },
                )

            advanced = current_block.block_type != BlockType.INTERACTION
            if current_block.block_type == BlockType.INTERACTION:
                advanced = has_user_input and outcome.input_accepted
            if (
                processed_block_index == session.profile_draft_block_index
                and not outcome.content.strip()
            ):
                msg = "profile draft is empty"
                raise ProfileResearchError(msg)

            if advanced:
                session.variables.update(outcome.variable_updates)
                self._update_context(
                    session,
                    current_block=current_block,
                    user_input=normalized_user_input,
                    outcome=outcome,
                )
                if processed_block_index == session.profile_draft_block_index:
                    session.profile_draft = outcome.content.strip()
                session.block_index += 1
            elif current_block.block_type == BlockType.INTERACTION and has_user_input:
                interaction_event = _event(
                    "interaction",
                    rerendered_interaction,
                    generated_block_bid=(
                        f"profile-research:{session.session_id}:{processed_block_index}"
                    ),
                    run_session_bid=session.session_id,
                    is_terminal=False,
                )
                events.append(interaction_event)
                yield interaction_event

            session.awaiting_input = (
                current_block.block_type == BlockType.INTERACTION and not advanced
            )
            session.done = session.block_index >= session.block_count
            terminal_event = _event(
                "done",
                self._summary(
                    session,
                    processed_block_index=processed_block_index,
                    advanced=advanced,
                ),
                run_session_bid=session.session_id,
                is_terminal=True,
            )
            events.append(terminal_event)
            self._remember_request(
                session,
                request_id=request_id,
                expected_block_index=expected_block_index,
                user_input=normalized_user_input,
                events=events,
            )
            self.store.save(session)
            yield terminal_event
        finally:
            with contextlib.suppress(Exception):
                lock.release()
            with contextlib.suppress(Exception):
                owner_lock.release()


def start_profile_research_session(
    app: Flask,
    *,
    user_bid: str,
    document: str,
    purpose: str,
    config_revision: int = 0,
    output_language: str | None = None,
) -> dict[str, Any]:
    """Create a profile-research session through the shared runtime."""
    return ProfileResearchRuntime(app).start_session(
        user_bid=user_bid,
        document=document,
        purpose=purpose,
        config_revision=config_revision,
        output_language=output_language,
    )


def stream_profile_research_session(
    app: Flask,
    *,
    user_bid: str,
    session_id: str,
    user_input: Mapping[str, Any] | None = None,
    expected_purpose: str | None = None,
    expected_block_index: int | None = None,
    request_id: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Stream one profile-research session cursor step."""
    yield from ProfileResearchRuntime(app).stream_session(
        user_bid=user_bid,
        session_id=session_id,
        user_input=user_input,
        expected_purpose=expected_purpose,
        expected_block_index=expected_block_index,
        request_id=request_id,
    )


def delete_profile_research_session(
    app: Flask,
    *,
    user_bid: str,
    session_id: str,
    expected_purpose: str | None = None,
) -> None:
    """Delete one authorized profile-research session."""
    ProfileResearchRuntime(app).delete_session(
        user_bid=user_bid,
        session_id=session_id,
        expected_purpose=expected_purpose,
    )


def delete_active_profile_research_session(
    app: Flask,
    *,
    user_bid: str,
    purpose: str,
) -> None:
    """Delete the active session for one owner and purpose."""
    ProfileResearchRuntime(app).delete_active_session(
        user_bid=user_bid,
        purpose=purpose,
    )


def _release_stream_db_session(_app: Flask) -> None:
    release_session_classified(source="profile research stream")


def build_profile_research_sse_response(
    app: Flask,
    *,
    event_iter_factory: Callable[[], Iterable[dict[str, Any]]],
    log_context: str,
) -> Response:
    """Build an SSE response with safe errors and DB-session cleanup."""
    safe_log_context = str(log_context or "profile research")[:80]

    def event_stream() -> Generator[str, None, None]:
        try:
            for event in event_iter_factory():
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            app.logger.info(
                "profile research client disconnected | context=%s",
                safe_log_context,
            )
            raise
        except Exception as exc:
            if is_protocol_interrupt_error(exc):
                invalidate_session(source="profile research stream protocol interrupt")
            public_code = getattr(exc, "public_code", ProfileResearchError.public_code)
            app.logger.warning(
                "profile research stream failed | context=%s | error_class=%s",
                safe_log_context,
                type(exc).__name__,
            )
            error_payload = json.dumps(_event("error", public_code), ensure_ascii=False)
            yield f"data: {error_payload}\n\n"
        finally:
            _release_stream_db_session(app)

    _release_stream_db_session(app)
    return Response(
        stream_with_context(event_stream()),
        headers={"Cache-Control": "no-cache"},
        mimetype="text/event-stream",
    )
