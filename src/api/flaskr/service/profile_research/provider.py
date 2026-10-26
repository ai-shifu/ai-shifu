"""MarkdownFlow provider adapter for the shared LLM route."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.api.llm import chat_llm
from flaskr.api.markdownflow import GatewayModel
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.profile_research.langfuse_tracing import (
    PROFILE_GENERATION_NAME,
    PROFILE_PRIVATE_GENERATION_NAME,
)
from markdown_flow import LLMProvider

if TYPE_CHECKING:
    from collections.abc import Generator

    from flask import Flask
    from flaskr.service.profile_research.session import _ProfileResearchSession


def create_profile_research_model(
    app: Flask, session: _ProfileResearchSession, span: object
) -> GatewayModel:
    """Keep agent tools on the shared gateway and the existing free usage policy."""
    return GatewayModel(
        app,
        session.model,
        user_id=session.user_bid,
        span=span,
        generation_name=PROFILE_GENERATION_NAME,
        usage_context=UsageContext(
            user_bid=session.user_bid,
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        ),
        usage_scene=BILL_USAGE_SCENE_DEBUG,
        billable=0,
    )


class _ProfileResearchLLMProvider(LLMProvider):
    """Thin adapter that keeps MarkdownFlow on the shared LLM route."""

    def __init__(
        self, app: Flask, session: _ProfileResearchSession, span: object
    ) -> None:
        self._app = app
        self._session = session
        self._span = span
        self.output_chunks: list[str] = []

    def _invoke(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None,
        temperature: float | None,
        stream: bool,
    ) -> Generator[str, None, None]:
        if not messages:
            msg = "No messages provided"
            raise ValueError(msg)
        actual_model = model or self._session.model
        actual_temperature = (
            temperature if temperature is not None else self._session.temperature
        )
        responses = chat_llm(
            self._app,
            self._session.user_bid,
            self._span,
            model=actual_model,
            messages=messages,
            stream=stream,
            generation_name=PROFILE_PRIVATE_GENERATION_NAME,
            temperature=actual_temperature,
            usage_context=UsageContext(
                user_bid=self._session.user_bid,
                usage_scene=BILL_USAGE_SCENE_DEBUG,
                billable=0,
            ),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        )
        for response in responses:
            if response.result:
                self.output_chunks.append(response.result)
                yield response.result

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        return "".join(
            self._invoke(
                messages,
                model=model,
                temperature=temperature,
                stream=False,
            )
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Generator[str, None, None]:
        yield from self._invoke(
            messages,
            model=model,
            temperature=temperature,
            stream=True,
        )
