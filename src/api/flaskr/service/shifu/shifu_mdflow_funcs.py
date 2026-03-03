from markdown_flow import MarkdownFlow
from flask import Flask
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.service.common import raise_error
from flaskr.dao import db
from flaskr.service.shifu.dtos import MdflowDTOParseResult
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from typing import TypedDict

from flaskr.service.shifu.shifu_history_manager import (
    save_outline_history,
    get_shifu_draft_meta,
    get_shifu_draft_revision,
    mask_contact_identifier,
)
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
    add_profile_item_quick,
)
from flaskr.service.user.models import UserInfo
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_shifu_mdflow(app: Flask, shifu_bid: str, outline_bid: str) -> str:
    """
    Get shifu mdflow
    """
    with app.app_context():
        outline_item = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.shifu_bid == shifu_bid,
                DraftOutlineItem.outline_item_bid == outline_bid,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if not outline_item:
            raise_error("server.shifu.outlineItemNotFound")
        return outline_item.content


class DraftConflictResult(TypedDict):
    conflict: bool
    meta: dict


class DraftSaveResult(TypedDict):
    conflict: bool
    new_revision: int


DraftSaveResponse = DraftConflictResult | DraftSaveResult

LESSON_HISTORY_MAX_VERSIONS = 500
LESSON_HISTORY_MAX_DAYS = 180


def cleanup_outline_history_versions(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    keep_versions: int = LESSON_HISTORY_MAX_VERSIONS,
    keep_days: int = LESSON_HISTORY_MAX_DAYS,
) -> None:
    """
    Keep outline version history bounded:
    - trim to around `keep_versions` latest non-deleted versions
    - trim to around `keep_days` days of non-deleted versions
    To keep outline-level revision stable for metadata-only updates, this
    cleanup always preserves both the latest version and the current
    content-anchor version. Therefore, actual retained rows can exceed strict
    limits by protected anchor rows.
    """
    latest_version = (
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.outline_item_bid == outline_bid,
            DraftOutlineItem.deleted == 0,
        )
        .order_by(DraftOutlineItem.id.desc())
        .first()
    )
    if not latest_version:
        return

    latest_id = int(latest_version.id)
    latest_content = latest_version.content or ""
    content_anchor_version = latest_version
    for version in _query_outline_versions(shifu_bid, outline_bid):
        if version.id == latest_version.id:
            continue
        if (version.content or "") != latest_content:
            break
        content_anchor_version = version
    protected_ids = {latest_id, int(content_anchor_version.id)}

    cutoff_time = datetime.now() - timedelta(days=max(1, keep_days))
    to_mark_deleted_ids: set[int] = set()

    # Trim by age.
    expired_query = DraftOutlineItem.query.filter(
        DraftOutlineItem.shifu_bid == shifu_bid,
        DraftOutlineItem.outline_item_bid == outline_bid,
        DraftOutlineItem.deleted == 0,
        DraftOutlineItem.updated_at < cutoff_time,
    )
    if protected_ids:
        expired_query = expired_query.filter(~DraftOutlineItem.id.in_(protected_ids))
    expired_ids = expired_query.with_entities(DraftOutlineItem.id).all()
    to_mark_deleted_ids.update(int(item.id) for item in expired_ids)

    # Trim by max count.
    overflow_query = DraftOutlineItem.query.filter(
        DraftOutlineItem.shifu_bid == shifu_bid,
        DraftOutlineItem.outline_item_bid == outline_bid,
        DraftOutlineItem.deleted == 0,
    )
    if protected_ids:
        overflow_query = overflow_query.filter(~DraftOutlineItem.id.in_(protected_ids))
    overflow_ids = (
        overflow_query.order_by(DraftOutlineItem.id.desc())
        .offset(max(1, keep_versions) - 1)
        .with_entities(DraftOutlineItem.id)
        .all()
    )
    to_mark_deleted_ids.update(int(item.id) for item in overflow_ids)

    if not to_mark_deleted_ids:
        return

    DraftOutlineItem.query.filter(DraftOutlineItem.id.in_(to_mark_deleted_ids)).update(
        {
            DraftOutlineItem.deleted: 1,
        },
        synchronize_session=False,
    )


def _cleanup_outline_history_versions(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    keep_versions: int = LESSON_HISTORY_MAX_VERSIONS,
    keep_days: int = LESSON_HISTORY_MAX_DAYS,
) -> None:
    """Backward-compatible alias for tests and internal callers."""
    cleanup_outline_history_versions(
        app,
        shifu_bid,
        outline_bid,
        keep_versions=keep_versions,
        keep_days=keep_days,
    )


def save_shifu_mdflow(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outline_bid: str,
    content: str,
    base_revision: int | None = None,
) -> DraftSaveResponse:
    """
    Save shifu mdflow
    """
    with app.app_context():
        lock_latest = isinstance(base_revision, int) and base_revision >= 0
        outline_query = DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.outline_item_bid == outline_bid,
        ).order_by(DraftOutlineItem.id.desc())
        if lock_latest:
            outline_query = outline_query.with_for_update()
        outline_item: DraftOutlineItem = outline_query.first()
        if not outline_item:
            raise_error("server.shifu.outlineItemNotFound")
        if outline_item.deleted == 1:
            return {
                "conflict": True,
                "meta": get_shifu_draft_meta(app, shifu_bid, outline_bid),
            }

        if lock_latest:
            latest_meta = get_shifu_draft_meta(app, shifu_bid, outline_bid)
            if int(latest_meta.get("deleted", 0) or 0) == 1:
                return {"conflict": True, "meta": latest_meta}
            latest_revision = int(latest_meta.get("revision", 0) or 0)
            updated_user_bid = (latest_meta.get("updated_user") or {}).get(
                "user_bid"
            ) or ""
            if latest_revision > base_revision and (
                not updated_user_bid or updated_user_bid != user_id
            ):
                return {"conflict": True, "meta": latest_meta}
        # create new version
        new_outline: DraftOutlineItem = outline_item.clone()
        new_outline.content = content

        # risk check
        # save to database
        new_revision = None
        if not outline_item.content == new_outline.content:
            check_text_with_risk_control(
                app, outline_item.outline_item_bid, user_id, content
            )
            new_outline.updated_user_bid = user_id
            new_outline.updated_at = datetime.now()
            db.session.add(new_outline)
            db.session.flush()
            markdown_flow = MarkdownFlow(content).set_output_language(
                get_markdownflow_output_language()
            )
            blocks = markdown_flow.get_all_blocks()
            variable_definitions = get_profile_item_definition_list(app, shifu_bid)

            variables = markdown_flow.extract_variables()
            for variable in variables:
                exist_variable = next(
                    (v for v in variable_definitions if v.profile_key == variable), None
                )
                if not exist_variable:
                    add_profile_item_quick(app, shifu_bid, variable, user_id)
            save_outline_history(
                app,
                user_id,
                shifu_bid,
                outline_bid,
                new_outline.id,
                len(blocks),
            )
            cleanup_outline_history_versions(
                app,
                shifu_bid,
                outline_bid,
            )
            db.session.commit()
            new_revision = int(new_outline.id)
        return {
            "conflict": False,
            "new_revision": new_revision
            if new_revision is not None
            else get_shifu_draft_revision(app, shifu_bid, outline_bid),
        }


def parse_shifu_mdflow(
    app: Flask, shifu_bid: str, outline_bid: str, data: str = None
) -> MdflowDTOParseResult:
    """
    Parse shifu mdflow
    """
    with app.app_context():
        outline_item = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.shifu_bid == shifu_bid,
                DraftOutlineItem.outline_item_bid == outline_bid,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if not outline_item:
            raise_error("server.shifu.outlineItemNotFound")
        mdflow = outline_item.content
        if data:
            mdflow = data
        markdown_flow = MarkdownFlow(mdflow).set_output_language(
            get_markdownflow_output_language()
        )
        blocks = markdown_flow.get_all_blocks()

        raw_variables = markdown_flow.extract_variables() or []
        profile_definitions = get_profile_item_definition_list(
            app, outline_item.shifu_bid
        )
        definition_keys = [
            item.profile_key for item in profile_definitions if item.profile_key
        ]

        dedup_vars: list[str] = []
        seen = set()
        for key in raw_variables + definition_keys:
            if not key or key in seen:
                continue
            dedup_vars.append(key)
            seen.add(key)

        return MdflowDTOParseResult(variables=dedup_vars, blocks_count=len(blocks))


def _query_outline_versions(shifu_bid: str, outline_bid: str):
    return (
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.outline_item_bid == outline_bid,
            DraftOutlineItem.deleted == 0,
        )
        .order_by(DraftOutlineItem.id.desc())
        .yield_per(200)
    )


def _get_app_timezone(app: Flask, tz_name: str | None = None) -> ZoneInfo:
    fallback_tz_name = app.config.get("TZ", "UTC")
    candidate_tz_name = (tz_name or fallback_tz_name or "UTC").strip()
    try:
        return ZoneInfo(candidate_tz_name)
    except ZoneInfoNotFoundError as error:
        app.logger.warning(
            "Failed to load timezone '%s': %s, falling back to '%s'",
            candidate_tz_name,
            error,
            fallback_tz_name,
        )
    except Exception as error:
        app.logger.warning(
            "Unexpected timezone config '%s': %s, falling back to UTC",
            candidate_tz_name,
            error,
        )

    if candidate_tz_name != fallback_tz_name:
        try:
            return ZoneInfo(fallback_tz_name)
        except ZoneInfoNotFoundError as error:
            app.logger.warning(
                "Failed to load fallback timezone '%s': %s, falling back to UTC",
                fallback_tz_name,
                error,
            )
        except Exception as error:
            app.logger.warning(
                "Unexpected fallback timezone config '%s': %s, falling back to UTC",
                fallback_tz_name,
                error,
            )

    return ZoneInfo("UTC")


def _serialize_with_app_timezone(
    app: Flask, dt: datetime | None, tz_name: str | None = None
) -> str | None:
    if dt is None:
        return None
    app_tz = _get_app_timezone(app, tz_name)
    if dt.tzinfo is None:
        source_tz = _get_app_timezone(app)
        dt = dt.replace(tzinfo=source_tz)
    return dt.astimezone(app_tz).isoformat()


def _format_with_app_timezone(
    app: Flask, dt: datetime | None, fmt: str, tz_name: str | None = None
) -> str | None:
    if dt is None:
        return None
    app_tz = _get_app_timezone(app, tz_name)
    if dt.tzinfo is None:
        source_tz = _get_app_timezone(app)
        dt = dt.replace(tzinfo=source_tz)
    return dt.astimezone(app_tz).strftime(fmt)


def get_shifu_mdflow_history(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    limit: int = 100,
    timezone_name: str | None = None,
) -> dict:
    """
    Get lesson content history for a specific outline.
    Only keep versions where markdown content actually changed.
    """
    with app.app_context():
        safe_limit = max(1, min(limit, 200))
        changed_versions: list[DraftOutlineItem] = []
        segment_content: str | None = None
        segment_oldest: DraftOutlineItem | None = None

        for version in _query_outline_versions(shifu_bid, outline_bid):
            current_content = version.content or ""
            if segment_content is None:
                segment_content = current_content
                segment_oldest = version
                continue
            if current_content == segment_content:
                segment_oldest = version
                continue

            if segment_oldest is not None:
                changed_versions.append(segment_oldest)
                if len(changed_versions) >= safe_limit:
                    break
            segment_content = current_content
            segment_oldest = version

        if segment_oldest is not None and len(changed_versions) < safe_limit:
            changed_versions.append(segment_oldest)

        if not changed_versions:
            return {"items": []}

        user_bids = {
            item.updated_user_bid for item in changed_versions if item.updated_user_bid
        }
        user_map = {}
        if user_bids:
            users = UserInfo.query.filter(
                UserInfo.user_bid.in_(user_bids),
                UserInfo.deleted == 0,
            ).all()
            user_map = {user.user_bid: user for user in users}

        items = []
        for item in changed_versions:
            user = user_map.get(item.updated_user_bid)
            masked_identifier = (
                mask_contact_identifier(user.user_identify)
                if user and user.user_identify
                else ""
            )
            user_name = (
                (user.nickname if user and user.nickname else "")
                or masked_identifier
                or item.updated_user_bid
            )
            items.append(
                {
                    "version_id": int(item.id),
                    "updated_at": _serialize_with_app_timezone(
                        app, item.updated_at, timezone_name
                    ),
                    "updated_at_display": _format_with_app_timezone(
                        app, item.updated_at, "%m-%d %H:%M:%S", timezone_name
                    ),
                    "updated_user_bid": item.updated_user_bid,
                    "updated_user_name": user_name,
                }
            )

        return {"items": items}


def restore_shifu_mdflow_history_version(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outline_bid: str,
    version_id: int,
    base_revision: int | None = None,
) -> dict:
    """
    Restore lesson content to the selected historical version.
    """
    with app.app_context():
        target_version = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.id == version_id,
                DraftOutlineItem.shifu_bid == shifu_bid,
                DraftOutlineItem.outline_item_bid == outline_bid,
                DraftOutlineItem.deleted == 0,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if not target_version:
            raise_error("server.shifu.outlineItemNotFound")

        latest_outline = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.shifu_bid == shifu_bid,
                DraftOutlineItem.outline_item_bid == outline_bid,
                DraftOutlineItem.deleted == 0,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if not latest_outline:
            raise_error("server.shifu.outlineItemNotFound")

        target_content = target_version.content or ""
        current_content = latest_outline.content or ""
        if target_content == current_content:
            return {
                "restored": False,
                "new_revision": get_shifu_draft_revision(app, shifu_bid, outline_bid),
            }

        effective_base_revision = (
            base_revision
            if isinstance(base_revision, int) and base_revision >= 0
            else get_shifu_draft_revision(app, shifu_bid, outline_bid)
        )
        result = save_shifu_mdflow(
            app,
            user_id,
            shifu_bid,
            outline_bid,
            target_content,
            base_revision=effective_base_revision,
        )
        if result.get("conflict"):
            return {"conflict": True, "meta": result.get("meta")}
        return {
            "restored": True,
            "new_revision": result.get("new_revision"),
        }
