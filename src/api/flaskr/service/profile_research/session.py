"""Shared Redis session state for learner-profile research."""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Generator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from flaskr.common.cache_provider import CacheLock, CacheProvider, redis_cache
from markdown_flow import USER_ANSWER_CONTEXT_KEY

if TYPE_CHECKING:
    from flask import Flask

PROFILE_ONBOARDING_PURPOSE = "profile-onboarding"
PROFILE_ONBOARDING_PREVIEW_PURPOSE = "profile-onboarding-preview"
ALLOWED_PROFILE_RESEARCH_PURPOSES = frozenset(
    {PROFILE_ONBOARDING_PURPOSE, PROFILE_ONBOARDING_PREVIEW_PURPOSE}
)

PROFILE_RESEARCH_SESSION_TTL_SECONDS = 30 * 60
# All supported API entrypoints configure a 300-second Gunicorn worker timeout.
# Leave one minute of headroom without making a hard-killed run keep its session
# busy for the rest of the conversation lifetime.
PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS = 6 * 60
SESSION_SCHEMA_VERSION = 1
MAX_DOCUMENT_CODEPOINTS = 100_000
MAX_BLOCK_COUNT = 100
MAX_INPUT_KEY_CODEPOINTS = 256
MAX_INPUT_KEY_COUNT = 100
MAX_INPUT_VALUES_PER_KEY = 100
MAX_INPUT_VALUE_COUNT = 100
MAX_INPUT_VALUE_CODEPOINTS = 4_000
MAX_INPUT_TOTAL_CODEPOINTS = 10_000


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


def _normalize_session_variables(raw: object) -> dict[str, str | list[str]]:
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


def _normalize_session_context(raw: object) -> list[dict[str, str]]:
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


def _normalize_profile_research_user_input(
    raw: Mapping[str, Any] | None,
) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        msg = "user_input must be an object"
        raise ProfileResearchValidationError(msg)
    if len(raw) > MAX_INPUT_KEY_COUNT:
        msg = "user_input has too many keys"
        raise ProfileResearchValidationError(msg)
    normalized: dict[str, list[str]] = {}
    total_value_count = 0
    total_length = 0
    for raw_key, raw_values in raw.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            msg = "user_input key is invalid"
            raise ProfileResearchValidationError(msg)
        if len(raw_key) > MAX_INPUT_KEY_CODEPOINTS:
            msg = "user_input key is too long"
            raise ProfileResearchValidationError(msg)
        if (
            not isinstance(raw_values, list)
            or not raw_values
            or len(raw_values) > MAX_INPUT_VALUES_PER_KEY
        ):
            msg = "user_input values are invalid"
            raise ProfileResearchValidationError(msg)
        total_value_count += len(raw_values)
        if total_value_count > MAX_INPUT_VALUE_COUNT:
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
            if len(raw_value) > MAX_INPUT_VALUE_CODEPOINTS:
                msg = "user_input value is too long"
                raise ProfileResearchValidationError(msg)
            total_length += len(raw_value)
            values.append(raw_value)
        normalized[raw_key] = values
    if total_length > MAX_INPUT_TOTAL_CODEPOINTS:
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
            "schema_version": SESSION_SCHEMA_VERSION,
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
        if int(payload.get("schema_version") or 0) != SESSION_SCHEMA_VERSION:
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
                variables=_normalize_session_variables(payload.get("variables")),
                context=_normalize_session_context(payload.get("context")),
                awaiting_input=bool(payload.get("awaiting_input", False)),
                done=bool(payload.get("done", False)),
                profile_draft=str(payload.get("profile_draft") or ""),
                last_request_id=str(payload.get("last_request_id") or ""),
                last_expected_block_index=(
                    int(last_expected_block_index)
                    if last_expected_block_index is not None
                    else None
                ),
                last_user_input=_normalize_profile_research_user_input(
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
