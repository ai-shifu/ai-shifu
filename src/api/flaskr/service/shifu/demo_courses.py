from __future__ import annotations

from flask import Flask
from typing import Any, Set

from flaskr.service.config.funcs import get_config as get_dynamic_config

BUILTIN_DEMO_TITLES: Set[str] = {
    "AI 师傅教学引导",
    "AI-Shifu Creation Guide",
}


def load_builtin_demo_titles() -> Set[str]:
    return set(BUILTIN_DEMO_TITLES)


def load_demo_shifu_bids() -> Set[str]:
    demo_bids: Set[str] = set()
    for key in ("DEMO_SHIFU_BID", "DEMO_EN_SHIFU_BID"):
        try:
            bid = str(get_dynamic_config(key, "") or "").strip()
        except Exception:
            bid = ""
        if bid:
            demo_bids.add(bid)
    return demo_bids


def resolve_demo_course_for_language(
    app: Flask, language: str | None
) -> dict[str, Any]:
    normalized_language = str(language or "").strip().lower()
    preferred_key = (
        "DEMO_SHIFU_BID"
        if normalized_language.startswith("zh")
        else "DEMO_EN_SHIFU_BID"
    )
    fallback_key = (
        "DEMO_EN_SHIFU_BID" if preferred_key == "DEMO_SHIFU_BID" else "DEMO_SHIFU_BID"
    )

    try:
        preferred_bid = str(get_dynamic_config(preferred_key, "") or "").strip()
    except Exception:
        preferred_bid = ""
    try:
        fallback_bid = str(get_dynamic_config(fallback_key, "") or "").strip()
    except Exception:
        fallback_bid = ""
    resolved_bid = preferred_bid or fallback_bid
    resolved_language = "zh-CN" if preferred_key == "DEMO_SHIFU_BID" else "en-US"
    if not preferred_bid and fallback_bid:
        resolved_language = "en-US" if fallback_key == "DEMO_EN_SHIFU_BID" else "zh-CN"

    title = ""
    if resolved_bid:
        for candidate_title, _ in _load_shifu_demo_metadata(app, resolved_bid):
            if candidate_title:
                title = candidate_title
                break
    if not title:
        title = (
            "AI 师傅教学引导"
            if resolved_language == "zh-CN"
            else "AI-Shifu Creation Guide"
        )

    return {
        "bid": resolved_bid,
        "title": title,
        "language": resolved_language,
    }


def is_builtin_demo_course(
    *, shifu_bid: str, title: str, created_user_bid: str
) -> bool:
    normalized_bid = str(shifu_bid or "").strip()
    normalized_title = str(title or "").strip()
    normalized_creator = str(created_user_bid or "").strip()
    return normalized_bid in load_demo_shifu_bids() or (
        normalized_creator == "system" and normalized_title in BUILTIN_DEMO_TITLES
    )


def is_builtin_demo_shifu(app: Flask, shifu_bid: str) -> bool:
    normalized_bid = str(shifu_bid or "").strip()
    if not normalized_bid:
        return False

    if is_builtin_demo_course(
        shifu_bid=normalized_bid,
        title="",
        created_user_bid="",
    ):
        return True

    for title, created_user_bid in _load_shifu_demo_metadata(app, normalized_bid):
        if is_builtin_demo_course(
            shifu_bid=normalized_bid,
            title=title,
            created_user_bid=created_user_bid,
        ):
            return True

    return False


def _load_shifu_demo_metadata(app: Flask, shifu_bid: str) -> list[tuple[str, str]]:
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu

    with app.app_context():
        metadata: list[tuple[str, str]] = []
        for model in (DraftShifu, PublishedShifu):
            row = (
                model.query.filter(
                    model.shifu_bid == shifu_bid,
                    model.deleted == 0,
                )
                .order_by(model.id.desc())
                .first()
            )
            if row is None:
                continue
            metadata.append(
                (
                    str(getattr(row, "title", "") or "").strip(),
                    str(getattr(row, "created_user_bid", "") or "").strip(),
                )
            )
        return metadata
