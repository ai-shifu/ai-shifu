"""Complete one split feedback response before running its pending action."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from .interaction_markup import contains_interaction_markup
from .tools import Deps, feedback_response_problem

if TYPE_CHECKING:
    from pydantic_ai import RunContext
    from pydantic_ai.messages import ModelResponse
    from pydantic_ai.models import ModelRequestContext


@dataclass
class FeedbackDraft:
    """The part already supplied for this answer, owned by the current run."""

    missing: Literal["action", "prose", "both"]
    prose_delivered: bool = False
    action: ToolCallPart | None = None
    required_prose_error: str | None = None
    batch: bool = False
    rejected_tools: tuple[str, ...] = ()


_REPAIRABLE_TOOLS = frozenset(
    {
        "interact",
        "finish",
        "remember",
        "recall",
        "read_exercise_history",
        "calculate_exercise_statistics",
    }
)


class CompleteFeedback(AbstractCapability[Deps]):
    """Use one native repair request without repeating learner-visible teaching."""

    async def before_model_request(
        self, ctx: RunContext[Deps], request_context: ModelRequestContext
    ) -> ModelRequestContext:
        """Explain which part the next response should supply."""
        deps = ctx.deps
        draft = deps.feedback_draft
        if draft is None:
            return request_context
        last = request_context.messages[-1]
        retries = (
            [part for part in last.parts if isinstance(part, RetryPromptPart)]
            if isinstance(last, ModelRequest)
            else []
        )
        if not isinstance(last, ModelRequest) or not retries:
            deps.feedback_draft = None
            return request_context
        if deps.feedback_repair_attempted:
            message = "Answer feedback remains incomplete after one repair"
            raise UnexpectedModelBehavior(message)
        deps.feedback_repair_attempted = True
        if draft.missing == "prose" and (
            not draft.required_prose_error
            or any(
                not isinstance(part.content, str)
                or not part.content.startswith(draft.required_prose_error)
                for part in retries
            )
        ):
            # The tool reported an actual argument or control problem, not just missing prose.
            draft.missing = "both"
            draft.action = None
        answer_id = next(iter(deps.direction_sections))
        if draft.batch:
            rejected = tuple(p.tool_name for p in retries if p.tool_name is not None)
            completed = {
                part.tool_name
                for part in last.parts
                if isinstance(part, ToolReturnPart)
            }
            if (
                len(rejected) != len(retries)
                or not set(rejected) <= _REPAIRABLE_TOOLS
                or completed.intersection(rejected)
            ):
                message = "Cannot safely identify the rejected feedback tool batch"
                raise UnexpectedModelBehavior(message)
            draft.rejected_tools = rejected
            notice = (
                "The learner already saw the teaching. Do not write any prose. "
                f"Retry only the rejected calls, in this order: {', '.join(rejected)}. "
                f"Use current answer_id {answer_id}. Do not repeat successful tools."
            )
        elif draft.missing == "action":
            status = (
                "The learner already saw the teaching. "
                if draft.prose_delivered
                else "This response only needs a corrected tool call. "
            )
            notice = (
                status
                + "Send only the actual interact or finish tool call for the next authored "
                f"action, with feedback for current answer_id {answer_id}. Do not write prose. "
                "Use ordinary authored_help with its exact rule when there is no authored "
                "checking-direction count. Do not skip a required learner action."
            )
        elif draft.missing == "prose":
            notice = (
                "The original action is held until its teaching is delivered. "
                "Write only the complete authored teaching as prose. The host will "
                "validate and run the original action after it. Do not print tool tags."
            )
        else:
            notice = (
                "In one response, send the required teaching and the correct actual tool "
                f"call, with valid feedback for current answer_id {answer_id}. "
                "For a structured checking direction, send only the corrected interact "
                "call and no free prose."
            )
        parts = [
            replace(
                part,
                content=(
                    part.content
                    if isinstance(part.content, str)
                    else part.model_response()
                ).removesuffix("; correct the whole response before any display")
                + "\n\n"
                + notice,
            )
            if isinstance(part, RetryPromptPart)
            else part
            for part in last.parts
        ]
        return replace(
            request_context,
            messages=[*request_context.messages[:-1], replace(last, parts=parts)],
        )

    async def after_model_request(
        self,
        ctx: RunContext[Deps],
        *,
        request_context: ModelRequestContext,  # noqa: ARG002 - Capability hook signature.
        response: ModelResponse,
    ) -> ModelResponse:
        """Remember split feedback or combine its missing part before tool validation."""
        deps = ctx.deps
        if not deps.stream_answer_feedback:
            return response
        draft = deps.feedback_draft
        calls = [part for part in response.parts if isinstance(part, ToolCallPart)]
        one_action = len(calls) == 1 and calls[0].tool_name in ("interact", "finish")
        if response.finish_reason not in (None, "stop", "tool_call"):
            message = "Answer feedback response was interrupted"
            raise UnexpectedModelBehavior(message)
        if draft is not None and deps.feedback_repair_attempted:
            if draft.missing == "action":
                matches = (
                    tuple(call.tool_name for call in calls) == draft.rejected_tools
                    if draft.batch
                    else one_action
                )
                if not matches:
                    message = (
                        "Answer feedback repair did not provide the requested tools"
                    )
                    raise UnexpectedModelBehavior(message)
                # Redundant prose was not streamed during the repair request.
                return replace(
                    response,
                    parts=[p for p in response.parts if not isinstance(p, TextPart)],
                )
            if calls or draft.missing == "both":
                if not one_action:
                    message = "Answer feedback repair supplied an unrelated tool"
                    raise UnexpectedModelBehavior(message)
                return response
            text = "".join(
                part.content for part in response.parts if isinstance(part, TextPart)
            )
            if (
                draft.action is not None
                and text.strip()
                and not contains_interaction_markup(
                    text, deps.literal_interaction_markup
                )
            ):
                return replace(
                    response,
                    parts=[
                        *response.parts,
                        replace(draft.action, tool_call_id=f"call_mdf_{uuid4().hex}"),
                    ],
                )
            message = "Answer feedback repair did not provide teaching"
            raise UnexpectedModelBehavior(message)
        if deps.feedback_repair_attempted:
            return response
        if deps.feedback_response_displayed and (
            not calls or one_action or len(calls) > 1
        ):
            deps.feedback_draft = FeedbackDraft(
                "action", prose_delivered=True, batch=len(calls) > 1
            )
        elif one_action:
            problem, _ = feedback_response_problem(deps, response)
            with_body = replace(response, parts=[TextPart("Feedback"), *response.parts])
            if not problem:
                deps.feedback_draft = FeedbackDraft("action")
            elif (
                not deps.feedback_text_delivered
                and not deps.interaction_markup_pending
                and feedback_response_problem(deps, with_body)[0] is None
            ):
                deps.feedback_draft = FeedbackDraft(
                    "prose", action=calls[0], required_prose_error=problem
                )
            else:
                deps.feedback_draft = FeedbackDraft("both")
        return response
