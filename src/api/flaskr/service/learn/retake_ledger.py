"""Transactional retake accounting, ready for the runtime's content commit boundary.

Every mutation locks the existing course policy before reading the balance. The
lock is released before any generation. This serializes last-slot admission and
policy edits on MySQL without relying on a frontend counter or a Redis lease.

Callers authenticate/authorize first. Runtime integration must settle content and
this ledger in the SAME unit of work; releasing requires that the owning producer
is stopped. A lost browser connection is not that proof.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.learn.retake_models import (
    CourseRetakePolicy,
    LessonRetakeAttempt,
    LessonRetakeRun,
)
from flaskr.service.learn.retake_policy import (
    DEFAULT_RETAKE_LIMIT,
    RetakeAllowance,
    RetakeRuleError,
    RetakeState,
    begin_attempt,
    settle_attempt,
    validate_limit,
)
from flaskr.util.datetime import now_utc
from sqlalchemy import func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask


def _validate_identity(*parts: tuple[str, int]) -> None:
    for value, maximum in parts:
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            reason = "invalid_identity"
            raise RetakeRuleError(reason)


def _lock_policy(namespace: str, shifu_bid: str) -> CourseRetakePolicy:
    row = (
        CourseRetakePolicy.query.filter_by(namespace=namespace, shifu_bid=shifu_bid)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if row is None:
        reason = "policy_not_enabled"
        raise RetakeRuleError(reason)
    return row


def configure_policy(
    app: Flask, *, namespace: str, shifu_bid: str, limit: int | None
) -> None:
    """First configuration starts the ledger; editing never clears history."""
    _validate_identity((namespace, 32), (shifu_bid, 36))
    validate_limit(limit)
    with app_context_scope(app), unit_of_work():
        row = (
            CourseRetakePolicy.query.filter_by(namespace=namespace, shifu_bid=shifu_bid)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if row is None:
            try:
                with db.session.begin_nested():
                    db.session.add(
                        CourseRetakePolicy(
                            namespace=namespace, shifu_bid=shifu_bid, lesson_limit=limit
                        )
                    )
                    db.session.flush()
            except IntegrityError:
                # A simultaneous first configuration won the primary-key race.
                row = _lock_policy(namespace, shifu_bid)
            else:
                return
        row.lesson_limit = limit


def ensure_default_policy(app: Flask, *, namespace: str, shifu_bid: str) -> None:
    """Reuse the course lock and history, replacing legacy settings with ten.

    Concurrent first activation uses an atomic MySQL upsert before row locking.
    The internal configurable primitive is retained for rollback and testing;
    every public admission path initializes the fixed platform rule first.
    """
    _validate_identity((namespace, 32), (shifu_bid, 36))
    with app_context_scope(app), unit_of_work():
        if db.engine.dialect.name == "mysql":
            # Insert before a missing-row SELECT lock: two first learners would
            # otherwise both hold gap locks and deadlock while inserting.
            statement = mysql_insert(CourseRetakePolicy).values(
                namespace=namespace,
                shifu_bid=shifu_bid,
                lesson_limit=DEFAULT_RETAKE_LIMIT,
            )
            db.session.execute(
                statement.on_duplicate_key_update(lesson_limit=DEFAULT_RETAKE_LIMIT)
            )
        else:
            configure_policy(
                app,
                namespace=namespace,
                shifu_bid=shifu_bid,
                limit=DEFAULT_RETAKE_LIMIT,
            )


def _attempts(namespace: str, shifu_bid: str, user_bid: str, outline_bid: str):  # noqa: ANN202 - SQLAlchemy legacy Query
    return LessonRetakeAttempt.query.filter_by(
        namespace=namespace,
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        outline_bid=outline_bid,
    )


def _balance(
    policy: CourseRetakePolicy,
    user_bid: str,
    outline_bid: str,
    *,
    locking: bool = False,
) -> RetakeAllowance:
    attempts = _attempts(policy.namespace, policy.shifu_bid, user_bid, outline_bid)
    if locking:
        # MySQL REPEATABLE READ may already have a snapshot from authorization.
        # A policy lock alone does not refresh ordinary aggregate reads. Read
        # actual attempt rows with locks so admission sees the latest committed
        # usage even when this request began before another reservation.
        counts = Counter(
            state
            for (state,) in attempts.with_entities(LessonRetakeAttempt.state)
            .with_for_update()
            .all()
        )
    else:
        counts = dict(
            attempts.with_entities(LessonRetakeAttempt.state, func.count())
            .group_by(LessonRetakeAttempt.state)
            .all()
        )
    return RetakeAllowance(
        limit=policy.lesson_limit,
        used=counts.get(RetakeState.COMMITTED, 0),
        reserved=counts.get(RetakeState.RESERVED, 0)
        + counts.get(RetakeState.RUNNING, 0),
    )


def get_allowance(
    app: Flask, *, namespace: str, shifu_bid: str, user_bid: str, outline_bid: str
) -> RetakeAllowance | None:
    """Return no policy when the course has never opted into this namespace."""
    with app_context_scope(app), unit_of_work():
        policy = CourseRetakePolicy.query.filter_by(
            namespace=namespace, shifu_bid=shifu_bid
        ).first()
        return _balance(policy, user_bid, outline_bid) if policy else None


def reserve_attempt(
    app: Flask,
    *,
    namespace: str,
    shifu_bid: str,
    user_bid: str,
    outline_bid: str,
    request_id: str,
    stage_reset: Callable[[], dict] | None = None,
) -> tuple[str, RetakeState]:
    """Reserve at most one in-flight round per learner/lesson; retries reuse it."""
    _validate_identity(
        (namespace, 32),
        (shifu_bid, 36),
        (user_bid, 36),
        (outline_bid, 36),
        (request_id, 36),
    )
    # Length prefixes avoid delimiter ambiguity in caller-provided identifiers.
    identity = "".join(
        f"{len(part)}:{part}"
        for part in (namespace, shifu_bid, user_bid, outline_bid, request_id)
    )
    attempt_id = hashlib.sha256(identity.encode()).hexdigest()
    with app_context_scope(app), unit_of_work():
        policy = _lock_policy(namespace, shifu_bid)
        existing = (
            LessonRetakeAttempt.query.filter_by(attempt_id=attempt_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if existing is not None:
            return attempt_id, RetakeState(existing.state)
        running = (
            LessonRetakeRun.query.filter_by(
                namespace=namespace,
                shifu_bid=shifu_bid,
                user_bid=user_bid,
                outline_bid=outline_bid,
                finished_at=None,
            )
            .with_for_update()
            .first()
        )
        if running is not None:
            reason = "retake_in_progress"
            raise RetakeRuleError(reason)
        balance = _balance(policy, user_bid, outline_bid, locking=True)
        active_committed = (
            _attempts(namespace, shifu_bid, user_bid, outline_bid)
            .filter(
                LessonRetakeAttempt.state == RetakeState.COMMITTED,
                LessonRetakeAttempt.producer_finished_at.is_(None),
            )
            .with_for_update()
            .populate_existing()
            .first()
        )
        if balance.reserved or active_committed is not None:
            reason = "retake_in_progress"
            raise RetakeRuleError(reason)
        if not balance.allowed:
            reason = "retake_limit_reached"
            raise RetakeRuleError(reason)
        row = LessonRetakeAttempt(
            attempt_id=attempt_id,
            namespace=namespace,
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            outline_bid=outline_bid,
            request_id=request_id,
            state=RetakeState.RESERVED,
        )
        db.session.add(row)
        if stage_reset is not None:
            row.recovery_data = stage_reset()
        db.session.flush()
        return attempt_id, RetakeState.RESERVED


def _locked_attempt(
    namespace: str, shifu_bid: str, attempt_id: str
) -> LessonRetakeAttempt:
    _lock_policy(namespace, shifu_bid)
    row = (
        LessonRetakeAttempt.query.filter_by(attempt_id=attempt_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if row is None or row.namespace != namespace or row.shifu_bid != shifu_bid:
        reason = "attempt_not_found"
        raise RetakeRuleError(reason)
    return row


def claim_attempt(
    app: Flask, *, namespace: str, shifu_bid: str, attempt_id: str, producer_id: str
) -> None:
    """Fence callbacks with the identity of the one producer that claimed it."""
    _validate_identity((producer_id, 36))
    with app_context_scope(app), unit_of_work():
        row = _locked_attempt(namespace, shifu_bid, attempt_id)
        row.state = begin_attempt(RetakeState(row.state))
        row.producer_id = producer_id


def finish_attempt(
    app: Flask,
    *,
    namespace: str,
    shifu_bid: str,
    attempt_id: str,
    producer_id: str | None,
    has_durable_content: bool,
    producer_stopped: bool,
    stage: Callable[[], None] | None = None,
) -> RetakeState:
    """Atomically persist content (or restore old state) with the final outcome.

    `stage` must perform DB mutations only; it never runs for a terminal replay.
    It is how the runtime binds content persistence/restoration to accounting,
    without this reusable module knowing a particular MarkdownFlow engine.
    """
    with app_context_scope(app), unit_of_work():
        row = _locked_attempt(namespace, shifu_bid, attempt_id)
        if row.producer_id != producer_id:
            reason = "producer_mismatch"
            raise RetakeRuleError(reason)
        old_state = RetakeState(row.state)
        target = settle_attempt(
            old_state,
            has_durable_content=has_durable_content,
            producer_stopped=producer_stopped,
        )
        if producer_stopped and row.producer_finished_at is None:
            row.producer_finished_at = now_utc()
        if target == old_state:
            return target
        if stage is not None:
            stage()
        row.state = target
        db.session.flush()
        return target
