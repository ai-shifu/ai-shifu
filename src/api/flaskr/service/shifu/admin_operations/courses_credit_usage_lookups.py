"""Lookups shared by operator course credit-usage queries.

Output summaries for usage rows, the user keyword filter, and the latest
bill-usage record loaders, split out of ``courses_credit_usage``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.admin_operations.courses_shared import (
    _normalize_identifier,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.user.models import (
    AuthCredential,
)
from flaskr.service.user.models import (
    UserInfo as UserEntity,
)
from sqlalchemy import false, or_

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.sql.selectable import Subquery


def _resolve_course_credit_usage_output_summary(
    usage_row: BillUsageRecord,
) -> str:
    normalized_generated_block_bid = str(
        getattr(usage_row, "generated_block_bid", "") or ""
    ).strip()
    shifu_bid = str(getattr(usage_row, "shifu_bid", "") or "")
    user_bid = str(getattr(usage_row, "user_bid", "") or "")
    outline_item_bid = str(getattr(usage_row, "outline_item_bid", "") or "")

    def resolve_element_summary(generated_block_bid: str) -> str:
        normalized_block_bid = str(generated_block_bid or "").strip()
        if not normalized_block_bid:
            return ""
        element_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.generated_block_bid == normalized_block_bid,
                LearnGeneratedElement.shifu_bid == shifu_bid,
                LearnGeneratedElement.user_bid == user_bid,
                LearnGeneratedElement.outline_item_bid == outline_item_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.role == "teacher",
                LearnGeneratedElement.is_final == 1,
                LearnGeneratedElement.is_renderable == 1,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
                LearnGeneratedElement.content_text != "",
            )
            .order_by(
                LearnGeneratedElement.sequence_number.asc(),
                LearnGeneratedElement.run_event_seq.asc(),
                LearnGeneratedElement.id.asc(),
            )
            .limit(20)
            .all()
        )
        return "\n".join(
            str(getattr(row, "content_text", "") or "").strip()
            for row in element_rows
            if str(getattr(row, "content_text", "") or "").strip()
        ).strip()

    def resolve_block_generated_content(generated_block_bid: str) -> str:
        normalized_block_bid = str(generated_block_bid or "").strip()
        if not normalized_block_bid:
            return ""
        block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid == normalized_block_bid,
                LearnGeneratedBlock.shifu_bid == shifu_bid,
                LearnGeneratedBlock.user_bid == user_bid,
                LearnGeneratedBlock.outline_item_bid == outline_item_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type.in_(
                    [
                        BLOCK_TYPE_MDANSWER_VALUE,
                        BLOCK_TYPE_MDCONTENT_VALUE,
                        BLOCK_TYPE_MDINTERACTION_VALUE,
                    ]
                ),
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        if not block:
            return ""
        generated_content = str(getattr(block, "generated_content", "") or "").strip()
        if generated_content:
            return generated_content
        if int(getattr(block, "type", 0) or 0) == BLOCK_TYPE_MDINTERACTION_VALUE:
            return str(getattr(block, "block_content_conf", "") or "").strip()
        return ""

    if normalized_generated_block_bid:
        exact_content = resolve_element_summary(
            normalized_generated_block_bid
        ) or resolve_block_generated_content(normalized_generated_block_bid)
        if exact_content:
            return exact_content

    return ""


def _load_course_credit_usage_output_summary_map(
    usage_rows: Sequence[BillUsageRecord],
) -> dict[str, str]:
    normalized_rows = [
        usage_row
        for usage_row in usage_rows
        if str(getattr(usage_row, "usage_bid", "") or "").strip()
        and str(getattr(usage_row, "generated_block_bid", "") or "").strip()
    ]
    if not normalized_rows:
        return {}

    generated_block_bids = sorted(
        {
            str(getattr(usage_row, "generated_block_bid", "") or "").strip()
            for usage_row in normalized_rows
            if str(getattr(usage_row, "generated_block_bid", "") or "").strip()
        }
    )
    if not generated_block_bids:
        return {}

    def context_key(row: object) -> tuple[str, str, str, str]:
        return (
            str(getattr(row, "generated_block_bid", "") or "").strip(),
            str(getattr(row, "shifu_bid", "") or "").strip(),
            str(getattr(row, "user_bid", "") or "").strip(),
            str(getattr(row, "outline_item_bid", "") or "").strip(),
        )

    usage_context_keys = {context_key(usage_row) for usage_row in normalized_rows}
    shifu_bids = sorted({key[1] for key in usage_context_keys if key[1]})
    user_bids = sorted({key[2] for key in usage_context_keys if key[2]})
    outline_item_bids = sorted({key[3] for key in usage_context_keys if key[3]})

    element_parts_map: dict[tuple[str, str, str, str], list[str]] = {}
    element_rows = (
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.generated_block_bid.in_(generated_block_bids),
            LearnGeneratedElement.shifu_bid.in_(shifu_bids),
            LearnGeneratedElement.user_bid.in_(user_bids),
            LearnGeneratedElement.outline_item_bid.in_(outline_item_bids),
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.role == "teacher",
            LearnGeneratedElement.is_final == 1,
            LearnGeneratedElement.is_renderable == 1,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
            LearnGeneratedElement.content_text != "",
        )
        .order_by(
            LearnGeneratedElement.generated_block_bid.asc(),
            LearnGeneratedElement.sequence_number.asc(),
            LearnGeneratedElement.run_event_seq.asc(),
            LearnGeneratedElement.id.asc(),
        )
        .yield_per(100)
    )
    for element in element_rows:
        generated_block_bid = str(
            getattr(element, "generated_block_bid", "") or ""
        ).strip()
        if not generated_block_bid:
            continue
        key = context_key(element)
        if key not in usage_context_keys:
            continue
        parts = element_parts_map.setdefault(key, [])
        if len(parts) >= 20:
            continue
        content = str(getattr(element, "content_text", "") or "").strip()
        if content:
            parts.append(content)

    element_summary_map = {
        key: "\n".join(parts) for key, parts in element_parts_map.items() if parts
    }

    missing_context_keys = [
        key for key in usage_context_keys if not element_summary_map.get(key)
    ]
    missing_context_key_set = set(missing_context_keys)
    missing_block_bids = sorted({key[0] for key in missing_context_keys if key[0]})
    block_summary_map: dict[tuple[str, str, str, str], str] = {}
    if missing_block_bids:
        block_rows = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid.in_(missing_block_bids),
                LearnGeneratedBlock.shifu_bid.in_(shifu_bids),
                LearnGeneratedBlock.user_bid.in_(user_bids),
                LearnGeneratedBlock.outline_item_bid.in_(outline_item_bids),
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type.in_(
                    [
                        BLOCK_TYPE_MDANSWER_VALUE,
                        BLOCK_TYPE_MDCONTENT_VALUE,
                        BLOCK_TYPE_MDINTERACTION_VALUE,
                    ]
                ),
            )
            .order_by(
                LearnGeneratedBlock.generated_block_bid.asc(),
                LearnGeneratedBlock.id.desc(),
            )
            .all()
        )
        for block in block_rows:
            generated_block_bid = str(
                getattr(block, "generated_block_bid", "") or ""
            ).strip()
            key = context_key(block)
            if (
                not generated_block_bid
                or key not in missing_context_key_set
                or key in block_summary_map
            ):
                continue
            generated_content = str(
                getattr(block, "generated_content", "") or ""
            ).strip()
            if generated_content:
                block_summary_map[key] = generated_content
                continue
            if int(getattr(block, "type", 0) or 0) == BLOCK_TYPE_MDINTERACTION_VALUE:
                block_summary_map[key] = str(
                    getattr(block, "block_content_conf", "") or ""
                ).strip()

    summary_by_usage_bid: dict[str, str] = {}
    for usage_row in normalized_rows:
        usage_bid = str(getattr(usage_row, "usage_bid", "") or "").strip()
        generated_block_bid = str(
            getattr(usage_row, "generated_block_bid", "") or ""
        ).strip()
        key = context_key(usage_row)
        summary = element_summary_map.get(key) or block_summary_map.get(key, "")
        if summary:
            summary_by_usage_bid[usage_bid] = summary

    return summary_by_usage_bid


def _build_credit_usage_user_keyword_filter(
    user_bid_column: object, keyword: str
) -> object | None:
    normalized = _normalize_identifier(keyword)
    if not normalized:
        return None

    nickname_match_exists = (
        db.session.query(UserEntity.id)
        .filter(
            UserEntity.user_bid == user_bid_column,
            UserEntity.deleted == 0,
            UserEntity.nickname.ilike(f"%{normalized}%"),
        )
        .exists()
    )

    if "@" in normalized:
        credential_identifier_filter = (
            db.func.lower(AuthCredential.identifier) == normalized
        )
        user_identifier_filter = db.func.lower(UserEntity.user_identify) == normalized
    elif normalized.isdigit():
        credential_identifier_filter = AuthCredential.identifier == normalized
        user_identifier_filter = UserEntity.user_identify == normalized
    else:
        return nickname_match_exists

    credential_match_exists = (
        db.session.query(AuthCredential.id)
        .filter(
            AuthCredential.user_bid == user_bid_column,
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            credential_identifier_filter,
        )
        .exists()
    )

    user_identifier_match_exists = (
        db.session.query(UserEntity.id)
        .filter(
            UserEntity.user_bid == user_bid_column,
            UserEntity.deleted == 0,
            user_identifier_filter,
        )
        .exists()
    )

    return or_(
        nickname_match_exists,
        credential_match_exists,
        user_identifier_match_exists,
    )


def _load_bill_usage_record_map(
    usage_bids: Sequence[str],
) -> dict[str, BillUsageRecord]:
    normalized_usage_bids = sorted(
        {
            str(usage_bid or "").strip()
            for usage_bid in usage_bids
            if str(usage_bid or "").strip()
        }
    )
    if not normalized_usage_bids:
        return {}

    rows = (
        BillUsageRecord.query.filter(
            BillUsageRecord.deleted == 0,
            BillUsageRecord.usage_bid.in_(normalized_usage_bids),
        )
        .order_by(BillUsageRecord.id.desc())
        .all()
    )
    usage_map: dict[str, BillUsageRecord] = {}
    for row in rows:
        usage_bid = str(row.usage_bid or "").strip()
        if usage_bid and usage_bid not in usage_map:
            usage_map[usage_bid] = row
    return usage_map


def _build_latest_bill_usage_record_subquery(
    *,
    user_bid: str = "",
    usage_bids: Sequence[str] | None = None,
) -> Subquery:
    normalized_user_bid = str(user_bid or "").strip()
    normalized_usage_bids = [
        str(usage_bid or "").strip()
        for usage_bid in usage_bids or []
        if str(usage_bid or "").strip()
    ]
    query = db.session.query(
        BillUsageRecord.usage_bid.label("usage_bid"),
        db.func.max(BillUsageRecord.id).label("max_id"),
    ).filter(
        BillUsageRecord.deleted == 0,
        BillUsageRecord.record_level == 0,
    )
    if normalized_user_bid:
        query = query.filter(BillUsageRecord.user_bid == normalized_user_bid)
    if usage_bids is not None and not normalized_usage_bids:
        query = query.filter(false())
    if normalized_usage_bids:
        query = query.filter(BillUsageRecord.usage_bid.in_(normalized_usage_bids))
    return query.group_by(BillUsageRecord.usage_bid).subquery()
