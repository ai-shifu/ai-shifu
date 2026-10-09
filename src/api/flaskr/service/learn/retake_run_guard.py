"""Serialize all enabled lesson producers with reset admission.

This is separate from retake accounting: first study and continuation consume no
retake, but must still exclude a simultaneous reset. Slots are not refunded by
age. Explicit platform repair requires the exact old producer identity and a
confirmed stop; it is never exposed as a learner or teacher API.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, require_transaction_owner, unit_of_work
from flaskr.service.learn.retake_ledger import (
    _lock_policy,
    ensure_default_policy,
    finish_attempt,
)
from flaskr.service.learn.retake_models import (
    LessonRetakeAttempt,
    LessonRetakeRun,
)
from flaskr.service.learn.retake_policy import RetakeRuleError, RetakeState
from flaskr.service.learn.retake_recovery import stage_restore_records
from flaskr.util.datetime import now_utc, to_utc_iso

if TYPE_CHECKING:
    from flask import Flask


@dataclass(frozen=True)
class LessonRunOwnership:
    """An immutable producer identity, not a quota charge."""

    namespace: str
    shifu_bid: str
    user_bid: str
    outline_bid: str
    producer_id: str
    attempt_id: str | None

    def scope(self) -> dict:
        """Stable key for the single producer slot."""
        return {
            "namespace": self.namespace,
            "shifu_bid": self.shifu_bid,
            "user_bid": self.user_bid,
            "outline_bid": self.outline_bid,
        }


def _pending(scope: dict) -> LessonRetakeAttempt | None:
    return (
        LessonRetakeAttempt.query.filter_by(**scope, producer_finished_at=None)
        .filter(
            LessonRetakeAttempt.state.in_(
                [RetakeState.RESERVED, RetakeState.RUNNING, RetakeState.COMMITTED]
            )
        )
        .with_for_update()
        .populate_existing()
        .first()
    )


def pending_lesson_attempt(**scope: str) -> bool:
    """Read existing obligations without enabling a new retake policy."""
    return (
        LessonRetakeAttempt.query.filter_by(**scope, producer_finished_at=None)
        .filter(
            LessonRetakeAttempt.state.in_(
                [
                    RetakeState.RESERVED,
                    RetakeState.RUNNING,
                    RetakeState.COMMITTED,
                ]
            )
        )
        .first()
        is not None
    )


def inspect_lesson_run(
    app: Flask, *, namespace: str, shifu_bid: str, user_bid: str, outline_bid: str
) -> dict:
    """Return operator diagnostics without releasing a slot or changing usage.

    This is application-shell tooling, not a learner endpoint. A pending record
    or its age cannot prove that a producer has stopped.
    """
    scope = {
        "namespace": namespace,
        "shifu_bid": shifu_bid,
        "user_bid": user_bid,
        "outline_bid": outline_bid,
    }
    with app_context_scope(app):
        row = LessonRetakeRun.query.filter_by(**scope).first()
        attempt = (
            LessonRetakeAttempt.query.filter_by(**scope, producer_finished_at=None)
            .filter(
                LessonRetakeAttempt.state.in_(
                    [
                        RetakeState.RESERVED,
                        RetakeState.RUNNING,
                        RetakeState.COMMITTED,
                    ]
                )
            )
            .first()
        )
        return {
            "blocked": (row is not None and row.finished_at is None)
            or attempt is not None,
            "producer_id": row.producer_id if row else None,
            "started_at": to_utc_iso(row.started_at) if row else None,
            "finished_at": to_utc_iso(row.finished_at)
            if row and row.finished_at
            else None,
            "attempt_id": attempt.attempt_id if attempt else None,
            "attempt_state": str(attempt.state) if attempt else None,
        }


def acquire_lesson_run(
    app: Flask,
    *,
    namespace: str,
    shifu_bid: str,
    user_bid: str,
    outline_bid: str,
    reload: bool = False,
) -> LessonRunOwnership | None:
    """Claim before touching progress or calling a model; release after unwind."""
    require_transaction_owner("acquire_lesson_run", app)
    scope = {
        "namespace": namespace,
        "shifu_bid": shifu_bid,
        "user_bid": user_bid,
        "outline_bid": outline_bid,
    }
    with app_context_scope(app), unit_of_work():
        ensure_default_policy(app, namespace=namespace, shifu_bid=shifu_bid)
        _lock_policy(namespace, shifu_bid)
        row = (
            LessonRetakeRun.query.filter_by(**scope)
            .with_for_update()
            .populate_existing()
            .first()
        )
        pending = _pending(scope)
        if (row is not None and row.finished_at is None) or (
            pending is not None and (reload or pending.state != RetakeState.RESERVED)
        ):
            reason = "retake_in_progress"
            raise RetakeRuleError(reason)
        if reload:
            reason = "retake_reload_not_supported"
            raise RetakeRuleError(reason)
        producer_id = uuid.uuid4().hex
        if row is None:
            row = LessonRetakeRun(**scope, producer_id=producer_id)
            db.session.add(row)
        row.producer_id = producer_id
        row.started_at = now_utc()
        row.finished_at = None
        return LessonRunOwnership(
            **scope,
            producer_id=producer_id,
            attempt_id=pending.attempt_id if pending else None,
        )


def release_lesson_run(app: Flask, ownership: LessonRunOwnership) -> None:
    """Release only this producer's slot, never a newer worker's slot."""
    with app_context_scope(app), unit_of_work():
        _lock_policy(ownership.namespace, ownership.shifu_bid)
        row = (
            LessonRetakeRun.query.filter_by(**ownership.scope())
            .with_for_update()
            .populate_existing()
            .first()
        )
        if (
            row is not None
            and row.producer_id == ownership.producer_id
            and row.finished_at is None
        ):
            row.finished_at = now_utc()


def repair_stopped_lesson_run(
    app: Flask,
    *,
    namespace: str,
    shifu_bid: str,
    user_bid: str,
    outline_bid: str,
    expected_producer_id: str,
    operator_bid: str,
    confirmed_stopped: bool,
) -> None:
    """Platform-only recovery after externally verifying that the worker stopped.

    The deployment operator must stop/replace the worker and confirm its absence
    before invoking this service from the application shell. A timeout, browser
    disconnect or a learner's report alone is insufficient. Stale identities fail
    closed. The repair and any refunded attempt restore in one transaction.
    """
    if (
        confirmed_stopped is not True
        or not operator_bid
        or len(operator_bid) > 36
        or not expected_producer_id
    ):
        reason = "repair_requires_confirmed_stop"
        raise RetakeRuleError(reason)
    scope = {
        "namespace": namespace,
        "shifu_bid": shifu_bid,
        "user_bid": user_bid,
        "outline_bid": outline_bid,
    }
    with app_context_scope(app), unit_of_work():
        _lock_policy(namespace, shifu_bid)
        row = (
            LessonRetakeRun.query.filter_by(**scope)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if row is None or row.producer_id != expected_producer_id:
            reason = "producer_mismatch"
            raise RetakeRuleError(reason)
        pending = _pending(scope)
        if pending is not None:
            if pending.producer_id not in (None, expected_producer_id):
                reason = "producer_mismatch"
                raise RetakeRuleError(reason)

            def restore() -> None:
                stage_restore_records(
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    snapshot=pending.recovery_data,
                )

            delivered = pending.state == RetakeState.COMMITTED
            finish_attempt(
                app,
                namespace=namespace,
                shifu_bid=shifu_bid,
                attempt_id=pending.attempt_id,
                producer_id=pending.producer_id,
                has_durable_content=delivered,
                producer_stopped=True,
                stage=None if delivered else restore,
            )
        if row.finished_at is not None and pending is None:
            return
        row.finished_at = now_utc()
        row.repair_log = [
            *(row.repair_log or []),
            {
                "operator_bid": operator_bid,
                "producer_id": expected_producer_id,
                "repaired_at": to_utc_iso(row.finished_at),
            },
        ]
