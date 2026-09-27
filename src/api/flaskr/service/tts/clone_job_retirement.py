"""Reconcile unfinished MiniMax jobs during retirement of in-product cloning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao.uow import app_context_scope, require_transaction_owner, unit_of_work
from flaskr.service.billing.api import (
    list_unsettled_operation_reservations,
    release_reserved_operation_credits,
)
from flaskr.service.tts.models import (
    TTS_CLONE_PROVIDER_MINIMAX,
    TTS_MINIMAX_CLONE_BILLING_FAILED,
    TTS_MINIMAX_CLONE_BILLING_RELEASED,
    TTS_MINIMAX_CLONE_BILLING_RESERVED,
    TTS_MINIMAX_CLONE_STATUS_BILLING_PENDING,
    TTS_MINIMAX_CLONE_STATUS_FAILED,
    TTS_MINIMAX_CLONE_STATUS_PROCESSING,
    TTS_MINIMAX_CLONE_STATUS_QUEUED,
    TTSMiniMaxClonedVoice,
)
from flaskr.util.datetime import now_utc
from sqlalchemy import and_, or_

if TYPE_CHECKING:
    from flask import Flask
    from flask_sqlalchemy.query import Query

_RETIREMENT_REASON = "workflow_retired"


def _unfinished_jobs() -> Query:
    """Include deleted jobs and failed jobs that may still hold credits."""
    return TTSMiniMaxClonedVoice.query.filter(
        TTSMiniMaxClonedVoice.provider == TTS_CLONE_PROVIDER_MINIMAX,
        or_(
            TTSMiniMaxClonedVoice.status.in_(
                (
                    TTS_MINIMAX_CLONE_STATUS_QUEUED,
                    TTS_MINIMAX_CLONE_STATUS_PROCESSING,
                    TTS_MINIMAX_CLONE_STATUS_BILLING_PENDING,
                )
            ),
            and_(
                TTSMiniMaxClonedVoice.status == TTS_MINIMAX_CLONE_STATUS_FAILED,
                TTSMiniMaxClonedVoice.billing_reservation_bid != "",
                TTSMiniMaxClonedVoice.billing_status.in_(
                    (
                        TTS_MINIMAX_CLONE_BILLING_RESERVED,
                        TTS_MINIMAX_CLONE_BILLING_FAILED,
                    )
                ),
            ),
        ),
    )


def retire_minimax_clone_jobs(
    app: Flask, *, apply: bool = False, workers_stopped: bool = False
) -> dict[str, object]:
    """Fail unfinished jobs and release holds after old producers/workers stop.

    This is an operator-only cutover operation, not a replacement clone worker.
    The acknowledgement is a deployment prerequisite: row locks cannot fence an
    old worker that has already started its provider call. Each job and its
    credit release commit together; a failed run can safely be retried.
    """
    if apply and not workers_stopped:
        message = (
            "Stop all old API instances and clone workers before applying retirement"
        )
        raise ValueError(message)
    require_transaction_owner("MiniMax clone job retirement", app)
    results: list[dict[str, str]] = []
    with app_context_scope(app):
        voice_bids = [
            row.voice_bid
            for row in _unfinished_jobs()
            .with_entities(TTSMiniMaxClonedVoice.voice_bid)
            .order_by(TTSMiniMaxClonedVoice.id)
            .all()
        ]
        for voice_bid in voice_bids:
            try:
                with unit_of_work(discard=not apply):
                    row = (
                        _unfinished_jobs()
                        .filter(TTSMiniMaxClonedVoice.voice_bid == voice_bid)
                        .populate_existing()
                        .with_for_update()
                        .first()
                    )
                    if row is None:
                        continue
                    if row.billing_reservation_bid:
                        release = release_reserved_operation_credits(
                            app,
                            reservation_bid=row.billing_reservation_bid,
                            reason=_RETIREMENT_REASON,
                        )
                        if release.status == "already_captured":
                            results.append(
                                {"voice_bid": voice_bid, "status": "already_captured"}
                            )
                            continue
                        _require_released(release.status)
                        row.billing_status = TTS_MINIMAX_CLONE_BILLING_RELEASED
                    row.status = TTS_MINIMAX_CLONE_STATUS_FAILED
                    row.failure_reason = _RETIREMENT_REASON
                    row.status_msg = "In-product MiniMax voice cloning has been retired"
                    row.updated_at = now_utc()
                results.append(
                    {
                        "voice_bid": voice_bid,
                        "status": "cancelled" if apply else "would_cancel",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "voice_bid": voice_bid,
                        "status": "manual_review",
                        "error_type": type(exc).__name__,
                    }
                )

        # Submission reserved credits before storing its voice row. Reconcile
        # those orphan holds too, but never refund a ready or otherwise tracked voice.
        for hold in list_unsettled_operation_reservations(
            app, operation_type="voice_clone"
        ):
            reservation_bid = hold["reservation_bid"]
            tracked = TTSMiniMaxClonedVoice.query.filter_by(
                billing_reservation_bid=reservation_bid
            ).first()
            if tracked is not None:
                # In a dry run these still include the jobs whose release was rolled back.
                # Any unexpected ready/tracked hold must block cutover for manual review.
                if tracked.voice_bid not in voice_bids:
                    results.append(
                        {"reservation_bid": reservation_bid, "status": "manual_review"}
                    )
                continue
            try:
                with unit_of_work(discard=not apply):
                    release = release_reserved_operation_credits(
                        app, reservation_bid=reservation_bid, reason=_RETIREMENT_REASON
                    )
                    _require_released(release.status)
                results.append(
                    {
                        "reservation_bid": reservation_bid,
                        "status": "released_orphan"
                        if apply
                        else "would_release_orphan",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "reservation_bid": reservation_bid,
                        "status": "manual_review",
                        "error_type": type(exc).__name__,
                    }
                )
    return {
        "dry_run": not apply,
        "jobs": results,
        "cancelled_count": sum(job["status"] == "cancelled" for job in results),
        "captured_count": sum(job["status"] == "already_captured" for job in results),
        "manual_review_count": sum(job["status"] == "manual_review" for job in results),
        "released_orphan_count": sum(
            job["status"] == "released_orphan" for job in results
        ),
    }


def _require_released(status: str) -> None:
    if status not in {"released", "already_released"}:
        message = f"Unexpected reservation release status: {status}"
        raise RuntimeError(message)
