"""Shared-permission writes for a shifu (grant / remove).

Moved out of ``service/shifu/route.py`` so the route only validates the
request and the transaction boundary lives with the persistence logic.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flaskr.common.cache_provider import cache as redis
from flaskr.common.config import get_redis_key_prefix
from flaskr.dao import db, uow
from flaskr.dao.uow import unit_of_work
from flaskr.i18n import _
from flaskr.service.common.models import raise_param_error
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.service.user.api import (
    ensure_demo_course_permissions,
    ensure_user_for_identifier,
    load_existing_demo_shifu_ids,
    load_user_aggregate_by_identifier,
    mark_creator_role_if_needed,
    run_creator_granted_post_auth,
    set_user_state,
    upsert_credential,
)
from flaskr.service.user.consts import USER_STATE_REGISTERED, USER_STATE_UNREGISTERED
from flaskr.util.uuid import generate_id

if TYPE_CHECKING:
    from flask import Flask

MAX_SHARED_COURSE_USERS = 10


def clear_shifu_permission_cache(app: Flask, user_id: str, shifu_bid: str) -> None:
    """Remove cached permission entries for a given user/shifu pair."""
    # Clear both legacy and current redis prefixes to avoid stale permissions.
    prefixes = {
        app.config.get("CACHE_KEY_PREFIX", "") or "",
        get_redis_key_prefix(app),
    }
    for prefix in prefixes:
        cache_key = f"{prefix}shifu_permission:{user_id}:{shifu_bid}"
        redis.delete(cache_key)


def grant_shifu_permissions(
    app: Flask,
    *,
    shifu_bid: str,
    owner_id: str,
    contact_type: str,
    contacts: list[str],
    permission: str,
) -> int:
    """Grant ``permission`` on ``shifu_bid`` to every contact, creating accounts as needed.

    ``contacts`` must already be normalized and validated by the caller. The
    whole grant is one unit of work; cache invalidation and the creator
    post-auth chain run only after it commits.
    """
    with unit_of_work():
        existing_auths = AiCourseAuth.query.filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.status == 1,
        ).all()
        existing_user_ids = {
            auth.user_id
            for auth in existing_auths
            if auth.user_id and auth.user_id != owner_id
        }

        user_id_by_contact: dict[str, str] = {}
        aggregate_by_contact: dict[str, object] = {}
        new_contact_count = 0
        for contact in contacts:
            aggregate = load_user_aggregate_by_identifier(
                contact, providers=[contact_type]
            )
            if aggregate:
                if aggregate.user_bid == owner_id:
                    continue
                user_id_by_contact[contact] = aggregate.user_bid
                aggregate_by_contact[contact] = aggregate
            else:
                new_contact_count += 1

        new_existing_user_ids = {
            user_id
            for user_id in user_id_by_contact.values()
            if user_id not in existing_user_ids and user_id != owner_id
        }

        if (
            len(existing_user_ids) + len(new_existing_user_ids) + new_contact_count
            > MAX_SHARED_COURSE_USERS
        ):
            raise_param_error(
                _("server.shifu.permissionContactLimit").format(
                    count=MAX_SHARED_COURSE_USERS
                )
            )

        auth_types = ["view"]
        if permission == "edit":
            auth_types = ["edit"]
        elif permission == "publish":
            # Publish grants both edit and publish permissions.
            auth_types = ["edit", "publish"]

        demo_shifu_ids = load_existing_demo_shifu_ids()
        creator_upgrade_contexts: dict[str, dict[str, object]] = {}
        touched_user_ids: list[str] = []
        for contact in contacts:
            aggregate = aggregate_by_contact.get(contact)
            created_new_user = False
            should_grant_demo_permissions = False
            if aggregate is None:
                aggregate, created_new_user = ensure_user_for_identifier(
                    app,
                    provider=contact_type,
                    identifier=contact,
                    defaults={"state": USER_STATE_REGISTERED},
                )
                should_grant_demo_permissions = created_new_user
            elif aggregate.state == USER_STATE_UNREGISTERED:
                set_user_state(aggregate.user_bid, USER_STATE_REGISTERED)
                should_grant_demo_permissions = True
            if not aggregate or aggregate.user_bid == owner_id:
                continue

            normalized_contact = contact
            if contact_type == "email":
                normalized_contact = contact.lower()

            upsert_credential(
                app,
                user_bid=aggregate.user_bid,
                provider_name=contact_type,
                subject_id=normalized_contact,
                subject_format=contact_type,
                identifier=normalized_contact,
                metadata={},
                verified=True,
            )
            if should_grant_demo_permissions:
                ensure_demo_course_permissions(
                    app, aggregate.user_bid, demo_ids=demo_shifu_ids
                )
            if permission in {"edit", "publish"}:
                creator_granted_now = mark_creator_role_if_needed(aggregate.user_bid)
                if creator_granted_now:
                    creator_upgrade_contexts.setdefault(
                        aggregate.user_bid,
                        {
                            "created_new_user": created_new_user,
                            "language": aggregate.user_language,
                        },
                    )

            auth = AiCourseAuth.query.filter(
                AiCourseAuth.course_id == shifu_bid,
                AiCourseAuth.user_id == aggregate.user_bid,
            ).first()
            if auth:
                auth.auth_type = json.dumps(auth_types)
                auth.status = 1
            else:
                db.session.add(
                    AiCourseAuth(
                        course_auth_id=generate_id(app),
                        user_id=aggregate.user_bid,
                        course_id=shifu_bid,
                        auth_type=json.dumps(auth_types),
                        status=1,
                    )
                )
            touched_user_ids.append(aggregate.user_bid)

        def finish_grant() -> None:
            for user_id in touched_user_ids:
                clear_shifu_permission_cache(app, user_id, shifu_bid)
            for user_id, upgrade_context in creator_upgrade_contexts.items():
                run_creator_granted_post_auth(
                    app,
                    user_id=user_id,
                    source="shifu_permission_grant",
                    created_new_user=bool(upgrade_context.get("created_new_user")),
                    language=str(upgrade_context.get("language") or ""),
                )

        uow.on_commit(finish_grant)
    return len(contacts)


def remove_shifu_permission(app: Flask, *, shifu_bid: str, user_id: str) -> bool:
    """Soft-delete a shared permission; the cache is cleared after commit."""
    with unit_of_work():
        auth = AiCourseAuth.query.filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.user_id == user_id,
        ).first()
        if auth:
            auth.status = 0
        uow.on_commit(lambda: clear_shifu_permission_cache(app, user_id, shifu_bid))
    return True
