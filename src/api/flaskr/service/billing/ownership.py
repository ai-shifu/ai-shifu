"""Ownership resolution helpers for billing admission and settlement."""

from __future__ import annotations

from typing import Any

from flask import Flask

from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG, normalize_usage_scene
from flaskr.service.shifu.utils import get_shifu_creator_bid


def resolve_shifu_creator_bid(app: Flask, shifu_bid: str) -> str | None:
    """Resolve the creator that owns a shifu for billing workflows."""

    normalized_shifu_bid = str(shifu_bid or "").strip()
    if not normalized_shifu_bid:
        return None
    return get_shifu_creator_bid(app, normalized_shifu_bid)


def resolve_usage_creator_bid(app: Flask, usage: Any) -> str | None:
    """Resolve the owning creator from a metering usage record or payload."""

    shifu_bid = _extract_usage_field(usage, "shifu_bid")
    if shifu_bid:
        return resolve_shifu_creator_bid(app, shifu_bid)

    raw_usage_scene = _extract_usage_field(usage, "usage_scene")
    if (
        raw_usage_scene
        and normalize_usage_scene(raw_usage_scene) == BILL_USAGE_SCENE_DEBUG
    ):
        creator_bid = _extract_usage_field(usage, "user_bid")
        return creator_bid or None

    return None


def _extract_usage_field(usage: Any, field_name: str) -> str:
    if isinstance(usage, dict):
        value = usage.get(field_name, "")
    else:
        value = getattr(usage, field_name, "")
    return str(value or "").strip()
