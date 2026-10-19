"""Creator-role backfill for users holding authoring course permissions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.service.user.repository import load_user_aggregate, mark_user_roles

from .cli_support import _normalize_cli_bid

if TYPE_CHECKING:
    from types import ModuleType


def _cli_facade() -> ModuleType:
    """Resolve collaborators through ``cli`` so its patch points stay live."""
    from . import cli

    return cli


def _auth_type_values(raw_auth_type: object) -> set[str]:
    if raw_auth_type is None:
        return set()
    if isinstance(raw_auth_type, (list, tuple, set)):
        return {
            str(item).strip().lower() for item in raw_auth_type if str(item).strip()
        }

    text = str(raw_auth_type or "").strip()
    if not text or text in {"[]", "null"}:
        return set()
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {item.strip().lower() for item in text.split(",") if item.strip()}

    if isinstance(parsed, list):
        return {str(item).strip().lower() for item in parsed if str(item).strip()}
    if isinstance(parsed, str):
        return {parsed.strip().lower()} if parsed.strip() else set()
    return set()


def _has_authoring_permission(raw_auth_type: object) -> bool:
    return bool(_auth_type_values(raw_auth_type).intersection({"edit", "publish"}))


def backfill_authoring_permission_creators(
    app: object,
    *,
    course_bid: str = "",
    user_bid: str = "",
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Backfill authoring permission creators."""
    normalized_course_bid = _normalize_cli_bid(course_bid)
    normalized_user_bid = _normalize_cli_bid(user_bid)
    normalized_limit = int(limit) if limit is not None and int(limit) > 0 else None

    with app.app_context():
        auth_query = AiCourseAuth.query.filter(AiCourseAuth.status == 1)
        if normalized_course_bid:
            auth_query = auth_query.filter(
                AiCourseAuth.course_id == normalized_course_bid
            )
        if normalized_user_bid:
            auth_query = auth_query.filter(AiCourseAuth.user_id == normalized_user_bid)
        auth_query = auth_query.order_by(AiCourseAuth.id.asc())
        if normalized_limit is not None:
            auth_query = auth_query.limit(normalized_limit)

        auth_rows = auth_query.all()
        candidates = _collect_authoring_permission_candidates(auth_rows)

        records: list[dict[str, Any]] = []
        role_granted_count = 0
        role_would_grant_count = 0
        role_skipped_count = 0
        trial_granted_count = 0
        trial_skipped_count = 0

        for current_user_bid, candidate in sorted(candidates.items()):
            record, role_outcome, trial_outcome = _backfill_authoring_creator(
                app,
                current_user_bid=current_user_bid,
                candidate=candidate,
                dry_run=dry_run,
            )
            if role_outcome == "granted":
                role_granted_count += 1
            elif role_outcome == "would_grant":
                role_would_grant_count += 1
            else:
                role_skipped_count += 1
            if trial_outcome == "granted":
                trial_granted_count += 1
            elif trial_outcome == "skipped":
                trial_skipped_count += 1
            records.append(record)

        return {
            "status": "completed",
            "dry_run": dry_run,
            "course_bid": normalized_course_bid or None,
            "user_bid": normalized_user_bid or None,
            "limit": normalized_limit,
            "auth_count": len(auth_rows),
            "creator_count": len(candidates),
            "role_granted_count": role_granted_count,
            "role_would_grant_count": role_would_grant_count,
            "role_skipped_count": role_skipped_count,
            "trial_granted_count": trial_granted_count,
            "trial_skipped_count": trial_skipped_count,
            "records": records,
        }


def _collect_authoring_permission_candidates(
    auth_rows: list[AiCourseAuth],
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for auth in auth_rows:
        current_user_bid = _normalize_cli_bid(auth.user_id)
        if not current_user_bid:
            continue
        candidate = candidates.setdefault(
            current_user_bid,
            {
                "course_bids": set(),
                "has_authoring_permission": False,
            },
        )
        current_course_bid = _normalize_cli_bid(auth.course_id)
        if current_course_bid:
            candidate["course_bids"].add(current_course_bid)
        if _has_authoring_permission(auth.auth_type):
            candidate["has_authoring_permission"] = True
    return candidates


def _backfill_authoring_creator(
    app: object,
    *,
    current_user_bid: str,
    candidate: dict[str, Any],
    dry_run: bool,
) -> tuple[dict[str, Any], str, str | None]:
    """Process one candidate; return its record and role/trial outcomes.

    The role outcome is ``granted``, ``would_grant`` or ``skipped``; the trial
    outcome is ``granted``, ``skipped`` or ``None`` when no trial count applies.
    """
    record: dict[str, Any] = {
        "creator_bid": current_user_bid,
        "course_bids": sorted(candidate["course_bids"]),
    }
    if not bool(candidate["has_authoring_permission"]):
        record.update(
            {
                "role_status": "skipped",
                "role_reason": "non_authoring_permission",
                "trial_status": "skipped",
                "trial_reason": "non_authoring_permission",
            }
        )
        return record, "skipped", "skipped"

    aggregate = load_user_aggregate(current_user_bid, with_credentials=False)
    if aggregate is None:
        record.update(
            {
                "role_status": "skipped",
                "role_reason": "user_not_found",
                "trial_status": "skipped",
                "trial_reason": "user_not_found",
            }
        )
        return record, "skipped", "skipped"

    if aggregate.is_creator:
        record.update(
            {
                "role_status": "skipped",
                "role_reason": "already_creator",
            }
        )
        role_outcome = "skipped"
    elif dry_run:
        record.update(
            {
                "role_status": "would_grant",
                "role_reason": None,
            }
        )
        role_outcome = "would_grant"
    else:
        with unit_of_work():
            mark_user_roles(current_user_bid, is_creator=True)
        record.update(
            {
                "role_status": "granted",
                "role_reason": None,
            }
        )
        role_outcome = "granted"

    if dry_run:
        record.update(
            {
                "trial_status": "dry_run",
                "trial_reason": "dry_run",
            }
        )
        return record, role_outcome, None

    trial_payload = _cli_facade().backfill_missing_creator_trial_credits(
        app,
        creator_bid=current_user_bid,
    )
    trial_record = (trial_payload.get("records") or [{}])[0] or {}
    trial_status = trial_record.get("status") or trial_payload.get("status")
    trial_reason = trial_record.get("reason") or trial_payload.get("reason")
    record.update(
        {
            "trial_status": trial_status,
            "trial_reason": trial_reason,
        }
    )
    if int(trial_payload.get("granted_count") or 0) > 0:
        return record, role_outcome, "granted"
    return record, role_outcome, "skipped"
