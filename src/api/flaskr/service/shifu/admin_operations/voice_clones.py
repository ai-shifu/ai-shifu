from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Optional, Sequence, Set

from flask import Flask
from sqlalchemy import or_

from flaskr.api.tts import get_default_voice_settings, synthesize_text
from flaskr.dao import db
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.admin_operations.shared import (
    format_operator_datetime,
    load_operator_user_map,
)
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.tts.api import (
    is_valid_minimax_custom_voice_id,
    serialize_minimax_cloned_voice,
)
from flaskr.service.tts.models import (
    TTSMiniMaxClonedVoice,
    TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED,
    TTS_MINIMAX_CLONE_STATUS_READY,
)
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

OPERATOR_VOICE_CLONE_SOURCE_METHOD = "operator_register"
# Short text/model used only to validate a registered voice_id against the
# platform MiniMax account (and keep the cloned voice alive past 168h).
OPERATOR_VOICE_VERIFY_TEXT = "Voice sample check."
OPERATOR_VOICE_VERIFY_MODEL = "speech-2.8-turbo"

OPERATOR_VOICE_CLONE_LIST_MAX_PAGE_SIZE = 100
OPERATOR_VOICE_CLONE_STATUSES = {
    "queued",
    "processing",
    "billing_pending",
    "failed",
    "ready",
}
OPERATOR_VOICE_CLONE_BILLING_STATUSES = {
    "not_required",
    "reserved",
    "charged",
    "released",
    "failed",
}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _decimal_to_str(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _find_matching_course_bids(keyword: str) -> Optional[Set[str]]:
    normalized = _normalize_text(keyword)
    if not normalized:
        return None

    filters = [DraftShifu.shifu_bid == normalized]
    if len(normalized) >= 2:
        filters.append(DraftShifu.title.ilike(f"%{normalized}%"))
    draft_rows = (
        db.session.query(DraftShifu.shifu_bid)
        .filter(DraftShifu.deleted == 0, or_(*filters))
        .all()
    )

    published_filters = [PublishedShifu.shifu_bid == normalized]
    if len(normalized) >= 2:
        published_filters.append(PublishedShifu.title.ilike(f"%{normalized}%"))
    published_rows = (
        db.session.query(PublishedShifu.shifu_bid)
        .filter(PublishedShifu.deleted == 0, or_(*published_filters))
        .all()
    )

    return {
        str(row[0] or "").strip()
        for row in [*draft_rows, *published_rows]
        if row and str(row[0] or "").strip()
    }


def _find_matching_voice_owner_bids(keyword: str) -> Optional[Set[str]]:
    normalized = _normalize_text(keyword)
    if not normalized:
        return None

    user_bids = {
        row[0]
        for row in db.session.query(UserEntity.user_bid)
        .filter(
            UserEntity.deleted == 0,
            or_(
                UserEntity.nickname.ilike(f"%{normalized}%"),
                UserEntity.user_identify == normalized,
            ),
        )
        .all()
        if row and row[0]
    }

    credential_rows = (
        db.session.query(AuthCredential.user_bid)
        .filter(
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email"]),
            AuthCredential.identifier == normalized,
        )
        .all()
    )
    for row in credential_rows:
        if row and row[0]:
            user_bids.add(row[0])

    return user_bids


def _load_course_map(shifu_bids: Sequence[str]) -> dict[str, dict[str, str]]:
    normalized_bids = sorted(
        {
            _normalize_text(shifu_bid)
            for shifu_bid in shifu_bids
            if _normalize_text(shifu_bid)
        }
    )
    if not normalized_bids:
        return {}

    course_map: dict[str, dict[str, str]] = {}
    draft_rows = (
        DraftShifu.query.filter(
            DraftShifu.deleted == 0,
            DraftShifu.shifu_bid.in_(normalized_bids),
        )
        .order_by(DraftShifu.id.desc())
        .all()
    )
    for row in draft_rows:
        shifu_bid = _normalize_text(row.shifu_bid)
        if shifu_bid and shifu_bid not in course_map:
            course_map[shifu_bid] = {
                "shifu_bid": shifu_bid,
                "course_name": row.title or "",
                "course_status": "draft",
            }

    missing_bids = [
        shifu_bid for shifu_bid in normalized_bids if shifu_bid not in course_map
    ]
    if not missing_bids:
        return course_map

    published_rows = (
        PublishedShifu.query.filter(
            PublishedShifu.deleted == 0,
            PublishedShifu.shifu_bid.in_(missing_bids),
        )
        .order_by(PublishedShifu.id.desc())
        .all()
    )
    for row in published_rows:
        shifu_bid = _normalize_text(row.shifu_bid)
        if shifu_bid and shifu_bid not in course_map:
            course_map[shifu_bid] = {
                "shifu_bid": shifu_bid,
                "course_name": row.title or "",
                "course_status": "published",
            }
    return course_map


def _serialize_voice_clone(
    row: TTSMiniMaxClonedVoice,
    *,
    user_map: dict[str, dict[str, str]],
    course_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    owner_user_bid = _normalize_text(row.owner_user_bid)
    shifu_bid = _normalize_text(row.shifu_bid)
    user = user_map.get(owner_user_bid, {})
    course = course_map.get(shifu_bid, {})
    return {
        "voice_bid": row.voice_bid or "",
        "display_name": row.display_name or "",
        "voice_id": row.voice_id or "",
        "owner_user_bid": owner_user_bid,
        "owner_mobile": user.get("mobile", ""),
        "owner_email": user.get("email", ""),
        "owner_nickname": user.get("nickname", ""),
        "shifu_bid": shifu_bid,
        "course_name": course.get("course_name", ""),
        "course_status": course.get("course_status", ""),
        "status": row.status or "",
        "status_msg": row.status_msg or "",
        "failure_reason": row.failure_reason or "",
        "retry_count": int(row.retry_count or 0),
        "source_capture_method": row.source_capture_method or "",
        "source_audio_duration_ms": int(row.source_audio_duration_ms or 0),
        "normalized_audio_duration_ms": int(row.normalized_audio_duration_ms or 0),
        "prompt_audio_duration_ms": int(row.prompt_audio_duration_ms or 0),
        "minimax_source_file_id": row.minimax_source_file_id or "",
        "minimax_prompt_file_id": row.minimax_prompt_file_id or "",
        "minimax_trace_id": row.minimax_trace_id or "",
        "minimax_status_code": int(row.minimax_status_code or 0),
        "minimax_status_msg": row.minimax_status_msg or "",
        "billing_status": row.billing_status or "",
        "estimated_credits": _decimal_to_str(row.estimated_credits),
        "charged_credits": _decimal_to_str(row.charged_credits),
        "billing_reservation_bid": row.billing_reservation_bid or "",
        "billing_ledger_bid": row.billing_ledger_bid or "",
        "clone_usage_bid": row.clone_usage_bid or "",
        "created_at": format_operator_datetime(row.created_at),
        "updated_at": format_operator_datetime(row.updated_at),
        "ready_at": format_operator_datetime(row.ready_at),
    }


def list_operator_voice_clones(
    app: Flask,
    *,
    page_index: int,
    page_size: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        page_index = max(int(page_index or 1), 1)
        page_size = min(
            max(int(page_size or 20), 1),
            OPERATOR_VOICE_CLONE_LIST_MAX_PAGE_SIZE,
        )

        query = TTSMiniMaxClonedVoice.query.filter(TTSMiniMaxClonedVoice.deleted == 0)

        status = _normalize_text(filters.get("status"))
        if status:
            query = query.filter(TTSMiniMaxClonedVoice.status == status)

        failure_reason = _normalize_text(filters.get("failure_reason"))
        if failure_reason:
            query = query.filter(TTSMiniMaxClonedVoice.failure_reason == failure_reason)

        billing_status = _normalize_text(filters.get("billing_status"))
        if billing_status:
            query = query.filter(TTSMiniMaxClonedVoice.billing_status == billing_status)

        start_time = filters.get("start_time")
        if start_time is not None:
            query = query.filter(TTSMiniMaxClonedVoice.created_at >= start_time)
        end_time = filters.get("end_time")
        if end_time is not None:
            query = query.filter(TTSMiniMaxClonedVoice.created_at <= end_time)

        minimax_status_code = filters.get("minimax_status_code")
        if minimax_status_code is not None:
            query = query.filter(
                TTSMiniMaxClonedVoice.minimax_status_code == minimax_status_code
            )

        voice_keyword = _normalize_text(filters.get("voice_keyword"))
        if voice_keyword:
            voice_filters = [
                TTSMiniMaxClonedVoice.voice_bid == voice_keyword,
                TTSMiniMaxClonedVoice.voice_id == voice_keyword,
            ]
            if len(voice_keyword) >= 2:
                voice_filters.append(
                    TTSMiniMaxClonedVoice.display_name.ilike(f"%{voice_keyword}%")
                )
            query = query.filter(or_(*voice_filters))

        user_keyword = _normalize_text(filters.get("user_keyword"))
        if user_keyword:
            matching_user_bids = _find_matching_voice_owner_bids(user_keyword) or set()
            if not matching_user_bids:
                return {
                    "items": [],
                    "page": page_index,
                    "page_size": page_size,
                    "total": 0,
                    "page_count": 0,
                }
            query = query.filter(
                TTSMiniMaxClonedVoice.owner_user_bid.in_(list(matching_user_bids))
            )

        course_keyword = _normalize_text(filters.get("course_keyword"))
        if course_keyword:
            matching_course_bids = _find_matching_course_bids(course_keyword) or set()
            if not matching_course_bids:
                return {
                    "items": [],
                    "page": page_index,
                    "page_size": page_size,
                    "total": 0,
                    "page_count": 0,
                }
            query = query.filter(
                TTSMiniMaxClonedVoice.shifu_bid.in_(list(matching_course_bids))
            )

        total = query.count()
        rows = (
            query.order_by(
                TTSMiniMaxClonedVoice.created_at.desc(),
                TTSMiniMaxClonedVoice.id.desc(),
            )
            .offset((page_index - 1) * page_size)
            .limit(page_size)
            .all()
        )

        user_map = load_operator_user_map([row.owner_user_bid for row in rows])
        course_map = _load_course_map([row.shifu_bid for row in rows])
        return {
            "items": [
                _serialize_voice_clone(row, user_map=user_map, course_map=course_map)
                for row in rows
            ],
            "page": page_index,
            "page_size": page_size,
            "total": total,
            "page_count": math.ceil(total / page_size) if total else 0,
        }


def _verify_minimax_voice_id(voice_id: str) -> None:
    """Run a short test synthesis to validate the voice id and keep it alive.

    The synthesis goes through the platform MiniMax account. It fails fast if
    the voice id does not exist under that account (e.g. it was cloned on a
    different MiniMax account), and, on success, locks the cloned voice in past
    MiniMax's 168-hour unused-voice expiry.
    """
    voice_settings = get_default_voice_settings("minimax")
    voice_settings.voice_id = voice_id
    try:
        synthesize_text(
            OPERATOR_VOICE_VERIFY_TEXT,
            voice_settings=voice_settings,
            provider_name="minimax",
            model=OPERATOR_VOICE_VERIFY_MODEL,
        )
    except Exception as exc:  # noqa: BLE001 - surface the real reason to the operator
        raise_param_error(f"voice_id verification failed: {exc}")


def register_operator_voice_clone(
    app: Flask,
    *,
    operator_user_bid: str,
    owner_user_bid: str,
    display_name: str,
    voice_id: str,
) -> dict[str, Any]:
    """Register a MiniMax voice cloned on the console and assign it to a teacher.

    Operations-managed path: an operator clones a voice on the platform MiniMax
    account, then registers the resulting ``voice_id`` here for a specific
    teacher. No audio is uploaded and no creator credits are charged; the row is
    written directly as ``ready`` / ``billing_status=not_required`` so it shows
    up in that teacher's course voice dropdown. A short test synthesis validates
    the id against the platform account and keeps it alive.
    """
    del operator_user_bid  # recorded by the route for audit; not persisted here
    normalized_owner_bid = _normalize_text(owner_user_bid)
    if not normalized_owner_bid:
        raise_param_error("owner_user_bid is required")
    normalized_display_name = _normalize_text(display_name)[:128]
    if not normalized_display_name:
        raise_param_error("display_name is required")
    normalized_voice_id = _normalize_text(voice_id)
    if not is_valid_minimax_custom_voice_id(normalized_voice_id):
        raise_param_error("voice_id is invalid")

    with app.app_context():
        # Validate the voice_id against the platform MiniMax account before any
        # DB query, so this external HTTP call does not hold a database
        # connection / open transaction while it runs.
        _verify_minimax_voice_id(normalized_voice_id)

        owner = UserEntity.query.filter(
            UserEntity.user_bid == normalized_owner_bid,
            UserEntity.deleted == 0,
        ).first()
        if owner is None:
            raise_param_error("owner_user_bid not found")
        if not int(owner.is_creator or 0):
            raise_param_error("owner_user_bid is not a teacher")

        existing = TTSMiniMaxClonedVoice.query.filter(
            TTSMiniMaxClonedVoice.deleted == 0,
            TTSMiniMaxClonedVoice.owner_user_bid == normalized_owner_bid,
            TTSMiniMaxClonedVoice.voice_id == normalized_voice_id,
        ).first()
        if existing is not None:
            raise_param_error("voice_id already exists")

        row = TTSMiniMaxClonedVoice(
            voice_bid=generate_id(app),
            owner_user_bid=normalized_owner_bid,
            shifu_bid="",
            display_name=normalized_display_name,
            voice_id=normalized_voice_id,
            status=TTS_MINIMAX_CLONE_STATUS_READY,
            status_msg="",
            source_capture_method=OPERATOR_VOICE_CLONE_SOURCE_METHOD,
            billing_status=TTS_MINIMAX_CLONE_BILLING_NOT_REQUIRED,
            estimated_credits=0,
            charged_credits=0,
            ready_at=now_utc(),
        )
        db.session.add(row)
        db.session.commit()
        return serialize_minimax_cloned_voice(row)
