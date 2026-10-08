"""Authorize explicit named-answer writes to existing same-owner course variables."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.service.profile.course_references import (
    SHARED_ANSWER_NAME,
    SHARED_ANSWER_PREFIX,
    _owner,
)
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.shifu.models import PublishedOutlineItem
from markdown_flow import MarkdownFlow
from sqlalchemy import func, select

if TYPE_CHECKING:
    from collections.abc import Iterable

    from flask import Flask

_NAME = SHARED_ANSWER_NAME
_COLLECT = re.compile(r"%\{\{\s*([^{}\s]+)\s*\}\}")
_READ = re.compile(r"(?<!%)\{\{\s*([^{}\s]+)\s*\}\}")


@dataclass(frozen=True)
class SharedAnswer:
    """One authorized source value version; no database object crosses into the engine."""

    source: str
    key: str
    value_id: int
    value: str


def shared_answer_names(text: str, *, collect: bool = False) -> frozenset[str]:
    """Recognize explicit reads or main-script collections outside fences/comments."""
    if SHARED_ANSWER_PREFIX not in text:
        return frozenset()
    pattern = _COLLECT if collect else _READ
    return frozenset(
        name
        for block in MarkdownFlow(text).get_all_blocks()
        for name in pattern.findall(block.content)
        if len(name) <= 255 and _NAME.fullmatch(name)
    )


def load_shared_answers(
    user_bid: str,
    course: str,
    names: Iterable[str],
    *,
    reserved: frozenset[str],
    outline_bid: str | None = None,
    lock: bool = False,
) -> dict[str, SharedAnswer]:
    """Resolve at most 32 published declarations and existing live source versions.

    Writes supply an outline ID and require its exact current collection declaration.
    Reads may use published read declarations anywhere in the destination course, with
    the caller independently supplying names from its current trusted author context.
    Locking resolution is only for the caller's persistence transaction, never a model call.
    """
    names = sorted(
        {name for name in names if _NAME.fullmatch(name) and len(name) <= 255}
    )[:32]
    if not names or not user_bid or not course:
        return {}
    owners = {
        bid: _owner(bid, lock=lock)
        for bid in sorted({course, *(_NAME.fullmatch(name).group(1) for name in names)})
    }
    owner = owners[course]
    if not owner:
        return {}
    query = PublishedOutlineItem.query.filter_by(shifu_bid=course)
    if outline_bid is not None:
        query = (
            query.filter_by(outline_item_bid=outline_bid)
            .order_by(PublishedOutlineItem.id.desc())
            .limit(1)
        )
    else:
        heads_query = (
            PublishedOutlineItem.query.with_entities(func.max(PublishedOutlineItem.id))
            .filter_by(shifu_bid=course)
            .group_by(PublishedOutlineItem.outline_item_bid)
            .subquery()
        )
        query = query.filter(PublishedOutlineItem.id.in_(select(heads_query)))
    if lock:
        query = query.populate_existing().with_for_update()
    heads: dict[str, PublishedOutlineItem] = {}
    for row in query.all():
        heads.setdefault(row.outline_item_bid, row)
    declared = set().union(
        *(
            shared_answer_names(row.content or "", collect=outline_bid is not None)
            for row in heads.values()
            if not row.deleted
        )
    )
    definitions = Variable.query.filter(
        Variable.shifu_bid == course, Variable.deleted == 0, Variable.key.in_(names)
    )
    if lock:
        definitions = definitions.populate_existing().with_for_update()
    declared &= {row.key for row in definitions.all()}
    result = {}
    for name in names:
        if name not in declared:
            continue
        source, key = _NAME.fullmatch(name).groups()
        if source == course or key.startswith("sys_") or key in reserved:
            continue
        if owners[source] != owner:
            continue
        definition = Variable.query.filter_by(shifu_bid=source, key=key, deleted=0)
        values = VariableValue.query.filter_by(
            user_bid=user_bid, shifu_bid=source, key=key
        )
        if lock:
            definition = definition.populate_existing().with_for_update()
            values = values.populate_existing().with_for_update()
        if definition.first() is None:
            continue
        value = values.order_by(VariableValue.id.desc()).first()
        if value is not None and not value.deleted:
            result[name] = SharedAnswer(source, key, value.id, value.value)
    return result


def stage_shared_answers(
    app: Flask,
    user_bid: str,
    course: str,
    outline_bid: str,
    values: dict[str, str],
    expected: dict[str, SharedAnswer],
) -> frozenset[str]:
    """Write accepted versions through the profile adapter in the caller's transaction.

    A deleted, changed or no-longer-authorized source is never restored or overwritten
    by an in-flight answer. Rejections leave the learner's answer as classroom evidence.
    """
    from flaskr.service.profile.dtos import ProfileToSave
    from flaskr.service.profile.funcs import get_global_profile_keys, save_user_profiles

    current = load_shared_answers(
        user_bid,
        course,
        values,
        reserved=get_global_profile_keys(),
        outline_bid=outline_bid,
        lock=True,
    )
    accepted = set()
    for name, value in values.items():
        source = current.get(name)
        if source is None or source != expected.get(name):
            continue
        save_user_profiles(
            app, user_bid, source.source, [ProfileToSave(source.key, value, "")]
        )
        accepted.add(name)
    return frozenset(accepted)
