"""Parse and format stored payment payloads for legacy order flows."""

import ast
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flaskr.util.datetime import now_utc


def _parse_stored_mapping(value: object) -> dict[str, Any]:
    parsed = _parse_json_payload(value)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, str):
        try:
            legacy_parsed = ast.literal_eval(parsed)
        except (SyntaxError, ValueError):
            return {}
        return legacy_parsed if isinstance(legacy_parsed, dict) else {}
    return {}


def _payment_payload_has_expired(payload: dict[str, Any], field: str) -> bool:
    raw_expiry = payload.get(field)
    if raw_expiry in (None, ""):
        return False
    try:
        return float(raw_expiry) <= now_utc().timestamp()
    except (TypeError, ValueError):
        return True


def _format_response_channel(payment_channel: str, provider_channel: str) -> str:
    if payment_channel == "stripe":
        return (
            "stripe"
            if provider_channel == "payment_intent"
            else f"stripe:{provider_channel}"
        )
    return provider_channel


def _sanitize_pingxx_text(value: str | None, *, fallback: str, max_length: int) -> str:
    text = (value or fallback or "").strip()
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if not text:
        text = fallback.strip() or "订单支付"
    return text[:max_length]


def _inject_order_query(url: str, order_id: str) -> str:
    if not url:
        return url
    parsed = urlsplit(url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "order_id" not in query_items:
        query_items["order_id"] = order_id
    new_query = urlencode(query_items, doseq=True)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            new_query,
            parsed.fragment,
        )
    )


def _stringify_payload(payload: object) -> str:
    if not payload:
        return "{}"
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    return json.dumps(payload)


def _parse_json_payload(value: object) -> object:
    if not value:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value
