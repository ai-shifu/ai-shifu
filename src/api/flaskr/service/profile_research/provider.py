"""Profile research model adapters for the shared LLM route."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Protocol

from flaskr.api.markdownflow import GatewayModel
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.profile_research.langfuse_tracing import (
    PROFILE_GENERATION_NAME,
    PROFILE_PRIVATE_GENERATION_NAME,
)
from pydantic_ai.direct import model_request
from pydantic_ai.messages import (
    ModelRequest,
    ModelRequestPart,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.settings import ModelSettings

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.profile_research.session import _ProfileResearchSession


# The summary carries every accepted answer of a questionnaire of up to
# MAX_BLOCK_COUNT questions. These calls have never had a gateway-side input cap,
# so the engine's per-turn budget is lifted and the provider's context limit
# stays the only bound.
_PRIVATE_COMPLETION_INPUT_BUDGET_BYTES = sys.maxsize


class ProfileResearchCompletion(Protocol):
    """One-shot text completion used for the profile summary and answer import."""

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Return the model's text reply to system and user messages."""
        ...


def _gateway_model(
    app: Flask,
    session: _ProfileResearchSession,
    span: object,
    *,
    model: str,
    generation_name: str,
    **budget: int,
) -> GatewayModel:
    """Keep every profile call on the shared gateway and the free usage policy."""
    return GatewayModel(
        app,
        model,
        user_id=session.user_bid,
        span=span,
        generation_name=generation_name,
        **budget,
        usage_context=UsageContext(
            user_bid=session.user_bid,
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        ),
        usage_scene=BILL_USAGE_SCENE_DEBUG,
        billable=0,
    )


def create_profile_research_model(
    app: Flask, session: _ProfileResearchSession, span: object
) -> GatewayModel:
    """Build the questionnaire agent's model."""
    return _gateway_model(
        app,
        session,
        span,
        model=session.model,
        generation_name=PROFILE_GENERATION_NAME,
    )


class _ProfileResearchGatewayCompletion:
    """Run private profile completions through the engine's gateway model."""

    def __init__(
        self, app: Flask, session: _ProfileResearchSession, span: object
    ) -> None:
        self._app = app
        self._session = session
        self._span = span

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Return the reply text; the session supplies an unset model or temperature."""
        if not messages:
            msg = "No messages provided"
            raise ValueError(msg)
        parts: list[ModelRequestPart] = []
        for message in messages:
            if message["role"] == "system":
                parts.append(SystemPromptPart(message["content"]))
            elif message["role"] == "user":
                parts.append(UserPromptPart(message["content"]))
            else:
                msg = f"Unsupported message role: {message['role']}"
                raise ValueError(msg)
        gateway = _gateway_model(
            self._app,
            self._session,
            self._span,
            model=model or self._session.model,
            generation_name=PROFILE_PRIVATE_GENERATION_NAME,
            input_budget_bytes=_PRIVATE_COMPLETION_INPUT_BUDGET_BYTES,
        )
        # A loop per call, closed afterwards: request threads keep no loop between calls.
        response = asyncio.run(
            model_request(
                gateway,
                [ModelRequest(parts=parts)],
                model_settings=ModelSettings(
                    temperature=(
                        temperature
                        if temperature is not None
                        else self._session.temperature
                    )
                ),
            )
        )
        return "".join(
            part.content for part in response.parts if isinstance(part, TextPart)
        )
