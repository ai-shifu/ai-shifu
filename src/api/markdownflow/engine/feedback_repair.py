"""Repair a missing or rejected answer-feedback tool call once."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from .tools import Deps, remember_target

if TYPE_CHECKING:
    from pydantic_ai import RunContext
    from pydantic_ai.models import ModelRequestContext


_TERMINAL_TOOLS = frozenset({"interact", "finish"})


def _remember_call_target(deps: Deps, call: ToolCallPart) -> tuple[str, str] | None:
    args = call.args_as_dict()
    key, scope = args.get("key"), args.get("scope", "session")
    if not isinstance(key, str) or scope not in ("session", "user"):
        return None
    return remember_target(deps, key, scope)


def _memory_repair_targets(
    deps: Deps,
    response: ModelResponse,
    retries: list[RetryPromptPart],
    returned: list[ToolReturnPart],
) -> dict[int, tuple[str, str]]:
    """Bind repair slots to failed memory calls by the original call ID."""
    writes = [
        part
        for part in response.parts
        if isinstance(part, ToolCallPart) and part.tool_name == "remember"
    ]
    targets = {part.tool_call_id: _remember_call_target(deps, part) for part in writes}
    completed = {
        targets.get(part.tool_call_id)
        for part in returned
        if part.tool_name == "remember"
    }
    repair_targets = {}
    for index, retry in enumerate(retries):
        if retry.tool_name != "remember":
            continue
        target = targets.get(retry.tool_call_id)
        if (
            len(targets) != len(writes)
            or target is None
            or None in completed
            or target in completed
        ):
            message = (
                "Cannot safely identify a distinct target for the rejected memory write"
            )
            raise UnexpectedModelBehavior(message)
        repair_targets[index] = target
    return repair_targets


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
        returned = [part for part in last.parts if isinstance(part, ToolReturnPart)]
        completed = {part.tool_name for part in returned}
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
                or completed.intersection(rejected) - {"remember"}
            ):
                message = "Cannot safely identify the rejected feedback tool batch"
                raise UnexpectedModelBehavior(message)
            deps.feedback_repair_tools = rejected
            notice = (
                f"Retry only the rejected calls, in this order: {', '.join(rejected)}. "
                f"Use current answer_id {answer_id}. Do not repeat successful tools."
            )
            if "remember" in rejected:
                response = next(
                    (
                        m
                        for m in reversed(request_context.messages[:-1])
                        if isinstance(m, ModelResponse)
                    ),
                    None,
                )
                if response is None:
                    message = "Cannot find the response with the rejected memory write"
                    raise UnexpectedModelBehavior(message)
                deps.feedback_repair_memory_targets = _memory_repair_targets(
                    deps, response, retries, returned
                )
                notice += " Keep each rejected remember call's original key and scope."
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
            # This hook runs before the SDK records the response in history.
            if any(isinstance(part, TextPart) for part in response.parts):
                deps.interrupted_feedback_response = response
            message = "Answer feedback response was interrupted"
            raise UnexpectedModelBehavior(message)
        expected = deps.feedback_repair_tools
        if expected is None:
            return response
        calls = [part for part in response.parts if isinstance(part, ToolCallPart)]
        matches = (
            tuple(call.tool_name for call in calls) == expected
            if expected
            else len(calls) == 1 and calls[0].tool_name in _TERMINAL_TOOLS
        )
        if not matches:
            message = "Answer feedback repair did not provide the requested tools"
            raise UnexpectedModelBehavior(message)
        if any(
            _remember_call_target(deps, calls[index]) != target
            for index, target in deps.feedback_repair_memory_targets.items()
        ):
            message = "Answer feedback repair changed a rejected memory write's target"
            raise UnexpectedModelBehavior(message)
        return replace(
            response,
            parts=[part for part in response.parts if not isinstance(part, TextPart)],
        )
