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
    get_shifu_draft_log,
)
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
    add_profile_item_quick,
)
from flaskr.service.user.models import UserInfo
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def get_shifu_mdflow(app: Flask, shifu_bid: str, outline_bid: str) -> str:
    """
    Get shifu mdflow
    """
    with app.app_context():
        outline_item = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_bid
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


def _cleanup_outline_history_versions(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    keep_versions: int = LESSON_HISTORY_MAX_VERSIONS,
    keep_days: int = LESSON_HISTORY_MAX_DAYS,
) -> None:
    """
    Keep outline version history bounded:
    - keep at most `keep_versions` latest non-deleted versions
    - keep at most `keep_days` days of non-deleted versions
    The latest version is always preserved.
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
    cutoff_time = datetime.now() - timedelta(days=max(1, keep_days))
    to_mark_deleted_ids: set[int] = set()

    # Trim by age.
    expired_ids = (
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.outline_item_bid == outline_bid,
            DraftOutlineItem.deleted == 0,
            DraftOutlineItem.updated_at < cutoff_time,
            DraftOutlineItem.id != latest_id,
        )
        .with_entities(DraftOutlineItem.id)
        .all()
    )
    to_mark_deleted_ids.update(int(item.id) for item in expired_ids)

    # Trim by max count.
    overflow_ids = (
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.outline_item_bid == outline_bid,
            DraftOutlineItem.deleted == 0,
            DraftOutlineItem.id != latest_id,
        )
        .order_by(DraftOutlineItem.id.desc())
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
        lock_latest = isinstance(base_revision, int)
        latest_log = get_shifu_draft_log(app, shifu_bid, for_update=lock_latest)
        latest_revision = int(latest_log.id) if latest_log else 0
        updated_user_bid = latest_log.updated_user_bid if latest_log else ""
        if (
            isinstance(base_revision, int)
            and base_revision >= 0
            and latest_revision > base_revision
            and (not updated_user_bid or updated_user_bid != user_id)
        ):
            return {"conflict": True, "meta": get_shifu_draft_meta(app, shifu_bid)}

        outline_item: DraftOutlineItem = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.outline_item_bid == outline_bid
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if not outline_item:
            raise_error("server.shifu.outlineItemNotFound")
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
            variable_definitions = get_profile_item_definition_list(
                app, outline_item.shifu_bid
            )

            variables = markdown_flow.extract_variables()
            for variable in variables:
                exist_variable = next(
                    (v for v in variable_definitions if v.profile_key == variable), None
                )
                if not exist_variable:
                    add_profile_item_quick(
                        app, outline_item.shifu_bid, variable, user_id
                    )
            new_revision = save_outline_history(
                app,
                user_id,
                outline_item.shifu_bid,
                outline_item.outline_item_bid,
                new_outline.id,
                len(blocks),
            )
            _cleanup_outline_history_versions(
                app,
                outline_item.shifu_bid,
                outline_item.outline_item_bid,
            )
            db.session.commit()
        return {
            "conflict": False,
            "new_revision": new_revision
            if new_revision is not None
            else get_shifu_draft_revision(app, shifu_bid),
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
                DraftOutlineItem.outline_item_bid == outline_bid
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
        .order_by(DraftOutlineItem.id.asc())
        .all()
    )


def _get_app_timezone(app: Flask) -> ZoneInfo:
    tz_name = app.config.get("TZ", "UTC")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _serialize_with_app_timezone(app: Flask, dt: datetime | None) -> str | None:
    if dt is None:
        return None
    app_tz = _get_app_timezone(app)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=app_tz).isoformat()
    return dt.astimezone(app_tz).isoformat()


def get_shifu_mdflow_history(
    app: Flask, shifu_bid: str, outline_bid: str, limit: int = 100
) -> dict:
    """
    Get lesson content history for a specific outline.
    Only keep versions where markdown content actually changed.
    """
    with app.app_context():
        safe_limit = max(1, min(limit, 200))
        versions = _query_outline_versions(shifu_bid, outline_bid)
        changed_versions: list[DraftOutlineItem] = []
        previous_content: str | None = None

        for version in versions:
            current_content = version.content or ""
            if previous_content is None:
                previous_content = current_content
                continue
            if current_content == previous_content:
                continue
            changed_versions.append(version)
            previous_content = current_content

        if not changed_versions:
            return {"items": []}

        changed_versions = changed_versions[-safe_limit:]
        changed_versions.reverse()

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
            user_name = (
                (user.nickname if user and user.nickname else "")
                or (user.user_identify if user and user.user_identify else "")
                or item.updated_user_bid
            )
            items.append(
                {
                    "version_id": int(item.id),
                    "updated_at": _serialize_with_app_timezone(app, item.updated_at),
                    "updated_user_bid": item.updated_user_bid,
                    "updated_user_name": user_name,
                }
            )

        return {"items": items}


def restore_shifu_mdflow_history_version(
    app: Flask, user_id: str, shifu_bid: str, outline_bid: str, version_id: int
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
                "new_revision": get_shifu_draft_revision(app, shifu_bid),
            }

        result = save_shifu_mdflow(
            app,
            user_id,
            shifu_bid,
            outline_bid,
            target_content,
            base_revision=None,
        )
        return {
            "restored": True,
            "new_revision": result.get("new_revision"),
        }
