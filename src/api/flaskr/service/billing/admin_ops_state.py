"""Handle admin ops state for creator billing."""

from __future__ import annotations

import json
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

from flaskr.service.common.models import raise_param_error
from flaskr.service.config.funcs import get_config, update_config

from .primitives import normalize_bid

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask

_ADMIN_OPS_OWNER_BID = "billing-admin-ops"
_CONFIG_STATUS_KEY = "ADMIN_BILLING.CONFIG_STATUS"
_CONFIG_STATUS_VALUES = {"pending", "in_progress", "completed", "exception"}


def build_admin_billing_ops_state(app: Flask) -> dict[str, Any]:
    with app.app_context():
        return {
            "config_status": _read_map(_CONFIG_STATUS_KEY),
        }


def update_admin_billing_config_status(
    app: Flask,
    *,
    creator_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized_creator_bid = normalize_bid(creator_bid)
    if not normalized_creator_bid:
        raise_param_error("creator_bid")

    status = str(payload.get("status") or "").strip().lower()
    if status not in _CONFIG_STATUS_VALUES:
        raise_param_error("status")

    record = {
        "status": status,
        "note": str(payload.get("note") or "").strip()[:500],
    }
    with app.app_context(), _admin_ops_lock(_CONFIG_STATUS_KEY):
        records = _read_map(_CONFIG_STATUS_KEY)
        records[normalized_creator_bid] = record
        _write_map(app, _CONFIG_STATUS_KEY, records)
    return record


@contextmanager
def _admin_ops_lock(key: str) -> Iterator[None]:
    try:
        from flaskr.dao import get_redis_client

        redis = get_redis_client()
        lock = (
            None
            if redis is None
            else redis.lock(
                f"billing:admin_ops_state:{key}",
                timeout=10,
                blocking_timeout=5,
            )
        )
    except Exception as exc:
        message = "Admin billing operations state lock is unavailable"
        raise RuntimeError(message) from exc
    if lock is None:
        message = "Admin billing operations state lock is unavailable"
        raise RuntimeError(message)

    acquired = lock.acquire(blocking=True, blocking_timeout=5)
    if not acquired:
        message = "Admin billing operations state is busy"
        raise RuntimeError(message)
    try:
        yield
    finally:
        with suppress(Exception):
            lock.release()


def _read_map(key: str) -> dict[str, Any]:
    payload = _load_json(get_config(key, "{}"))
    return payload if isinstance(payload, dict) else {}


def _write_map(app: Flask, key: str, value: dict[str, Any]) -> None:
    update_config(
        app,
        key,
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        is_secret=False,
        remark="Admin billing operations state",
        updated_by=_ADMIN_OPS_OWNER_BID,
    )


def _load_json(value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
