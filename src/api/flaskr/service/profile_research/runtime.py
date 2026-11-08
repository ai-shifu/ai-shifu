"""Standalone MarkdownFlow runtime for learner-profile research."""

from __future__ import annotations

import contextlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import Flask, Response, stream_with_context
from flaskr.api.llm.model_selection import get_default_llm_model
from flaskr.api.markdownflow import Session
from flaskr.dao import (
    invalidate_session,
    is_protocol_interrupt_error,
    release_session_classified,
)
from flaskr.service.learn.api import (
    ElementDTO,
    GeneratedType,
    PreviewElementRunAdapter,
    RunMarkdownFlowDTO,
    checkpoint_of,
    restore_turn_checkpoint,
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
    _ProfileResearchGatewayCompletion,
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
from markdownflow import USER_ANSWER_CONTEXT_KEY

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping

    from flaskr.service.profile_research.provider import ProfileResearchCompletion
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
    "delete_profile_research_session",
    "start_profile_research_session",
    "stream_profile_research_assistant_answers",
    "stream_profile_research_session",
    "validate_profile_research_document",
]

_NICKNAME_VARIABLE_KEY = "sys_user_nickname"


@dataclass
class _RunAdmission:
    session: _ProfileResearchSession
    user_input: dict[str, list[str]]
    immediate_events: list[dict[str, Any]] | None = None
    refresh_session: bool = False


def _collected_nickname(session: _ProfileResearchSession) -> str | None:
    raw_nickname = session.variables.get(_NICKNAME_VARIABLE_KEY)
    if isinstance(raw_nickname, str):
        normalized = raw_nickname.strip()
        return normalized or None
    if isinstance(raw_nickname, list):
        normalized_values = [value.strip() for value in raw_nickname if value.strip()]
        if normalized_values:
            return ", ".join(normalized_values)
    return None


def _restore_profile_answer_checkpoint(
    session: _ProfileResearchSession, native: Session, question_id: str
) -> dict[str, Any]:
    """Restore the target and retire its later evidence on the detached session."""
    checkpoint = session.answer_checkpoints[question_id]
    restore_turn_checkpoint(native, checkpoint)
    if not native.pending or native.pending[0].tool_call_id != question_id:
        msg = "answer checkpoint does not match the target interaction"
        raise ProfileResearchValidationError(msg)
    session.engine_session = native.to_dict()
    session.variables = checkpoint["profile_variables"].copy()
    del session.context[checkpoint["profile_context_length"] :]
    session.done = False
    session.profile_draft = ""
    # Redis JSON preserves insertion order, which is answer order even when
    # several deferred calls originally came from the same model response.
    keys = list(session.answer_checkpoints)
    for retired_id in keys[keys.index(question_id) :]:
        del session.answer_checkpoints[retired_id]
    return checkpoint


class ProfileResearchRuntime:
    """Run owner-scoped guided profile collection on shared Redis state."""

    def __init__(
        self,
        app: Flask,
        *,
        store: _ProfileResearchSessionStore | None = None,
        provider_factory: Callable[
            [Flask, _ProfileResearchSession, object], ProfileResearchCompletion
        ] = _ProfileResearchGatewayCompletion,
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
        """Create an independent session bound to its owner and purpose."""
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
        self.store.save(session)
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
        """Delete only the authorized session identified by its caller."""
        normalized_session_id = str(session_id or "").strip()
        normalized_user_bid = str(user_bid or "").strip()
        normalized_purpose = self._resolve_existing_session_purpose(
            user_bid=normalized_user_bid,
            session_id=normalized_session_id,
            expected_purpose=expected_purpose,
        )
        with _hold_profile_research_lock(self.store.lock(normalized_session_id)):
            session = self._load_authorized_session(
                user_bid=normalized_user_bid,
                session_id=normalized_session_id,
                expected_purpose=normalized_purpose,
            )
            self.store.delete(session.session_id)

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
            "rewindable_interaction_ids": list(session.answer_checkpoints),
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
        rewind: bool = False,
    ) -> _RunAdmission:
        session = self._load_authorized_session(
            user_bid=user_bid,
            session_id=session_id,
            expected_purpose=purpose,
        )
        normalized_user_input = _normalize_user_input(user_input)
        if rewind and (
            not normalized_user_input or not expected_interaction_id or not request_id
        ):
            msg = "rewind requires a submitted answer and a request identity"
            raise ProfileResearchValidationError(msg)
        replay = self._replay_or_validate_request(
            session,
            request_id=request_id,
            expected_turn_index=expected_turn_index,
            user_input=normalized_user_input,
            operation="rewind" if rewind else "run",
            expected_interaction_id=expected_interaction_id,
        )
        if replay is not None:
            return _RunAdmission(
                session=session,
                user_input=normalized_user_input,
                immediate_events=replay,
                refresh_session=True,
            )
        if rewind:
            if (
                session.engine_session is None
                or expected_interaction_id not in session.answer_checkpoints
            ):
                msg = "answered interaction cannot be rewound"
                raise ProfileResearchValidationError(msg)
            return _RunAdmission(session=session, user_input=normalized_user_input)
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
        bid = f"profile-research:{session.session_id}:{session.turn_index}"
        interaction = next(
            (chunk for chunk in result.chunks if chunk.interaction is not None), None
        )

        def block_events() -> Generator[RunMarkdownFlowDTO, None, None]:
            for chunk in result.chunks:
                if not chunk.content:
                    continue
                yield RunMarkdownFlowDTO(
                    outline_bid="",
                    generated_block_bid=bid,
                    type=GeneratedType.CONTENT,
                    content=chunk.content,
                ).set_mdflow_stream_parts([(chunk.content, chunk.type, chunk.number)])
            yield RunMarkdownFlowDTO(
                outline_bid="",
                generated_block_bid=bid,
                type=GeneratedType.BREAK,
                content="",
            )
            if interaction is not None and interaction.interaction is not None:
                yield RunMarkdownFlowDTO(
                    outline_bid="",
                    generated_block_bid=bid,
                    type=GeneratedType.INTERACTION,
                    content=interaction.interaction,
                )

        adapter = PreviewElementRunAdapter(
            self.app,
            shifu_bid="",
            outline_bid="",
            user_bid=session.user_bid,
            run_session_bid=session.session_id,
        )
        for message in adapter.process(block_events()):
            element = message.content
            if not isinstance(element, ElementDTO):
                continue
            element_type = element.element_type.value
            is_interaction = element_type == "interaction"
            # The preview adapter uses request-local random IDs. The element order
            # gives Profile a deterministic display slot for an uncommitted retry.
            slot = "interaction" if is_interaction else str(element.element_index)
            events.append(
                _event(
                    "interaction" if is_interaction else "content",
                    element.content,
                    element_type=element_type,
                    generated_block_bid=f"{bid}:{slot}",
                    run_session_bid=session.session_id,
                    is_final=element.is_final,
                    is_terminal=False,
                    interaction_id=(
                        interaction.interaction_id
                        if is_interaction and interaction is not None
                        else None
                    ),
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
        rewind: bool = False,
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
        lock = self.store.lock(normalized_session_id)
        _acquire_profile_research_lock(lock)
        try:
            admission = self._admit_run(
                user_bid=normalized_user_bid,
                session_id=normalized_session_id,
                purpose=normalized_purpose,
                user_input=user_input,
                expected_turn_index=expected_turn_index,
                request_id=request_id,
                expected_interaction_id=expected_interaction_id,
                rewind=rewind,
            )
            if admission.immediate_events is not None:
                immediate_events = admission.immediate_events
                if admission.refresh_session and rewind:
                    immediate_events = self._save_replayable_result(
                        admission.session, immediate_events
                    )
                elif admission.refresh_session:
                    self.store.save(admission.session)
                yield from immediate_events
                return

            # A failed turn or private transformation leaves the stored native Session
            # untouched, including its pending calls and exact-request replay data.
            staged = deepcopy(admission.session)
            operation = "rewind" if rewind else "run"
            checkpoint = None
            if (
                expected_interaction_id is not None
                and staged.engine_session is not None
            ):
                native = Session.from_dict(staged.engine_session)
                if rewind:
                    checkpoint = _restore_profile_answer_checkpoint(
                        staged, native, expected_interaction_id
                    )
                else:
                    checkpoint = checkpoint_of(native)
                    checkpoint["profile_variables"] = staged.variables.copy()
                    checkpoint["profile_context_length"] = len(staged.context)
            with ProfileTrace(
                staged, admission.user_input, operation=operation
            ) as trace:
                events, input_accepted, finished = self._execute_turn(
                    session=staged,
                    user_input=admission.user_input,
                    trace=trace,
                )
                if rewind and not input_accepted:
                    # Keep the old branch, including any finished draft. The
                    # rejected native response was run against a detached copy.
                    original = admission.session
                    rejected = _event(
                        "done",
                        self._summary(
                            original, processed_turn_index=original.turn_index
                        ),
                        run_session_bid=original.session_id,
                        is_terminal=True,
                    )
                    self._remember_request(
                        original,
                        request_id=request_id,
                        expected_turn_index=expected_turn_index,
                        user_input=admission.user_input,
                        events=[rejected],
                        operation=operation,
                        expected_interaction_id=expected_interaction_id,
                    )
                    published = self._save_replayable_result(original, [rejected])
                    trace.complete_turn("rejected")
                    yield from published
                    return
                if (
                    input_accepted
                    and checkpoint is not None
                    and expected_interaction_id
                ):
                    staged.answer_checkpoints[expected_interaction_id] = checkpoint
                if rewind:
                    events.insert(
                        0,
                        _event(
                            "rewind",
                            {"interaction_id": expected_interaction_id},
                            run_session_bid=staged.session_id,
                            is_terminal=False,
                        ),
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
                    operation=operation,
                    expected_interaction_id=expected_interaction_id,
                )
                published = [
                    event for event in all_events if event.get("type") != "phase"
                ]
                if rewind:
                    published = self._save_replayable_result(staged, published)
                else:
                    self.store.save(staged)
                trace.publish(staged, events)
                yield from published
        finally:
            with contextlib.suppress(Exception):
                lock.release()

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
        with _hold_profile_research_lock(self.store.lock(normalized_session_id)):
            session = self._load_authorized_session(
                user_bid=normalized_user_bid,
                session_id=normalized_session_id,
                expected_purpose=purpose,
            )
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
            # variables, or context is published until both steps succeed.
            with ProfileTrace(session, raw_text, operation="delegate") as trace:
                staged = deepcopy(session)
                answers, nickname = self._extract_assistant_answers(
                    staged, raw_text, trace=trace
                )
                if nickname and not _collected_nickname(staged):
                    staged.variables[_NICKNAME_VARIABLE_KEY] = nickname
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
                published = self._save_replayable_result(staged, [event])
                trace.publish(staged, published)
                yield from published

    def _save_replayable_result(
        self, session: _ProfileResearchSession, events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Resolve a session-write outcome before permitting another operation."""
        try:
            self.store.save(session)
        except Exception:
            # A lost write acknowledgement can follow a committed result.
            # Keep the session lock while reading back that outcome.
            try:
                persisted = self.store.load(session.session_id)
                replay = self._replay_or_validate_request(
                    persisted,
                    request_id=session.last_request_id,
                    expected_turn_index=session.last_expected_turn_index,
                    user_input=session.last_user_input,
                    operation=session.last_operation,
                    raw_text=session.last_raw_text,
                    expected_interaction_id=session.last_expected_interaction_id,
                )
            except Exception as exc:
                # Busy means retry the same request, not edit the draft or
                # switch back to manual while the write outcome is unknown.
                msg = "profile result persistence is uncertain"
                raise ProfileResearchSessionBusy(msg) from exc
            if replay is not None:
                # The stored request matches. Use the intended event slice, which
                # includes the phase on a replay and omits it after a live phase.
                return events
            # A readable unchanged cursor confirms failure before publication.
            raise
        return events


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
    rewind: bool = False,
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
        rewind=rewind,
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
