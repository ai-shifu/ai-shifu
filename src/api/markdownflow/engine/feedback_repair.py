"""Repair a missing or rejected answer-feedback tool call once."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from .tools import Deps

if TYPE_CHECKING:
    from pydantic_ai import RunContext
    from pydantic_ai.messages import ModelResponse
    from pydantic_ai.models import ModelRequestContext


_TERMINAL_TOOLS = frozenset({"interact", "finish"})


class CompleteFeedback(AbstractCapability[Deps]):
    """Target only missing or rejected tool calls on the native retry."""

    async def before_model_request(
        self, ctx: RunContext[Deps], request_context: ModelRequestContext
    ) -> ModelRequestContext:
        """Pass tool errors and the next expected action to the model."""
        deps = ctx.deps
        if not deps.stream_answer_feedback:
            return request_context
        last = request_context.messages[-1]
        retries = (
            [part for part in last.parts if isinstance(part, RetryPromptPart)]
            if isinstance(last, ModelRequest)
            else []
        )
        if not isinstance(last, ModelRequest) or not retries:
            deps.feedback_repair_tools = None
            return request_context
        if deps.feedback_repair_attempted:
            message = "Answer feedback tool calls remain incomplete after one repair"
            raise UnexpectedModelBehavior(message)

        rejected = tuple(p.tool_name for p in retries if p.tool_name is not None)
        offered_tools = {
            tool.name
            for tool in request_context.model_request_parameters.function_tools
        }
        completed = {
            part.tool_name for part in last.parts if isinstance(part, ToolReturnPart)
        }
        answer_id = next(iter(deps.direction_sections))
        if (
            len(retries) == 1
            and not completed
            and not (set(rejected) & (offered_tools - _TERMINAL_TOOLS))
        ):
            # A printed control already tells us which tool is missing.
            if deps.interaction_markup_pending:
                deps.feedback_repair_tools = ("interact",)
                action = "interact"
            else:
                deps.feedback_repair_tools = ()
                action = "interact or finish"
            notice = (
                f"Send only the actual {action} tool call for the next authored "
                f"action, with feedback for current answer_id {answer_id}. "
                "Use ordinary authored_help with its exact rule when there is no authored "
                "checking-direction count. Do not skip a required learner action."
            )
        else:
            if (
                len(rejected) != len(retries)
                or not set(rejected) <= offered_tools
                or completed.intersection(rejected)
            ):
                message = "Cannot safely identify the rejected feedback tool batch"
                raise UnexpectedModelBehavior(message)
            deps.feedback_repair_tools = rejected
            notice = (
                f"Retry only the rejected calls, in this order: {', '.join(rejected)}. "
                f"Use current answer_id {answer_id}. Do not repeat successful tools."
            )
        deps.feedback_repair_attempted = True
        parts = [
            replace(
                part,
                content=(
                    part.content
                    if isinstance(part.content, str)
                    else part.model_response()
                )
                + "\n\n"
                + notice
                + " Do not write any prose.",
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
        """Drop repair prose and reject unrelated tool calls before execution."""
        deps = ctx.deps
        if not deps.stream_answer_feedback:
            return response
        if response.finish_reason not in (None, "stop", "tool_call"):
            message = "Answer feedback response was interrupted"
            raise UnexpectedModelBehavior(message)
        expected = deps.feedback_repair_tools
        if expected is None:
            return response
        calls = tuple(
            part.tool_name for part in response.parts if isinstance(part, ToolCallPart)
        )
        matches = (
            calls == expected
            if expected
            else len(calls) == 1 and calls[0] in _TERMINAL_TOOLS
        )
        if not matches:
            message = "Answer feedback repair did not provide the requested tools"
            raise UnexpectedModelBehavior(message)
        return replace(
            response,
            parts=[part for part in response.parts if not isinstance(part, TextPart)],
        )
