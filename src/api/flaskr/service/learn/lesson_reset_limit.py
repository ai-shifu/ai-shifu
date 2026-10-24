"""Limit how many times a learner may reset one lesson.

Usage lives in ``learn_lesson_reset_records``: one row per effective reset, written in
the same transaction that retires the learning state, so the count can never drift from
what actually happened. Every function here runs inside the caller's unit of work and
never commits on its own.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from flaskr.common.config import get_config
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope
from flaskr.service.common.models import raise_error
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.models import LearnLessonResetRecord, LearnProgressRecord
from flaskr.service.learn.preview_permissions import has_shifu_staff_permission
from flaskr.service.order.consts import LEARN_STATUS_NOT_STARTED, LEARN_STATUS_RESET
from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem

if TYPE_CHECKING:
    from flask import Flask


def get_lesson_reset_limit() -> int:
    """Return the configured limit; 0 means resets are unlimited."""
    try:
        return max(int(get_config("LESSON_RESET_LIMIT", 0) or 0), 0)
    except (TypeError, ValueError):
        return 0


def is_lesson_reset_exempt(app: Flask, user_bid: str, shifu_bid: str) -> bool:
    """Course owners and active collaborators reset freely while authoring."""
    return has_shifu_staff_permission(app, user_bid, shifu_bid)


def require_reset_lesson(shifu_bid: str, outline_bid: str) -> None:
    """Reject a lesson from another course before touching progress or counters."""
    for model in (PublishedOutlineItem, DraftOutlineItem):
        if model.query.filter_by(
            shifu_bid=shifu_bid, outline_item_bid=outline_bid, deleted=0
        ).first():
            return
    raise_error("server.shifu.lessonNotFoundInCourse")


def normalize_reset_request_id(value: str | None) -> str | None:
    """Hash the client trace id so any format fits the receipt column."""
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()


def count_lesson_resets(
    user_bid: str, shifu_bid: str, outline_bid: str, *, for_update: bool = False
) -> int:
    """Count resets that consumed this learner's allowance for the lesson.

    ``for_update`` makes the count a locking read. Under MySQL REPEATABLE READ a plain
    count reuses the transaction's first snapshot and can miss a counted row another
    reset committed meanwhile; a locking read returns the latest committed rows and
    holds next-key locks on the scope index, so concurrent admissions for the same
    learner and lesson serialize on it. The rows are at most the limit, so loading
    them is cheap. Advisory readers keep the plain count.
    """
    query = db.session.query(LearnLessonResetRecord.id).filter(
        LearnLessonResetRecord.user_bid == user_bid,
        LearnLessonResetRecord.shifu_bid == shifu_bid,
        LearnLessonResetRecord.outline_item_bid == outline_bid,
        LearnLessonResetRecord.counted == 1,
        LearnLessonResetRecord.deleted == 0,
    )
    if for_update:
        return len(query.with_for_update().all())
    return query.count()


def find_reset_receipt(
    user_bid: str, request_id: str | None
) -> LearnLessonResetRecord | None:
    """Return the reset already recorded for this client request, if any."""
    if not request_id:
        return None
    return LearnLessonResetRecord.query.filter(
        LearnLessonResetRecord.user_bid == user_bid,
        LearnLessonResetRecord.request_id == request_id,
    ).first()


def has_learning_state(user_bid: str, shifu_bid: str, outline_bid: str) -> bool:
    """Tell whether a reset of this lesson would retire generated learning.

    Mirrors the charging rule in ``reset_learn_record``: NOT_STARTED placeholders
    that a 1.0 lesson inserts on open do not count, a live published session does.
    """
    progress = (
        db.session.query(LearnProgressRecord.id)
        .filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status.notin_(
                [LEARN_STATUS_RESET, LEARN_STATUS_NOT_STARTED]
            ),
        )
        .first()
    )
    if progress is not None:
        return True
    return (
        db.session.query(LearnAgentSession.id)
        .filter(
            LearnAgentSession.user_bid == user_bid,
            LearnAgentSession.shifu_bid == shifu_bid,
            LearnAgentSession.outline_item_bid == outline_bid,
            LearnAgentSession.deleted == 0,
            LearnAgentSession.active_key
            == active_key_for(user_bid, outline_bid, preview_mode=False),
        )
        .first()
        is not None
    )


def record_lesson_reset(
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str = "",
    preview_mode: bool = False,
    counted: bool = True,
    request_id: str | None = None,
) -> LearnLessonResetRecord:
    """Stage one reset row in the caller's transaction."""
    record = LearnLessonResetRecord(
        reset_record_bid=uuid.uuid4().hex,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        progress_record_bid=progress_record_bid or "",
        preview_mode=1 if preview_mode else 0,
        counted=1 if counted else 0,
        request_id=request_id,
        deleted=0,
    )
    db.session.add(record)
    db.session.flush()
    return record


def get_lesson_reset_status(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    *,
    preview_mode: bool = False,
) -> dict[str, bool]:
    """Tell the client whether a reset would be admitted, without exposing counts."""
    with app_context_scope(app):
        require_reset_lesson(shifu_bid, outline_bid)
        limit = get_lesson_reset_limit()
        if (
            limit == 0
            or preview_mode
            or is_lesson_reset_exempt(app, user_bid, shifu_bid)
        ):
            return {"can_reset": True}
        # A reset that would retire nothing chargeable is always admitted, so the
        # dialog must not call it exhausted.
        if not has_learning_state(user_bid, shifu_bid, outline_bid):
            return {"can_reset": True}
        return {
            "can_reset": count_lesson_resets(user_bid, shifu_bid, outline_bid) < limit
        }
