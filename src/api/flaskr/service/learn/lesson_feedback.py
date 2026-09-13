"""Handle lesson feedback for learning sessions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import (
    app_context_scope,
    require_transaction_owner,
    unit_of_work,
)
from flaskr.i18n import _
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.const import CONTEXT_INTERACTION_LESSON_FEEDBACK_SCORE
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.shifu.consts import BLOCK_TYPE_MDINTERACTION_VALUE
from flaskr.util import generate_id
from flaskr.util.datetime import to_utc_iso
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from flask import Flask

_FEEDBACK_COMMENT_MAX_LENGTH = 1000
_VALID_MODES = {"read", "listen"}


def build_lesson_feedback_interaction_md() -> str:
    """Build lesson feedback interaction md."""
    placeholder = _("server.learn.lessonFeedbackCommentPlaceholder")
    return (
        f"?[%{{{{{CONTEXT_INTERACTION_LESSON_FEEDBACK_SCORE}}}}}"
        f"1|2|3|4|5|...{placeholder}]"
    )


def is_lesson_feedback_interaction(content: str | None) -> bool:
    """Return whether lesson feedback interaction."""
    marker = f"%{{{{{CONTEXT_INTERACTION_LESSON_FEEDBACK_SCORE}}}}}"
    return bool(content and marker in content)


def _normalize_mode(mode: str | None) -> str:
    if mode is None:
        return "read"
    normalized = str(mode).strip().lower()
    if normalized not in _VALID_MODES:
        raise_param_error("mode")
    return normalized


def _normalize_score(score: object) -> int:
    try:
        normalized = int(score)
    except (TypeError, ValueError):
        raise_param_error("score")
    if normalized < 1 or normalized > 5:
        raise_param_error("score")
    return normalized


def _normalize_comment(comment: str | None) -> str:
    if comment is None:
        return ""
    normalized = str(comment).strip()
    if len(normalized) > _FEEDBACK_COMMENT_MAX_LENGTH:
        raise_param_error("comment")
    return normalized


def _resolve_progress_record_bid(
    user_bid: str, shifu_bid: str, outline_bid: str
) -> str:
    progress = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .order_by(LearnProgressRecord.id.desc())
        .first()
    )
    if not progress:
        return ""
    return progress.progress_record_bid or ""


def _serialize_feedback_generated_content(score: int, comment: str) -> str:
    return json.dumps({"score": score, "comment": comment}, ensure_ascii=False)


def _sync_feedback_to_generated_block(
    user_bid: str, shifu_bid: str, outline_bid: str, score: int, comment: str
) -> None:
    marker = f"%{{{{{CONTEXT_INTERACTION_LESSON_FEEDBACK_SCORE}}}}}"
    feedback_block = (
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.outline_item_bid == outline_bid,
            LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.block_content_conf.contains(marker, autoescape=True),
        )
        .order_by(LearnGeneratedBlock.id.desc())
        .first()
    )
    if feedback_block:
        feedback_block.generated_content = _serialize_feedback_generated_content(
            score, comment
        )


def submit_lesson_feedback(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    score: object,
    comment: str | None,
    mode: str | None,
) -> dict:
    """Submit lesson feedback."""
    # The IntegrityError handler re-reads the winner in a fresh unit of work;
    # nested, the conflict would only surface at the caller's commit.
    require_transaction_owner("lesson feedback submission")
    normalized_score = _normalize_score(score)
    normalized_comment = _normalize_comment(comment)
    normalized_mode = _normalize_mode(mode)

    with app_context_scope(app):
        progress_record_bid = _resolve_progress_record_bid(
            user_bid, shifu_bid, outline_bid
        )

        def _load_active_feedback() -> LearnLessonFeedback | None:
            return (
                LearnLessonFeedback.query.filter(
                    LearnLessonFeedback.user_bid == user_bid,
                    LearnLessonFeedback.shifu_bid == shifu_bid,
                    LearnLessonFeedback.outline_item_bid == outline_bid,
                    LearnLessonFeedback.deleted == 0,
                )
                .order_by(LearnLessonFeedback.id.desc())
                .first()
            )

        def _apply_feedback(record: LearnLessonFeedback) -> None:
            if not record.bid:
                record.bid = record.lesson_feedback_bid or generate_id(app)
            if not record.lesson_feedback_bid:
                record.lesson_feedback_bid = record.bid
            record.score = normalized_score
            record.comment = normalized_comment
            record.mode = normalized_mode
            if progress_record_bid:
                record.progress_record_bid = progress_record_bid

        try:
            with unit_of_work():
                existing = _load_active_feedback()
                if not existing and not progress_record_bid:
                    raise_param_error("outline_bid")
                if existing:
                    _apply_feedback(existing)
                    feedback_record = existing
                else:
                    feedback_bid = generate_id(app)
                    feedback_record = LearnLessonFeedback(
                        bid=feedback_bid,
                        lesson_feedback_bid=feedback_bid,
                        shifu_bid=shifu_bid,
                        outline_item_bid=outline_bid,
                        progress_record_bid=progress_record_bid,
                        user_bid=user_bid,
                        score=normalized_score,
                        comment=normalized_comment,
                        mode=normalized_mode,
                        deleted=0,
                    )
                    db.session.add(feedback_record)

                # Querying the generated block must not autoflush a newly-added
                # feedback row. During concurrent submissions another request may
                # have inserted the unique active feedback first; the commit
                # raises IntegrityError and the fallback below merges into it.
                with db.session.no_autoflush:
                    _sync_feedback_to_generated_block(
                        user_bid,
                        shifu_bid,
                        outline_bid,
                        normalized_score,
                        normalized_comment,
                    )
        except IntegrityError:
            # Lost the race on the unique active row (our insert was rolled
            # back): re-read the winner and apply this submission to it.
            with unit_of_work():
                feedback_record = _load_active_feedback()
                if not feedback_record:
                    raise
                _apply_feedback(feedback_record)
                _sync_feedback_to_generated_block(
                    user_bid,
                    shifu_bid,
                    outline_bid,
                    normalized_score,
                    normalized_comment,
                )
        return {
            "lesson_feedback_bid": feedback_record.lesson_feedback_bid,
            "shifu_bid": shifu_bid,
            "outline_bid": outline_bid,
            "score": normalized_score,
            "comment": normalized_comment,
            "mode": normalized_mode,
        }


def list_lesson_feedbacks(
    app: Flask,
    *,
    shifu_bid: str,
    outline_bid: str | None = None,
    page_index: int = 1,
    page_size: int = 20,
) -> dict:
    """Return lesson feedbacks."""
    safe_page_index = max(int(page_index or 1), 1)
    safe_page_size = min(max(int(page_size or 20), 1), 100)

    with app.app_context():
        query = LearnLessonFeedback.query.filter(
            LearnLessonFeedback.shifu_bid == shifu_bid,
            LearnLessonFeedback.deleted == 0,
        )
        if outline_bid:
            query = query.filter(LearnLessonFeedback.outline_item_bid == outline_bid)

        total = query.count()
        rows = (
            query.order_by(
                LearnLessonFeedback.updated_at.desc(), LearnLessonFeedback.id.desc()
            )
            .offset((safe_page_index - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        return {
            "items": [
                {
                    "lesson_feedback_bid": row.lesson_feedback_bid,
                    "shifu_bid": row.shifu_bid,
                    "outline_bid": row.outline_item_bid,
                    "progress_record_bid": row.progress_record_bid,
                    "user_bid": row.user_bid,
                    "score": row.score,
                    "comment": row.comment,
                    "mode": row.mode,
                    "created_at": to_utc_iso(row.created_at),
                    "updated_at": to_utc_iso(row.updated_at),
                }
                for row in rows
            ],
            "total": total,
            "page_index": safe_page_index,
            "page_size": safe_page_size,
        }
