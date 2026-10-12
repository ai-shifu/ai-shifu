"""Compare lesson content revisions without reading text or conversation JSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.learn.agent.models import (
    AGENT_SESSION_SCHEMA_VERSION,
    LearnAgentSession,
    active_key_for,
)
from sqlalchemy import select, tuple_

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class LessonContentState:
    """Learning status and content freshness for one scoped lesson attempt."""

    started: bool = False
    finished: bool = False
    has_content_update: bool = False


def _content_state(
    baseline: int | None,
    current: int | None,
    turn: int,
    finished: int,
    schema_version: int,
) -> LessonContentState:
    # A persisted revision (including unknown=0) means actual messages were saved.
    # Legacy sessions retain their scalar progress even without a known baseline.
    # An unreadable document schema only disqualifies the update recommendation.
    started = baseline is not None or turn > 0 or finished == 1
    return LessonContentState(
        started=started,
        finished=started and finished == 1,
        has_content_update=bool(
            schema_version == AGENT_SESSION_SCHEMA_VERSION
            and baseline
            and baseline > 0
            and current
            and current > 0
            and baseline != current
        ),
    )


def lesson_content_state_from_session(
    *,
    row: LearnAgentSession | None,
    current_revision: int | None,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
) -> LessonContentState:
    """Reuse a loaded preview session with the same rules as batch reads."""
    if (
        row is None
        or row.user_bid != user_bid
        or row.shifu_bid != shifu_bid
        or row.outline_item_bid != outline_bid
        or row.active_key
        != active_key_for(user_bid, outline_bid, preview_mode=preview_mode)
        or row.deleted != 0
    ):
        return LessonContentState()
    return _content_state(
        row.content_revision,
        current_revision,
        row.turn,
        row.finished,
        row.schema_version,
    )


def load_lesson_content_states(
    *,
    user_bid: str,
    shifu_bid: str,
    preview_mode: bool,
    outline_revisions: Mapping[str, int | None],
) -> dict[str, LessonContentState]:
    """Read one indexed scalar batch for lessons in the validated current structure.

    The caller filters hidden/deleted/non-leaf physical outline records and
    formal progress. Missing version metadata remains unknown; this read never
    reconstructs a baseline from history or the current lesson.
    """
    if not outline_revisions:
        return {}
    session = LearnAgentSession.__table__.c
    scoped_keys = [
        (bid, active_key_for(user_bid, bid, preview_mode=preview_mode))
        for bid in outline_revisions
    ]
    query = select(
        session.outline_item_bid,
        session.content_revision,
        session.turn,
        session.finished,
        session.schema_version,
    ).where(
        session.active_key.in_([key for _, key in scoped_keys]),
        tuple_(session.outline_item_bid, session.active_key).in_(scoped_keys),
        session.user_bid == user_bid,
        session.shifu_bid == shifu_bid,
        session.deleted == 0,
    )
    return {
        row.outline_item_bid: _content_state(
            row.content_revision,
            outline_revisions[row.outline_item_bid],
            row.turn,
            row.finished,
            row.schema_version,
        )
        for row in db.session.execute(query)
    }
