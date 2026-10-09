"""Manage a learner's persistent custom course values and deletion generations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.profile.funcs import get_global_profile_keys
from flaskr.service.profile.models import VariableValue
from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Query


def _course_rows(user_bid: str, shifu_bid: str) -> Query[VariableValue]:
    return VariableValue.query.filter(
        VariableValue.user_bid == user_bid,
        VariableValue.shifu_bid == shifu_bid,
        ~VariableValue.key.startswith("sys_", autoescape=True),
        VariableValue.key.not_in(get_global_profile_keys()),
        VariableValue.key != "",
    )


def course_memory_deletion_state(
    user_bid: str, shifu_bid: str, *, lock: bool = False
) -> tuple[dict[str, int], frozenset[str]]:
    """Read deletion generations and keys whose newest version is deleted.

    Locking reads are current reads under MySQL repeatable-read isolation. Callers
    holding this lock must finish their unit of work before releasing it; model
    calls must never occur inside that transaction.
    """
    query = (
        _course_rows(user_bid, shifu_bid)
        .with_entities(VariableValue.id, VariableValue.key, VariableValue.deleted)
        .order_by(VariableValue.id)
    )
    if lock:
        query = query.populate_existing().with_for_update()
    rows = query.all()
    generations: dict[str, int] = {}
    live: set[str] = set()
    for row in rows:
        if not row.deleted:
            live.add(row.key)
        if row.deleted:
            generations[row.key] = row.id
    return generations, frozenset(generations.keys() - live)


def course_memory_value_versions(
    user_bid: str, shifu_bid: str, *, lock: bool = False
) -> dict[str, int]:
    """Read latest row versions so delayed proposals cannot overwrite newer values.

    A locking read is current under repeatable-read isolation and must remain in
    the caller's final write transaction, never across model calls.
    """
    query = (
        _course_rows(user_bid, shifu_bid)
        .with_entities(VariableValue.id, VariableValue.key)
        .order_by(VariableValue.id)
    )
    if lock:
        query = query.populate_existing().with_for_update()
    return {row.key: row.id for row in query.all()}


def list_course_memory(
    user_bid: str, shifu_bid: str, *, before: int | None = None
) -> dict:
    """Page all current custom values, independently of model context budgets."""
    heads = (
        _course_rows(user_bid, shifu_bid)
        .filter(VariableValue.deleted == 0)
        .with_entities(func.max(VariableValue.id))
        .group_by(VariableValue.key)
        .subquery()
    )
    query = VariableValue.query.filter(
        VariableValue.id.in_(select(heads)), VariableValue.deleted == 0
    )
    if before is not None:
        query = query.filter(VariableValue.id < before)
    rows = query.order_by(VariableValue.id.desc()).limit(51).all()
    return {
        "items": [
            {
                "value_id": str(row.id),
                "key": row.key,
                "value": row.value,
                "updated_at": row.updated_at,
            }
            for row in rows[:50]
        ],
        "next_before": str(rows[49].id) if len(rows) > 50 else None,
    }


def delete_course_memory(user_bid: str, shifu_bid: str, value_id: int) -> dict:
    """Invalidate all versions of an owned key, refusing a stale version selection."""
    with unit_of_work():
        rows = (
            _course_rows(user_bid, shifu_bid)
            .with_entities(VariableValue.id, VariableValue.key, VariableValue.deleted)
            .order_by(VariableValue.id)
            .populate_existing()
            .with_for_update()
            .all()
        )
        selected = next((r for r in rows if r.id == value_id), None)
        if selected is None:
            return {"conflict": False}
        versions = [r for r in rows if r.key == selected.key]
        newest = max(
            (r for r in versions if not r.deleted), key=lambda r: r.id, default=None
        )
        if newest is not None and newest.id != value_id:
            return {"conflict": True}
        if newest is None:
            return {"conflict": False}
        _course_rows(user_bid, shifu_bid).filter(
            VariableValue.key == selected.key, VariableValue.deleted == 0
        ).update({VariableValue.deleted: 1}, synchronize_session="fetch")
        # An appended marker advances the generation even when a legacy retired
        # row already had a larger ID than the live value being deleted.
        db.session.add(
            VariableValue(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                key=selected.key,
                value="",
                variable_value_bid=uuid4().hex,
                deleted=1,
            )
        )
        db.session.flush()
        return {"conflict": False}
