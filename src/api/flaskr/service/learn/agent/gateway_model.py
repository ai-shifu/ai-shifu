"""Let the MarkdownFlow 2.0 engine call models through this project's own LLM gateway.

The engine is built on pydantic-ai, which normally opens its own connection to a provider. That
would bypass everything `chat_llm` already does: provider routing, credentials, billing, usage
metering and Langfuse tracing. `GatewayModel` is a pydantic-ai `Model` that forwards each request
to `chat_llm` instead, so an agent lesson is billed and traced exactly like every other LLM call
here.

`chat_llm` is a synchronous generator and the engine is asyncio throughout. This module does not
solve that: it is written to be driven from a thread that owns an event loop, and the bridge that
arranges one is a separate concern. What it does do is yield control between chunks so a caller
sharing the loop is not starved.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from flaskr.api.llm import chat_llm
from flaskr.util.datetime import now_utc
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponseStreamEvent,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.usage import RequestUsage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator
    from datetime import datetime

    from flask import Flask
    from flaskr.api.langfuse import LangfuseObservationHandle
    from flaskr.api.llm import LLMStreamResponse
    from pydantic_ai.settings import ModelSettings
    from pydantic_ai.tools import RunContext, ToolDefinition

# `chat_llm` reports why the provider stopped; pydantic-ai spells the tool-call case differently.
_FINISH_REASONS = {
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_call",
    "content_filter": "content_filter",
}


def _text_of(content: object) -> str:
    """Flatten a user prompt into text: the engine only ever sends text parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return "".join(_text_of(c) for c in content)
    return str(content)


def map_messages(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Turn pydantic-ai's message history into the chat payload `chat_llm` sends.

    System content is merged into a single leading message: several providers reject a second
    system message, and the engine composes its instructions as one block anyway.
    """
    system: list[str] = []
    out: list[dict[str, Any]] = []
    # Instructions live on the request, not among its parts: an agent built with `instructions=`
    # puts its whole system prompt there and nowhere else. Every request in the history carries the
    # value that applied when it was made, so only the last one is in force -- merging them would
    # resend instructions the agent has already moved on from.
    current = next(
        (
            m.instructions
            for m in reversed(messages)
            if isinstance(m, ModelRequest) and m.instructions
        ),
        None,
    )
    if current:
        system.append(current)
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    system.append(_text_of(part.content))
                elif isinstance(part, UserPromptPart):
                    out.append({"role": "user", "content": _text_of(part.content)})
                elif isinstance(part, ToolReturnPart):
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": part.tool_call_id,
                            "content": _text_of(part.model_response_str()),
                        }
                    )
                elif isinstance(part, RetryPromptPart):
                    # A retry aimed at a specific call is a tool result; a bare one is feedback.
                    if part.tool_name:
                        out.append(
                            {
                                "role": "tool",
                                "tool_call_id": part.tool_call_id,
                                "content": part.model_response(),
                            }
                        )
                    else:
                        out.append({"role": "user", "content": part.model_response()})
        elif isinstance(message, ModelResponse):
            text = "".join(p.content for p in message.parts if isinstance(p, TextPart))
            calls = [p for p in message.parts if isinstance(p, ToolCallPart)]
            # ThinkingPart is dropped: reasoning is not part of the conversation the provider
            # expects back, and some of them reject it.
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if calls:
                entry["tool_calls"] = [
                    {
                        "id": call.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": call.tool_name,
                            "arguments": call.args_as_json_str(),
                        },
                    }
                    for call in calls
                ]
            out.append(entry)
    if system:
        out.insert(0, {"role": "system", "content": "\n\n".join(system)})
    return out


def map_tools(parameters: ModelRequestParameters) -> list[dict[str, Any]]:
    """Describe the tools the way the chat API expects.

    Takes `declared_tool_defs`, the set the framework resolved for this request, rather than every
    authored tool: a tool can be withheld until the run reveals it, and sending its schema anyway
    would let the model call a capability the engine has not offered. Note that `tool_defs` is the
    wrong one to reach for -- it is a name lookup over everything, withheld tools included.
    """
    definitions: list[ToolDefinition] = list(parameters.declared_tool_defs.values())
    return [
        {
            "type": "function",
            "function": {
                "name": d.name,
                "description": d.description or "",
                "parameters": d.parameters_json_schema,
            },
        }
        for d in definitions
    ]


# pydantic-ai's names for the sampling knobs, and what the chat API calls them. Anything not
# listed is ignored rather than guessed at.
_SETTING_NAMES = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "stop_sequences",
    "seed",
)


def _settings_to_kwargs(settings: ModelSettings | None) -> dict[str, object]:
    """Carry the sampling settings a caller set on the agent through to the gateway."""
    if not settings:
        return {}
    out: dict[str, object] = {}
    for name in _SETTING_NAMES:
        value = settings.get(name)
        if value is None:
            continue
        out["stop" if name == "stop_sequences" else name] = value
    return out


@dataclass
class GatewayStreamedResponse(StreamedResponse):
    """Reassemble one `chat_llm` stream into the parts pydantic-ai expects."""

    _model_name: str = ""
    _timestamp: datetime = field(default_factory=now_utc)
    _chunks: Any = None

    @property
    def model_name(self) -> str:
        """The model this response came from."""
        return self._model_name

    @property
    def provider_name(self) -> str:
        """Everything here is routed by this project's own gateway."""
        return "ai-shifu"

    @property
    def provider_url(self) -> str:
        """There is no single provider endpoint: the gateway picks one per model."""
        return ""

    @property
    def timestamp(self) -> datetime:
        """When the response started."""
        return self._timestamp

    async def close_stream(self) -> None:
        """Unwind the gateway generator when the run is cancelled.

        The base class raises instead, so without this a host that stops a lesson gets
        `NotImplementedError` and the `chat_llm` generator -- and the provider connection under
        it -- stays open until garbage collection. Safe to call more than once.
        """
        chunks, self._chunks = self._chunks, iter(())
        close = getattr(chunks, "close", None)
        if close is not None:
            close()

    async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
        for chunk in self._chunks:
            if chunk.result:
                for event in self._parts_manager.handle_text_delta(
                    vendor_part_id="content", content=chunk.result
                ):
                    yield event
            for delta in chunk.tool_call_deltas:
                event = self._parts_manager.handle_tool_call_delta(
                    # The index is what stitches one call's arguments back together across
                    # chunks; the name and id only arrive on the first fragment.
                    vendor_part_id=delta.get("index", 0),
                    tool_name=delta.get("name") or None,
                    args=delta.get("arguments") or None,
                    tool_call_id=delta.get("id") or None,
                )
                if event is not None:
                    yield event
            if chunk.finish_reason:
                self.finish_reason = _FINISH_REASONS.get(
                    str(chunk.finish_reason), "stop"
                )
            if chunk.usage:
                self._usage = RequestUsage(
                    input_tokens=int(getattr(chunk.usage, "prompt_tokens", 0) or 0),
                    output_tokens=int(
                        getattr(chunk.usage, "completion_tokens", 0) or 0
                    ),
                )
            # `chat_llm` is a synchronous generator, so nothing here ever awaits on its own.
            # Yield to the loop between chunks so a caller sharing it keeps running.
            await asyncio.sleep(0)


@dataclass(init=False)
class GatewayModel(Model):
    """A pydantic-ai model that calls this project's LLM gateway instead of a provider."""

    def __init__(
        self,
        app: Flask,
        model: str,
        *,
        user_id: str,
        span: LangfuseObservationHandle,
        generation_name: str = "agent_lesson",
        **chat_llm_kwargs: object,
    ) -> None:
        """Bind the gateway call this model makes: which app, model and learner it bills to.

        `span` is required, not optional: `chat_llm` opens a generation on it before it reaches a
        provider, so there is no working call without one.
        """
        super().__init__()
        self._app = app
        self._model = model
        self._user_id = user_id
        self._span = span
        self._generation_name = generation_name
        self._chat_llm_kwargs = chat_llm_kwargs

    @property
    def model_name(self) -> str:
        """The model name handed to the gateway."""
        return self._model

    @property
    def system(self) -> str:
        """The gateway, not a provider: which one it routes to is its own decision."""
        return "ai-shifu"

    def _stream(
        self,
        messages: list[ModelMessage],
        parameters: ModelRequestParameters,
        settings: ModelSettings | None = None,
    ) -> Generator[LLMStreamResponse, None, None]:
        tools = map_tools(parameters)

        kwargs: dict[str, object] = dict(self._chat_llm_kwargs)
        kwargs.update(_settings_to_kwargs(settings))
        if tools:
            kwargs["tools"] = tools
            # No `tool_choice`: some providers reject forcing a choice while reasoning, and the
            # engine relies on the model deciding when to call `interact` or `finish`.
        return chat_llm(
            app=self._app,
            user_id=self._user_id,
            span=self._span,
            model=self._model,
            messages=map_messages(messages),
            generation_name=self._generation_name,
            emit_tool_calls=True,
            **kwargs,
        )

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Run one non-streaming request by draining the stream."""
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        response = GatewayStreamedResponse(
            model_request_parameters=model_request_parameters,
            _model_name=self._model,
            _chunks=self._stream(messages, model_request_parameters, model_settings),
        )
        try:
            async for _ in response:
                pass
        finally:
            await response.close_stream()
        return response.get()

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,  # noqa: ARG002 - part of the signature
    ) -> AsyncIterator[StreamedResponse]:
        """Stream one request; the engine consumes the events as they arrive."""
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        response = GatewayStreamedResponse(
            model_request_parameters=model_request_parameters,
            _model_name=self._model,
            _chunks=self._stream(messages, model_request_parameters, model_settings),
        )
        try:
            yield response
        finally:
            # Leaving the context must unwind the gateway generator too, so an abandoned stream
            # does not outlive the request that started it.
            await response.close_stream()
