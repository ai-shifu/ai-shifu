"""Resolve explicit, published, same-owner references without copying learner values."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.shifu.models import DraftShifu, PublishedOutlineItem, PublishedShifu
from markdown_flow import MarkdownFlow
from sqlalchemy import and_, func, or_, select

if TYPE_CHECKING:
    from collections.abc import Iterable

COURSE_REFERENCE_PREFIX = "course:"
SHARED_ANSWER_PREFIX = "share:"
SHARED_ANSWER_NAME = re.compile(r"share:([0-9a-f]{32}):([a-zA-Z_][a-zA-Z0-9_-]*)\Z")
MAX_COURSE_REFERENCES = 32
_REFERENCE = re.compile(r"course:([0-9a-f]{32}):([^:{}\s]+)\Z")
_READ_VARIABLE = re.compile(r"(?<!%)\{\{\s*([^{}\s]+)\s*\}\}")


def is_course_reference(key: str) -> bool:
    """Reserve the entire namespace, including malformed or unauthorized references."""
    return key.startswith((COURSE_REFERENCE_PREFIX, SHARED_ANSWER_PREFIX))


def is_course_reference_name(key: str) -> bool:
    """Recognize the explicit source notation without interpreting format specifiers."""
    return len(key) <= 255 and bool(
        _REFERENCE.fullmatch(key) or SHARED_ANSWER_NAME.fullmatch(key)
    )


def course_reference_reads(text: str) -> set[str]:
    """Find explicit reads in one author document, excluding fences and comments."""
    if COURSE_REFERENCE_PREFIX not in text:
        return set()
    return {
        key
        for block in MarkdownFlow(text).get_all_blocks()
        for key in _READ_VARIABLE.findall(block.content)
        if is_course_reference(key)
    }


def _owner(course: str, *, lock: bool = False) -> str | None:
    """Require current and published ownership to agree; old live revisions cannot revive it."""
    rows = []
    for model in (DraftShifu, PublishedShifu):
        query = model.query.filter_by(shifu_bid=course)
        if lock:
            query = query.populate_existing().with_for_update()
        rows.append(query.order_by(model.id.desc()).first())
    draft, published = rows
    if (
        draft is None
        or published is None
        or draft.deleted
        or published.deleted
        or not draft.created_user_bid
        or draft.created_user_bid != published.created_user_bid
    ):
        return None
    return draft.created_user_bid


def _published_reads(course: str) -> set[str]:
    """Read actual author content, excluding collected names, fences and comments."""
    heads = (
        db.session.query(func.max(PublishedOutlineItem.id))
        .filter(PublishedOutlineItem.shifu_bid == course)
        .group_by(PublishedOutlineItem.outline_item_bid)
        .subquery()
    )
    outlines = PublishedOutlineItem.query.filter(
        PublishedOutlineItem.id.in_(select(heads)), PublishedOutlineItem.deleted == 0
    ).all()
    published = (
        PublishedShifu.query.filter_by(shifu_bid=course)
        .order_by(PublishedShifu.id.desc())
        .first()
    )
    texts = [published.llm_system_prompt or ""] if published else []
    for outline in outlines:
        texts.extend((outline.content or "", outline.llm_system_prompt or ""))
    return set().union(*(course_reference_reads(text) for text in texts))


def load_course_references(
    user_bid: str,
    course: str,
    candidates: Iterable[str],
    *,
    reserved: frozenset[str],
) -> dict[str, str]:
    """Resolve at most 32 declared published names for this learner, with no global fallback."""
    candidates = {key for key in candidates if is_course_reference(key)}
    if not candidates or not course or not user_bid:
        return {}
    owner = _owner(course)
    if not owner:
        return {}
    definitions = Variable.query.filter(
        Variable.shifu_bid == course,
        Variable.deleted == 0,
        Variable.key.in_(candidates),
    ).all()
    eligible = _published_reads(course) & {item.key for item in definitions}
    references: dict[str, tuple[str, str]] = {}
    owners: dict[str, str | None] = {course: owner}
    for name in sorted(eligible)[:MAX_COURSE_REFERENCES]:
        match = _REFERENCE.fullmatch(name)
        if match is None or len(name) > 255:
            continue
        source, key = match.groups()
        if source == course or key.startswith("sys_") or key in reserved:
            continue
        if source not in owners:
            owners[source] = _owner(source)
        if owners[source] == owner:
            references[name] = (source, key)
    if not references:
        return {}
    heads = (
        db.session.query(func.max(VariableValue.id))
        .filter(
            VariableValue.user_bid == user_bid,
            or_(
                *(
                    and_(VariableValue.shifu_bid == source, VariableValue.key == key)
                    for source, key in set(references.values())
                )
            ),
        )
        .group_by(VariableValue.shifu_bid, VariableValue.key)
        .subquery()
    )
    rows = VariableValue.query.filter(VariableValue.id.in_(select(heads))).all()
    values = {(row.shifu_bid, row.key): row.value for row in rows if not row.deleted}
    return {name: values[pair] for name, pair in references.items() if pair in values}
