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
from flaskr.common.i18n_utils import resolve_markdownflow_output_language
from flaskr.dao import (
    invalidate_session,
    is_protocol_interrupt_error,
    release_session_classified,
)
from flaskr.service.profile_research.document import (
    _append_profile_summary,
    validate_profile_research_document,
)
from flaskr.service.profile_research.events import (
    _compact_replay_events,
    _expand_replay_events,
)
from flaskr.service.profile_research.events import (
    _profile_research_event as _event,
)
from flaskr.service.profile_research.provider import _ProfileResearchLLMProvider
from flaskr.service.profile_research.session import (
    ALLOWED_PROFILE_RESEARCH_PURPOSES as _ALLOWED_PURPOSES,
)
from flaskr.service.profile_research.session import (
    MAX_BLOCK_COUNT as _MAX_BLOCK_COUNT,
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
from flaskr.service.profile_research.session import (
    _normalize_session_variables as _normalize_variables,
)
from flaskr.util import generate_id
from markdown_flow import (
    USER_ANSWER_CONTEXT_KEY,
    BlockType,
    LLMProvider,
    LLMResult,
    MarkdownFlow,
    ProcessMode,
)

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
    "stream_profile_research_session",
    "validate_profile_research_document",
]

_NICKNAME_VARIABLE_KEY = "sys_user_nickname"


@dataclass
class _StepOutcome:
    content: str = ""
    prompt: str = ""
    variable_updates: dict[str, str | list[str]] = field(default_factory=dict)
    input_accepted: bool = False
    answer_values: list[str] = field(default_factory=list)


@dataclass
class _RunAdmission:
    session: _ProfileResearchSession
    user_input: dict[str, list[str]]
    immediate_events: list[dict[str, Any]] | None = None
    refresh_session: bool = False


@dataclass
class _BlockExecution:
    processed_block_index: int
    current_block: Any
    has_user_input: bool
    outcome: _StepOutcome
    rerendered_interaction: str
    streamed_events: list[dict[str, Any]]


def _iter_results(
    result: LLMResult | Iterable[LLMResult],
) -> Iterable[LLMResult]:
    if isinstance(result, LLMResult):
        return (result,)
    return result


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
            "nickname": _collected_nickname(session) if session.done else None,
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

    def _admit_run(
        self,
        *,
        user_bid: str,
        session_id: str,
        purpose: str,
        user_input: Mapping[str, Any] | None,
        expected_block_index: int | None,
        request_id: str | None,
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
            expected_block_index=expected_block_index,
            user_input=normalized_user_input,
        )
        if replay is not None:
            return _RunAdmission(
                session=session,
                user_input=normalized_user_input,
                immediate_events=replay,
                refresh_session=True,
            )
        if session.done:
            return _RunAdmission(
                session=session,
                user_input=normalized_user_input,
                immediate_events=[
                    _event(
                        "done",
                        self._summary(
                            session,
                            processed_block_index=max(session.block_index - 1, 0),
                            advanced=False,
                        ),
                        run_session_bid=session.session_id,
                        is_terminal=True,
                    )
                ],
            )
        return _RunAdmission(session=session, user_input=normalized_user_input)

    def _execute_block(
        self,
        *,
        session: _ProfileResearchSession,
        user_input: dict[str, list[str]],
    ) -> Generator[dict[str, Any], None, _BlockExecution]:
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
            has_user_input = bool(user_input)
            if current_block.block_type != BlockType.INTERACTION and has_user_input:
                msg = "user_input is not expected for this block"
                raise ProfileResearchValidationError(msg)
            rendering_interaction = (
                current_block.block_type == BlockType.INTERACTION and not has_user_input
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
                user_input=user_input or None,
            )
            generated_block_bid = (
                f"profile-research:{session.session_id}:{processed_block_index}"
            )
            event_bid = (
                f"{generated_block_bid}:feedback"
                if current_block.block_type == BlockType.INTERACTION and has_user_input
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

        return _BlockExecution(
            processed_block_index=processed_block_index,
            current_block=current_block,
            has_user_input=has_user_input,
            outcome=outcome,
            rerendered_interaction=rerendered_interaction,
            streamed_events=events,
        )

    def _finalize_run(
        self,
        *,
        session: _ProfileResearchSession,
        execution: _BlockExecution,
        user_input: dict[str, list[str]],
        expected_block_index: int | None,
        request_id: str | None,
    ) -> list[dict[str, Any]]:
        current_block = execution.current_block
        outcome = execution.outcome
        processed_block_index = execution.processed_block_index
        advanced = current_block.block_type != BlockType.INTERACTION
        if current_block.block_type == BlockType.INTERACTION:
            advanced = execution.has_user_input and outcome.input_accepted
        if (
            processed_block_index == session.profile_draft_block_index
            and not outcome.content.strip()
        ):
            msg = "profile draft is empty"
            raise ProfileResearchError(msg)

        trailing_events: list[dict[str, Any]] = []
        if advanced:
            session.variables.update(outcome.variable_updates)
            self._update_context(
                session,
                current_block=current_block,
                user_input=user_input,
                outcome=outcome,
            )
            if processed_block_index == session.profile_draft_block_index:
                session.profile_draft = outcome.content.strip()
            session.block_index += 1
        elif (
            current_block.block_type == BlockType.INTERACTION
            and execution.has_user_input
        ):
            trailing_events.append(
                _event(
                    "interaction",
                    execution.rerendered_interaction,
                    generated_block_bid=(
                        f"profile-research:{session.session_id}:{processed_block_index}"
                    ),
                    run_session_bid=session.session_id,
                    is_terminal=False,
                )
            )

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
        all_events = [*execution.streamed_events, *trailing_events, terminal_event]
        self._remember_request(
            session,
            request_id=request_id,
            expected_block_index=expected_block_index,
            user_input=user_input,
            events=all_events,
        )
        self.store.save(session)
        return [*trailing_events, terminal_event]

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
            admission = self._admit_run(
                user_bid=normalized_user_bid,
                session_id=normalized_session_id,
                purpose=normalized_purpose,
                user_input=user_input,
                expected_block_index=expected_block_index,
                request_id=request_id,
            )
            if admission.immediate_events is not None:
                if admission.refresh_session:
                    self.store.save(admission.session)
                yield from admission.immediate_events
                return

            execution = yield from self._execute_block(
                session=admission.session,
                user_input=admission.user_input,
            )
            yield from self._finalize_run(
                session=admission.session,
                execution=execution,
                user_input=admission.user_input,
                expected_block_index=expected_block_index,
                request_id=request_id,
            )
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
