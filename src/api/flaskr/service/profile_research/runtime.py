"""Standalone MarkdownFlow runtime for learner-profile research."""

from __future__ import annotations

import contextlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import Flask, Response, stream_with_context
from flaskr.api.llm.model_selection import get_default_llm_model
from flaskr.dao import (
    invalidate_session,
    is_protocol_interrupt_error,
    release_session_classified,
)
from flaskr.service.profile.api import (
    LEARNER_PROFILE_MAX_LENGTH,
    LEARNER_PROFILE_NICKNAME_MAX_LENGTH,
)
from flaskr.service.profile_research.assistant_answers import parse_assistant_answers
from flaskr.service.profile_research.document import (
    _profile_summary_prompt,
    validate_profile_research_document,
)
from flaskr.service.profile_research.engine_runtime import (
    profile_answer_evidence,
    run_profile_turn,
)
from flaskr.service.profile_research.events import (
    _compact_replay_events,
    _expand_replay_events,
)
from flaskr.service.profile_research.events import (
    _profile_research_event as _event,
)
from flaskr.service.profile_research.langfuse_tracing import ProfileTrace
from flaskr.service.profile_research.provider import (
    _ProfileResearchLLMProvider,
    create_profile_research_model,
)
from flaskr.service.profile_research.session import (
    ALLOWED_PROFILE_RESEARCH_PURPOSES as _ALLOWED_PURPOSES,
)
from flaskr.service.profile_research.session import (
    PROFILE_ONBOARDING_PREVIEW_PURPOSE,
    PROFILE_ONBOARDING_PURPOSE,
    PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS,
    PROFILE_RESEARCH_SESSION_TTL_SECONDS,
    ProfileResearchError,
    ProfileResearchSessionBusy,
    ProfileResearchSessionBusyError,
    ProfileResearchSessionNotFound,
    ProfileResearchSessionNotFoundError,
    ProfileResearchValidationError,
    _acquire_profile_research_lock,
    _hold_profile_research_lock,
    _ProfileResearchSession,
    _ProfileResearchSessionStore,
)
from flaskr.service.profile_research.session import (
    _normalize_profile_research_user_input as _normalize_user_input,
)
from flaskr.util import generate_id
from markdown_flow import USER_ANSWER_CONTEXT_KEY, LLMProvider

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping

    from pydantic_ai.models import Model

__all__ = [
    "PROFILE_ONBOARDING_PREVIEW_PURPOSE",
    "PROFILE_ONBOARDING_PURPOSE",
    "PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS",
    "PROFILE_RESEARCH_SESSION_TTL_SECONDS",
    "ProfileResearchError",
    "ProfileResearchRuntime",
    "ProfileResearchSessionBusy",
    "ProfileResearchSessionBusyError",
    "ProfileResearchSessionNotFound",
    "ProfileResearchSessionNotFoundError",
    "ProfileResearchValidationError",
    "build_profile_research_sse_response",
    "delete_active_profile_research_session",
    "delete_profile_research_session",
    "start_profile_research_session",
    "stream_profile_research_assistant_answers",
    "stream_profile_research_session",
    "validate_profile_research_document",
]

_NICKNAME_MEMORY_KEY = "sys_user_nickname"


@dataclass
class _RunAdmission:
    session: _ProfileResearchSession
    user_input: dict[str, list[str]]
    immediate_events: list[dict[str, Any]] | None = None
    refresh_session: bool = False


def _collected_nickname(session: _ProfileResearchSession) -> str | None:
    raw_nickname = session.memory.get(_NICKNAME_MEMORY_KEY)
    if isinstance(raw_nickname, str):
        normalized = raw_nickname.strip()
        return normalized or None
    if isinstance(raw_nickname, list):
        normalized_values = [value.strip() for value in raw_nickname if value.strip()]
        if normalized_values:
            return ", ".join(normalized_values)
    return None


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
        model_factory: Callable[
            [Flask, _ProfileResearchSession, object], Model
        ] = create_profile_research_model,
    ) -> None:
        """Initialize the runtime with shared storage and provider adapters."""
        self.app = app
        self.store = store or _ProfileResearchSessionStore(app)
        self._provider_factory = provider_factory
        self._model_factory = model_factory

    def start_session(
        self,
        *,
        user_bid: str,
        document: str,
        purpose: str,
        config_revision: int,
        output_language: str | None,
        assistant_prompt: str = "",
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
        model = get_default_llm_model(self.app)
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
            document=document,
            assistant_prompt=assistant_prompt,
            model=model,
            temperature=temperature,
            output_language=normalized_output_language,
            config_revision=revision,
            turn_index=0,
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

    def _summary(
        self,
        session: _ProfileResearchSession,
        *,
        processed_turn_index: int,
        input_accepted: bool = False,
    ) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "turn_index": processed_turn_index,
            "next_turn_index": session.turn_index,
            "input_accepted": input_accepted,
            "pending_interaction_ids": [
                pending["tool_call_id"]
                for pending in (session.engine_session or {}).get("pending", [])
            ]
            if not session.done
            else [],
            "awaiting_input": session.awaiting_input,
            "done": session.done,
            "profile_draft": session.profile_draft if session.done else None,
            "nickname": _collected_nickname(session) if session.done else None,
            "config_revision": session.config_revision,
        }

    @staticmethod
    def _remember_request(
        session: _ProfileResearchSession,
        *,
        request_id: str | None,
        expected_turn_index: int | None,
        user_input: dict[str, list[str]],
        events: list[dict[str, Any]],
        operation: str = "run",
        raw_text: str = "",
        expected_interaction_id: str | None = None,
    ) -> None:
        session.last_operation = operation
        session.last_raw_text = raw_text if request_id else ""
        session.last_request_id = request_id or ""
        session.last_expected_turn_index = expected_turn_index
        session.last_expected_interaction_id = expected_interaction_id
        session.last_user_input = user_input if request_id else {}
        session.last_events = _compact_replay_events(events) if request_id else []

    @staticmethod
    def _replay_or_validate_request(
        session: _ProfileResearchSession,
        *,
        request_id: str | None,
        expected_turn_index: int | None,
        user_input: dict[str, list[str]],
        operation: str = "run",
        raw_text: str = "",
        expected_interaction_id: str | None = None,
    ) -> list[dict[str, Any]] | None:
        if request_id is None and expected_turn_index is None:
            return None
        if request_id is None or expected_turn_index is None:
            msg = "expected_turn_index and request_id must be provided together"
            raise ProfileResearchValidationError(msg)
        normalized_request_id = str(request_id).strip()
        if not normalized_request_id or len(normalized_request_id) > 128:
            msg = "request_id is invalid"
            raise ProfileResearchValidationError(msg)
        if normalized_request_id == session.last_request_id:
            if (
                operation == session.last_operation
                and raw_text == session.last_raw_text
                and expected_turn_index == session.last_expected_turn_index
                and expected_interaction_id == session.last_expected_interaction_id
                and user_input == session.last_user_input
                and session.last_events
            ):
                return _expand_replay_events(session.last_events)
            msg = "request_id was reused with different run input"
            raise ProfileResearchValidationError(msg)
        if expected_turn_index != session.turn_index:
            msg = "expected_turn_index does not match the request revision"
            raise ProfileResearchValidationError(msg)
        return None

    def _admit_run(
        self,
        *,
        user_bid: str,
        session_id: str,
        purpose: str,
        user_input: Mapping[str, Any] | None,
        expected_turn_index: int | None,
        request_id: str | None,
        expected_interaction_id: str | None = None,
    ) -> _RunAdmission:
        session = self._load_authorized_session(
            user_bid=user_bid,
            session_id=session_id,
            expected_purpose=purpose,
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
            expected_turn_index=expected_turn_index,
            user_input=normalized_user_input,
            expected_interaction_id=expected_interaction_id,
        )
        if replay is not None:
            return _RunAdmission(
                session=session,
                user_input=normalized_user_input,
                immediate_events=replay,
                refresh_session=True,
            )
        pending = (session.engine_session or {}).get("pending") or []
        if normalized_user_input:
            actual_id = pending[0].get("tool_call_id") if pending else None
            if expected_interaction_id is None or expected_interaction_id != actual_id:
                msg = "expected_interaction_id does not match the pending question"
                raise ProfileResearchValidationError(msg)
        elif expected_interaction_id is not None:
            msg = "expected_interaction_id requires user_input"
            raise ProfileResearchValidationError(msg)
        if session.done:
            return _RunAdmission(
                session=session,
                user_input=normalized_user_input,
                immediate_events=[
                    _event(
                        "done",
                        self._summary(
                            session,
                            processed_turn_index=session.turn_index,
                        ),
                        run_session_bid=session.session_id,
                        is_terminal=True,
                    )
                ],
            )
        return _RunAdmission(session=session, user_input=normalized_user_input)

    def _execute_turn(
        self,
        *,
        session: _ProfileResearchSession,
        user_input: dict[str, list[str]],
        trace: ProfileTrace,
    ) -> tuple[list[dict[str, Any]], bool, bool]:
        """Adapt one native engine turn without owning questionnaire progression."""
        events: list[dict[str, Any]] = []
        result = run_profile_turn(
            session=session,
            user_input=user_input,
            model=self._model_factory(self.app, session, trace.model_parent),
            observer=trace.event,
        )
        element_content: dict[tuple[int, str, int], str] = {}
        segments: dict[int, int] = {}
        html_segments: dict[int, int] = {}
        previous_identity: tuple[int, str] | None = None
        segment = 0
        bid = f"profile-research:{session.session_id}:{session.turn_index}"
        for chunk in result.chunks:
            if chunk.interaction is not None:
                events.append(
                    _event(
                        "interaction",
                        chunk.interaction,
                        element_type="interaction",
                        generated_block_bid=f"{bid}:interaction",
                        run_session_bid=session.session_id,
                        is_terminal=False,
                        interaction_id=chunk.interaction_id,
                    )
                )
                continue
            if not chunk.content:
                continue
            identity = (chunk.number, chunk.type)
            if identity != previous_identity:
                previous_identity = identity
                if chunk.type == "html" and chunk.number in html_segments:
                    segment = html_segments[chunk.number]
                else:
                    segment = segments.get(chunk.number, 0)
                    segments[chunk.number] = segment + 1
                    if chunk.type == "html":
                        html_segments[chunk.number] = segment
            key = (*identity, segment)
            content = element_content.get(key, "") + chunk.content
            element_content[key] = content
            events.append(
                _event(
                    "content",
                    content,
                    element_type=chunk.type,
                    generated_block_bid=f"{bid}:{chunk.number}:{segment}",
                    run_session_bid=session.session_id,
                    is_terminal=False,
                )
            )
        return events, result.input_accepted, result.finished

    def _generate_profile_draft(
        self,
        session: _ProfileResearchSession,
        *,
        trace: ProfileTrace | None = None,
    ) -> str:
        """Transform accepted learner evidence without publishing private model text."""
        evidence = profile_answer_evidence(session)
        supplemental = [
            message[USER_ANSWER_CONTEXT_KEY]
            for message in session.context
            if message.get(USER_ANSWER_CONTEXT_KEY)
        ]
        if not evidence and not supplemental:
            return ""
        instructions = _profile_summary_prompt()
        if session.output_language:
            instructions += f"\n\nOUTPUT LANGUAGE: {session.output_language}"
        messages = [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "accepted_answers": evidence,
                        "supplemental_answers": supplemental,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        with ProfileTrace.summary(session, messages, trace=trace) as summary:
            draft = (
                self._provider_factory(self.app, session, summary)
                .complete(
                    messages=messages,
                    model=session.model,
                    temperature=session.temperature,
                )
                .strip()
            )
            if not draft:
                msg = "profile draft is empty"
                raise ProfileResearchError(msg)
            summary.update(output=draft)
            return draft

    @staticmethod
    def _summary_phase(session: _ProfileResearchSession) -> dict[str, Any]:
        return _event(
            "phase",
            {"phase": "summary"},
            run_session_bid=session.session_id,
            is_terminal=False,
        )

    def stream_session(
        self,
        *,
        user_bid: str,
        session_id: str,
        user_input: Mapping[str, Any] | None,
        expected_purpose: str | None,
        expected_turn_index: int | None = None,
        request_id: str | None = None,
        expected_interaction_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Run a native questionnaire turn and atomically persist its public result."""
        if expected_interaction_id is not None:
            if (
                not isinstance(expected_interaction_id, str)
                or not expected_interaction_id.strip()
                or len(expected_interaction_id.strip()) > 256
            ):
                msg = "expected_interaction_id is invalid"
                raise ProfileResearchValidationError(msg)
            expected_interaction_id = expected_interaction_id.strip()
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
            admission = self._admit_run(
                user_bid=normalized_user_bid,
                session_id=normalized_session_id,
                purpose=normalized_purpose,
                user_input=user_input,
                expected_turn_index=expected_turn_index,
                request_id=request_id,
                expected_interaction_id=expected_interaction_id,
            )
            if admission.immediate_events is not None:
                if admission.refresh_session:
                    self.store.save(admission.session)
                yield from admission.immediate_events
                return

            # A failed turn or private transformation leaves the stored native Session
            # untouched, including its pending calls and exact-request replay data.
            staged = deepcopy(admission.session)
            with ProfileTrace(staged, admission.user_input) as trace:
                events, input_accepted, finished = self._execute_turn(
                    session=staged,
                    user_input=admission.user_input,
                    trace=trace,
                )
                if finished:
                    phase = self._summary_phase(staged)
                    yield phase
                    events.insert(0, phase)
                    staged.profile_draft = self._generate_profile_draft(
                        staged, trace=trace
                    )
                staged.awaiting_input = bool(
                    (staged.engine_session or {}).get("pending")
                )
                staged.done = finished
                processed_turn_index = staged.turn_index
                staged.turn_index += 1
                terminal = _event(
                    "done",
                    self._summary(
                        staged,
                        processed_turn_index=processed_turn_index,
                        input_accepted=input_accepted,
                    ),
                    run_session_bid=staged.session_id,
                    is_terminal=True,
                )
                all_events = [*events, terminal]
                self._remember_request(
                    staged,
                    request_id=request_id,
                    expected_turn_index=expected_turn_index,
                    user_input=admission.user_input,
                    events=all_events,
                    expected_interaction_id=expected_interaction_id,
                )
                self.store.save(staged)
                trace.publish(staged, events)
                yield from [event for event in events if event.get("type") != "phase"]
                yield terminal
        finally:
            with contextlib.suppress(Exception):
                lock.release()
            with contextlib.suppress(Exception):
                owner_lock.release()

    def _extract_assistant_answers(
        self,
        session: _ProfileResearchSession,
        raw_text: str,
        *,
        trace: ProfileTrace | None = None,
    ) -> tuple[str, str]:
        with ProfileTrace.import_answers(session, raw_text, trace=trace) as extraction:
            provider = self._provider_factory(self.app, session, extraction)
            answers, nickname = parse_assistant_answers(provider, session, raw_text)
            extraction.update(output={"answers": answers, "nickname": nickname})
            return answers, nickname

    def stream_assistant_answers(
        self,
        *,
        user_bid: str,
        session_id: str,
        raw_text: str,
        expected_turn_index: int,
        request_id: str,
    ) -> Generator[dict[str, Any], None, None]:
        """Atomically transform imported and native accepted questionnaire evidence."""
        if (
            not isinstance(raw_text, str)
            or not raw_text.strip()
            or len(raw_text) > 10_000
        ):
            msg = "assistant answers must contain at most 10000 characters"
            raise ProfileResearchValidationError(msg)
        normalized_user_bid = str(user_bid or "").strip()
        normalized_session_id = str(session_id or "").strip()
        purpose = self._resolve_existing_session_purpose(
            user_bid=normalized_user_bid,
            session_id=normalized_session_id,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
        owner_lock = self.store.owner_lock(
            user_bid=normalized_user_bid, purpose=purpose
        )
        with (
            _hold_profile_research_lock(owner_lock),
            _hold_profile_research_lock(self.store.lock(normalized_session_id)),
        ):
            session = self._load_authorized_session(
                user_bid=normalized_user_bid,
                session_id=normalized_session_id,
                expected_purpose=purpose,
            )
            active = self.store.active_session_id(
                user_bid=session.user_bid, purpose=purpose
            )
            if active is not None and active != session.session_id:
                msg = "session not found"
                raise ProfileResearchSessionNotFound(msg)
            replay = self._replay_or_validate_request(
                session,
                request_id=request_id,
                expected_turn_index=expected_turn_index,
                user_input={},
                operation="delegate",
                raw_text=raw_text,
            )
            if replay is not None:
                yield from replay
                return
            if not session.assistant_prompt or session.done:
                msg = "assistant answers are not available for this session"
                raise ProfileResearchValidationError(msg)

            # All provider work happens on a detached snapshot. No cursor,
            # memory, or context is published until both steps succeed.
            with ProfileTrace(session, raw_text, operation="delegate") as trace:
                staged = deepcopy(session)
                answers, nickname = self._extract_assistant_answers(
                    staged, raw_text, trace=trace
                )
                if nickname and not _collected_nickname(staged):
                    staged.memory[_NICKNAME_MEMORY_KEY] = nickname
                if (
                    len(_collected_nickname(staged) or "")
                    > LEARNER_PROFILE_NICKNAME_MAX_LENGTH
                ):
                    msg = "assistant nickname is too long"
                    raise ProfileResearchValidationError(msg)
                has_manual_answers = bool(profile_answer_evidence(staged)) or any(
                    message.get(USER_ANSWER_CONTEXT_KEY) for message in staged.context
                )
                if (
                    not answers
                    and not has_manual_answers
                    and not _collected_nickname(staged)
                ):
                    msg = "assistant answers contain no usable information"
                    raise ProfileResearchValidationError(msg)
                if answers:
                    staged.context.append(
                        {
                            "role": "user",
                            "content": answers,
                            USER_ANSWER_CONTEXT_KEY: answers,
                        }
                    )
                phase = self._summary_phase(staged)
                yield phase
                draft = self._generate_profile_draft(staged, trace=trace)
                if len(draft) > LEARNER_PROFILE_MAX_LENGTH:
                    msg = "assistant profile draft is invalid"
                    raise ProfileResearchValidationError(msg)
                staged.profile_draft = draft
                staged.awaiting_input = False
                staged.done = True
                processed_turn_index = staged.turn_index
                staged.turn_index += 1
                summary = self._summary(
                    staged,
                    processed_turn_index=processed_turn_index,
                )
                summary["operation"] = "delegate"
                event = _event(
                    "done", summary, run_session_bid=staged.session_id, is_terminal=True
                )
                self._remember_request(
                    staged,
                    request_id=request_id,
                    expected_turn_index=expected_turn_index,
                    user_input={},
                    operation="delegate",
                    raw_text=raw_text,
                    events=[phase, event],
                )
                published = self._save_assistant_result(staged, event)
                trace.publish(staged, published)
                yield from published

    def _save_assistant_result(
        self, session: _ProfileResearchSession, event: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Resolve a session-write outcome before permitting another operation."""
        try:
            self.store.save(session)
        except Exception:
            # save() writes the replay payload before refreshing its active
            # pointer. A refresh failure does not undo a committed result.
            # Keep the owner/session locks while reading back that outcome.
            try:
                persisted = self.store.load(session.session_id)
                replay = self._replay_or_validate_request(
                    persisted,
                    request_id=session.last_request_id,
                    expected_turn_index=session.last_expected_turn_index,
                    user_input={},
                    operation="delegate",
                    raw_text=session.last_raw_text,
                )
            except Exception as exc:
                # Busy means retry the same request, not edit the draft or
                # switch back to manual while the write outcome is unknown.
                msg = "assistant result persistence is uncertain"
                raise ProfileResearchSessionBusy(msg) from exc
            if replay is not None:
                return [item for item in replay if item.get("type") != "phase"]
            # A readable unchanged cursor confirms failure before publication.
            raise
        return [event]


def start_profile_research_session(
    app: Flask,
    *,
    user_bid: str,
    document: str,
    purpose: str,
    config_revision: int = 0,
    output_language: str | None = None,
    assistant_prompt: str = "",
) -> dict[str, Any]:
    """Create a profile-research session through the shared runtime."""
    return ProfileResearchRuntime(app).start_session(
        user_bid=user_bid,
        document=document,
        purpose=purpose,
        config_revision=config_revision,
        output_language=output_language,
        assistant_prompt=assistant_prompt,
    )


def stream_profile_research_session(
    app: Flask,
    *,
    user_bid: str,
    session_id: str,
    user_input: Mapping[str, Any] | None = None,
    expected_purpose: str | None = None,
    expected_turn_index: int | None = None,
    request_id: str | None = None,
    expected_interaction_id: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Stream one native turn of the complete profile questionnaire."""
    yield from ProfileResearchRuntime(app).stream_session(
        user_bid=user_bid,
        session_id=session_id,
        user_input=user_input,
        expected_purpose=expected_purpose,
        expected_turn_index=expected_turn_index,
        request_id=request_id,
        expected_interaction_id=expected_interaction_id,
    )


def stream_profile_research_assistant_answers(
    app: Flask,
    *,
    user_bid: str,
    session_id: str,
    raw_text: str,
    expected_turn_index: int,
    request_id: str,
) -> Generator[dict[str, Any], None, None]:
    """Import external answers into an authorized learner session."""
    yield from ProfileResearchRuntime(app).stream_assistant_answers(
        user_bid=user_bid,
        session_id=session_id,
        raw_text=raw_text,
        expected_turn_index=expected_turn_index,
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
