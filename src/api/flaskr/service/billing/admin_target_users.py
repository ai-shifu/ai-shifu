from __future__ import annotations

from importlib import import_module
from typing import Any

from flask import Flask

from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.phone_numbers import (
    is_valid_sms_mobile,
    normalize_phone_identifier,
)


def resolve_admin_entitlement_grant_target(
    app: Flask,
    *,
    creator_bid: str,
    creator_mobile: str,
) -> tuple[str, bool, bool]:
    normalized_creator_bid = str(creator_bid or "").strip()
    if normalized_creator_bid:
        return normalized_creator_bid, False, False

    normalized_creator_mobile = _normalize_creator_mobile(creator_mobile)
    repository = _user_repository()
    user_consts = _user_consts()
    user_utils = _user_utils()

    existing_aggregate = repository.load_user_aggregate_by_identifier(
        normalized_creator_mobile,
        providers=["phone"],
    )
    created_new_user = False
    should_grant_demo_permissions = False
    if existing_aggregate is None:
        target_aggregate, created_new_user = repository.ensure_user_for_identifier(
            app,
            provider="phone",
            identifier=normalized_creator_mobile,
            defaults={
                "identify": normalized_creator_mobile,
                "nickname": "",
                "state": user_consts.USER_STATE_REGISTERED,
            },
        )
        should_grant_demo_permissions = True
    else:
        target_aggregate = existing_aggregate
        if existing_aggregate.state == user_consts.USER_STATE_UNREGISTERED:
            should_grant_demo_permissions = True

    target_user_bid = str(target_aggregate.user_bid or "").strip()
    if not target_user_bid:
        raise_param_error("creator_mobile")

    if should_grant_demo_permissions:
        repository.set_user_state(target_user_bid, user_consts.USER_STATE_REGISTERED)

    repository.upsert_credential(
        app,
        user_bid=target_user_bid,
        provider_name="phone",
        subject_id=normalized_creator_mobile,
        subject_format="phone",
        identifier=normalized_creator_mobile,
        metadata={},
        verified=True,
    )

    if should_grant_demo_permissions:
        demo_shifu_ids = user_utils.load_existing_demo_shifu_ids()
        if demo_shifu_ids:
            user_utils.ensure_demo_course_permissions(
                app,
                target_user_bid,
                demo_ids=demo_shifu_ids,
            )

    creator_granted_now = user_utils.mark_creator_role_if_needed(target_user_bid)
    return target_user_bid, creator_granted_now, created_new_user


def resolve_existing_admin_billing_target_user_bid(
    *,
    creator_bid: str,
    creator_mobile: str,
) -> str:
    normalized_creator_bid = str(creator_bid or "").strip()
    if normalized_creator_bid:
        return normalized_creator_bid

    normalized_creator_mobile = _normalize_creator_mobile(creator_mobile)
    existing_aggregate = _user_repository().load_user_aggregate_by_identifier(
        normalized_creator_mobile,
        providers=["phone"],
    )
    if existing_aggregate is None or not str(existing_aggregate.user_bid or "").strip():
        raise_error("server.user.userNotFound")

    return str(existing_aggregate.user_bid).strip()


def run_admin_creator_granted_post_auth(
    app: Flask,
    *,
    user_id: str,
    created_new_user: bool,
    source: str = "billing_admin_entitlement_grant",
) -> None:
    _user_utils().run_creator_granted_post_auth(
        app,
        user_id=user_id,
        source=source,
        created_new_user=created_new_user,
    )


def _normalize_creator_mobile(creator_mobile: str) -> str:
    normalized_creator_mobile = normalize_phone_identifier(creator_mobile)
    if not normalized_creator_mobile:
        raise_param_error("creator_mobile")
    if not is_valid_sms_mobile(normalized_creator_mobile):
        raise_param_error("mobile")
    return normalized_creator_mobile


def _user_repository() -> Any:
    return import_module("flaskr.service.user.repository")


def _user_utils() -> Any:
    return import_module("flaskr.service.user.utils")


def _user_consts() -> Any:
    return import_module("flaskr.service.user.consts")
