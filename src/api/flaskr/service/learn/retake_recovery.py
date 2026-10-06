"""Transactional progress/session snapshots for a failed new retake round.

Only references and fields changed by reset are retained; teaching content stays
in the original rows. Call these staging helpers inside the ledger transaction.
"""

from flaskr.dao import db
from flaskr.dao.uow import in_unit_of_work
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.const import ROLE_TEACHER
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.learn.retake_policy import RetakeRuleError
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.shifu.consts import BLOCK_TYPE_MDCONTENT_VALUE
from sqlalchemy import and_, or_


def _require_transaction() -> None:
    if not in_unit_of_work():
        reason = "recovery_requires_transaction"
        raise RetakeRuleError(reason)


def _progress(user_bid: str, shifu_bid: str, outline_bid: str):  # noqa: ANN202 - SQLAlchemy legacy Query
    return LearnProgressRecord.query.filter_by(
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        deleted=0,
    )


def stage_reset_records(*, user_bid: str, shifu_bid: str, outline_bid: str) -> dict:
    """Save the reset boundary and retire only this learner's non-preview state."""
    _require_transaction()
    records = (
        _progress(user_bid, shifu_bid, outline_bid)
        .filter(LearnProgressRecord.status != LEARN_STATUS_RESET)
        .with_for_update()
        .all()
    )
    previous_teaching = LearnGeneratedBlock.query.filter(
        LearnGeneratedBlock.user_bid == user_bid,
        LearnGeneratedBlock.shifu_bid == shifu_bid,
        LearnGeneratedBlock.outline_item_bid == outline_bid,
        LearnGeneratedBlock.progress_record_bid.in_(
            [row.progress_record_bid for row in records]
        ),
        LearnGeneratedBlock.deleted == 0,
        LearnGeneratedBlock.status == 1,
        or_(
            LearnGeneratedBlock.role == ROLE_TEACHER,
            # Historical agent turns used an empty source block and default role 0.
            # Keep student/error blocks and source-backed legacy rows excluded.
            and_(
                LearnGeneratedBlock.role == 0,
                LearnGeneratedBlock.block_bid == "",
            ),
        ),
        LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
        LearnGeneratedBlock.generated_content != "",
    ).first()
    if not records or previous_teaching is None:
        reason = "nothing_to_retake"
        raise RetakeRuleError(reason)
    key = active_key_for(user_bid, outline_bid, preview_mode=False)
    session = (
        LearnAgentSession.query.filter_by(
            active_key=key,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            deleted=0,
        )
        .with_for_update()
        .first()
    )
    snapshot = {
        "version": 1,
        "progress": [
            {"bid": row.progress_record_bid, "status": row.status} for row in records
        ],
        "session_bid": session.agent_session_bid if session else None,
    }
    for row in records:
        row.status = LEARN_STATUS_RESET
    if session is not None:
        session.deleted = 1
        session.active_key = None
    return snapshot


def stage_restore_records(
    *, user_bid: str, shifu_bid: str, outline_bid: str, snapshot: dict
) -> None:
    """Restore once, only after the owning producer stopped without teaching.

    Old content is never copied or deleted. Empty replacement records are retired
    before restoring the exact original status and agent-session identity.
    """
    _require_transaction()
    if not snapshot or snapshot.get("version") != 1:
        reason = "invalid_recovery_snapshot"
        raise RetakeRuleError(reason)
    old = {item["bid"]: item["status"] for item in snapshot["progress"]}
    records = _progress(user_bid, shifu_bid, outline_bid).with_for_update().all()
    originals = {
        row.progress_record_bid: row
        for row in records
        if row.progress_record_bid in old
    }
    if len(originals) != len(old) or any(
        row.status != LEARN_STATUS_RESET for row in originals.values()
    ):
        reason = "recovery_state_changed"
        raise RetakeRuleError(reason)
    key = active_key_for(user_bid, outline_bid, preview_mode=False)
    current = (
        LearnAgentSession.query.filter_by(active_key=key).with_for_update().first()
    )
    if current is not None:
        current.active_key = None
        current.deleted = 1
        db.session.flush()
    for row in records:
        row.status = old.get(row.progress_record_bid, LEARN_STATUS_RESET)
    if snapshot["session_bid"]:
        previous = (
            LearnAgentSession.query.filter_by(
                agent_session_bid=snapshot["session_bid"],
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                deleted=1,
            )
            .with_for_update()
            .first()
        )
        if previous is None:
            reason = "recovery_session_missing"
            raise RetakeRuleError(reason)
        previous.deleted = 0
        previous.active_key = key
