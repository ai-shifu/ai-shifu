"""Operator course creator transfer and course copy flows.

Split mechanically out of the former giant module (backend overhaul B5).
"""

from __future__ import annotations

from datetime import datetime

from flaskr.util.datetime import now_utc
from typing import Any, Dict, Sequence
from flask import Flask, current_app
from flaskr.common.cache_provider import cache as redis
from flaskr.common.config import get_redis_key_prefix
from flaskr.i18n import _
from flaskr.dao import db
from flaskr.service.common.models import (
    raise_error,
    raise_error_with_args,
    raise_param_error,
)
from flaskr.service.profile.models import Variable
from flaskr.util import generate_id
from flaskr.service.shifu.consts import (
    SHIFU_NAME_MAX_LENGTH,
)
from flaskr.service.shifu.shifu_draft_funcs import (
    check_text_with_risk_control,
    get_latest_shifu_draft,
)
from flaskr.service.shifu.shifu_history_manager import (
    HistoryItem,
    save_outline_tree_history,
    save_shifu_history,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedShifu,
)
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.service.user.consts import (
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.repository import (
    ensure_user_for_identifier,
    load_user_aggregate_by_identifier,
    set_user_state,
    upsert_credential,
)
from flaskr.service.user.utils import (
    ensure_demo_course_permissions,
    load_existing_demo_shifu_ids,
    mark_creator_role_if_needed,
    run_creator_granted_post_auth,
)
from markdown_flow import MarkdownFlow

from flaskr.service.shifu.admin_operations.courses_shared import (
    OPERATOR_TARGET_CONTACT_MAX_LENGTH,
    OPERATOR_TARGET_EMAIL_PATTERN,
    OPERATOR_TARGET_PHONE_PATTERN,
    _get_legacy_admin_symbol,
    _is_operator_visible_course,
    _normalize_identifier,
)


def _load_latest_course_for_transfer(shifu_bid: str):
    draft = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_bid,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    if draft:
        return draft

    return (
        PublishedShifu.query.filter(
            PublishedShifu.shifu_bid == shifu_bid,
            PublishedShifu.deleted == 0,
        )
        .order_by(PublishedShifu.id.desc())
        .first()
    )


def _load_latest_active_draft_outlines(shifu_bid: str) -> list[DraftOutlineItem]:
    latest_outline_ids = (
        db.session.query(
            DraftOutlineItem.outline_item_bid.label("outline_item_bid"),
            db.func.max(DraftOutlineItem.id).label("max_id"),
        )
        .filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
        )
        .group_by(DraftOutlineItem.outline_item_bid)
        .subquery()
    )
    return (
        db.session.query(DraftOutlineItem)
        .join(latest_outline_ids, DraftOutlineItem.id == latest_outline_ids.c.max_id)
        .filter(DraftOutlineItem.deleted == 0)
        .order_by(DraftOutlineItem.position.asc(), DraftOutlineItem.id.asc())
        .all()
    )


def _build_course_copy_title(source_title: str) -> str:
    normalized_title = str(source_title or "").strip() or _(
        "server.shifu.copyCourseTitleFallback"
    )
    suffix = _("server.shifu.copyCourseTitleSuffix")
    if len(normalized_title) + len(suffix) <= SHIFU_NAME_MAX_LENGTH:
        return f"{normalized_title}{suffix}"
    return f"{normalized_title[: SHIFU_NAME_MAX_LENGTH - len(suffix)]}{suffix}"


def _resolve_course_copy_title(source_title: str, requested_title: str) -> str:
    normalized_requested_title = str(requested_title or "").strip()
    if normalized_requested_title:
        if len(normalized_requested_title) > SHIFU_NAME_MAX_LENGTH:
            raise_error_with_args(
                "server.shifu.shifuNameTooLong",
                max_length=SHIFU_NAME_MAX_LENGTH,
            )
        return normalized_requested_title
    return _build_course_copy_title(source_title)


def _build_outline_history_tree(
    outlines: Sequence[DraftOutlineItem],
) -> list[HistoryItem]:
    outline_children_map: Dict[str, list[DraftOutlineItem]] = {}
    for outline in outlines:
        parent_bid = str(outline.parent_bid or "").strip()
        outline_children_map.setdefault(parent_bid, []).append(outline)

    def _count_blocks(content: str) -> int:
        if not content:
            return 0
        mdflow = MarkdownFlow(content).set_output_language(
            get_markdownflow_output_language()
        )
        return len(mdflow.get_all_blocks())

    def _build(parent_bid: str) -> list[HistoryItem]:
        children = outline_children_map.get(parent_bid, [])
        children.sort(key=lambda item: (item.position or "", item.id))
        history_items: list[HistoryItem] = []
        for child in children:
            history_items.append(
                HistoryItem(
                    bid=str(child.outline_item_bid or "").strip(),
                    id=int(child.id),
                    type="outline",
                    children=_build(str(child.outline_item_bid or "").strip()),
                    child_count=_count_blocks(child.content or ""),
                )
            )
        return history_items

    return _build("")


def _copy_course_variable_definitions(
    *,
    source_shifu_bid: str,
    target_shifu_bid: str,
    creator_user_bid: str,
    updated_user_bid: str,
    now: datetime,
) -> None:
    variable_definitions = (
        Variable.query.filter(
            Variable.shifu_bid == source_shifu_bid,
            Variable.deleted == 0,
        )
        .order_by(Variable.id.asc())
        .all()
    )
    for definition in variable_definitions:
        db.session.add(
            Variable(
                variable_bid=generate_id(current_app),
                shifu_bid=target_shifu_bid,
                key=str(definition.key or "").strip(),
                is_hidden=definition.is_hidden,
                deleted=0,
                created_at=now,
                created_user_bid=creator_user_bid,
                updated_at=now,
                updated_user_bid=updated_user_bid,
            )
        )


def _run_course_copy_draft_risk_check(
    app: Flask,
    *,
    source_draft: DraftShifu,
    target_shifu_bid: str,
    operator_user_bid: str,
    new_course_name: str,
) -> None:
    draft_to_check = source_draft.clone()
    draft_to_check.shifu_bid = target_shifu_bid
    draft_to_check.title = new_course_name
    check_content = str(draft_to_check.get_str_to_check() or "").strip()
    if check_content:
        _get_legacy_admin_symbol(
            "check_text_with_risk_control", check_text_with_risk_control
        )(app, target_shifu_bid, operator_user_bid, check_content)


def _run_course_copy_outline_risk_check(
    app: Flask,
    *,
    source_outline: DraftOutlineItem,
    target_outline_bid: str,
    operator_user_bid: str,
) -> None:
    outline_to_check = source_outline.clone()
    outline_to_check.outline_item_bid = target_outline_bid
    outline_check_content = str(outline_to_check.get_str_to_check() or "").strip()
    if outline_check_content:
        _get_legacy_admin_symbol(
            "check_text_with_risk_control", check_text_with_risk_control
        )(app, target_outline_bid, operator_user_bid, outline_check_content)

    markdown_content = str(outline_to_check.content or "").strip()
    if markdown_content:
        _get_legacy_admin_symbol(
            "check_text_with_risk_control", check_text_with_risk_control
        )(app, target_outline_bid, operator_user_bid, markdown_content)


def _validate_operator_target_contact(contact_type: str, identifier: str) -> str:
    normalized_contact_type = str(contact_type or "").strip().lower()
    normalized_identifier = _normalize_identifier(identifier)
    if normalized_contact_type not in {"phone", "email"}:
        raise_param_error("contact_type")
    if (
        not normalized_identifier
        or len(normalized_identifier) > OPERATOR_TARGET_CONTACT_MAX_LENGTH
    ):
        raise_param_error("contact")
    if normalized_contact_type == "phone":
        if not OPERATOR_TARGET_PHONE_PATTERN.match(normalized_identifier):
            raise_param_error("mobile")
        return normalized_identifier
    if not OPERATOR_TARGET_EMAIL_PATTERN.match(normalized_identifier):
        raise_param_error("email")
    return normalized_identifier.lower()


def _prepare_operator_target_creator(
    app: Flask,
    *,
    contact_type: str,
    identifier: str,
    previous_creator_user_bid: str = "",
    allow_same_user: bool = False,
) -> Dict[str, Any]:
    normalized_contact_type = str(contact_type or "").strip().lower()
    normalized_identifier = _validate_operator_target_contact(
        normalized_contact_type, identifier
    )

    lookup_providers = (
        ["email", "google"] if normalized_contact_type == "email" else ["phone"]
    )

    existing_aggregate = load_user_aggregate_by_identifier(
        normalized_identifier,
        providers=lookup_providers,
    )
    created_new_user = False
    granted_demo_permissions = False
    if existing_aggregate is None:
        target_aggregate, created_new_user = ensure_user_for_identifier(
            app,
            provider=normalized_contact_type,
            identifier=normalized_identifier,
            defaults={
                "identify": normalized_identifier,
                "nickname": "",
                "state": USER_STATE_REGISTERED,
            },
        )
    else:
        target_aggregate = existing_aggregate

    target_user_bid = str(target_aggregate.user_bid or "").strip()
    if not target_user_bid:
        raise_error("server.shifu.transferCreatorTargetNotFound")
    if (
        previous_creator_user_bid
        and not allow_same_user
        and target_user_bid == previous_creator_user_bid
    ):
        raise_error("server.shifu.transferCreatorSameUser")

    should_grant_demo_permissions = created_new_user
    if (
        existing_aggregate is not None
        and existing_aggregate.state == USER_STATE_UNREGISTERED
    ):
        set_user_state(target_user_bid, USER_STATE_REGISTERED)
        should_grant_demo_permissions = True

    upsert_credential(
        app,
        user_bid=target_user_bid,
        provider_name=normalized_contact_type,
        subject_id=normalized_identifier,
        subject_format=normalized_contact_type,
        identifier=normalized_identifier,
        metadata={},
        verified=True,
    )

    if should_grant_demo_permissions:
        demo_shifu_ids = load_existing_demo_shifu_ids()
        if demo_shifu_ids:
            ensure_demo_course_permissions(
                app,
                target_user_bid,
                demo_ids=demo_shifu_ids,
            )
            granted_demo_permissions = True

    creator_granted_now = mark_creator_role_if_needed(target_user_bid)
    return {
        "target_aggregate": target_aggregate,
        "target_user_bid": target_user_bid,
        "normalized_identifier": normalized_identifier,
        "created_new_user": created_new_user,
        "granted_demo_permissions": granted_demo_permissions,
        "creator_granted_now": creator_granted_now,
    }


def _clear_shifu_permission_cache(app: Flask, user_id: str, shifu_bid: str) -> None:
    prefixes = {
        app.config.get("CACHE_KEY_PREFIX", "") or "",
        get_redis_key_prefix(app),
    }
    for prefix in prefixes:
        cache_key = f"{prefix}shifu_permission:{user_id}:{shifu_bid}"
        redis.delete(cache_key)


def _clear_shifu_creator_cache(app: Flask, shifu_bid: str) -> None:
    prefixes = {
        get_redis_key_prefix(app),
        "ai-shifu",
    }
    for prefix in prefixes:
        cache_key = f"{prefix}:shifu_creator:{shifu_bid}"
        redis.delete(cache_key)


def _update_course_creator_bid(
    shifu_bid: str,
    creator_user_bid: str,
    updated_user_bid: str = "",
) -> None:
    draft_values = {DraftShifu.created_user_bid: creator_user_bid}
    published_values = {PublishedShifu.created_user_bid: creator_user_bid}
    normalized_updated_user_bid = str(updated_user_bid or "").strip()
    if normalized_updated_user_bid:
        updated_at = now_utc()
        draft_values[DraftShifu.updated_user_bid] = normalized_updated_user_bid
        draft_values[DraftShifu.updated_at] = updated_at
        published_values[PublishedShifu.updated_user_bid] = normalized_updated_user_bid
        published_values[PublishedShifu.updated_at] = updated_at
    DraftShifu.query.filter(DraftShifu.shifu_bid == shifu_bid).update(
        draft_values,
        synchronize_session=False,
    )
    PublishedShifu.query.filter(PublishedShifu.shifu_bid == shifu_bid).update(
        published_values,
        synchronize_session=False,
    )


def transfer_operator_course_creator(
    app: Flask,
    *,
    shifu_bid: str,
    contact_type: str,
    identifier: str,
    operator_user_bid: str = "",
) -> Dict[str, Any]:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_contact_type = str(contact_type or "").strip().lower()
        normalized_identifier = _normalize_identifier(identifier)
        normalized_operator_user_bid = str(operator_user_bid or "").strip()

        latest_course = _load_latest_course_for_transfer(normalized_shifu_bid)
        if not latest_course:
            raise_error("server.shifu.shifuNotFound")
        if not _is_operator_visible_course(latest_course):
            raise_error("server.shifu.transferCreatorDemoNotAllowed")

        previous_creator_user_bid = str(latest_course.created_user_bid or "").strip()
        target_creator_result = _prepare_operator_target_creator(
            app,
            contact_type=normalized_contact_type,
            identifier=normalized_identifier,
            previous_creator_user_bid=previous_creator_user_bid,
        )
        target_aggregate = target_creator_result["target_aggregate"]
        target_user_bid = target_creator_result["target_user_bid"]
        created_new_user = target_creator_result["created_new_user"]
        granted_demo_permissions = target_creator_result["granted_demo_permissions"]
        creator_granted_now = target_creator_result["creator_granted_now"]
        _update_course_creator_bid(
            normalized_shifu_bid,
            target_user_bid,
            updated_user_bid=normalized_operator_user_bid,
        )
        if normalized_operator_user_bid and getattr(latest_course, "id", 0):
            save_shifu_history(
                app,
                normalized_operator_user_bid,
                normalized_shifu_bid,
                int(latest_course.id),
            )

        db.session.commit()
        if previous_creator_user_bid:
            _clear_shifu_permission_cache(
                app, previous_creator_user_bid, normalized_shifu_bid
            )
        _clear_shifu_permission_cache(app, target_user_bid, normalized_shifu_bid)
        _clear_shifu_creator_cache(app, normalized_shifu_bid)
        if creator_granted_now:
            _get_legacy_admin_symbol(
                "run_creator_granted_post_auth", run_creator_granted_post_auth
            )(
                app,
                user_id=target_user_bid,
                source="operator_transfer_creator",
                login_context="admin",
                created_new_user=created_new_user,
                language=target_aggregate.user_language,
            )
        return {
            "shifu_bid": normalized_shifu_bid,
            "previous_creator_user_bid": previous_creator_user_bid,
            "target_creator_user_bid": target_user_bid,
            "created_new_user": created_new_user,
            "granted_demo_permissions": granted_demo_permissions,
        }


def copy_operator_course(
    app: Flask,
    *,
    shifu_bid: str,
    contact_type: str,
    identifier: str,
    operator_user_bid: str,
    new_course_name: str = "",
) -> Dict[str, Any]:
    with app.app_context():
        normalized_shifu_bid = str(shifu_bid or "").strip()
        normalized_contact_type = str(contact_type or "").strip().lower()
        normalized_identifier = _normalize_identifier(identifier)
        normalized_operator_user_bid = str(operator_user_bid or "").strip()
        if not normalized_operator_user_bid:
            raise_param_error("operator_user_bid")

        source_draft = get_latest_shifu_draft(normalized_shifu_bid)
        if not source_draft:
            raise_error("server.shifu.copyCourseDraftNotFound")
        if not _is_operator_visible_course(source_draft):
            raise_error("server.shifu.copyCourseDemoNotAllowed")

        action_user_bid = normalized_operator_user_bid
        now = now_utc()
        new_shifu_bid = generate_id(app)
        resolved_new_course_name = _resolve_course_copy_title(
            source_draft.title,
            new_course_name,
        )
        source_outlines = _load_latest_active_draft_outlines(normalized_shifu_bid)
        outline_bid_map: Dict[str, str] = {
            str(item.outline_item_bid or "").strip(): generate_id(app)
            for item in source_outlines
        }

        _run_course_copy_draft_risk_check(
            app,
            source_draft=source_draft,
            target_shifu_bid=new_shifu_bid,
            operator_user_bid=action_user_bid,
            new_course_name=resolved_new_course_name,
        )
        for source_outline in source_outlines:
            old_outline_bid = str(source_outline.outline_item_bid or "").strip()
            _run_course_copy_outline_risk_check(
                app,
                source_outline=source_outline,
                target_outline_bid=outline_bid_map[old_outline_bid],
                operator_user_bid=action_user_bid,
            )

        target_creator_result = _prepare_operator_target_creator(
            app,
            contact_type=normalized_contact_type,
            identifier=normalized_identifier,
            previous_creator_user_bid=str(source_draft.created_user_bid or "").strip(),
            allow_same_user=True,
        )
        target_aggregate = target_creator_result["target_aggregate"]
        target_user_bid = target_creator_result["target_user_bid"]
        created_new_user = target_creator_result["created_new_user"]
        granted_demo_permissions = target_creator_result["granted_demo_permissions"]
        creator_granted_now = target_creator_result["creator_granted_now"]

        new_draft = source_draft.clone()
        new_draft.shifu_bid = new_shifu_bid
        new_draft.title = resolved_new_course_name
        new_draft.created_at = now
        new_draft.updated_at = now
        new_draft.created_user_bid = target_user_bid
        new_draft.updated_user_bid = action_user_bid
        new_draft.deleted = 0
        db.session.add(new_draft)
        db.session.flush()

        source_outline_map = {
            str(item.outline_item_bid or "").strip(): item for item in source_outlines
        }
        copied_outlines: Dict[str, DraftOutlineItem] = {}

        for source_outline in source_outlines:
            old_outline_bid = str(source_outline.outline_item_bid or "").strip()
            new_outline_bid = outline_bid_map[old_outline_bid]

            new_outline = source_outline.clone()
            new_outline.shifu_bid = new_shifu_bid
            new_outline.outline_item_bid = new_outline_bid
            new_outline.parent_bid = ""
            new_outline.prerequisite_item_bids = ""
            new_outline.created_at = now
            new_outline.updated_at = now
            new_outline.created_user_bid = target_user_bid
            new_outline.updated_user_bid = action_user_bid
            new_outline.deleted = 0
            db.session.add(new_outline)
            db.session.flush()
            copied_outlines[old_outline_bid] = new_outline

        for old_outline_bid, copied_outline in copied_outlines.items():
            source_outline = source_outline_map[old_outline_bid]
            parent_old_bid = str(source_outline.parent_bid or "").strip()
            if parent_old_bid:
                copied_outline.parent_bid = outline_bid_map.get(parent_old_bid, "")

            prerequisite_old_bids = [
                bid.strip()
                for bid in str(source_outline.prerequisite_item_bids or "").split(",")
                if bid.strip()
            ]
            copied_outline.prerequisite_item_bids = ",".join(
                outline_bid_map[bid]
                for bid in prerequisite_old_bids
                if bid in outline_bid_map
            )

        save_shifu_history(app, action_user_bid, new_shifu_bid, new_draft.id)
        outline_tree = _build_outline_history_tree(list(copied_outlines.values()))
        save_outline_tree_history(
            app,
            action_user_bid,
            new_shifu_bid,
            outline_tree,
            new_draft.id,
        )
        _copy_course_variable_definitions(
            source_shifu_bid=normalized_shifu_bid,
            target_shifu_bid=new_shifu_bid,
            creator_user_bid=target_user_bid,
            updated_user_bid=action_user_bid,
            now=now,
        )

        db.session.commit()
        if creator_granted_now:
            _get_legacy_admin_symbol(
                "run_creator_granted_post_auth", run_creator_granted_post_auth
            )(
                app,
                user_id=target_user_bid,
                source="operator_copy_course",
                login_context="admin",
                created_new_user=created_new_user,
                language=target_aggregate.user_language,
            )

        return {
            "source_shifu_bid": normalized_shifu_bid,
            "new_shifu_bid": new_shifu_bid,
            "new_course_name": resolved_new_course_name,
            "target_creator_user_bid": target_user_bid,
            "created_new_user": created_new_user,
            "granted_demo_permissions": granted_demo_permissions,
        }
