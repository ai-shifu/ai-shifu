"""Resolve and authorize the course version attached to a durable lesson attempt."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from flaskr.dao.uow import app_context_scope
from flaskr.service.common.models import raise_error
from flaskr.service.learn.agent.lesson_record import find_active_progress_record
from flaskr.service.learn.agent.session_store import (
    LessonAttemptSource,
    load_lesson_attempt_source,
)
from flaskr.service.learn.preview_permissions import require_shifu_preview_permission
from flaskr.service.shifu.api import HistoryItem
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)

if TYPE_CHECKING:
    from flask import Flask


@dataclass(frozen=True)
class ResolvedLessonSource:
    """The content and course settings resolved from one physical version."""

    source: LessonAttemptSource
    outline: DraftOutlineItem | PublishedOutlineItem
    course: DraftShifu | PublishedShifu
    structure: HistoryItem | None
    progress_record_bid: str | None = None


def resolve_requested_lesson_source(
    *, shifu_bid: str, outline_bid: str, preview_mode: bool
) -> ResolvedLessonSource:
    """Read current rows for the requested version, independent of an attempt."""
    return _read_source(
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        preview_mode=preview_mode,
        pinned=None,
    )


def resolve_lesson_source(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
) -> ResolvedLessonSource:
    """Resume the pinned source, or use the requested version for a fresh attempt."""
    scope = {"user_bid": user_bid, "shifu_bid": shifu_bid, "outline_bid": outline_bid}
    with app_context_scope(app):
        pinned = load_lesson_attempt_source(**scope)
        source_is_draft = pinned.preview_mode if pinned is not None else preview_mode
        if source_is_draft:
            require_shifu_preview_permission(app, user_bid, shifu_bid)
        resolved = _read_source(
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=source_is_draft,
            pinned=pinned,
        )
        progress = find_active_progress_record(**scope)
        return (
            replace(resolved, progress_record_bid=progress.progress_record_bid)
            if progress is not None
            else resolved
        )


def _read_source(
    *,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
    pinned: LessonAttemptSource | None,
) -> ResolvedLessonSource:
    course_model = DraftShifu if preview_mode else PublishedShifu
    outline_model = DraftOutlineItem if preview_mode else PublishedOutlineItem
    structure_model = LogDraftStruct if preview_mode else LogPublishedStruct
    courses = course_model.query.filter_by(shifu_bid=shifu_bid)
    outlines = outline_model.query.filter_by(
        shifu_bid=shifu_bid, outline_item_bid=outline_bid
    )
    structures = structure_model.query.filter_by(shifu_bid=shifu_bid)
    live_course = courses.filter_by(deleted=0).order_by(course_model.id.desc()).first()
    if live_course is None:
        raise_error("server.shifu.shifuNotFound")
    exact = pinned is not None and pinned.outline_row_id is not None
    if exact:
        # Old physical rows can be marked deleted when an edit or publication
        # supersedes them. The requested route checks current lesson visibility.
        outline = outlines.filter_by(id=pinned.outline_row_id).first()
        course = courses.filter_by(id=pinned.course_row_id).first()
        structure_row = structures.filter_by(id=pinned.structure_row_id).first()
        if (
            (pinned.structure_row_id is not None and structure_row is None)
            or outline is None
            or course is None
        ):
            raise_error("server.learn.agentRewindUnavailable")
    else:
        live_outline = (
            outlines.filter_by(deleted=0).order_by(outline_model.id.desc()).first()
        )
        if live_outline is None or live_outline.hidden:
            raise_error("server.shifu.lessonNotFoundInCourse")
        structure_row = (
            structures.filter_by(deleted=0).order_by(structure_model.id.desc()).first()
        )
        outline = live_outline
        course = live_course
    structure = (
        HistoryItem.from_json(structure_row.struct)
        if structure_row is not None
        else None
    )
    revision = None
    if structure is not None:
        node = _find_lesson(structure, outline_bid)
        if node is None or structure.bid != shifu_bid:
            raise_error("server.shifu.lessonNotFoundInCourse")
        if not exact:
            outline = outlines.filter_by(id=node.id, deleted=0, hidden=0).first()
            course = courses.filter_by(id=structure.id, deleted=0).first()
        if (
            outline is None
            or course is None
            or node.id != outline.id
            or structure.id != course.id
        ):
            raise_error("server.shifu.lessonNotFoundInCourse")
        revision = node.content_revision
    elif (
        not exact
        and outline_model.query.filter_by(
            shifu_bid=shifu_bid, parent_bid=outline_bid, deleted=0
        ).first()
        is not None
    ):
        raise_error("server.shifu.lessonNotFoundInCourse")
    source = (
        pinned
        if pinned is not None
        else LessonAttemptSource(
            preview_mode=preview_mode,
            outline_row_id=outline.id,
            course_row_id=course.id,
            structure_row_id=structure_row.id if structure_row is not None else None,
            content_revision=revision,
        )
    )
    return ResolvedLessonSource(source, outline, course, structure)


def _find_lesson(structure: HistoryItem, outline_bid: str) -> HistoryItem | None:
    from flaskr.service.learn.learn_funcs import is_lesson_outline

    pending = list(structure.children)
    while pending:
        node = pending.pop()
        if node.type == "outline" and node.bid == outline_bid:
            return node if is_lesson_outline(node) else None
        pending.extend(node.children)
    return None
