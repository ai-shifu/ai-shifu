"""Use one precedence for active progress in teaching, history, and the catalog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_LOCKED, LEARN_STATUS_NOT_STARTED

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

_PLACEHOLDER_STATUSES = (LEARN_STATUS_NOT_STARTED, LEARN_STATUS_LOCKED)


def progress_record_order() -> tuple[ColumnElement[bool], ColumnElement[int]]:
    """Sort active rows with started attempts first, then newest within each group."""
    return (
        LearnProgressRecord.status.in_(_PLACEHOLDER_STATUSES).asc(),
        LearnProgressRecord.id.desc(),
    )


def progress_record_rank(record: LearnProgressRecord) -> tuple[bool, int]:
    """Return the equivalent precedence when selecting from already loaded rows."""
    return (record.status not in _PLACEHOLDER_STATUSES, int(record.id or 0))
