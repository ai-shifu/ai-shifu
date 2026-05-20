"""Get Biji Knowledge Base ask provider adapter."""

from typing import Any, Generator

import requests
from flask import Flask

from flaskr.i18n import _

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


def _top_k_value(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 5
    return max(1, min(parsed, 10))


def _extract_results(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    if isinstance(payload.get("results"), list):
        return payload["results"]
    return []


def _check_api_error(payload: Any) -> None:
    if not isinstance(payload, dict):
        return

    success = payload.get("success")
    if success is False:
        message = (
            extract_text(payload.get("error"))
            or extract_text(payload.get("message"))
            or str(payload)
        )
        raise AskProviderError(f"get_biji_knowledge error: {message}")

    code = payload.get("code")
    if code is not None and str(code) not in {"0", "200"}:
        message = (
            extract_text(payload.get("message"))
            or extract_text(payload.get("error"))
            or str(payload)
        )
        raise AskProviderError(f"get_biji_knowledge error: {message}")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _format_result(index: int, result: Any) -> str:
    if not isinstance(result, dict):
        content = extract_text(result) or _normalize_text(result)
        return f"{index}. {content}".strip() + "\n\n"

    title = _normalize_text(result.get("title") or result.get("note_id"))
    content = extract_text(result.get("content")) or extract_text(result)
    created_at = _normalize_text(result.get("created_at"))

    header = f"{index}. **{title}**" if title else f"{index}."
    parts = [header]
    if content:
        parts.extend(["", content])
    if created_at:
        created_at_label = _("server.learn.askProviderResultCreatedAt")
        parts.extend(["", f"{created_at_label}: {created_at}"])
    return "\n".join(parts).strip() + "\n\n"


class GetBijiKnowledgeAskProviderAdapter:
    provider = "get_biji_knowledge"

    def stream_answer(
        self,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, Any]],
        provider_config: dict[str, Any],
        runtime: AskProviderRuntime | None = None,
    ) -> Generator[AskProviderChunk, None, None]:
        del app, user_id, messages, runtime

        config = provider_config.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        api_key = _normalize_text(config.get("api_key"))
        client_id = _normalize_text(config.get("client_id"))
        topic_id = _normalize_text(config.get("topic_id"))
        if not api_key or not client_id or not topic_id:
            raise AskProviderConfigError(
                "get_biji_knowledge api_key/client_id/topic_id are required in ask_provider_config.config"
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

        _check_api_error(payload_data)
        results = _extract_results(payload_data)
        if not results:
            yield AskProviderChunk(content=str(_("server.learn.askProviderNoResults")))
            return

        for index, result in enumerate(results, start=1):
            chunk = _format_result(index, result)
            if chunk.strip():
                yield AskProviderChunk(content=chunk)
