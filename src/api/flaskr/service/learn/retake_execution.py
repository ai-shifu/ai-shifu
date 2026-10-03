"""Bind retake accounting to the producer and durable teaching writes.

The producer owns this scope. HTTP teardown must never settle it: a disconnected
browser may leave its producer running. Process crashes remain pending for
explicit recovery, never a timed refund that could race an unfenced worker.
"""

from __future__ import annotations

import contextvars
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.dao import (
    db,
    invalidate_session,
    is_abnormal_stream_termination,
    is_protocol_interrupt_error,
)
from flaskr.dao.uow import (
    app_context_scope,
    in_unit_of_work,
    require_transaction_owner,
    unit_of_work,
)
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.learn.retake_ledger import (
    _locked_attempt,
    claim_attempt,
    finish_attempt,
)
from flaskr.service.learn.retake_models import LessonRetakeAttempt
from flaskr.service.learn.retake_policy import RetakeRuleError, RetakeState
from flaskr.service.learn.retake_recovery import stage_restore_records
from flaskr.service.learn.retake_rollout import retake_namespace

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


@dataclass(frozen=True)
class RetakeExecution:
    """Server-issued identity passed only within one producer thread."""

    app: Flask
    namespace: str
    shifu_bid: str
    user_bid: str
    outline_bid: str
    attempt_id: str
    producer_id: str

    def ledger_identity(self) -> dict:
        """Arguments shared by claim and finalization."""
        return {
            "namespace": self.namespace,
            "shifu_bid": self.shifu_bid,
            "attempt_id": self.attempt_id,
            "producer_id": self.producer_id,
        }


_current: contextvars.ContextVar[RetakeExecution | None] = contextvars.ContextVar(
    "retake_execution", default=None
)


def stage_retake_content(
    *, shifu_bid: str, user_bid: str, outline_bid: str, content: str
) -> None:
    """Commit the first nonempty teaching text with the caller's content write."""
    execution = _current.get()
    if execution is None or not (content or "").strip():
        return
    if (shifu_bid, user_bid, outline_bid) != (
        execution.shifu_bid,
        execution.user_bid,
        execution.outline_bid,
    ):
        return
    if not in_unit_of_work():
        reason = "content_requires_transaction"
        raise RetakeRuleError(reason)
    finish_attempt(
        execution.app,
        **execution.ledger_identity(),
        has_durable_content=True,
        producer_stopped=False,
    )


@contextmanager
def owning_retake(execution: RetakeExecution) -> Iterator[None]:
    """Claim exactly once, then settle only after the producer's generator closes."""
    require_transaction_owner("owning_retake", execution.app)
    with app_context_scope(execution.app):
        with unit_of_work():
            row = _locked_attempt(
                execution.namespace, execution.shifu_bid, execution.attempt_id
            )
            if (row.user_bid, row.outline_bid) != (
                execution.user_bid,
                execution.outline_bid,
            ):
                reason = "attempt_identity_mismatch"
                raise RetakeRuleError(reason)
            claim_attempt(execution.app, **execution.ledger_identity())
        token = _current.set(execution)
        try:
            yield
        finally:
            _current.reset(token)
            # Drop incomplete writes and any invalidated connection before inspecting
            # committed state. This scope belongs at the producer boundary only.
            exc = sys.exception()
            if exc is not None and (
                is_abnormal_stream_termination(exc) or is_protocol_interrupt_error(exc)
            ):
                invalidate_session(source="retake producer abort", session=db.session)
            db.session.remove()
            with unit_of_work():
                row = _locked_attempt(
                    execution.namespace, execution.shifu_bid, execution.attempt_id
                )
                delivered = row.state == RetakeState.COMMITTED
                snapshot = row.recovery_data

                def restore() -> None:
                    stage_restore_records(
                        user_bid=execution.user_bid,
                        shifu_bid=execution.shifu_bid,
                        outline_bid=execution.outline_bid,
                        snapshot=snapshot,
                    )

                finish_attempt(
                    execution.app,
                    **execution.ledger_identity(),
                    has_durable_content=delivered,
                    producer_stopped=True,
                    stage=None if delivered else restore,
                )


def track_retake_events(
    events: Iterator,
    *,
    app: Flask,
    shifu_bid: str,
    user_bid: str,
    outline_bid: str,
    preview_mode: bool,
    input_type: str | None,
    reload_generated_block_bid: str | None = None,
    reload_element_bid: str | None = None,
) -> Iterator:
    """Wrap the actual producer, leaving first study, preview and Ask unchanged."""
    namespace = retake_namespace(shifu_bid)
    if (
        namespace is None
        or preview_mode
        or input_type == INPUT_TYPE_ASK
        or reload_generated_block_bid
        or reload_element_bid
    ):
        yield from events
        return
    with app_context_scope(app), unit_of_work():
        pending = (
            LessonRetakeAttempt.query.filter_by(
                namespace=namespace,
                shifu_bid=shifu_bid,
                user_bid=user_bid,
                outline_bid=outline_bid,
                producer_finished_at=None,
            )
            .filter(
                LessonRetakeAttempt.state.in_(
                    [RetakeState.RESERVED, RetakeState.RUNNING, RetakeState.COMMITTED]
                )
            )
            .first()
        )
        attempt_id = pending.attempt_id if pending is not None else None
    if attempt_id is None:
        yield from events
        return
    execution = RetakeExecution(
        app=app,
        namespace=namespace,
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        outline_bid=outline_bid,
        attempt_id=attempt_id,
        producer_id=uuid.uuid4().hex,
    )
    with owning_retake(execution):
        yield from events
