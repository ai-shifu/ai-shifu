from __future__ import annotations

from typing import Set

from flaskr.service.config.funcs import get_config as get_dynamic_config

# Built-in demo course IDs observed in legacy environments.
LEGACY_DEMO_SHIFU_BIDS: Set[str] = {
    "e867343eaab44488ad792ec54d8b82b5",  # AI 师傅教学引导
    "b5d7844387e940ed9480a6f945a6db6a",  # AI-Shifu Creation Guide
}

BUILTIN_DEMO_TITLES: Set[str] = {
    "AI 师傅教学引导",
    "AI-Shifu Creation Guide",
}


def load_demo_shifu_bids() -> Set[str]:
    demo_bids: Set[str] = set(LEGACY_DEMO_SHIFU_BIDS)
    for key in ("DEMO_SHIFU_BID", "DEMO_EN_SHIFU_BID"):
        bid = str(get_dynamic_config(key, "") or "").strip()
        if bid:
            demo_bids.add(bid)
    return demo_bids


def is_builtin_demo_course(
    *, shifu_bid: str, title: str, created_user_bid: str
) -> bool:
    normalized_bid = str(shifu_bid or "").strip()
    normalized_title = str(title or "").strip()
    normalized_creator = str(created_user_bid or "").strip()
    return normalized_bid in load_demo_shifu_bids() or (
        normalized_creator == "system" and normalized_title in BUILTIN_DEMO_TITLES
    )
