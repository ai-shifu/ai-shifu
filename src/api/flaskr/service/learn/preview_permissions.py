from __future__ import annotations

import json
from typing import Optional

from flask import Flask, request

from flaskr.service.common import raise_error
from flaskr.service.common.dtos import UserInfo
from flaskr.service.config import get_config
from flaskr.service.shifu.models import AiCourseAuth, DraftShifu, PublishedShifu


BUILTIN_DEMO_TITLES = {
    "AI 师傅教学引导",
    "AI-Shifu Creation Guide",
}


def _extract_preview_token() -> Optional[str]:
    token = request.cookies.get("token", None)
    if not token:
        token = request.args.get("token", None)
    if not token:
        token = request.headers.get("Token", None)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
    if not token and request.method.upper() == "POST" and request.is_json:
        payload = request.get_json(silent=True) or {}
        token = payload.get("token", None)
    return str(token).strip() if token else None


def resolve_preview_request_user(app: Flask) -> UserInfo:
    """Resolve the current user for preview endpoints that bypass global auth."""
    token = _extract_preview_token()
    if not token:
        raise_error("server.user.userNotLogin")

    from flaskr.route import user as user_route

    user = user_route.validate_user(app, token)
    request.user = user
    return user


def _normalize_auth_types(raw_value: object) -> set[str]:
    if raw_value is None:
        return set()
    if isinstance(raw_value, (set, list, tuple)):
        return {str(item) for item in raw_value if str(item).strip()}
    if isinstance(raw_value, str):
        trimmed = raw_value.strip()
        if not trimmed:
            return set()
        try:
            parsed = json.loads(trimmed)
        except json.JSONDecodeError:
            return {trimmed}
        if isinstance(parsed, (list, tuple, set)):
            return {str(item) for item in parsed if str(item).strip()}
        if isinstance(parsed, str):
            return {parsed} if parsed.strip() else set()
    return set()


def _auth_types_to_permissions(auth_types: set[str]) -> set[str]:
    permissions: set[str] = set()
    for item in auth_types:
        lowered = item.lower()
        if lowered in {"view", "read", "readonly"} or lowered == "1":
            permissions.add("view")
        if lowered in {"edit", "write"} or lowered == "2":
            permissions.update({"view", "edit"})
        if lowered in {"publish"} or lowered == "4":
            permissions.add("publish")
    return permissions


def _load_course_rows(shifu_bid: str) -> list[object]:
    rows: list[object] = []
    for model in (DraftShifu, PublishedShifu):
        row = (
            model.query.filter(
                model.shifu_bid == shifu_bid,
                model.deleted == 0,
            )
            .order_by(model.id.desc())
            .first()
        )
        if row is not None:
            rows.append(row)
    return rows


def _load_demo_shifu_bids() -> set[str]:
    demo_bids: set[str] = set()
    for key in ("DEMO_SHIFU_BID", "DEMO_EN_SHIFU_BID"):
        try:
            bid = str(get_config(key, "") or "").strip()
        except Exception:
            bid = ""
        if bid:
            demo_bids.add(bid)
    return demo_bids


def is_builtin_demo_shifu(app: Flask, shifu_bid: str) -> bool:
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_shifu_bid:
        return False
    if normalized_shifu_bid in _load_demo_shifu_bids():
        return True

    with app.app_context():
        for row in _load_course_rows(normalized_shifu_bid):
            title = str(getattr(row, "title", "") or "").strip()
            creator_bid = str(getattr(row, "created_user_bid", "") or "").strip()
            if creator_bid == "system" and title in BUILTIN_DEMO_TITLES:
                return True
    return False


def _get_shifu_creator_bid(app: Flask, shifu_bid: str) -> Optional[str]:
    with app.app_context():
        for row in _load_course_rows(shifu_bid):
            creator_bid = str(getattr(row, "created_user_bid", "") or "").strip()
            if creator_bid:
                return creator_bid
    return None


def _has_preview_permission(app: Flask, user_bid: str, shifu_bid: str) -> bool:
    with app.app_context():
        creator_bid = _get_shifu_creator_bid(app, shifu_bid)
        if creator_bid and creator_bid == user_bid:
            return True

        auth = AiCourseAuth.query.filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.user_id == user_bid,
            AiCourseAuth.status == 1,
        ).first()
        if auth is None:
            return False

        permissions = _auth_types_to_permissions(_normalize_auth_types(auth.auth_type))
        return bool(permissions.intersection({"view", "edit", "publish"}))


def require_shifu_preview_permission(app: Flask, user_bid: str, shifu_bid: str) -> None:
    """Require course view permission before exposing draft preview content."""
    normalized_user_bid = str(user_bid or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_user_bid:
        raise_error("server.user.userNotLogin")
    if not normalized_shifu_bid:
        raise_error("server.shifu.shifuNotFound")

    if is_builtin_demo_shifu(app, normalized_shifu_bid):
        return

    creator_bid = _get_shifu_creator_bid(app, normalized_shifu_bid)
    if not creator_bid:
        raise_error("server.shifu.shifuNotFound")

    if _has_preview_permission(app, normalized_user_bid, normalized_shifu_bid):
        return

    raise_error("server.shifu.noPermission")
