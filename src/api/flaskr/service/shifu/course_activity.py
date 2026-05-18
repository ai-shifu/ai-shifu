from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Set

from sqlalchemy import and_, or_

from flaskr.dao import db

from .models import DraftOutlineItem, DraftShifu, PublishedOutlineItem, PublishedShifu


def _record_course_activity(
    activity_map: Dict[str, Dict[str, Any]],
    *,
    shifu_bid: str,
    updated_at: Optional[datetime],
    updated_user_bid: str,
    prefer_on_equal: bool = False,
) -> None:
    if not shifu_bid:
        return
    current = activity_map.get(shifu_bid)
    candidate_time = updated_at or datetime.min
    current_time = (
        current.get("updated_at")
        if current and current.get("updated_at")
        else datetime.min
    )
    should_replace = current is None or candidate_time > current_time
    if (
        not should_replace
        and prefer_on_equal
        and current is not None
        and candidate_time == current_time
    ):
        should_replace = True
    if should_replace:
        activity_map[shifu_bid] = {
            "updated_at": updated_at,
            "updated_user_bid": str(updated_user_bid or "").strip(),
        }


def load_course_activity_map(
    drafts: Iterable[DraftShifu],
    published: Iterable[PublishedShifu],
    *,
    include_published_outline: bool = True,
) -> Dict[str, Dict[str, Any]]:
    activity_map: Dict[str, Dict[str, Any]] = {}
    shifu_bids: Set[str] = set()

    for course in list(drafts) + list(published):
        shifu_bid = str(course.shifu_bid or "").strip()
        if not shifu_bid:
            continue
        shifu_bids.add(shifu_bid)
        _record_course_activity(
            activity_map,
            shifu_bid=shifu_bid,
            updated_at=course.updated_at,
            updated_user_bid=course.updated_user_bid or "",
        )

    if not shifu_bids:
        return activity_map

    ordered_shifu_bids = sorted(shifu_bids)
    outline_models = [DraftOutlineItem]
    if include_published_outline:
        outline_models.append(PublishedOutlineItem)
    for model in outline_models:
        latest_updated_subquery = (
            db.session.query(
                model.shifu_bid.label("shifu_bid"),
                db.func.max(model.updated_at).label("max_updated_at"),
            )
            .filter(
                model.deleted == 0,
                model.shifu_bid.in_(ordered_shifu_bids),
            )
            .group_by(model.shifu_bid)
            .subquery()
        )
        latest_id_subquery = (
            db.session.query(
                model.shifu_bid.label("shifu_bid"),
                db.func.max(model.id).label("max_id"),
            )
            .join(
                latest_updated_subquery,
                and_(
                    model.shifu_bid == latest_updated_subquery.c.shifu_bid,
                    or_(
                        model.updated_at == latest_updated_subquery.c.max_updated_at,
                        and_(
                            model.updated_at.is_(None),
                            latest_updated_subquery.c.max_updated_at.is_(None),
                        ),
                    ),
                ),
            )
            .filter(
                model.deleted == 0,
                model.shifu_bid.in_(ordered_shifu_bids),
            )
            .group_by(model.shifu_bid)
            .subquery()
        )
        rows = (
            db.session.query(
                model.shifu_bid,
                model.updated_at,
                model.updated_user_bid,
            )
            .join(latest_id_subquery, model.id == latest_id_subquery.c.max_id)
            .all()
        )
        for shifu_bid, updated_at, updated_user_bid in rows:
            normalized_shifu_bid = str(shifu_bid or "").strip()
            if not normalized_shifu_bid:
                continue
            _record_course_activity(
                activity_map,
                shifu_bid=normalized_shifu_bid,
                updated_at=updated_at,
                updated_user_bid=updated_user_bid or "",
                prefer_on_equal=True,
            )

    return activity_map
