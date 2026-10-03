"""Application-facing retake contracts; HTTP callers enforce course permissions."""

from functools import partial
from typing import Never

from flask import Flask
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common import raise_error
from flaskr.service.learn.retake_ledger import (
    configure_policy,
    get_allowance,
    reserve_attempt,
)
from flaskr.service.learn.retake_models import CourseRetakePolicy, LessonRetakeRun
from flaskr.service.learn.retake_policy import RetakeRuleError, RetakeState
from flaskr.service.learn.retake_recovery import stage_reset_records
from flaskr.service.learn.retake_rollout import retake_namespace


def raise_retake_error(error: RetakeRuleError) -> Never:
    """Expose stable localized outcomes rather than internal rule identifiers."""
    key = {
        "retake_reload_not_supported": "server.learn.retakeUseChapter",
        "retake_limit_reached": "server.learn.retakeLimitReached",
        "retake_in_progress": "server.learn.retakeInProgress",
        "attempt_not_reserved": "server.learn.retakeInProgress",
        "nothing_to_retake": "server.learn.retakeNotStarted",
        "previous_attempt_released": "server.learn.retakePreviousFailed",
        "invalid_identity": "server.learn.retakeInvalidRequest",
        "invalid_limit": "server.learn.retakeInvalidRequest",
    }.get(str(error), "server.learn.retakeUnavailable")
    raise_error(key)


def read_policy(app: Flask, shifu_bid: str) -> dict:
    """Return rollout availability separately from the teacher's setting."""
    namespace = retake_namespace(shifu_bid)
    if namespace is None:
        return {"available": False, "configured": False, "limit": None}
    with app_context_scope(app), unit_of_work():
        row = CourseRetakePolicy.query.filter_by(
            namespace=namespace, shifu_bid=shifu_bid
        ).first()
        return {
            "available": True,
            "configured": row is not None,
            "limit": row.lesson_limit if row else None,
        }


def update_policy(app: Flask, shifu_bid: str, limit: object) -> dict:
    """Apply a live per-lesson allowance without republishing or clearing usage."""
    namespace = retake_namespace(shifu_bid)
    if namespace is None:
        raise_error("server.learn.retakeUnavailable")
    try:
        configure_policy(app, namespace=namespace, shifu_bid=shifu_bid, limit=limit)
    except RetakeRuleError as exc:
        raise_retake_error(exc)
    return read_policy(app, shifu_bid)


def read_status(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    outline_bid: str,
    preview_mode: bool = False,
) -> dict:
    """Read this learner's balance; this response never grants admission."""
    namespace = None if preview_mode else retake_namespace(shifu_bid)
    result = {
        "available": False,
        "limit": None,
        "used": 0,
        "reserved": 0,
        "remaining": None,
        "allowed": True,
        "in_progress": False,
    }
    if namespace is None:
        return result
    with app_context_scope(app), unit_of_work():
        balance = get_allowance(
            app,
            namespace=namespace,
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            outline_bid=outline_bid,
        )
        if balance is None:
            return result
        busy = (
            LessonRetakeRun.query.filter_by(
                namespace=namespace,
                shifu_bid=shifu_bid,
                user_bid=user_bid,
                outline_bid=outline_bid,
                finished_at=None,
            ).first()
            is not None
        )
        return {
            "available": True,
            "limit": balance.limit,
            "used": balance.used,
            "reserved": balance.reserved,
            "remaining": balance.remaining,
            "allowed": balance.allowed and not busy and not balance.reserved,
            "in_progress": busy or bool(balance.reserved),
        }


def try_limited_reset(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    outline_bid: str,
    request_id: str | None,
) -> bool:
    """Handle an opted-in reset atomically; False selects the legacy path."""
    namespace = retake_namespace(shifu_bid)
    if namespace is None:
        return False
    with app_context_scope(app), unit_of_work():
        policy = (
            CourseRetakePolicy.query.filter_by(namespace=namespace, shifu_bid=shifu_bid)
            .with_for_update()
            .first()
        )
        if policy is None:
            return False
        try:
            _, state = reserve_attempt(
                app,
                namespace=namespace,
                shifu_bid=shifu_bid,
                user_bid=user_bid,
                outline_bid=outline_bid,
                request_id=request_id,
                stage_reset=partial(
                    stage_reset_records,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                ),
            )
        except RetakeRuleError as exc:
            raise_retake_error(exc)
        if state == RetakeState.RELEASED:
            raise_error("server.learn.retakePreviousFailed")
    return True
