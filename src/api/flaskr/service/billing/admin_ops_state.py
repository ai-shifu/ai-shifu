from __future__ import annotations

from contextlib import contextmanager
import json
from importlib import import_module
from typing import Any, Iterator

from flask import Flask

from flaskr.service.common.models import raise_param_error
from .primitives import normalize_bid

_ADMIN_OPS_OWNER_BID = "billing-admin-ops"
_CONFIG_STATUS_KEY = "ADMIN_BILLING.CONFIG_STATUS"
_EXCEPTION_HANDLED_KEY = "ADMIN_BILLING.EXCEPTION_HANDLED"
_CONFIG_STATUS_VALUES = {"pending", "in_progress", "completed", "exception"}


def build_admin_billing_ops_state(app: Flask) -> dict[str, Any]:
    with app.app_context():
        return {
            "config_status": _read_map(_CONFIG_STATUS_KEY),
            "exception_handled": _read_map(_EXCEPTION_HANDLED_KEY),
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


def update_admin_billing_exception_handled(
    app: Flask,
    *,
    row_key: str,
    handled: bool,
) -> dict[str, Any]:
    normalized_row_key = str(row_key or "").strip()
    if not normalized_row_key or len(normalized_row_key) > 200:
        raise_param_error("row_key")

    with app.app_context(), _admin_ops_lock(_EXCEPTION_HANDLED_KEY):
        records = _read_map(_EXCEPTION_HANDLED_KEY)
        if handled:
            records[normalized_row_key] = True
        else:
            records.pop(normalized_row_key, None)
        _write_map(app, _EXCEPTION_HANDLED_KEY, records)
    return {"row_key": normalized_row_key, "handled": handled}


@contextmanager
def _admin_ops_lock(key: str) -> Iterator[None]:
    try:
        from flaskr import dao

        redis = getattr(dao, "redis_client", None)
        lock = (
            redis.lock(
                f"billing:admin_ops_state:{key}",
                timeout=10,
                blocking_timeout=5,
            )
            if redis is not None
            else None
        )
    except Exception:
        lock = None

    if lock is None:
        yield
        return

    acquired = lock.acquire(blocking=True, blocking_timeout=5)
    if not acquired:
        raise RuntimeError("Admin billing operations state is busy")
    try:
        yield
    finally:
        try:
            lock.release()
        except Exception:
            pass


def _read_map(key: str) -> dict[str, Any]:
    funcs = _saas_funcs(required=False)
    if funcs is None:
        return {}
    payload = _load_json(funcs.get_sass_config(_ADMIN_OPS_OWNER_BID, key, default="{}"))
    return payload if isinstance(payload, dict) else {}


def _write_map(app: Flask, key: str, value: dict[str, Any]) -> None:
    funcs = _saas_funcs(required=False)
    if funcs is None:
        return
    funcs.create_or_update_saas_user_config(
        app,
        funcs.SaasUserConfigCreateDTO(
            user_bid=_ADMIN_OPS_OWNER_BID,
            key=key,
            value=json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
            is_encrypted=1,
            remark="Admin billing operations state",
        ),
    )


def _load_json(value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _saas_funcs(*, required: bool = True):
    try:
        return import_module(
            "flaskr.plugins.ai_shifu_saas_plugin.src.service.config.funcs"
        )
    except ModuleNotFoundError as exc:
        if not str(exc.name or "").startswith("flaskr.plugins.ai_shifu_saas_plugin"):
            raise
        if required:
            raise RuntimeError("SaaS config plugin is not installed") from exc
        return None
