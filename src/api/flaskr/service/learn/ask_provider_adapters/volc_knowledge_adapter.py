"""Volcengine Knowledge Base ask provider adapter."""

import copy
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Generator
from urllib.parse import quote

import requests
from flask import Flask

from flaskr.service.shifu.shifu_draft_funcs import ASK_PROVIDER_VOLC_KNOWLEDGE

from .base import (
    AskProviderChunk,
    AskProviderConfigError,
    AskProviderError,
    AskProviderRuntime,
    AskProviderTimeoutError,
)
from .common import extract_text, provider_timeout_seconds, raise_for_provider_response


def _hash_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _hmac_sha256(key: bytes, content: str) -> bytes:
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


def _normalize_query(params: dict[str, Any] | None) -> str:
    if not params:
        return ""

    encoded_parts: list[str] = []
    for key in sorted(params.keys()):
        value = params[key]
        if isinstance(value, list):
            values = value
        else:
            values = [value]
        for item in values:
            item_text = "" if item is None else str(item)
            encoded_parts.append(
                f"{quote(str(key), safe='-_.~')}={quote(item_text, safe='-_.~')}"
            )
    return "&".join(encoded_parts)


def _normalize_header_value(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _build_volc_signature_headers(
    *,
    method: str,
    path: str,
    query_params: dict[str, Any] | None,
    headers: dict[str, str],
    body: str,
    ak: str,
    sk: str,
    service: str,
    region: str,
) -> dict[str, str]:
    x_date = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]
    x_content_sha256 = _hash_sha256(body)

    signable_headers = {
        "content-type": _normalize_header_value(headers.get("Content-Type", "")),
        "host": _normalize_header_value(headers.get("Host", "")),
        "v-account-id": _normalize_header_value(headers.get("V-Account-Id", "")),
        "x-content-sha256": x_content_sha256,
        "x-date": x_date,
    }
    signed_header_keys = sorted(signable_headers.keys())
    signed_headers = ";".join(signed_header_keys)
    canonical_headers = "\n".join(
        f"{key}:{signable_headers[key]}" for key in signed_header_keys
    )

    canonical_request_str = "\n".join(
        [
            method.upper(),
            path,
            _normalize_query(query_params),
            canonical_headers,
            "",
            signed_headers,
            x_content_sha256,
        ]
    )
    hashed_canonical_request = _hash_sha256(canonical_request_str)
    credential_scope = "/".join([short_x_date, region, service, "request"])
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request]
    )

    k_date = _hmac_sha256(sk.encode("utf-8"), short_x_date)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    k_signing = _hmac_sha256(k_service, "request")
    signature = _hmac_sha256(k_signing, string_to_sign).hex()

    return {
        "X-Date": x_date,
        "X-Content-Sha256": x_content_sha256,
        "Authorization": (
            "HMAC-SHA256 Credential="
            f"{ak}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }


def _to_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def _normalize_pre_processing(
    config_value: Any, user_query: str
) -> dict[str, Any] | None:
    if not isinstance(config_value, dict):
        return None
    pre_processing = copy.deepcopy(config_value)
    messages = pre_processing.get("messages")
    if not isinstance(messages, list):
        return pre_processing

    normalized_messages: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip() or "user"
        content = item.get("content")
        if role == "user" and (content is None or not str(content).strip()):
            content = user_query
        elif content is None:
            content = ""
        normalized_messages.append({"role": role, "content": str(content)})

    if normalized_messages:
        pre_processing["messages"] = normalized_messages
    return pre_processing


def _collect_text_chunks(payload: Any) -> list[str]:
    chunks: list[str] = []
    seen: set[str] = set()

    def _append(value: Any) -> None:
        text = extract_text(value)
        if text and text not in seen:
            seen.add(text)
            chunks.append(text)

    if isinstance(payload, list):
        for item in payload:
            _append(item)
        return chunks

    if isinstance(payload, dict):
        if isinstance(payload.get("data"), (dict, list)):
            data = payload.get("data")
        else:
            data = payload

        for key in (
            "chunk_list",
            "chunks",
            "records",
            "result_list",
            "results",
            "search_results",
            "knowledge_list",
            "list",
            "items",
        ):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, list):
                for item in value:
                    _append(item)

        if not chunks:
            _append(data)

    return chunks


class VolcKnowledgeAskProviderAdapter:
    provider = ASK_PROVIDER_VOLC_KNOWLEDGE

    def stream_answer(
        self,
        app: Flask,
        user_id: str,
        user_query: str,
        messages: list[dict[str, Any]],
        provider_config: dict[str, Any],
        runtime: AskProviderRuntime | None = None,
    ) -> Generator[AskProviderChunk, None, None]:
        _ = (messages, runtime)
        config = provider_config.get("config") or {}
        if not isinstance(config, dict):
            config = {}

        account_id = str(config.get("account_id") or "").strip()
        ak = str(config.get("ak") or "").strip()
        sk = str(config.get("sk") or "").strip()
        collection_name = str(config.get("collection_name") or "").strip()
        if not account_id or not ak or not sk or not collection_name:
            raise AskProviderConfigError(
                "volc_knowledge account_id/ak/sk/collection_name are required in ask_provider_config.config"
            )

        domain = str(
            config.get("domain") or "api-knowledgebase.mlp.cn-beijing.volces.com"
        ).strip()
        scheme = str(config.get("scheme") or "https").strip().lower()
        if scheme not in {"http", "https"}:
            scheme = "https"
        path = str(config.get("path") or "/api/knowledge/collection/search_knowledge")
        path = path.strip() or "/api/knowledge/collection/search_knowledge"
        if not path.startswith("/"):
            path = "/" + path
        project = str(config.get("project") or "default").strip() or "default"
        service = str(config.get("service") or "air").strip() or "air"
        region = str(config.get("region") or "cn-north-1").strip() or "cn-north-1"

        payload: dict[str, Any] = {
            "project": project,
            "name": collection_name,
            "query": user_query,
            "limit": _to_positive_int(config.get("limit"), 20),
        }
        dense_weight = config.get("dense_weight")
        if isinstance(dense_weight, (int, float)):
            payload["dense_weight"] = float(dense_weight)

        image_query = str(config.get("image_query") or "").strip()
        if image_query:
            payload["image_query"] = image_query

        pre_processing = _normalize_pre_processing(
            config.get("pre_processing"), user_query
        )
        if pre_processing is not None:
            payload["pre_processing"] = pre_processing
        for field in ("post_processing", "query_param"):
            value = config.get(field)
            if isinstance(value, dict):
                payload[field] = copy.deepcopy(value)

        request_timeout_seconds = provider_timeout_seconds()
        unsigned_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "Host": domain,
            "V-Account-Id": account_id,
        }
        request_body = json.dumps(payload, ensure_ascii=False)
        signed_headers = _build_volc_signature_headers(
            method="POST",
            path=path,
            query_params=None,
            headers=unsigned_headers,
            body=request_body,
            ak=ak,
            sk=sk,
            service=service,
            region=region,
        )
        request_headers = {**unsigned_headers, **signed_headers}

        try:
            response = requests.request(
                method="POST",
                url=f"{scheme}://{domain}{path}",
                headers=request_headers,
                data=request_body,
                timeout=(5, request_timeout_seconds),
            )
        except requests.Timeout as exc:
            raise AskProviderTimeoutError("volc_knowledge request timeout") from exc
        except requests.RequestException as exc:
            raise AskProviderError(f"volc_knowledge request failed: {exc}") from exc

        response = raise_for_provider_response(response, self.provider)

        try:
            payload_data = response.json()
        except ValueError as exc:
            raise AskProviderError("volc_knowledge response is not valid json") from exc

        if isinstance(payload_data, dict):
            code = payload_data.get("code")
            data = payload_data.get("data")
            if code is not None and str(code) not in {"0", "200"} and data is None:
                message = extract_text(payload_data.get("message")) or str(payload_data)
                raise AskProviderError(f"volc_knowledge error: {message}")

        chunks = _collect_text_chunks(payload_data)
        if not chunks:
            app.logger.warning(
                "volc_knowledge response contains no text chunks, payload=%s",
                payload_data,
            )
            raise AskProviderError("volc_knowledge response has no retrievable text")

        for chunk in chunks:
            yield AskProviderChunk(content=chunk)
