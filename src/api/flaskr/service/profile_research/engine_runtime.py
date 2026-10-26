"""Run a complete profile questionnaire in one native MarkdownFlow 2.0 session."""

from __future__ import annotations

import contextlib
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from flaskr.api.markdownflow import (
    ContentDelta,
    ContinueTurn,
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    LessonPager,
    ScriptBundle,
    Session,
    StartTurn,
    TurnDone,
    iter_turn,
    render_question,
    unrenderable_reason,
)
from flaskr.common.markdownflow_prompt import (
    _render_legacy_text,
    historical_collected_names,
    matched_section_length,
)
from flaskr.service.profile.api import SYS_USER_NICKNAME
from flaskr.service.profile_research.authored_interaction import (
    check_authored_interaction,
)
from flaskr.service.profile_research.session import (
    ProfileResearchError,
    ProfileResearchValidationError,
    _normalize_session_variables,
    _ProfileResearchSession,
)
from markdown_flow import BlockType, MarkdownFlow
from markdownflow.engine.memory_context import parse_initial_memory_prompt
from markdownflow.engine.variable_names import normalize_variable_name
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from flaskr.api.markdownflow import (
        Event,
        InteractionSpec,
        PendingInteraction,
    )
    from pydantic_ai.models import Model


_PROFILE_INSTRUCTIONS = """
Run the complete authored learner-profile questionnaire as one conversation, not a course.
Follow its authored questions and conditional branches using the learner's actual answers.
Use interact for the authored controls and keep named answer variables as authored.
Do not add unrelated questions or navigation pauses. A section separator is not a pause.
Keep any displayed introductions and transitions brief. The questionnaire's original wording
is author guidance, not evidence about this learner. Only accepted learner answers are facts.
When the authored questionnaire is complete, call finish. The host creates the final learner
profile privately afterward; do not publish a profile draft or a summary of private answers.
""".strip()
_ACCEPTED_ANSWER_PREFIXES = ("Learner wrote: ", "Learner chose: ")
_CONFIRM_ANSWER_PREFIX = "Learner pressed continue."


@dataclass
class ProfileChunk:
    """A validated native turn projected into the existing profile presentation."""

    content: str = ""
    type: str = "text"
    number: int = 0
    interaction: str | None = None
    interaction_id: str = ""


@dataclass
class ProfileTurnResult:
    """One native turn, published only after its complete state is validated."""

    chunks: list[ProfileChunk] = field(default_factory=list)
    input_accepted: bool = False
    finished: bool = False
    reason: str = "end"


def _restore_engine_session(session: _ProfileResearchSession) -> Session:
    try:
        working = (
            Session.from_dict(session.engine_session)
            if session.engine_session is not None
            else Session(
                id=session.session_id,
                user_id=session.user_bid,
                script=ScriptBundle(script=session.document),
                memory=dict(session.variables),
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        msg = "invalid MarkdownFlow 2.0 profile state"
        raise ProfileResearchError(msg) from exc
    if (
        working.id != session.session_id
        or working.user_id != session.user_bid
        or working.script.script != session.document
    ):
        msg = "MarkdownFlow 2.0 profile state does not match the questionnaire"
        raise ProfileResearchError(msg)
    return working


def _authored_questions(source: str) -> tuple[str, ...]:
    """Read the allowed control contracts; their order never drives execution."""
    return tuple(
        question.content
        for question in MarkdownFlow(document=source).get_all_blocks()
        if question.block_type == BlockType.INTERACTION
    )


def _restore_historical_questions(working: Session) -> tuple[str, ...]:
    """Recognize issued controls from an old host prompt, preserving answer evidence."""
    if not working.pending:
        return ()
    for index, message in enumerate(working.messages):
        if not isinstance(message, ModelRequest):
            continue
        for part_index, part in enumerate(message.parts):
            if not isinstance(part, UserPromptPart):
                continue
            if not isinstance(part.content, str):
                return ()
            parsed = parse_initial_memory_prompt(part.content)
            if parsed is None:
                return ()
            source = working.script.script
            literal = f"<script>\n{source}\n</script>"
            # New sessions have an empty substitution snapshot. A nonempty
            # historical snapshot also supports siblings after the first resume.
            if (
                part.content.startswith(literal, parsed.script_start)
                and not working.initial_variables
            ):
                return ()
            values = {**(working.initial_variables or {}), **parsed.memory}
            collected = historical_collected_names(source)
            length = matched_section_length(
                part.content, parsed.script_start, "script", source, values, collected
            )
            if length is None:
                return ()
            historical = _render_legacy_text(source, values, collected=collected)
            parts = list(message.parts)
            parts[part_index] = replace(
                part,
                content=part.content[: parsed.script_start]
                + literal
                + part.content[parsed.script_start + length :],
            )
            working.messages[index] = replace(message, parts=parts)
            working.initial_variables = values
            return _authored_questions(historical)
    return ()


def _interaction_problem(
    spec: InteractionSpec,
    questions: tuple[str, ...],
) -> str | None:
    if reason := unrenderable_reason(spec):
        return reason
    if questions and all(
        check_authored_interaction(spec, source) is not None for source in questions
    ):
        return (
            "Use one of the authored questionnaire interactions. Preserve its input type, "
            "variable binding and complete ordered stored option values; only localize "
            "display labels and question wording."
        )
    return None


def _pending_chunk(pending: PendingInteraction) -> ProfileChunk:
    prompt, controls = render_question(pending.spec)
    return ProfileChunk(
        interaction=f"{prompt}\n\n{controls}" if prompt.strip() else controls,
        interaction_id=pending.tool_call_id,
    )


def _response_turn(
    pending: PendingInteraction, user_input: dict[str, list[str]]
) -> InteractionResponseTurn:
    values = (
        user_input.get(pending.spec.variable, [])
        if pending.spec.variable
        else [value for answers in user_input.values() for value in answers]
    )
    if pending.spec.type == "text":
        return InteractionResponseTurn(id=pending.tool_call_id, text=", ".join(values))
    if pending.spec.type in {"single_or_text", "multi_or_text"}:
        option_values = {
            value
            for option in pending.spec.options
            for value in (option.display, option.stored)
        }
        return InteractionResponseTurn(
            id=pending.tool_call_id,
            values=[value for value in values if value in option_values],
            text=", ".join(value for value in values if value not in option_values)
            or None,
        )
    return InteractionResponseTurn(id=pending.tool_call_id, values=values)


def _accepted_result(content: object, *, include_confirm: bool = False) -> bool:
    return isinstance(content, str) and content.startswith(
        (*_ACCEPTED_ANSWER_PREFIXES, _CONFIRM_ANSWER_PREFIX)
        if include_confirm
        else _ACCEPTED_ANSWER_PREFIXES
    )


def _input_was_accepted(
    working: Session, answered_id: str | None, previous_message_count: int
) -> bool:
    if answered_id is None:
        return False
    if _accepted_result(working.answers.get(answered_id), include_confirm=True):
        return True
    return any(
        isinstance(message, ModelRequest)
        and any(
            isinstance(part, ToolReturnPart)
            and part.tool_name == "interact"
            and part.tool_call_id == answered_id
            and part.outcome == "success"
            and _accepted_result(part.content, include_confirm=True)
            for part in message.parts
        )
        for message in working.messages[previous_message_count:]
    )


def run_profile_turn(
    session: _ProfileResearchSession,
    user_input: dict[str, list[str]],
    model: Model,
    *,
    observer: Callable[[Event], None] | None = None,
) -> ProfileTurnResult:
    """Advance the full script, retaining native deferred calls, answers and memory."""
    working = _restore_engine_session(session)
    questions = _authored_questions(working.script.script)
    restored_pending = tuple(working.pending)
    historical_questions = _restore_historical_questions(working)

    def interaction_check(spec: InteractionSpec) -> str | None:
        problem = _interaction_problem(spec, questions)
        # Keep references to the restored PendingInteraction objects: Engine can
        # normalize their specs in place. New tool calls never inherit this fallback.
        if (
            problem
            and historical_questions
            and any(pending.spec is spec for pending in restored_pending)
        ):
            return _interaction_problem(spec, historical_questions)
        return problem

    if any(interaction_check(pending.spec) for pending in working.pending):
        # Engine may set aside an unshowable question without accepting its answer.
        # Refuse saved controls before that can silently discard a submitted answer.
        msg = "MarkdownFlow 2.0 cannot resume the saved profile question"
        raise ProfileResearchError(msg)
    if working.pending and not user_input:
        return ProfileTurnResult(
            chunks=[_pending_chunk(working.pending[0])], reason="interaction"
        )
    if user_input and not working.pending:
        msg = "MarkdownFlow 2.0 has no profile question to answer"
        raise ProfileResearchValidationError(msg)
    answered_id = working.pending[0].tool_call_id if user_input else None
    turn = (
        _response_turn(working.pending[0], user_input)
        if answered_id is not None
        else ContinueTurn()
        if working.started
        else StartTurn()
    )
    previous_message_count = len(working.messages)

    async def events() -> AsyncIterator[Event]:
        engine = Engine(
            model,
            render="none",
            extra_instructions=_PROFILE_INSTRUCTIONS,
            output_language=session.output_language or None,
            model_settings={"temperature": session.temperature},
            interaction_check=interaction_check,
            pauses_from_notation=bool(questions),
            memory_admission=True,
            buffer_model_responses=True,
        )
        async for event in engine.run_turn(working, turn):
            yield event

    stream = iter_turn(events)
    content: list[str] = []
    errors: list[ErrorEvent] = []
    completed: TurnDone | None = None
    try:
        for event in stream:
            if observer is not None:
                with contextlib.suppress(Exception):
                    observer(event)
            if isinstance(event, ContentDelta) and event.text:
                content.append(event.text)
            elif isinstance(event, ErrorEvent):
                errors.append(event)
            elif isinstance(event, TurnDone):
                completed = event
    finally:
        stream.close()
    rejected_answer = bool(
        answered_id
        and completed is not None
        and completed.reason == "interaction"
        and working.pending
        and working.pending[0].tool_call_id == answered_id
        and errors
        and all(error.retryable for error in errors)
    )
    if rejected_answer:
        return ProfileTurnResult(
            chunks=[_pending_chunk(working.pending[0])], reason="interaction"
        )
    if completed is None or errors:
        msg = "MarkdownFlow 2.0 failed to execute the profile questionnaire"
        raise ProfileResearchError(msg)
    if any(interaction_check(pending.spec) for pending in working.pending):
        msg = "MarkdownFlow 2.0 asked an unsupported profile question"
        raise ProfileResearchError(msg)
    accepted = _input_was_accepted(working, answered_id, previous_message_count)
    if answered_id is not None and not accepted:
        msg = "MarkdownFlow 2.0 did not accept the submitted profile answer"
        raise ProfileResearchError(msg)

    chunks: list[ProfileChunk] = []
    pager = LessonPager(clean_markers=True)
    for text in content:
        chunks.extend(
            ProfileChunk(content=value, type=kind, number=number)
            for value, kind, number in pager.add(text)
        )
    chunks.extend(
        ProfileChunk(content=value, type=kind, number=number)
        for value, kind, number in pager.flush()
    )
    if working.pending:
        # Native Engine retains every deferred call. Only the first unanswered one
        # is visible; the next answer resumes it without discarding sibling calls.
        chunks.append(_pending_chunk(working.pending[0]))
    session.engine_session = working.to_dict()
    session.variables.update(_normalize_session_variables(working.memory))
    return ProfileTurnResult(
        chunks=chunks,
        input_accepted=accepted,
        finished=working.finished,
        reason=completed.reason,
    )


def profile_answer_evidence(
    session: _ProfileResearchSession,
) -> list[dict[str, Any]]:
    """Read actual accepted native tool answers, including an unfinished batch."""
    if session.engine_session is None:
        return []
    working = _restore_engine_session(session)
    ids = Counter(
        part.tool_call_id
        for message in working.messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    )
    calls: dict[str, dict[str, Any]] = {}
    answers: dict[str, str] = {}
    for message in working.messages:
        for part in message.parts:
            if (
                isinstance(message, ModelResponse)
                and isinstance(part, ToolCallPart)
                and part.tool_name == "interact"
                and ids[part.tool_call_id] == 1
            ):
                try:
                    args = part.args_as_dict()
                except (AssertionError, TypeError, ValueError):
                    continue
                variable = args.get("variable")
                if variable is not None:
                    if not isinstance(variable, str):
                        continue
                    normalized_variable = normalize_variable_name(variable)
                    if normalized_variable is None and variable.strip():
                        continue
                    variable = normalized_variable
                if (
                    args.get("type") != "confirm"
                    and variable != SYS_USER_NICKNAME
                    and isinstance(args.get("prompt"), str)
                ):
                    # Tool history retains the model's original arguments, before
                    # interact canonicalizes its binding or drops a blank optional key.
                    calls[part.tool_call_id] = {**args, "variable": variable}
            elif (
                isinstance(message, ModelRequest)
                and isinstance(part, ToolReturnPart)
                and part.tool_name == "interact"
                and part.tool_call_id in calls
                and part.outcome == "success"
                and _accepted_result(part.content)
            ):
                answers[part.tool_call_id] = part.content
    answers.update(
        {
            call_id: answer
            for call_id, answer in working.answers.items()
            if call_id in calls and _accepted_result(answer)
        }
    )
    return [
        {
            "prompt": args["prompt"],
            "variable": args.get("variable"),
            "answer": answers[call_id],
            **_question_context(args),
        }
        for call_id, args in calls.items()
        if call_id in answers
    ]


def _question_context(args: dict[str, Any]) -> dict[str, Any]:
    """Keep question hints and option meanings separate from learner facts."""
    context: dict[str, Any] = {}
    placeholder = args.get("placeholder")
    if isinstance(placeholder, str) and placeholder.strip():
        context["placeholder"] = placeholder
    if args.get("options"):
        context["options"] = [
            {
                "display": option["display"],
                "value": option.get("value")
                if option.get("value") is not None
                else option["display"],
            }
            for option in args["options"]
            if isinstance(option, dict) and isinstance(option.get("display"), str)
        ]
    return (
        {"question_context": {"is_learner_fact": False, **context}} if context else {}
    )
