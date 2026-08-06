"""Standalone MarkdownFlow runtime for learner-profile research."""

from __future__ import annotations

import contextlib
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
from flaskr.common.cache_provider import CacheProvider, redis_cache
from flaskr.common.i18n_utils import resolve_markdownflow_output_language
from flaskr.dao import db
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.util import generate_id
from flaskr.util.prompt_loader import load_prompt_template
from markdown_flow import (
    USER_ANSWER_CONTEXT_KEY,
    BlockType,
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
PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS = 30 * 60
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
    public_code = "transient_markdownflow_invalid"


class ProfileResearchSessionNotFound(ProfileResearchError):
    public_code = "transient_markdownflow_session_not_found"


class ProfileResearchSessionBusy(ProfileResearchError):
    public_code = "transient_markdownflow_session_busy"


def _normalize_variables(raw: Any) -> dict[str, str | list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ProfileResearchSessionNotFound("invalid session variables")
    variables: dict[str, str | list[str]] = {}
    for raw_key, raw_value in raw.items():
        key = str(raw_key)
        if isinstance(raw_value, list):
            variables[key] = [str(value) for value in raw_value]
        elif raw_value is not None:
            variables[key] = str(raw_value)
    return variables


def _normalize_context(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProfileResearchSessionNotFound("invalid session context")
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
        raise ProfileResearchValidationError("user_input must be an object")
    if len(raw) > _MAX_INPUT_KEY_COUNT:
        raise ProfileResearchValidationError("user_input has too many keys")
    normalized: dict[str, list[str]] = {}
    total_value_count = 0
    total_length = 0
    for raw_key, raw_values in raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ProfileResearchValidationError("user_input key is invalid")
        if len(raw_key) > _MAX_INPUT_KEY_CODEPOINTS:
            raise ProfileResearchValidationError("user_input key is too long")
        if (
            not isinstance(raw_values, list)
            or not raw_values
            or len(raw_values) > _MAX_INPUT_VALUES_PER_KEY
        ):
            raise ProfileResearchValidationError("user_input values are invalid")
        total_value_count += len(raw_values)
        if total_value_count > _MAX_INPUT_VALUE_COUNT:
            raise ProfileResearchValidationError("user_input has too many values")
        values: list[str] = []
        for raw_value in raw_values:
            if not isinstance(raw_value, str):
                raise ProfileResearchValidationError(
                    "user_input values must be strings"
                )
            if not raw_value.strip():
                raise ProfileResearchValidationError(
                    "user_input values must not be blank"
                )
            if len(raw_value) > _MAX_INPUT_VALUE_CODEPOINTS:
                raise ProfileResearchValidationError("user_input value is too long")
            total_length += len(raw_value)
            values.append(raw_value)
        normalized[raw_key] = values
    if total_length > _MAX_INPUT_TOTAL_CODEPOINTS:
        raise ProfileResearchValidationError("user_input is too long")
    return normalized


@dataclass
class _ProfileResearchSession:
    session_id: str
    user_bid: str
    purpose: str
    document: str
    document_prompt: str
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
            "document_prompt": self.document_prompt,
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
            raise ProfileResearchSessionNotFound("session schema mismatch")
        try:
            raw_events = payload.get("last_events")
            if raw_events is None:
                events: list[dict[str, Any]] = []
            elif isinstance(raw_events, list):
                events = [
                    dict(event) for event in raw_events if isinstance(event, Mapping)
                ]
            else:
                raise TypeError("invalid replay events")
            last_expected_block_index = payload.get("last_expected_block_index")
            return cls(
                session_id=str(payload["session_id"]),
                user_bid=str(payload["user_bid"]),
                purpose=str(payload["purpose"]),
                document=str(payload["document"]),
                document_prompt=str(payload.get("document_prompt") or ""),
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
            raise ProfileResearchSessionNotFound("invalid session payload") from exc

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

    def save(self, session: _ProfileResearchSession) -> None:
        self._cache.setex(
            self._key(session.session_id),
            self._ttl_seconds,
            json.dumps(session.to_cache_payload(), ensure_ascii=False),
        )

    def load(self, session_id: str) -> _ProfileResearchSession:
        raw = self._cache.get(self._key(session_id))
        if raw is None:
            raise ProfileResearchSessionNotFound("session not found")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            payload = json.loads(str(raw))
        except (TypeError, ValueError) as exc:
            raise ProfileResearchSessionNotFound("invalid session payload") from exc
        if not isinstance(payload, Mapping):
            raise ProfileResearchSessionNotFound("invalid session payload")
        return _ProfileResearchSession.from_cache_payload(payload)

    def delete(self, session_id: str) -> None:
        self._cache.delete(self._key(session_id))

    def lock(self, session_id: str):
        return self._cache.lock(
            f"{self._key(session_id)}:lock",
            timeout=PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS,
            blocking_timeout=0,
        )


class _ProfileResearchLLMProvider(LLMProvider):
    """Thin adapter that keeps MarkdownFlow on the shared LLM route."""

    def __init__(self, app: Flask, session: _ProfileResearchSession, span: Any):
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
            raise ValueError("No messages provided")
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


def _iter_results(result: Any) -> Iterable[LLMResult]:
    if isinstance(result, LLMResult):
        return (result,)
    return result


def _event(
    event_type: str,
    content: Any,
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
        raise ProfileResearchValidationError("document is empty")
    if len(document) > _MAX_DOCUMENT_CODEPOINTS:
        raise ProfileResearchValidationError("document is too long")
    flow = MarkdownFlow(document=document)
    blocks = flow.get_all_blocks()
    if not blocks:
        raise ProfileResearchValidationError("document has no blocks")
    if len(blocks) >= _MAX_BLOCK_COUNT:
        raise ProfileResearchValidationError("document has too many blocks")
    interaction_count = sum(
        block.block_type == BlockType.INTERACTION for block in blocks
    )
    if interaction_count == 0:
        raise ProfileResearchValidationError("document must contain an interaction")
    return {
        "block_count": len(blocks),
        "interaction_block_count": interaction_count,
        "content_block_count": len(blocks) - interaction_count,
        "variables": list(flow.extract_variables()),
    }


class ProfileResearchRuntime:
    def __init__(
        self,
        app: Flask,
        *,
        store: _ProfileResearchSessionStore | None = None,
        provider_factory: Callable[
            [Flask, _ProfileResearchSession, Any], LLMProvider
        ] = _ProfileResearchLLMProvider,
    ) -> None:
        self.app = app
        self.store = store or _ProfileResearchSessionStore(app)
        self._provider_factory = provider_factory

    def start_session(
        self,
        *,
        user_bid: str,
        document: str,
        document_prompt: str | None,
        purpose: str,
        config_revision: int,
        output_language: str | None,
    ) -> dict[str, Any]:
        normalized_user_bid = str(user_bid or "").strip()
        normalized_purpose = str(purpose or "").strip()
        if not normalized_user_bid:
            raise ProfileResearchValidationError("user_bid is required")
        if normalized_purpose not in _ALLOWED_PURPOSES:
            raise ProfileResearchValidationError("purpose is invalid")
        validate_profile_research_document(document)

        normalized_output_language = str(output_language or "").strip()
        snapshotted_document = _append_profile_summary(document)
        flow = MarkdownFlow(snapshotted_document)
        blocks = flow.get_all_blocks()
        if not blocks or blocks[-1].block_type != BlockType.CONTENT:
            raise ProfileResearchValidationError("profile summary block is invalid")
        if len(blocks) > _MAX_BLOCK_COUNT:
            raise ProfileResearchValidationError("document has too many blocks")

        model = str(self.app.config.get("DEFAULT_LLM_MODEL", "") or "").strip()
        if not model:
            raise ProfileResearchValidationError("LLM model is not configured")
        try:
            temperature = float(self.app.config.get("DEFAULT_LLM_TEMPERATURE", 0.3))
            revision = max(int(config_revision or 0), 0)
        except (TypeError, ValueError) as exc:
            raise ProfileResearchValidationError("runtime config is invalid") from exc
        if temperature < 0 or temperature > 2:
            raise ProfileResearchValidationError("LLM temperature is invalid")

        session = _ProfileResearchSession(
            session_id=generate_id(self.app),
            user_bid=normalized_user_bid,
            purpose=normalized_purpose,
            document=snapshotted_document,
            document_prompt=str(document_prompt or "").strip(),
            model=model,
            temperature=temperature,
            output_language=normalized_output_language,
            config_revision=revision,
            block_index=0,
            block_count=len(blocks),
            profile_draft_block_index=len(blocks) - 1,
        )
        self.store.save(session)
        return session.to_view()

    def _load_authorized_session(
        self,
        *,
        user_bid: str,
        session_id: str,
        expected_purpose: str | None,
    ) -> _ProfileResearchSession:
        session = self.store.load(str(session_id or "").strip())
        if session.user_bid != str(user_bid or "").strip():
            raise ProfileResearchSessionNotFound("session not found")
        if (
            expected_purpose is not None
            and session.purpose != str(expected_purpose).strip()
        ):
            raise ProfileResearchSessionNotFound("session not found")
        return session

    def delete_session(
        self,
        *,
        user_bid: str,
        session_id: str,
        expected_purpose: str | None,
    ) -> None:
        normalized_session_id = str(session_id or "").strip()
        lock = self.store.lock(normalized_session_id)
        if not bool(lock.acquire(blocking=False)):
            raise ProfileResearchSessionBusy("session is busy")
        try:
            session = self._load_authorized_session(
                user_bid=user_bid,
                session_id=normalized_session_id,
                expected_purpose=expected_purpose,
            )
            self.store.delete(session.session_id)
        finally:
            with contextlib.suppress(Exception):
                lock.release()

    def _build_flow(
        self,
        session: _ProfileResearchSession,
        provider: LLMProvider,
    ) -> MarkdownFlow:
        document_prompt = (
            None
            if session.block_index == session.profile_draft_block_index
            else session.document_prompt or None
        )
        flow = MarkdownFlow(
            document=session.document,
            llm_provider=provider,
            document_prompt=document_prompt,
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
            raise ProfileResearchValidationError(
                "expected_block_index and request_id must be provided together"
            )
        normalized_request_id = str(request_id).strip()
        if not normalized_request_id or len(normalized_request_id) > 128:
            raise ProfileResearchValidationError("request_id is invalid")
        if normalized_request_id == session.last_request_id:
            if (
                expected_block_index == session.last_expected_block_index
                and user_input == session.last_user_input
                and session.last_events
            ):
                return _expand_replay_events(session.last_events)
            raise ProfileResearchValidationError(
                "request_id was reused with different run input"
            )
        if expected_block_index != session.block_index:
            raise ProfileResearchValidationError(
                "expected_block_index does not match the session cursor"
            )
        return None

    def _update_context(
        self,
        session: _ProfileResearchSession,
        *,
        current_block: Any,
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
        normalized_session_id = str(session_id or "").strip()
        lock = self.store.lock(normalized_session_id)
        if not bool(lock.acquire(blocking=False)):
            raise ProfileResearchSessionBusy("session is busy")
        try:
            session = self._load_authorized_session(
                user_bid=user_bid,
                session_id=normalized_session_id,
                expected_purpose=expected_purpose,
            )
            normalized_user_input = _normalize_user_input(user_input)
            replay = self._replay_or_validate_request(
                session,
                request_id=request_id,
                expected_block_index=expected_block_index,
                user_input=normalized_user_input,
            )
            if replay is not None:
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
                    raise ProfileResearchSessionNotFound("session document changed")
                if session.block_index < 0 or session.block_index >= len(blocks):
                    raise ProfileResearchSessionNotFound("invalid session cursor")
                processed_block_index = session.block_index
                current_block = blocks[processed_block_index]
                has_user_input = bool(normalized_user_input)
                if current_block.block_type != BlockType.INTERACTION and has_user_input:
                    raise ProfileResearchValidationError(
                        "user_input is not expected for this block"
                    )
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
                    raise ProfileResearchError(
                        "MarkdownFlow returned an empty interaction"
                    )
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
                        raise ProfileResearchError(
                            "MarkdownFlow returned an empty interaction"
                        )
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
                raise ProfileResearchError("profile draft is empty")

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


def start_profile_research_session(
    app: Flask,
    *,
    user_bid: str,
    document: str,
    document_prompt: str | None = None,
    purpose: str,
    config_revision: int = 0,
    output_language: str | None = None,
) -> dict[str, Any]:
    return ProfileResearchRuntime(app).start_session(
        user_bid=user_bid,
        document=document,
        document_prompt=document_prompt,
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
    ProfileResearchRuntime(app).delete_session(
        user_bid=user_bid,
        session_id=session_id,
        expected_purpose=expected_purpose,
    )


def _release_stream_db_session(app: Flask) -> None:
    try:
        db.session.remove()
    except Exception:
        app.logger.warning("profile research DB session cleanup failed", exc_info=True)


def build_profile_research_sse_response(
    app: Flask,
    *,
    event_iter_factory: Callable[[], Iterable[dict[str, Any]]],
    log_context: str,
) -> Response:
    safe_log_context = str(log_context or "profile research")[:80]

    def event_stream():
        try:
            for event in event_iter_factory():
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            app.logger.info(
                "profile research client disconnected | context=%s",
                safe_log_context,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - SSE must terminate safely
            public_code = getattr(exc, "public_code", ProfileResearchError.public_code)
            app.logger.warning(
                "profile research stream failed | context=%s | error_class=%s",
                safe_log_context,
                type(exc).__name__,
            )
            yield f"data: {json.dumps(_event('error', public_code), ensure_ascii=False)}\n\n"
        finally:
            _release_stream_db_session(app)

    _release_stream_db_session(app)
    return Response(
        stream_with_context(event_stream()),
        headers={"Cache-Control": "no-cache"},
        mimetype="text/event-stream",
    )
