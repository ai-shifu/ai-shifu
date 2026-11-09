"""Limit how many times a learner may reset one lesson.

Usage lives in ``learn_lesson_reset_records``: effective resets write the ledger in
the same transaction that retires learning state, and accepted empty requests with an
ID write uncounted receipts. These helpers never commit on their own.
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
from flaskr.service.learn.agent.session_store import (
    UnreadableLessonAttemptSourceError,
    load_lesson_attempt_source,
)
from flaskr.service.learn.models import LearnLessonResetRecord, LearnProgressRecord
from flaskr.service.learn.preview_permissions import (
    has_shifu_staff_permission,
    is_builtin_demo_shifu,
)
from flaskr.service.order.consts import LEARN_STATUS_NOT_STARTED, LEARN_STATUS_RESET
from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem

if TYPE_CHECKING:
    from flask import Flask
    from sqlalchemy.exc import IntegrityError


def get_lesson_reset_limit() -> int:
    """Return the configured limit; 0 means resets are unlimited."""
    try:
        return max(int(get_config("LESSON_RESET_LIMIT", 0) or 0), 0)
    except (TypeError, ValueError):
        return 0


def is_lesson_reset_exempt(app: Flask, user_bid: str, shifu_bid: str) -> bool:
    """Course owners and active collaborators reset freely while authoring."""
    return has_shifu_staff_permission(app, user_bid, shifu_bid)


def is_unavailable_draft_attempt(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    for_update: bool = False,
) -> bool:
    """Let a learner discard a private attempt after losing draft access."""
    try:
        source = load_lesson_attempt_source(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            for_update=for_update,
        )
    except UnreadableLessonAttemptSourceError:
        # Damaged provenance cannot grant the draft recovery exemption. The
        # ordinary reset allowance still lets the owner discard the attempt.
        return False
    # Callers already applied the owner and collaborator reset exemption.
    return bool(
        source is not None
        and source.preview_mode
        and not is_builtin_demo_shifu(app, shifu_bid)
    )


def require_reset_lesson(
    shifu_bid: str, outline_bid: str, *, preview_mode: bool | None = None
) -> None:
    """Check lesson membership in the requested course version."""
    models = (
        (PublishedOutlineItem, DraftOutlineItem)
        if preview_mode is None
        else (DraftOutlineItem if preview_mode else PublishedOutlineItem,)
    )
    for model in models:
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


def is_reset_receipt_conflict(error: IntegrityError) -> bool:
    """Identify only duplicate keys for a learner's reset request ID."""
    args = error.orig.args if error.orig is not None else ()
    if args == (
        "UNIQUE constraint failed: learn_lesson_reset_records.user_bid, "
        "learn_lesson_reset_records.request_id",
    ):
        return True
    if len(args) < 2 or args[0] != 1062:
        return False
    index = str(args[1]).rpartition(" for key ")[2].strip("'\"`").rsplit(".", 1)[-1]
    return index == "uq_learn_lesson_reset_records_request"


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
            LearnAgentSession.active_key.in_(
                [
                    active_key_for(user_bid, outline_bid),
                    active_key_for(user_bid, outline_bid, preview_mode=True),
                ]
            ),
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
        require_reset_lesson(shifu_bid, outline_bid, preview_mode=preview_mode)
        limit = get_lesson_reset_limit()
        if (
            limit == 0
            or is_lesson_reset_exempt(app, user_bid, shifu_bid)
            or (
                not preview_mode
                and is_unavailable_draft_attempt(
                    app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
                )
            )
        ):
            return {"can_reset": True}
        # A reset that would retire nothing chargeable is always admitted, so the
        # dialog must not call it exhausted.
        if not has_learning_state(user_bid, shifu_bid, outline_bid):
            return {"can_reset": True}
        return {
            "can_reset": count_lesson_resets(user_bid, shifu_bid, outline_bid) < limit
        }
