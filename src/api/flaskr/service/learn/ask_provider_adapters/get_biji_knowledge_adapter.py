"""Get Biji (Dedao Brain) knowledge base ask provider adapter.

Calls the Get Biji OpenAPI semantic recall endpoint to retrieve knowledge
snippets for the learner's question, then synthesizes a natural-language
answer through the built-in ask LLM when the runtime provides
``llm_context_stream_factory``. Without that factory it falls back to
emitting the formatted snippets directly.

API reference: https://www.biji.com/openapi
"""

from typing import Any, Generator

import requests
from flask import Flask

from flaskr.i18n import _

from .consts import ASK_PROVIDER_GET_BIJI_KNOWLEDGE

from .base import (
    AskProviderChunk,
    AskProviderConfigError,
    AskProviderError,
    AskProviderRuntime,
    AskProviderTimeoutError,
)
from .common import extract_text, provider_timeout_seconds, raise_for_provider_response


GET_BIJI_BASE_URL = "https://openapi.biji.com"
GET_BIJI_KNOWLEDGE_RECALL_PATH = "/open/api/v1/resource/recall/knowledge"

DEFAULT_TOP_K = 5
MAX_TOP_K = 10

NO_RESULTS_CONTEXT = (
    "No relevant material was found in the knowledge base for this question."
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _top_k_value(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_TOP_K
    return max(1, min(parsed, MAX_TOP_K))


def _raise_for_api_error(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("success") is not False:
        return

    error = payload.get("error")
    message = ""
    reason = ""
    if isinstance(error, dict):
        message = _normalize_text(error.get("message"))
        reason = _normalize_text(error.get("reason"))
    if not message:
        message = extract_text(error) or extract_text(payload) or str(payload)
    detail = f"{message} (reason: {reason})" if reason else message
    raise AskProviderError(f"get_biji_knowledge error: {detail}")


def _extract_results(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    return []


def _format_result(index: int, result: Any) -> str:
    if not isinstance(result, dict):
        content = extract_text(result) or _normalize_text(result)
        return f"{index}. {content}".strip() if content else ""

    title = _normalize_text(result.get("title"))
    content = extract_text(result.get("content")) or extract_text(result)
    created_at = _normalize_text(result.get("created_at"))

    if not title and not content:
        return ""

    header = f"{index}. **{title}**" if title else f"{index}."
    parts = [header]
    if content:
        parts.append(content)
    if created_at:
        parts.append(f"({created_at})")
    return "\n".join(parts).strip()


class GetBijiKnowledgeAskProviderAdapter:
    provider = ASK_PROVIDER_GET_BIJI_KNOWLEDGE

    def stream_answer(
        self,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, Any]],
        provider_config: dict[str, Any],
        runtime: AskProviderRuntime | None = None,
    ) -> Generator[AskProviderChunk, None, None]:
        del app, user_id, messages

        config = provider_config.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        api_key = _normalize_text(config.get("api_key"))
        client_id = _normalize_text(config.get("client_id"))
        topic_id = _normalize_text(config.get("topic_id"))
        if not api_key or not client_id or not topic_id:
            raise AskProviderConfigError(
                "get_biji_knowledge api_key/client_id/topic_id are required "
                "in ask_provider_config.config"
            )

        payload = {
            "topic_id": topic_id,
            "query": user_query,
            "top_k": _top_k_value(config.get("top_k")),
        }
        headers = {
            "Authorization": api_key,
            "X-Client-ID": client_id,
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{GET_BIJI_BASE_URL}{GET_BIJI_KNOWLEDGE_RECALL_PATH}",
                headers=headers,
                json=payload,
                timeout=(5, provider_timeout_seconds()),
            )
        except requests.Timeout as exc:
            raise AskProviderTimeoutError("get_biji_knowledge request timeout") from exc
        except requests.RequestException as exc:
            raise AskProviderError(f"get_biji_knowledge request failed: {exc}") from exc

        response = raise_for_provider_response(response, self.provider)
        try:
            payload_data = response.json()
        except ValueError as exc:
            raise AskProviderError(
                "get_biji_knowledge response is not valid json"
            ) from exc

        _raise_for_api_error(payload_data)
        results = _extract_results(payload_data)
        formatted_results = [
            formatted
            for formatted in (
                _format_result(index, result)
                for index, result in enumerate(results, start=1)
            )
            if formatted
        ]

        context_factory = getattr(runtime, "llm_context_stream_factory", None)
        if context_factory is not None:
            knowledge_context = (
                "\n\n".join(formatted_results)
                if formatted_results
                else NO_RESULTS_CONTEXT
            )
            for chunk in context_factory(knowledge_context):
                current_content = getattr(chunk, "result", None)
                if isinstance(current_content, str) and current_content:
                    yield AskProviderChunk(content=current_content)
            return

        if not formatted_results:
            yield AskProviderChunk(content=str(_("server.learn.askProviderNoResults")))
            return
        for formatted in formatted_results:
            yield AskProviderChunk(content=formatted + "\n\n")
