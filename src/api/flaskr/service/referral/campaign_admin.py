"""Operator configuration APIs for referral campaigns."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from flask import Flask
from sqlalchemy import or_

from flaskr.dao import db
from flaskr.service.billing.consts import (
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
)
from flaskr.service.billing.models import BillingProduct
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.uuid import generate_id

from .consts import (
    REFERRAL_CAMPAIGN_STATUS_ACTIVE,
    REFERRAL_CAMPAIGN_STATUS_ARCHIVED,
    REFERRAL_CAMPAIGN_STATUS_DRAFT,
    REFERRAL_CAMPAIGN_STATUS_ENDED,
    REFERRAL_CAMPAIGN_STATUS_PAUSED,
    REFERRAL_INVITEE_BENEFIT_EXISTING_TRIAL_ONLY,
    REFERRAL_REWARD_CAP_SCOPE_NONE,
    REFERRAL_REWARD_CAP_SCOPE_PER_CAMPAIGN,
    REFERRAL_REWARD_CAP_SCOPE_PER_INVITER,
    REFERRAL_REWARD_TARGET_INVITER,
    REFERRAL_REWARD_TIMING_IMMEDIATE_EXTEND_OR_DEFER,
    REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
    REFERRAL_RULE_STATUS_ACTIVE,
    REFERRAL_RULE_STATUS_DRAFT,
    REFERRAL_RULE_STATUS_PAUSED,
    REFERRAL_TRIGGER_INVITED_REGISTRATION,
)
from .models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteRelation,
    ReferralInviteReward,
)


DEFAULT_PAGE_INDEX = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
REFERRAL_CAMPAIGN_STATUS_FILTERS = {
    "active",
    "not_started",
    "ended",
    "inactive",
}
REFERRAL_CAP_SCOPES = {
    REFERRAL_REWARD_CAP_SCOPE_NONE,
    REFERRAL_REWARD_CAP_SCOPE_PER_INVITER,
    REFERRAL_REWARD_CAP_SCOPE_PER_CAMPAIGN,
}


def list_operator_referral_campaigns(
    app: Flask,
    *,
    page_index: int,
    page_size: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        safe_page_index, safe_page_size = _normalize_page(page_index, page_size)
        query = ReferralCampaign.query.filter(ReferralCampaign.deleted == 0)
        keyword = _normalize_text(filters.get("keyword"))
        if keyword:
            like_value = f"%{keyword}%"
            query = query.filter(
                or_(
                    ReferralCampaign.campaign_code.ilike(like_value),
                    ReferralCampaign.campaign_name.ilike(like_value),
                    ReferralCampaign.campaign_bid.ilike(like_value),
                )
            )
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        if start_time is not None:
            query = query.filter(
                (ReferralCampaign.ends_at.is_(None))
                | (ReferralCampaign.ends_at >= start_time)
            )
        if end_time is not None:
            query = query.filter(
                (ReferralCampaign.starts_at.is_(None))
                | (ReferralCampaign.starts_at <= end_time)
            )

        status_filter = _normalize_text(filters.get("status"))
        now = datetime.now()
        if status_filter:
            query = _apply_status_filter(query, status_filter, now=now)

        total = query.count()
        rows = (
            query.order_by(
                ReferralCampaign.updated_at.desc(), ReferralCampaign.id.desc()
            )
            .offset((safe_page_index - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        campaign_bids = [row.campaign_bid for row in rows if row.campaign_bid]
        rules = _latest_rule_map(campaign_bids)
        relation_counts = _count_by_campaign(ReferralInviteRelation, campaign_bids)
        reward_counts = _count_by_campaign(ReferralInviteReward, campaign_bids)
        items = [
            _serialize_campaign(
                row,
                rule=rules.get(row.campaign_bid),
                relation_count=relation_counts.get(row.campaign_bid, 0),
                reward_count=reward_counts.get(row.campaign_bid, 0),
                now=now,
            )
            for row in rows
        ]
        return {
            "items": items,
            "page": safe_page_index,
            "page_size": safe_page_size,
            "total": total,
            "page_count": ceil(total / safe_page_size) if total else 0,
            "summary": {
                "total": total,
                "active": sum(
                    1 for item in items if item["computed_status"] == "active"
                ),
                "relation_count": sum(relation_counts.values()),
                "reward_count": sum(reward_counts.values()),
            },
        }


def get_operator_referral_campaign_detail(
    app: Flask,
    *,
    campaign_bid: str,
) -> dict[str, Any]:
    with app.app_context():
        campaign = _load_campaign_or_404(campaign_bid)
        rule = _load_latest_rule(campaign.campaign_bid)
        return {
            "campaign": _serialize_campaign(
                campaign,
                rule=rule,
                relation_count=_count_rows(
                    ReferralInviteRelation,
                    campaign.campaign_bid,
                ),
                reward_count=_count_rows(ReferralInviteReward, campaign.campaign_bid),
                now=datetime.now(),
            )
        }


def create_operator_referral_campaign(
    app: Flask,
    operator_user_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        data = _normalize_payload(payload, is_create=True)
        _assert_campaign_code_available(data["campaign_code"])
        _assert_product_code_is_active_plan(data["reward_product_code"])
        _assert_rule_code_available(
            campaign_bid=None,
            reward_rule_bid=None,
            rule_code=data["rule_code"],
        )

        campaign = ReferralCampaign(
            campaign_bid=generate_id(app),
            campaign_code=data["campaign_code"],
            campaign_name=data["campaign_name"],
            campaign_status=(
                REFERRAL_CAMPAIGN_STATUS_ACTIVE
                if data["enabled"]
                else REFERRAL_CAMPAIGN_STATUS_DRAFT
            ),
            feature_flag_key=data["feature_flag_key"],
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            invite_route_template=data["invite_route_template"],
            inviter_eligibility=data["inviter_eligibility"],
            invitee_eligibility=data["invitee_eligibility"],
            invitee_benefit_policy=data["invitee_benefit_policy"],
            rules_copy_i18n_key=data["rules_copy_i18n_key"],
            metadata_json={"operator_user_bid": _normalize_text(operator_user_bid)},
        )
        rule = _build_rule(
            app,
            campaign_bid=campaign.campaign_bid,
            data=data,
            status=(
                REFERRAL_RULE_STATUS_ACTIVE
                if data["enabled"]
                else REFERRAL_RULE_STATUS_DRAFT
            ),
        )
        db.session.add_all([campaign, rule])
        db.session.commit()
        return {"campaign_bid": campaign.campaign_bid}


def update_operator_referral_campaign(
    app: Flask,
    operator_user_bid: str,
    campaign_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        campaign = _load_campaign_or_404(campaign_bid)
        rule = _load_latest_rule(campaign.campaign_bid)
        data = _normalize_payload(payload, is_create=False, existing=campaign)
        _assert_product_code_is_active_plan(data["reward_product_code"])
        _assert_rule_code_available(
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid if rule is not None else None,
            rule_code=data["rule_code"],
        )

        campaign.campaign_name = data["campaign_name"]
        campaign.feature_flag_key = data["feature_flag_key"]
        campaign.starts_at = data["starts_at"]
        campaign.ends_at = data["ends_at"]
        campaign.invite_route_template = data["invite_route_template"]
        campaign.inviter_eligibility = data["inviter_eligibility"]
        campaign.invitee_eligibility = data["invitee_eligibility"]
        campaign.invitee_benefit_policy = data["invitee_benefit_policy"]
        campaign.rules_copy_i18n_key = data["rules_copy_i18n_key"]
        metadata = (
            campaign.metadata_json if isinstance(campaign.metadata_json, dict) else {}
        )
        metadata["operator_user_bid"] = _normalize_text(operator_user_bid)
        campaign.metadata_json = metadata
        if data["enabled"] is not None:
            campaign.campaign_status = (
                REFERRAL_CAMPAIGN_STATUS_ACTIVE
                if data["enabled"]
                else REFERRAL_CAMPAIGN_STATUS_PAUSED
            )

        if rule is None:
            rule = _build_rule(
                app,
                campaign_bid=campaign.campaign_bid,
                data=data,
                status=(
                    REFERRAL_RULE_STATUS_ACTIVE
                    if campaign.campaign_status == REFERRAL_CAMPAIGN_STATUS_ACTIVE
                    else REFERRAL_RULE_STATUS_PAUSED
                ),
            )
            db.session.add(rule)
        else:
            _apply_rule(rule, data)
            if data["enabled"] is not None:
                rule.rule_status = (
                    REFERRAL_RULE_STATUS_ACTIVE
                    if data["enabled"]
                    else REFERRAL_RULE_STATUS_PAUSED
                )
        db.session.add(campaign)
        db.session.commit()
        return {"campaign_bid": campaign.campaign_bid}


def update_operator_referral_campaign_status(
    app: Flask,
    operator_user_bid: str,
    campaign_bid: str,
    enabled: object,
) -> dict[str, Any]:
    with app.app_context():
        campaign = _load_campaign_or_404(campaign_bid)
        enabled_value = _parse_bool(enabled, "enabled")
        now = datetime.now()
        if enabled_value and campaign.ends_at is not None and campaign.ends_at <= now:
            raise_param_error("enabled")
        rule = _load_latest_rule(campaign.campaign_bid)
        if rule is None:
            raise_error("server.referral.rewardRuleNotFound")
        campaign.campaign_status = (
            REFERRAL_CAMPAIGN_STATUS_ACTIVE
            if enabled_value
            else REFERRAL_CAMPAIGN_STATUS_PAUSED
        )
        rule.rule_status = (
            REFERRAL_RULE_STATUS_ACTIVE
            if enabled_value
            else REFERRAL_RULE_STATUS_PAUSED
        )
        metadata = (
            campaign.metadata_json if isinstance(campaign.metadata_json, dict) else {}
        )
        metadata["operator_user_bid"] = _normalize_text(operator_user_bid)
        campaign.metadata_json = metadata
        db.session.add_all([campaign, rule])
        db.session.commit()
        return {"campaign_bid": campaign.campaign_bid, "enabled": enabled_value}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_page(page_index: int, page_size: int) -> tuple[int, int]:
    try:
        safe_page_index = max(int(page_index or DEFAULT_PAGE_INDEX), 1)
    except (TypeError, ValueError):
        safe_page_index = DEFAULT_PAGE_INDEX
    try:
        safe_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    except (TypeError, ValueError):
        safe_page_size = DEFAULT_PAGE_SIZE
    return safe_page_index, min(safe_page_size, MAX_PAGE_SIZE)


def _serialize_dt(value: datetime | None) -> str:
    # Match the API fmt sink: stored values are UTC; treat naive as UTC and emit
    # ISO 8601 with a 'Z' suffix so the frontend can convert to the viewer's tz.
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _parse_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    normalized = _normalize_text(value)
    if not normalized:
        return None
    for datetime_format in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(normalized, datetime_format)
            return parsed
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        raise_param_error(field_name)
    return parsed.replace(tzinfo=None)


def _parse_bool(value: object, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalize_text(value).lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise_param_error(field_name)


def _parse_positive_int(value: object, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise_param_error(field_name)
    if parsed <= 0:
        raise_param_error(field_name)
    return parsed


def _parse_int(value: object, field_name: str, *, default: int = 0) -> int:
    if value is None or _normalize_text(value) == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise_param_error(field_name)


def _parse_optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None or _normalize_text(value) == "":
        return None
    return _parse_positive_int(value, field_name)


def _parse_positive_decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(_normalize_text(value))
    except (InvalidOperation, ValueError):
        raise_param_error(field_name)
    if parsed <= 0:
        raise_param_error(field_name)
    return parsed


def _parse_json_object(value: object, field_name: str) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            raise_param_error(field_name)
        if isinstance(parsed, dict):
            return parsed
    raise_param_error(field_name)


def _normalize_payload(
    payload: dict[str, Any],
    *,
    is_create: bool,
    existing: ReferralCampaign | None = None,
) -> dict[str, Any]:
    campaign_code = _normalize_text(payload.get("campaign_code"))
    if is_create and not campaign_code:
        raise_param_error("campaign_code")
    if not is_create:
        campaign_code = (
            existing.campaign_code if existing is not None else campaign_code
        )
    campaign_name = _normalize_text(payload.get("campaign_name"))
    if not campaign_name:
        raise_param_error("campaign_name")
    starts_at = _parse_datetime(payload.get("starts_at"), "starts_at")
    ends_at = _parse_datetime(payload.get("ends_at"), "ends_at")
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise_param_error("ends_at")
    reward_product_code = _normalize_text(payload.get("reward_product_code"))
    if not reward_product_code:
        raise_param_error("reward_product_code")
    cap_scope = (
        _normalize_text(payload.get("reward_cap_scope"))
        or REFERRAL_REWARD_CAP_SCOPE_NONE
    )
    if cap_scope not in REFERRAL_CAP_SCOPES:
        raise_param_error("reward_cap_scope")
    cap_count = _parse_optional_positive_int(
        payload.get("reward_cap_count"),
        "reward_cap_count",
    )
    if cap_scope == REFERRAL_REWARD_CAP_SCOPE_NONE:
        cap_count = None
    elif cap_count is None:
        raise_param_error("reward_cap_count")

    enabled = None
    if "enabled" in payload:
        enabled = _parse_bool(payload.get("enabled"), "enabled")
    resolved_enabled = enabled if enabled is not None else (True if is_create else None)
    if resolved_enabled and ends_at is not None and ends_at <= datetime.now():
        raise_param_error("enabled")

    rule_code = (
        _normalize_text(payload.get("rule_code"))
        or f"{campaign_code}_invited_registration"
    )
    return {
        "campaign_code": campaign_code,
        "campaign_name": campaign_name,
        "enabled": resolved_enabled,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "reward_product_code": reward_product_code,
        "reward_cycle_count": _parse_positive_int(
            payload.get("reward_cycle_count"),
            "reward_cycle_count",
        ),
        "reward_credit_amount": _parse_positive_decimal(
            payload.get("reward_credit_amount"),
            "reward_credit_amount",
        ),
        "reward_credit_validity_days": _parse_positive_int(
            payload.get("reward_credit_validity_days"),
            "reward_credit_validity_days",
        ),
        "reward_cap_scope": cap_scope,
        "reward_cap_count": cap_count,
        "feature_flag_key": _normalize_text(payload.get("feature_flag_key")),
        "invite_route_template": _normalize_text(payload.get("invite_route_template"))
        or "/invite/{invite_code}",
        "inviter_eligibility": _parse_json_object(
            payload.get("inviter_eligibility"),
            "inviter_eligibility",
        ),
        "invitee_eligibility": _parse_json_object(
            payload.get("invitee_eligibility"),
            "invitee_eligibility",
        ),
        "invitee_benefit_policy": _normalize_text(payload.get("invitee_benefit_policy"))
        or REFERRAL_INVITEE_BENEFIT_EXISTING_TRIAL_ONLY,
        "rules_copy_i18n_key": _normalize_text(payload.get("rules_copy_i18n_key")),
        "rule_code": rule_code,
        "priority": _parse_int(payload.get("priority"), "priority"),
    }


def _build_rule(
    app: Flask,
    *,
    campaign_bid: str,
    data: dict[str, Any],
    status: int,
) -> ReferralCampaignRewardRule:
    rule = ReferralCampaignRewardRule(
        reward_rule_bid=generate_id(app),
        campaign_bid=campaign_bid,
        rule_status=status,
        trigger_event=REFERRAL_TRIGGER_INVITED_REGISTRATION,
        reward_target=REFERRAL_REWARD_TARGET_INVITER,
        reward_type=REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
        reward_timing_policy=REFERRAL_REWARD_TIMING_IMMEDIATE_EXTEND_OR_DEFER,
        metadata_json={},
    )
    _apply_rule(rule, data)
    return rule


def _apply_rule(rule: ReferralCampaignRewardRule, data: dict[str, Any]) -> None:
    rule.rule_code = data["rule_code"]
    rule.reward_product_code = data["reward_product_code"]
    rule.reward_cycle_count = data["reward_cycle_count"]
    rule.reward_credit_amount = data["reward_credit_amount"]
    rule.reward_credit_validity_days = data["reward_credit_validity_days"]
    rule.reward_cap_scope = data["reward_cap_scope"]
    rule.reward_cap_count = data["reward_cap_count"]
    rule.priority = data["priority"]
    rule.starts_at = data["starts_at"]
    rule.ends_at = data["ends_at"]


def _load_campaign_or_404(campaign_bid: str) -> ReferralCampaign:
    campaign = (
        ReferralCampaign.query.filter(
            ReferralCampaign.deleted == 0,
            ReferralCampaign.campaign_bid == _normalize_text(campaign_bid),
        )
        .order_by(ReferralCampaign.id.desc())
        .first()
    )
    if campaign is None:
        raise_error("server.referral.campaignNotFound")
    return campaign


def _load_latest_rule(campaign_bid: str) -> ReferralCampaignRewardRule | None:
    return (
        ReferralCampaignRewardRule.query.filter(
            ReferralCampaignRewardRule.deleted == 0,
            ReferralCampaignRewardRule.campaign_bid == _normalize_text(campaign_bid),
        )
        .order_by(
            ReferralCampaignRewardRule.priority.desc(),
            ReferralCampaignRewardRule.id.desc(),
        )
        .first()
    )


def _latest_rule_map(campaign_bids: list[str]) -> dict[str, ReferralCampaignRewardRule]:
    if not campaign_bids:
        return {}
    rows = (
        ReferralCampaignRewardRule.query.filter(
            ReferralCampaignRewardRule.deleted == 0,
            ReferralCampaignRewardRule.campaign_bid.in_(campaign_bids),
        )
        .order_by(
            ReferralCampaignRewardRule.campaign_bid.asc(),
            ReferralCampaignRewardRule.priority.desc(),
            ReferralCampaignRewardRule.id.desc(),
        )
        .all()
    )
    result: dict[str, ReferralCampaignRewardRule] = {}
    for row in rows:
        result.setdefault(row.campaign_bid, row)
    return result


def _count_by_campaign(model, campaign_bids: list[str]) -> dict[str, int]:
    if not campaign_bids:
        return {}
    rows = (
        db.session.query(model.campaign_bid, db.func.count(model.id))
        .filter(model.deleted == 0, model.campaign_bid.in_(campaign_bids))
        .group_by(model.campaign_bid)
        .all()
    )
    return {campaign_bid: int(count or 0) for campaign_bid, count in rows}


def _count_rows(model, campaign_bid: str) -> int:
    return int(
        model.query.filter(
            model.deleted == 0,
            model.campaign_bid == _normalize_text(campaign_bid),
        ).count()
        or 0
    )


def _assert_campaign_code_available(
    campaign_code: str,
    *,
    exclude_campaign_bid: str | None = None,
) -> None:
    query = ReferralCampaign.query.filter(
        ReferralCampaign.deleted == 0,
        ReferralCampaign.campaign_code == campaign_code,
    )
    if exclude_campaign_bid:
        query = query.filter(ReferralCampaign.campaign_bid != exclude_campaign_bid)
    if query.first() is not None:
        raise_param_error("campaign_code")


def _assert_rule_code_available(
    *,
    campaign_bid: str | None,
    reward_rule_bid: str | None,
    rule_code: str,
) -> None:
    query = ReferralCampaignRewardRule.query.filter(
        ReferralCampaignRewardRule.deleted == 0,
        ReferralCampaignRewardRule.rule_code == rule_code,
    )
    if campaign_bid:
        query = query.filter(ReferralCampaignRewardRule.campaign_bid == campaign_bid)
    if reward_rule_bid:
        query = query.filter(
            ReferralCampaignRewardRule.reward_rule_bid != reward_rule_bid
        )
    if query.first() is not None:
        raise_param_error("rule_code")


def _assert_product_code_is_active_plan(product_code: str) -> None:
    product = BillingProduct.query.filter(
        BillingProduct.deleted == 0,
        BillingProduct.product_code == product_code,
        BillingProduct.product_type == BILLING_PRODUCT_TYPE_PLAN,
        BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
    ).first()
    if product is None:
        raise_param_error("reward_product_code")


def _apply_status_filter(query, status: str, *, now: datetime):
    if status == "active":
        return query.filter(
            ReferralCampaign.campaign_status == REFERRAL_CAMPAIGN_STATUS_ACTIVE,
            (ReferralCampaign.starts_at.is_(None))
            | (ReferralCampaign.starts_at <= now),
            (ReferralCampaign.ends_at.is_(None)) | (ReferralCampaign.ends_at > now),
        )
    if status == "not_started":
        return query.filter(
            ReferralCampaign.campaign_status == REFERRAL_CAMPAIGN_STATUS_ACTIVE,
            ReferralCampaign.starts_at > now,
        )
    if status == "ended":
        return query.filter(ReferralCampaign.ends_at <= now)
    if status == "inactive":
        return query.filter(
            ReferralCampaign.campaign_status.in_(
                [
                    REFERRAL_CAMPAIGN_STATUS_DRAFT,
                    REFERRAL_CAMPAIGN_STATUS_PAUSED,
                    REFERRAL_CAMPAIGN_STATUS_ARCHIVED,
                    REFERRAL_CAMPAIGN_STATUS_ENDED,
                ]
            )
        )
    raise_param_error("status")


def _computed_status(campaign: ReferralCampaign, *, now: datetime) -> str:
    if int(campaign.campaign_status or 0) != REFERRAL_CAMPAIGN_STATUS_ACTIVE:
        return "inactive"
    if campaign.ends_at is not None and campaign.ends_at <= now:
        return "ended"
    if campaign.starts_at is not None and campaign.starts_at > now:
        return "not_started"
    return "active"


def _serialize_campaign(
    campaign: ReferralCampaign,
    *,
    rule: ReferralCampaignRewardRule | None,
    relation_count: int,
    reward_count: int,
    now: datetime,
) -> dict[str, Any]:
    return {
        "campaign_bid": campaign.campaign_bid,
        "campaign_code": campaign.campaign_code,
        "campaign_name": campaign.campaign_name,
        "campaign_status": int(campaign.campaign_status or 0),
        "computed_status": _computed_status(campaign, now=now),
        "enabled": int(campaign.campaign_status or 0)
        == REFERRAL_CAMPAIGN_STATUS_ACTIVE,
        "feature_flag_key": campaign.feature_flag_key or "",
        "starts_at": _serialize_dt(campaign.starts_at),
        "ends_at": _serialize_dt(campaign.ends_at),
        "invite_route_template": campaign.invite_route_template or "",
        "inviter_eligibility": campaign.inviter_eligibility or {},
        "invitee_eligibility": campaign.invitee_eligibility or {},
        "invitee_benefit_policy": campaign.invitee_benefit_policy or "",
        "rules_copy_i18n_key": campaign.rules_copy_i18n_key or "",
        "reward_rule_bid": rule.reward_rule_bid if rule is not None else "",
        "rule_code": rule.rule_code if rule is not None else "",
        "rule_status": int(rule.rule_status or 0) if rule is not None else 0,
        "reward_product_code": rule.reward_product_code if rule is not None else "",
        "reward_cycle_count": int(rule.reward_cycle_count or 0)
        if rule is not None
        else 0,
        "reward_credit_amount": _serialize_decimal(
            rule.reward_credit_amount if rule is not None else None
        ),
        "reward_credit_validity_days": (
            int(rule.reward_credit_validity_days or 0) if rule is not None else 0
        ),
        "reward_cap_scope": (
            rule.reward_cap_scope
            if rule is not None
            else REFERRAL_REWARD_CAP_SCOPE_NONE
        ),
        "reward_cap_count": rule.reward_cap_count if rule is not None else None,
        "reward_timing_policy": (
            rule.reward_timing_policy
            if rule is not None
            else REFERRAL_REWARD_TIMING_IMMEDIATE_EXTEND_OR_DEFER
        ),
        "priority": int(rule.priority or 0) if rule is not None else 0,
        "relation_count": relation_count,
        "reward_count": reward_count,
        "created_at": _serialize_dt(campaign.created_at),
        "updated_at": _serialize_dt(campaign.updated_at),
    }
