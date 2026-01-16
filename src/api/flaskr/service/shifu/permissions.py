from __future__ import annotations

import json
from typing import Dict, Optional, Set

from flask import Flask

from flaskr.dao import db
from flaskr.service.shifu.models import AiCourseAuth, DraftShifu


DEFAULT_SHIFU_PERMISSIONS = {"view", "edit", "publish"}


def _normalize_auth_types(raw_value: object) -> Set[str]:
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
    return set()


def _auth_types_to_permissions(auth_types: Set[str]) -> Set[str]:
    """
    Map stored auth_type values (strings or numeric codes) to normalized permissions.
    Codes: 1=view, 2=edit, 4=publish.
    """
    perms: Set[str] = set()
    for item in auth_types:
        lowered = item.lower()
        if lowered in {"view", "read", "readonly"} or lowered == "1":
            perms.add("view")
        if lowered in {"edit", "write"} or lowered == "2":
            perms.update({"view", "edit"})
        if lowered in {"publish"} or lowered == "4":
            perms.add("publish")
    return perms


def get_user_shifu_permissions(app: Flask, user_id: str) -> Dict[str, Set[str]]:
    with app.app_context():
        permission_map: Dict[str, Set[str]] = {}

        created_shifus = (
            db.session.query(DraftShifu.shifu_bid)
            .filter(
                DraftShifu.created_user_bid == user_id,
                DraftShifu.deleted == 0,
            )
            .distinct()
            .all()
        )
        for (shifu_bid,) in created_shifus:
            if shifu_bid:
                permission_map[shifu_bid] = set(DEFAULT_SHIFU_PERMISSIONS)

        shared_auths = AiCourseAuth.query.filter(AiCourseAuth.user_id == user_id).all()
        for auth in shared_auths:
            shifu_bid = auth.course_id
            if not shifu_bid or shifu_bid in permission_map:
                continue
            auth_types = _normalize_auth_types(auth.auth_type)
            permission_map.setdefault(shifu_bid, set()).update(
                _auth_types_to_permissions(auth_types) or auth_types
            )

        return permission_map


def get_user_shifu_bids(
    app: Flask, user_id: str, permission: Optional[str] = None
) -> list[str]:
    permission_map = get_user_shifu_permissions(app, user_id)
    if not permission:
        return list(permission_map.keys())
    return [
        shifu_bid
        for shifu_bid, permissions in permission_map.items()
        if permission in permissions
    ]


def has_shifu_permission(
    permission_map: Dict[str, Set[str]],
    shifu_bid: str,
    permission: str,
) -> bool:
    if not shifu_bid:
        return False
    permissions = permission_map.get(shifu_bid, set())
    return permission in permissions
