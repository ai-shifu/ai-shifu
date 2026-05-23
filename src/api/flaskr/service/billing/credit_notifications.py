"""Credit notification center orchestration."""

from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, has_app_context
from sqlalchemy.exc import IntegrityError

from flaskr.api.sms.aliyun import get_sms_template_ali, send_sms_ali
from flaskr.common.observability import record_credit_notification_event
from flaskr.dao import db
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.config import get_config
from flaskr.service.config.funcs import add_config
from flaskr.service.user.consts import USER_STATE_UNREGISTERED
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.timezone import serialize_with_app_timezone
from flaskr.util.uuid import generate_id

from .consts import (
    BILL_CONFIG_KEY_CREDIT_NOTIFICATION_SMS_CONFIG,
    CREDIT_BUCKET_STATUS_ACTIVE,
    CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
    CREDIT_NOTIFICATION_CHANNEL_SMS,
    CREDIT_NOTIFICATION_PROCESSABLE_STATUSES,
    CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
    CREDIT_NOTIFICATION_STATUS_PENDING,
    CREDIT_NOTIFICATION_STATUS_SENT,
    CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE,
    CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
    CREDIT_NOTIFICATION_TYPE_EXPIRING,
    CREDIT_NOTIFICATION_TYPE_GRANTED,
    CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
    DEFAULT_CREDIT_NOTIFICATION_SMS_CONFIG,
)
from .models import (
    BillingDailyLedgerSummary,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
    NotificationRecord,
    NotificationTemplate,
)
from .notifications import load_creator_mobile_snapshot
from .primitives import is_billing_enabled
from .primitives import normalize_bid as _normalize_bid
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal

TASK_NAME = "billing.send_credit_notification"
SOURCE_TYPE_LEDGER = "ledger"
SOURCE_TYPE_WALLET = "wallet"
SOURCE_TYPE_WALLET_BUCKET = "wallet_bucket"
LIMIT_STATE_NORMAL = "normal"
LIMIT_STATE_SOFTLIMIT = "softlimit"
LIMIT_STATE_HARDLIMIT = "hardlimit"
_ZERO = Decimal("0")
LOW_BALANCE_THRESHOLD_KIND_FIXED = "fixed"
LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS = "estimated_days"
LOW_BALANCE_ESTIMATED_DAYS_MAX_DAYS = 365
LOW_BALANCE_ESTIMATED_DAYS_MAX_LOOKBACK_DAYS = 365
NOTIFICATION_TEMPLATE_PROVIDER_ALIYUN = "aliyun"
NOTIFICATION_TEMPLATE_SYNC_STATUS_SYNCED = "synced"
NOTIFICATION_TEMPLATE_SYNC_STATUS_FAILED_PROVIDER = "failed_provider"
NOTIFICATION_TEMPLATE_SYNC_STATUS_MISSING_CREDENTIALS = "missing_credentials"
_TEMPLATE_PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
CREDIT_NOTIFICATION_TEMPLATE_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    CREDIT_NOTIFICATION_TYPE_GRANTED: ("credits", "source", "expires_at"),
    CREDIT_NOTIFICATION_TYPE_EXPIRING: ("credits", "expires_at", "window"),
    CREDIT_NOTIFICATION_TYPE_LOW_BALANCE: (
        "available_credits",
        "threshold",
        "threshold_kind",
        "trigger_days",
        "lookback_days",
        "avg_daily_consumption",
        "estimated_remaining_days",
    ),
}


def _maybe_app_context(app: Flask):
    return nullcontext() if has_app_context() else app.app_context()


@dataclass(slots=True, frozen=True)
class CreditNotificationStageResult:
    status: str
    notification_bid: str = ""
    notification_type: str = ""
    creator_bid: str = ""
    source_type: str = ""
    source_bid: str = ""
    dedupe_key: str = ""
    enqueued: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "notification_bid": self.notification_bid or None,
            "notification_type": self.notification_type or None,
            "creator_bid": self.creator_bid or None,
            "source_type": self.source_type or None,
            "source_bid": self.source_bid or None,
            "dedupe_key": self.dedupe_key or None,
            "enqueued": self.enqueued,
        }


def _deep_merge(defaults: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_positive_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _normalize_positive_int(value: Any, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise_param_error(field_name)
    if parsed <= 0:
        raise_param_error(field_name)
    return parsed


def _decimal_from_policy(value: Any, default: Decimal = _ZERO) -> Decimal:
    try:
        parsed = _quantize_credit_amount(Decimal(str(value or "0").strip()))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        return default
    return parsed if parsed.is_finite() else default


def _normalize_policy_decimal(value: Any, field_name: str) -> Decimal:
    try:
        parsed = _quantize_credit_amount(Decimal(str(value or "0").strip()))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        raise_param_error(field_name)
    if not parsed.is_finite():
        raise_param_error(field_name)
    return parsed


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise_param_error(field_name)


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise_param_error(field_name)
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _validate_hhmm(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    parts = normalized.split(":")
    if len(parts) != 2:
        raise_param_error(field_name)
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except (TypeError, ValueError):
        raise_param_error(field_name)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise_param_error(field_name)
    return f"{hour:02d}:{minute:02d}"


def _normalize_fixed_thresholds(value: Any, field_name: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise_param_error(field_name)
    thresholds: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise_param_error(field_name)
        kind = str(item.get("kind") or "fixed").strip()
        if kind != LOW_BALANCE_THRESHOLD_KIND_FIXED:
            raise_param_error(field_name)
        amount = _normalize_policy_decimal(item.get("value"), field_name)
        thresholds.append(
            {"kind": LOW_BALANCE_THRESHOLD_KIND_FIXED, "value": str(amount)}
        )
    return thresholds


def _normalize_low_balance_thresholds(
    value: Any, field_name: str
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise_param_error(field_name)
    thresholds: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise_param_error(field_name)
        kind = str(item.get("kind") or LOW_BALANCE_THRESHOLD_KIND_FIXED).strip()
        if kind == LOW_BALANCE_THRESHOLD_KIND_FIXED:
            amount = _normalize_policy_decimal(
                item.get("value"),
                f"{field_name}.value",
            )
            thresholds.append(
                {"kind": LOW_BALANCE_THRESHOLD_KIND_FIXED, "value": str(amount)}
            )
            continue
        if kind == LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS:
            days = _normalize_positive_int(
                item.get("days"),
                f"{field_name}.days",
            )
            lookback_days = _normalize_positive_int(
                item.get("lookback_days"),
                f"{field_name}.lookback_days",
            )
            min_consumed_days = _normalize_positive_int(
                item.get("min_consumed_days"),
                f"{field_name}.min_consumed_days",
            )
            if days > LOW_BALANCE_ESTIMATED_DAYS_MAX_DAYS:
                raise_param_error(f"{field_name}.days")
            if lookback_days > LOW_BALANCE_ESTIMATED_DAYS_MAX_LOOKBACK_DAYS:
                raise_param_error(f"{field_name}.lookback_days")
            if min_consumed_days > lookback_days:
                raise_param_error(f"{field_name}.min_consumed_days")
            threshold: dict[str, Any] = {
                "kind": LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS,
                "days": days,
                "lookback_days": lookback_days,
                "min_consumed_days": min_consumed_days,
            }
            if "fallback_fixed_value" in item:
                raw_value = item.get("fallback_fixed_value")
                raw_fallback = "" if raw_value is None else str(raw_value).strip()
                if raw_fallback:
                    threshold["fallback_fixed_value"] = str(
                        _normalize_policy_decimal(
                            raw_fallback,
                            f"{field_name}.fallback_fixed_value",
                        )
                    )
                else:
                    threshold["fallback_fixed_value"] = ""
            thresholds.append(threshold)
            continue
        raise_param_error(field_name)
    return thresholds


def _validate_policy_for_save(payload: dict[str, Any]) -> dict[str, Any]:
    policy = _deep_merge(DEFAULT_CREDIT_NOTIFICATION_SMS_CONFIG, payload)
    channel = str(policy.get("channel") or CREDIT_NOTIFICATION_CHANNEL_SMS).strip()
    if channel != CREDIT_NOTIFICATION_CHANNEL_SMS:
        raise_param_error("channel")
    policy["channel"] = CREDIT_NOTIFICATION_CHANNEL_SMS
    policy["enabled"] = _coerce_bool(policy.get("enabled"))

    type_policies = _require_mapping(policy.get("types"), "types")
    for notification_type in (
        CREDIT_NOTIFICATION_TYPE_EXPIRING,
        CREDIT_NOTIFICATION_TYPE_GRANTED,
        CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
    ):
        current = _require_mapping(
            type_policies.get(notification_type),
            f"types.{notification_type}",
        )
        current["enabled"] = _coerce_bool(current.get("enabled"))
        current["template_code"] = str(current.get("template_code") or "").strip()
        if current["enabled"] and policy["enabled"] and not current["template_code"]:
            raise_param_error(f"types.{notification_type}.template_code")

    expiring = type_policies[CREDIT_NOTIFICATION_TYPE_EXPIRING]
    windows = _normalize_string_list(
        expiring.get("windows"),
        "types.credit_expiring.windows",
    )
    for window in windows:
        if _parse_window_days(window) is None:
            raise_param_error("types.credit_expiring.windows")
    expiring["windows"] = windows

    low_balance = type_policies[CREDIT_NOTIFICATION_TYPE_LOW_BALANCE]
    low_balance["thresholds"] = _normalize_low_balance_thresholds(
        low_balance.get("thresholds"),
        "types.low_balance.thresholds",
    )

    softlimit = _require_mapping(policy.get("softlimit"), "softlimit")
    softlimit["enabled"] = _coerce_bool(softlimit.get("enabled"))
    softlimit["disable_debug"] = _coerce_bool(softlimit.get("disable_debug", True))
    softlimit["teacher_page_alert"] = _coerce_bool(
        softlimit.get("teacher_page_alert", True)
    )
    softlimit["sms_enabled"] = _coerce_bool(softlimit.get("sms_enabled", False))
    softlimit_threshold = _require_mapping(
        softlimit.get("threshold"),
        "softlimit.threshold",
    )
    softlimit["threshold"] = _normalize_fixed_thresholds(
        [softlimit_threshold],
        "softlimit.threshold",
    )[0]

    for list_group in ("blacklist", "opt_out"):
        current = _require_mapping(policy.get(list_group), list_group)
        current["creator_bids"] = _normalize_string_list(
            current.get("creator_bids"),
            f"{list_group}.creator_bids",
        )
        current["mobiles"] = _normalize_string_list(
            current.get("mobiles"),
            f"{list_group}.mobiles",
        )

    frequency = _require_mapping(policy.get("frequency"), "frequency")
    frequency["per_mobile_per_day"] = _coerce_positive_int(
        frequency.get("per_mobile_per_day"),
        0,
    )
    frequency["per_creator_per_type_per_day"] = _coerce_positive_int(
        frequency.get("per_creator_per_type_per_day"),
        0,
    )

    quiet_hours = _require_mapping(policy.get("quiet_hours"), "quiet_hours")
    quiet_hours["enabled"] = _coerce_bool(quiet_hours.get("enabled"))
    quiet_hours["start"] = _validate_hhmm(quiet_hours.get("start"), "quiet_hours.start")
    quiet_hours["end"] = _validate_hhmm(quiet_hours.get("end"), "quiet_hours.end")
    quiet_hours["timezone"] = str(
        quiet_hours.get("timezone") or "Asia/Shanghai"
    ).strip()

    budget = _require_mapping(policy.get("budget"), "budget")
    budget["daily_sms_limit"] = _coerce_positive_int(budget.get("daily_sms_limit"), 0)
    budget["dry_run_required"] = _coerce_bool(budget.get("dry_run_required", True))
    budget["sms_unit_cost"] = str(
        _decimal_from_policy(budget.get("sms_unit_cost"), _ZERO)
    )
    return policy


def load_credit_notification_policy() -> dict[str, Any]:
    try:
        raw_config = get_config(BILL_CONFIG_KEY_CREDIT_NOTIFICATION_SMS_CONFIG, "")
    except KeyError:
        raw_config = ""
    parsed: dict[str, Any] = {}
    if raw_config:
        try:
            candidate = json.loads(str(raw_config))
        except (TypeError, ValueError):
            candidate = {}
        if isinstance(candidate, dict):
            parsed = candidate
    policy = _deep_merge(DEFAULT_CREDIT_NOTIFICATION_SMS_CONFIG, parsed)
    policy["enabled"] = _coerce_bool(policy.get("enabled"))
    policy["channel"] = CREDIT_NOTIFICATION_CHANNEL_SMS
    type_policies = policy.get("types")
    if not isinstance(type_policies, dict):
        type_policies = {}
        policy["types"] = type_policies
    for notification_type in (
        CREDIT_NOTIFICATION_TYPE_EXPIRING,
        CREDIT_NOTIFICATION_TYPE_GRANTED,
        CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
    ):
        current = type_policies.get(notification_type)
        if not isinstance(current, dict):
            current = {}
            type_policies[notification_type] = current
        current["enabled"] = _coerce_bool(current.get("enabled"))
        current["template_code"] = str(current.get("template_code") or "").strip()
    return policy


def save_credit_notification_policy(
    app: Flask, payload: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise_param_error("policy")
    policy = _validate_policy_for_save(payload)
    _validate_credit_notification_policy_templates(app, policy)
    serialized = json.dumps(
        policy, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    ok = add_config(
        app,
        BILL_CONFIG_KEY_CREDIT_NOTIFICATION_SMS_CONFIG,
        serialized,
        is_secret=False,
        remark="Credit notification SMS policy config",
    )
    if not ok:
        raise_error("server.common.systemError")
    return load_credit_notification_policy()


def _type_policy(policy: dict[str, Any], notification_type: str) -> dict[str, Any]:
    types = policy.get("types")
    if not isinstance(types, dict):
        return {}
    item = types.get(notification_type)
    return item if isinstance(item, dict) else {}


def _notification_type_enabled(policy: dict[str, Any], notification_type: str) -> bool:
    return _coerce_bool(policy.get("enabled")) and _coerce_bool(
        _type_policy(policy, notification_type).get("enabled")
    )


def _template_code(policy: dict[str, Any], notification_type: str) -> str:
    return str(
        _type_policy(policy, notification_type).get("template_code") or ""
    ).strip()


def _supported_template_placeholders(notification_type: str) -> set[str]:
    placeholders = CREDIT_NOTIFICATION_TEMPLATE_PLACEHOLDERS.get(notification_type)
    if placeholders is None:
        raise_param_error("notification_type")
    return set(placeholders)


def _extract_template_placeholders(template_content: Any) -> list[str]:
    content = str(template_content or "")
    return sorted(set(_TEMPLATE_PLACEHOLDER_PATTERN.findall(content)))


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value or "")
    return value


def _aliyun_sms_credentials_configured(app: Flask) -> bool:
    return bool(
        str(app.config.get("ALIBABA_CLOUD_SMS_ACCESS_KEY_ID") or "").strip()
        and str(app.config.get("ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET") or "").strip()
    )


def _template_body_value(body: Any, field_name: str) -> str:
    return str(getattr(body, field_name, "") or "").strip()


def _provider_template_response_payload(
    response: Any,
    *,
    requested_template_code: str,
) -> dict[str, Any]:
    body = getattr(response, "body", None)
    if body is None:
        return {"template_code": requested_template_code}
    return {
        "code": _template_body_value(body, "code"),
        "message": _template_body_value(body, "message"),
        "request_id": _template_body_value(body, "request_id"),
        "template_code": requested_template_code,
        "template_status": _template_body_value(body, "template_status"),
        "template_type": _template_body_value(body, "template_type"),
    }


def _load_notification_template(template_code: str) -> NotificationTemplate | None:
    return (
        NotificationTemplate.query.filter(
            NotificationTemplate.deleted == 0,
            NotificationTemplate.channel == CREDIT_NOTIFICATION_CHANNEL_SMS,
            NotificationTemplate.provider == NOTIFICATION_TEMPLATE_PROVIDER_ALIYUN,
            NotificationTemplate.template_code == template_code,
        )
        .order_by(NotificationTemplate.id.desc())
        .first()
    )


def _get_or_create_notification_template(
    app: Flask,
    *,
    template_code: str,
    now: datetime,
) -> NotificationTemplate:
    template = _load_notification_template(template_code)
    if template is not None:
        return template
    template = NotificationTemplate(
        notification_template_bid=generate_id(app),
        channel=CREDIT_NOTIFICATION_CHANNEL_SMS,
        provider=NOTIFICATION_TEMPLATE_PROVIDER_ALIYUN,
        template_code=template_code,
        template_name="",
        template_content="",
        template_status="",
        template_type="",
        variable_attribute_json={},
        provider_response_json={},
        placeholders_json=[],
        sync_status=NOTIFICATION_TEMPLATE_SYNC_STATUS_FAILED_PROVIDER,
        error_code="",
        error_message="",
        last_synced_at=None,
        metadata_json={},
        deleted=0,
        created_at=now,
        updated_at=now,
    )
    db.session.add(template)
    return template


def _serialize_notification_template(
    template: NotificationTemplate,
    *,
    notification_type: str,
) -> dict[str, Any]:
    supported = sorted(_supported_template_placeholders(notification_type))
    actual = sorted(
        str(item or "").strip()
        for item in (template.placeholders_json or [])
        if str(item or "").strip()
    )
    actual_set = set(actual)
    supported_set = set(supported)
    unsupported = sorted(actual_set - supported_set)
    unused_supported = sorted(supported_set - actual_set)
    sync_status = str(template.sync_status or "").strip()
    return {
        "notification_template_bid": template.notification_template_bid,
        "notification_type": notification_type,
        "channel": template.channel,
        "provider": template.provider,
        "template_code": template.template_code,
        "template_name": template.template_name,
        "template_content": template.template_content or "",
        "template_status": template.template_status,
        "template_type": template.template_type,
        "variable_attribute": template.variable_attribute_json or {},
        "provider_response": template.provider_response_json or {},
        "placeholders": actual,
        "supported_placeholders": supported,
        "unused_supported_placeholders": unused_supported,
        "unsupported_placeholders": unsupported,
        "sync_status": sync_status,
        "error_code": template.error_code,
        "error_message": template.error_message or "",
        "last_synced_at": template.last_synced_at.isoformat()
        if template.last_synced_at
        else "",
        "compatible": sync_status == NOTIFICATION_TEMPLATE_SYNC_STATUS_SYNCED
        and not unsupported,
    }


def _mark_template_sync_failed(
    template: NotificationTemplate,
    *,
    now: datetime,
    sync_status: str,
    error_code: str,
    error_message: str,
    provider_response: dict[str, Any] | None = None,
) -> None:
    template.template_content = template.template_content or ""
    template.placeholders_json = list(template.placeholders_json or [])
    template.provider_response_json = dict(provider_response or {})
    template.sync_status = sync_status
    template.error_code = str(error_code or "").strip()[:128]
    template.error_message = str(error_message or "").strip()
    template.last_synced_at = now
    template.updated_at = now
    db.session.add(template)


def sync_credit_notification_template(
    app: Flask,
    *,
    notification_type: str,
    template_code: str,
) -> dict[str, Any]:
    normalized_type = str(notification_type or "").strip()
    _supported_template_placeholders(normalized_type)
    normalized_template_code = str(template_code or "").strip()
    if not normalized_template_code:
        raise_param_error("template_code")

    with _maybe_app_context(app):
        now = datetime.now()
        template = _get_or_create_notification_template(
            app,
            template_code=normalized_template_code,
            now=now,
        )
        if not _aliyun_sms_credentials_configured(app):
            _mark_template_sync_failed(
                template,
                now=now,
                sync_status=NOTIFICATION_TEMPLATE_SYNC_STATUS_MISSING_CREDENTIALS,
                error_code="missing_credentials",
                error_message="missing_credentials",
            )
            db.session.commit()
            return _serialize_notification_template(
                template,
                notification_type=normalized_type,
            )

        try:
            response = get_sms_template_ali(app, template_code=normalized_template_code)
            body = getattr(response, "body", None)
        except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
            _mark_template_sync_failed(
                template,
                now=now,
                sync_status=NOTIFICATION_TEMPLATE_SYNC_STATUS_FAILED_PROVIDER,
                error_code="provider_exception",
                error_message="provider_exception",
                provider_response={"message": str(exc)},
            )
            db.session.commit()
            return _serialize_notification_template(
                template,
                notification_type=normalized_type,
            )
        if body is None:
            _mark_template_sync_failed(
                template,
                now=now,
                sync_status=NOTIFICATION_TEMPLATE_SYNC_STATUS_FAILED_PROVIDER,
                error_code="provider_failed",
                error_message="provider_failed",
            )
            db.session.commit()
            return _serialize_notification_template(
                template,
                notification_type=normalized_type,
            )

        provider_response = _provider_template_response_payload(
            response,
            requested_template_code=normalized_template_code,
        )
        response_code = _template_body_value(body, "code")
        if response_code and response_code != "OK":
            _mark_template_sync_failed(
                template,
                now=now,
                sync_status=NOTIFICATION_TEMPLATE_SYNC_STATUS_FAILED_PROVIDER,
                error_code=response_code,
                error_message=response_code,
                provider_response=provider_response,
            )
            db.session.commit()
            return _serialize_notification_template(
                template,
                notification_type=normalized_type,
            )

        template_content = _template_body_value(body, "template_content")
        template.template_name = _template_body_value(body, "template_name")
        template.template_content = template_content
        template.template_status = _template_body_value(body, "template_status")
        template.template_type = _template_body_value(body, "template_type")
        template.variable_attribute_json = _json_safe(
            getattr(body, "variable_attribute", {}) or {}
        )
        template.provider_response_json = provider_response
        template.placeholders_json = _extract_template_placeholders(template_content)
        template.sync_status = NOTIFICATION_TEMPLATE_SYNC_STATUS_SYNCED
        template.error_code = ""
        template.error_message = ""
        template.last_synced_at = now
        template.updated_at = now
        db.session.add(template)
        db.session.commit()
        return _serialize_notification_template(
            template,
            notification_type=normalized_type,
        )


def _ensure_credit_notification_template_compatible(
    app: Flask,
    *,
    notification_type: str,
    template_code: str,
) -> dict[str, Any]:
    with _maybe_app_context(app):
        template = _load_notification_template(template_code)
        if (
            template is not None
            and template.sync_status == NOTIFICATION_TEMPLATE_SYNC_STATUS_SYNCED
        ):
            return _serialize_notification_template(
                template,
                notification_type=notification_type,
            )
    return sync_credit_notification_template(
        app,
        notification_type=notification_type,
        template_code=template_code,
    )


def _validate_credit_notification_policy_templates(
    app: Flask, policy: dict[str, Any]
) -> None:
    if not _coerce_bool(policy.get("enabled")):
        return
    for notification_type in (
        CREDIT_NOTIFICATION_TYPE_EXPIRING,
        CREDIT_NOTIFICATION_TYPE_GRANTED,
        CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
    ):
        if not _notification_type_enabled(policy, notification_type):
            continue
        template_code = _template_code(policy, notification_type)
        if not template_code:
            continue
        result = _ensure_credit_notification_template_compatible(
            app,
            notification_type=notification_type,
            template_code=template_code,
        )
        if result.get("sync_status") != NOTIFICATION_TEMPLATE_SYNC_STATUS_SYNCED:
            error_code = str(result.get("error_code") or "sync_failed")
            raise_param_error(f"types.{notification_type}.template_code:{error_code}")
        unsupported = [
            str(item or "").strip()
            for item in result.get("unsupported_placeholders", [])
            if str(item or "").strip()
        ]
        if unsupported:
            raise_param_error(
                "types."
                f"{notification_type}.template_code unsupported placeholders: "
                f"{','.join(sorted(unsupported))}"
            )


def _estimated_sms_cost(policy: dict[str, Any], count: int) -> str:
    budget = policy.get("budget")
    unit_cost = _ZERO
    if isinstance(budget, dict):
        unit_cost = _decimal_from_policy(budget.get("sms_unit_cost"), _ZERO)
    return str(_quantize_credit_amount(unit_cost * max(0, int(count or 0))))


def build_credit_granted_dedupe_key(ledger_bid: str) -> str:
    return f"{CREDIT_NOTIFICATION_TYPE_GRANTED}:{_normalize_bid(ledger_bid)}"


def build_credit_expiring_dedupe_key(wallet_bucket_bid: str, window: str) -> str:
    return f"{CREDIT_NOTIFICATION_TYPE_EXPIRING}:{_normalize_bid(wallet_bucket_bid)}:{_normalize_bid(window)}"


def build_low_balance_dedupe_key(creator_bid: str, threshold: str, day: date) -> str:
    return (
        f"{CREDIT_NOTIFICATION_TYPE_LOW_BALANCE}:"
        f"{_normalize_bid(creator_bid)}:{str(threshold or '').strip()}:{day.isoformat()}"
    )


def build_low_balance_estimated_days_dedupe_key(
    creator_bid: str,
    *,
    days: int,
    lookback_days: int,
    day: date,
) -> str:
    return (
        f"{CREDIT_NOTIFICATION_TYPE_LOW_BALANCE}:"
        f"{_normalize_bid(creator_bid)}:estimated_days:{int(days)}:"
        f"lookback:{int(lookback_days)}:{day.isoformat()}"
    )


def _provider_response_payload(response: Any) -> dict[str, Any]:
    body = getattr(response, "body", None)
    if body is None:
        return {}
    return {
        "code": str(getattr(body, "code", "") or "").strip(),
        "message": str(getattr(body, "message", "") or "").strip(),
        "request_id": str(getattr(body, "request_id", "") or "").strip(),
        "biz_id": str(getattr(body, "biz_id", "") or "").strip(),
    }


def _serialize_dt(app: Flask, value: datetime | None) -> str:
    if value is None:
        return ""
    return str(serialize_with_app_timezone(app, value) or "")


def _amount_text(value: Any) -> str:
    try:
        return str(_quantize_credit_amount(value))
    except Exception:
        return str(value or "").strip()


def _is_valid_sms_mobile(mobile: str) -> bool:
    normalized = str(mobile or "").strip()
    if normalized.startswith("+"):
        normalized = normalized[1:]
    return normalized.isdigit() and 5 <= len(normalized) <= 20


def _is_notification_eligible_creator(creator_bid: str) -> bool:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return False
    creator = (
        UserEntity.query.filter(
            UserEntity.user_bid == normalized_creator_bid,
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.desc())
        .first()
    )
    if creator is None:
        return False
    if not bool(creator.is_creator):
        return False
    return int(creator.state or USER_STATE_UNREGISTERED) != USER_STATE_UNREGISTERED


def _is_notification_eligible_creator_cached(
    creator_bid: str,
    cache: dict[str, bool],
) -> bool:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid:
        return False
    if normalized_creator_bid not in cache:
        cache[normalized_creator_bid] = _is_notification_eligible_creator(
            normalized_creator_bid
        )
    return cache[normalized_creator_bid]


def _stage_notification_record(
    app: Flask,
    *,
    notification_type: str,
    creator_bid: str,
    source_type: str,
    source_bid: str,
    dedupe_key: str,
    template_params: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> CreditNotificationStageResult:
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_source_bid = _normalize_bid(source_bid)
    normalized_dedupe_key = str(dedupe_key or "").strip()
    if (
        not normalized_creator_bid
        or not normalized_source_bid
        or not normalized_dedupe_key
    ):
        return CreditNotificationStageResult(
            status="invalid",
            notification_type=notification_type,
            creator_bid=normalized_creator_bid,
            source_type=source_type,
            source_bid=normalized_source_bid,
            dedupe_key=normalized_dedupe_key,
        )

    resolved_policy = policy or load_credit_notification_policy()
    if not _notification_type_enabled(resolved_policy, notification_type):
        return CreditNotificationStageResult(
            status="noop_disabled",
            notification_type=notification_type,
            creator_bid=normalized_creator_bid,
            source_type=source_type,
            source_bid=normalized_source_bid,
            dedupe_key=normalized_dedupe_key,
        )
    if not _is_notification_eligible_creator(normalized_creator_bid):
        record_credit_notification_event(
            "stage",
            notification_type=notification_type,
            channel=CREDIT_NOTIFICATION_CHANNEL_SMS,
            status="skipped_ineligible_creator",
        )
        return CreditNotificationStageResult(
            status="skipped_ineligible_creator",
            notification_type=notification_type,
            creator_bid=normalized_creator_bid,
            source_type=source_type,
            source_bid=normalized_source_bid,
            dedupe_key=normalized_dedupe_key,
        )

    existing = (
        NotificationRecord.query.filter(
            NotificationRecord.deleted == 0,
            NotificationRecord.dedupe_key == normalized_dedupe_key,
        )
        .order_by(NotificationRecord.id.desc())
        .first()
    )
    if existing is not None:
        record_credit_notification_event(
            "stage",
            notification_type=existing.notification_type,
            channel=existing.channel,
            status="suppressed_duplicate",
        )
        return CreditNotificationStageResult(
            status="suppressed_duplicate",
            notification_bid=existing.notification_bid,
            notification_type=existing.notification_type,
            creator_bid=existing.creator_bid,
            source_type=existing.source_type,
            source_bid=existing.source_bid,
            dedupe_key=existing.dedupe_key,
        )

    now = datetime.now()
    mobile = load_creator_mobile_snapshot(normalized_creator_bid)
    notification_status = CREDIT_NOTIFICATION_STATUS_PENDING
    error_code = ""
    error_message = ""
    attempted_at = None
    if not mobile:
        notification_status = CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE
        error_code = "missing_mobile"
        error_message = "Creator mobile is empty."
        attempted_at = now
    elif not _is_valid_sms_mobile(mobile):
        notification_status = CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE
        error_code = "invalid_mobile"
        error_message = "Creator mobile is invalid."
        attempted_at = now
    notification = NotificationRecord(
        notification_bid=generate_id(app),
        notification_type=notification_type,
        channel=CREDIT_NOTIFICATION_CHANNEL_SMS,
        creator_bid=normalized_creator_bid,
        target_user_bid=normalized_creator_bid,
        mobile_snapshot=mobile,
        source_type=source_type,
        source_bid=normalized_source_bid,
        dedupe_key=normalized_dedupe_key,
        status=notification_status,
        template_code=_template_code(resolved_policy, notification_type),
        template_params_json={
            key: str(value or "").strip() for key, value in template_params.items()
        },
        policy_snapshot_json=resolved_policy,
        provider_response_json={},
        error_code=error_code,
        error_message=error_message,
        requested_at=now,
        attempted_at=attempted_at,
        metadata_json=dict(metadata or {}),
    )
    try:
        with db.session.begin_nested():
            db.session.add(notification)
            db.session.flush()
    except IntegrityError:
        existing = (
            NotificationRecord.query.filter(
                NotificationRecord.deleted == 0,
                NotificationRecord.dedupe_key == normalized_dedupe_key,
            )
            .order_by(NotificationRecord.id.desc())
            .first()
        )
        if existing is not None:
            record_credit_notification_event(
                "stage",
                notification_type=existing.notification_type,
                channel=existing.channel,
                status="suppressed_duplicate",
            )
            return CreditNotificationStageResult(
                status="suppressed_duplicate",
                notification_bid=existing.notification_bid,
                notification_type=existing.notification_type,
                creator_bid=existing.creator_bid,
                source_type=existing.source_type,
                source_bid=existing.source_bid,
                dedupe_key=existing.dedupe_key,
            )
        raise
    record_credit_notification_event(
        "stage",
        notification_type=notification.notification_type,
        channel=notification.channel,
        status=notification.status,
    )
    return CreditNotificationStageResult(
        status=notification.status,
        notification_bid=notification.notification_bid,
        notification_type=notification.notification_type,
        creator_bid=notification.creator_bid,
        source_type=notification.source_type,
        source_bid=notification.source_bid,
        dedupe_key=notification.dedupe_key,
    )


def stage_credit_granted_notification(
    app: Flask,
    *,
    ledger_bid: str,
    commit: bool = True,
    enqueue: bool = True,
) -> dict[str, Any]:
    normalized_ledger_bid = _normalize_bid(ledger_bid)
    if not normalized_ledger_bid:
        return CreditNotificationStageResult(status="invalid_ledger_bid").to_payload()
    with _maybe_app_context(app):
        ledger = (
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.ledger_bid == normalized_ledger_bid,
            )
            .order_by(CreditLedgerEntry.id.desc())
            .first()
        )
        if ledger is None:
            return CreditNotificationStageResult(status="not_found").to_payload()
        result = _stage_notification_record(
            app,
            notification_type=CREDIT_NOTIFICATION_TYPE_GRANTED,
            creator_bid=ledger.creator_bid,
            source_type=SOURCE_TYPE_LEDGER,
            source_bid=ledger.ledger_bid,
            dedupe_key=build_credit_granted_dedupe_key(ledger.ledger_bid),
            template_params={
                "credits": _amount_text(ledger.amount),
                "source": str(
                    (ledger.metadata_json or {}).get("grant_source")
                    or ledger.source_type
                ),
                "expires_at": _serialize_dt(app, ledger.expires_at),
            },
            metadata={
                "wallet_bucket_bid": ledger.wallet_bucket_bid,
                "ledger_bid": ledger.ledger_bid,
            },
        )
        if commit:
            db.session.commit()
        payload = result.to_payload()
    if enqueue:
        if payload.get("status") == CREDIT_NOTIFICATION_STATUS_PENDING:
            enqueue_result = enqueue_credit_notification(
                app,
                notification_bid=str(payload.get("notification_bid") or ""),
            )
            payload["enqueued"] = bool(enqueue_result.get("enqueued"))
        else:
            payload["enqueued"] = False
    return payload


def stage_credit_granted_notification_for_order(
    app: Flask,
    *,
    creator_bid: str,
    bill_order_bid: str,
    commit: bool = False,
    enqueue: bool = False,
) -> dict[str, Any]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_creator_bid or not normalized_bill_order_bid:
        return CreditNotificationStageResult(status="invalid_order").to_payload()
    with _maybe_app_context(app):
        ledger = (
            CreditLedgerEntry.query.filter(
                CreditLedgerEntry.deleted == 0,
                CreditLedgerEntry.creator_bid == normalized_creator_bid,
                CreditLedgerEntry.idempotency_key
                == f"grant:{normalized_bill_order_bid}",
            )
            .order_by(CreditLedgerEntry.id.desc())
            .first()
        )
        if ledger is None:
            return CreditNotificationStageResult(status="not_found").to_payload()
        ledger_bid = str(ledger.ledger_bid or "").strip()
    return stage_credit_granted_notification(
        app,
        ledger_bid=ledger_bid,
        commit=commit,
        enqueue=enqueue,
    )


def _parse_window_days(window: Any) -> int | None:
    normalized = str(window or "").strip().lower()
    if not normalized.endswith("d"):
        return None
    try:
        days = int(normalized[:-1])
    except (TypeError, ValueError):
        return None
    return days if days >= 0 else None


def scan_credit_expiring_notifications(
    app: Flask,
    *,
    now: datetime | None = None,
    creator_bid: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    scan_now = now or datetime.now()
    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        policy = load_credit_notification_policy()
        if not _notification_type_enabled(policy, CREDIT_NOTIFICATION_TYPE_EXPIRING):
            return {
                "status": "noop_disabled",
                "candidate_count": 0,
                "created_count": 0,
                "estimated_sms_cost": "0",
                "dry_run": dry_run,
                "notifications": [],
            }
        windows = _type_policy(policy, CREDIT_NOTIFICATION_TYPE_EXPIRING).get("windows")
        if not isinstance(windows, list):
            windows = ["7d", "3d", "1d", "0d"]

        notifications: list[dict[str, Any]] = []
        creator_eligibility_cache: dict[str, bool] = {}
        for raw_window in windows:
            window = str(raw_window or "").strip()
            days = _parse_window_days(window)
            if days is None:
                continue
            window_start = scan_now + timedelta(days=days)
            window_end = scan_now + timedelta(days=days + 1)
            query = CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.status == CREDIT_BUCKET_STATUS_ACTIVE,
                CreditWalletBucket.effective_to.isnot(None),
                CreditWalletBucket.effective_to > window_start,
                CreditWalletBucket.effective_to <= window_end,
                CreditWalletBucket.available_credits > _ZERO,
            )
            if normalized_creator_bid:
                query = query.filter(
                    CreditWalletBucket.creator_bid == normalized_creator_bid
                )
            buckets = (
                query.order_by(
                    CreditWalletBucket.effective_to.asc(),
                    CreditWalletBucket.id.asc(),
                )
                .limit(500)
                .all()
            )
            for bucket in buckets:
                if not _is_notification_eligible_creator_cached(
                    bucket.creator_bid,
                    creator_eligibility_cache,
                ):
                    continue
                dedupe_key = build_credit_expiring_dedupe_key(
                    bucket.wallet_bucket_bid,
                    window,
                )
                if dry_run:
                    notifications.append(
                        {
                            "status": "candidate",
                            "notification_type": CREDIT_NOTIFICATION_TYPE_EXPIRING,
                            "creator_bid": bucket.creator_bid,
                            "source_bid": bucket.wallet_bucket_bid,
                            "dedupe_key": dedupe_key,
                        }
                    )
                    continue
                result = _stage_notification_record(
                    app,
                    notification_type=CREDIT_NOTIFICATION_TYPE_EXPIRING,
                    creator_bid=bucket.creator_bid,
                    source_type=SOURCE_TYPE_WALLET_BUCKET,
                    source_bid=bucket.wallet_bucket_bid,
                    dedupe_key=dedupe_key,
                    template_params={
                        "credits": _amount_text(bucket.available_credits),
                        "expires_at": _serialize_dt(app, bucket.effective_to),
                        "window": window,
                    },
                    metadata={
                        "wallet_bid": bucket.wallet_bid,
                        "wallet_bucket_bid": bucket.wallet_bucket_bid,
                        "window": window,
                    },
                    policy=policy,
                )
                notifications.append(result.to_payload())
        if not dry_run:
            db.session.commit()
    enqueued_count = 0
    if not dry_run:
        for item in notifications:
            if item.get("status") != "pending":
                continue
            enqueue_result = enqueue_credit_notification(
                app,
                notification_bid=str(item.get("notification_bid") or ""),
            )
            item["enqueued"] = bool(enqueue_result.get("enqueued"))
            enqueued_count += int(bool(enqueue_result.get("enqueued")))
    candidate_count = sum(
        1
        for item in notifications
        if item.get("status")
        in {
            "candidate",
            CREDIT_NOTIFICATION_STATUS_PENDING,
            "suppressed_duplicate",
        }
    )
    return {
        "status": "created" if candidate_count else "noop",
        "candidate_count": candidate_count,
        "created_count": sum(
            1
            for item in notifications
            if item.get("status") == CREDIT_NOTIFICATION_STATUS_PENDING
        ),
        "enqueued_count": enqueued_count,
        "estimated_sms_cost": _estimated_sms_cost(policy, len(notifications))
        if dry_run
        else "0",
        "dry_run": dry_run,
        "notifications": notifications,
    }


def _load_low_balance_thresholds(policy: dict[str, Any]) -> list[dict[str, Any]]:
    thresholds = _type_policy(policy, CREDIT_NOTIFICATION_TYPE_LOW_BALANCE).get(
        "thresholds"
    )
    if not isinstance(thresholds, list):
        thresholds = [{"kind": LOW_BALANCE_THRESHOLD_KIND_FIXED, "value": "0"}]
    values: list[dict[str, Any]] = []
    for item in thresholds:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or LOW_BALANCE_THRESHOLD_KIND_FIXED).strip()
        if kind == LOW_BALANCE_THRESHOLD_KIND_FIXED:
            values.append(
                {
                    "kind": LOW_BALANCE_THRESHOLD_KIND_FIXED,
                    "value": str(_decimal_from_policy(item.get("value"), _ZERO)),
                }
            )
            continue
        if kind != LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS:
            continue
        days = _coerce_positive_int(item.get("days"), 0)
        lookback_days = _coerce_positive_int(item.get("lookback_days"), 0)
        min_consumed_days = _coerce_positive_int(item.get("min_consumed_days"), 0)
        if days <= 0 or lookback_days <= 0 or min_consumed_days <= 0:
            continue
        threshold: dict[str, Any] = {
            "kind": LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS,
            "days": days,
            "lookback_days": lookback_days,
            "min_consumed_days": min_consumed_days,
        }
        fallback_value = item.get("fallback_fixed_value")
        if fallback_value is not None and str(fallback_value).strip():
            threshold["fallback_fixed_value"] = str(
                _decimal_from_policy(fallback_value, _ZERO)
            )
        values.append(threshold)
    return values or [{"kind": LOW_BALANCE_THRESHOLD_KIND_FIXED, "value": str(_ZERO)}]


def _load_creator_daily_consumption_stats(
    *,
    creator_bid: str,
    scan_day: date,
    lookback_days: int,
) -> dict[str, Any]:
    start_day = scan_day - timedelta(days=lookback_days)
    rows = (
        BillingDailyLedgerSummary.query.filter(
            BillingDailyLedgerSummary.deleted == 0,
            BillingDailyLedgerSummary.creator_bid == creator_bid,
            BillingDailyLedgerSummary.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            BillingDailyLedgerSummary.stat_date >= start_day.isoformat(),
            BillingDailyLedgerSummary.stat_date < scan_day.isoformat(),
        )
        .order_by(BillingDailyLedgerSummary.stat_date.asc())
        .all()
    )
    daily_totals: dict[str, Decimal] = {}
    for row in rows:
        amount = abs(_to_decimal(row.amount))
        if amount <= _ZERO:
            continue
        stat_date = str(row.stat_date or "").strip()
        daily_totals[stat_date] = daily_totals.get(stat_date, _ZERO) + amount
    consumed_days = len(daily_totals)
    total_consumed = sum(daily_totals.values(), start=_ZERO)
    avg_daily_consumption = (
        _quantize_credit_amount(total_consumed / Decimal(consumed_days))
        if consumed_days > 0
        else _ZERO
    )
    return {
        "lookback_days": int(lookback_days),
        "consumed_days": consumed_days,
        "total_consumed": _quantize_credit_amount(total_consumed),
        "avg_daily_consumption": avg_daily_consumption,
    }


def _low_balance_template_params(
    *,
    available: Decimal,
    threshold_kind: str,
    threshold: str = "",
    trigger_days: int | None = None,
    lookback_days: int | None = None,
    avg_daily_consumption: Decimal | None = None,
    estimated_remaining_days: Decimal | None = None,
) -> dict[str, Any]:
    return {
        "available_credits": _amount_text(available),
        "threshold": str(threshold or "").strip(),
        "threshold_kind": str(threshold_kind or "").strip(),
        "trigger_days": str(trigger_days or ""),
        "lookback_days": str(lookback_days or ""),
        "avg_daily_consumption": (
            _amount_text(avg_daily_consumption)
            if avg_daily_consumption is not None
            else ""
        ),
        "estimated_remaining_days": (
            _amount_text(estimated_remaining_days)
            if estimated_remaining_days is not None
            else ""
        ),
    }


def _low_balance_dry_run_payload(
    *,
    status: str,
    creator_bid: str,
    source_bid: str,
    dedupe_key: str,
    template_params: dict[str, Any],
    reason: str = "",
) -> dict[str, Any]:
    payload = {
        "status": status,
        "notification_type": CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
        "creator_bid": creator_bid,
        "source_bid": source_bid,
        "dedupe_key": dedupe_key,
        **template_params,
    }
    if reason:
        payload["reason"] = reason
    return payload


def scan_low_balance_notifications(
    app: Flask,
    *,
    now: datetime | None = None,
    creator_bid: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    scan_now = now or datetime.now()
    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        policy = load_credit_notification_policy()
        if not _notification_type_enabled(policy, CREDIT_NOTIFICATION_TYPE_LOW_BALANCE):
            return {
                "status": "noop_disabled",
                "candidate_count": 0,
                "created_count": 0,
                "estimated_sms_cost": "0",
                "dry_run": dry_run,
                "notifications": [],
            }
        thresholds = _load_low_balance_thresholds(policy)
        query = CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid != "",
        )
        if normalized_creator_bid:
            query = query.filter(CreditWallet.creator_bid == normalized_creator_bid)
        wallets = query.order_by(CreditWallet.id.asc()).limit(1000).all()
        notifications: list[dict[str, Any]] = []
        daily_consumption_cache: dict[tuple[str, int], dict[str, Any]] = {}
        creator_eligibility_cache: dict[str, bool] = {}
        for wallet in wallets:
            if not _is_notification_eligible_creator_cached(
                wallet.creator_bid,
                creator_eligibility_cache,
            ):
                continue
            available = _to_decimal(wallet.available_credits)
            for threshold in thresholds:
                kind = str(
                    threshold.get("kind") or LOW_BALANCE_THRESHOLD_KIND_FIXED
                ).strip()
                threshold_key = ""
                dedupe_key = ""
                template_params: dict[str, Any] = {}
                metadata: dict[str, Any] = {"wallet_bid": wallet.wallet_bid}

                if kind == LOW_BALANCE_THRESHOLD_KIND_FIXED:
                    threshold_value = _decimal_from_policy(
                        threshold.get("value"),
                        _ZERO,
                    )
                    if available > threshold_value:
                        continue
                    threshold_key = str(threshold_value)
                    dedupe_key = build_low_balance_dedupe_key(
                        wallet.creator_bid,
                        threshold_key,
                        scan_now.date(),
                    )
                    template_params = _low_balance_template_params(
                        available=available,
                        threshold_kind=LOW_BALANCE_THRESHOLD_KIND_FIXED,
                        threshold=threshold_key,
                    )
                    metadata["threshold_kind"] = LOW_BALANCE_THRESHOLD_KIND_FIXED

                elif kind == LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS:
                    days = _coerce_positive_int(threshold.get("days"), 0)
                    lookback_days = _coerce_positive_int(
                        threshold.get("lookback_days"),
                        0,
                    )
                    min_consumed_days = _coerce_positive_int(
                        threshold.get("min_consumed_days"),
                        0,
                    )
                    if days <= 0 or lookback_days <= 0 or min_consumed_days <= 0:
                        continue
                    cache_key = (wallet.creator_bid, lookback_days)
                    stats = daily_consumption_cache.get(cache_key)
                    if stats is None:
                        stats = _load_creator_daily_consumption_stats(
                            creator_bid=wallet.creator_bid,
                            scan_day=scan_now.date(),
                            lookback_days=lookback_days,
                        )
                        daily_consumption_cache[cache_key] = stats
                    avg_daily_consumption = _to_decimal(
                        stats.get("avg_daily_consumption")
                    )
                    consumed_days = int(stats.get("consumed_days") or 0)
                    fallback_value = threshold.get("fallback_fixed_value")
                    has_fallback = (
                        fallback_value is not None and str(fallback_value).strip()
                    )
                    if consumed_days <= 0 or avg_daily_consumption <= _ZERO:
                        if dry_run:
                            notifications.append(
                                _low_balance_dry_run_payload(
                                    status="skipped",
                                    creator_bid=wallet.creator_bid,
                                    source_bid=wallet.creator_bid,
                                    dedupe_key=build_low_balance_estimated_days_dedupe_key(
                                        wallet.creator_bid,
                                        days=days,
                                        lookback_days=lookback_days,
                                        day=scan_now.date(),
                                    ),
                                    template_params=_low_balance_template_params(
                                        available=available,
                                        threshold_kind=(
                                            LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS
                                        ),
                                        trigger_days=days,
                                        lookback_days=lookback_days,
                                    ),
                                    reason="missing_daily_consumption_summary",
                                )
                            )
                        continue
                    if consumed_days < min_consumed_days:
                        if has_fallback:
                            fallback_threshold = _decimal_from_policy(
                                fallback_value,
                                _ZERO,
                            )
                            if available <= fallback_threshold:
                                threshold_key = str(fallback_threshold)
                                dedupe_key = build_low_balance_dedupe_key(
                                    wallet.creator_bid,
                                    threshold_key,
                                    scan_now.date(),
                                )
                                template_params = _low_balance_template_params(
                                    available=available,
                                    threshold_kind=LOW_BALANCE_THRESHOLD_KIND_FIXED,
                                    threshold=threshold_key,
                                )
                                metadata.update(
                                    {
                                        "threshold_kind": (
                                            LOW_BALANCE_THRESHOLD_KIND_FIXED
                                        ),
                                        "fallback_from": (
                                            LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS
                                        ),
                                        "lookback_days": lookback_days,
                                        "consumed_days": consumed_days,
                                    }
                                )
                            elif dry_run:
                                notifications.append(
                                    _low_balance_dry_run_payload(
                                        status="skipped",
                                        creator_bid=wallet.creator_bid,
                                        source_bid=wallet.creator_bid,
                                        dedupe_key=build_low_balance_dedupe_key(
                                            wallet.creator_bid,
                                            str(fallback_threshold),
                                            scan_now.date(),
                                        ),
                                        template_params=_low_balance_template_params(
                                            available=available,
                                            threshold_kind=(
                                                LOW_BALANCE_THRESHOLD_KIND_FIXED
                                            ),
                                            threshold=str(fallback_threshold),
                                        ),
                                        reason=(
                                            "insufficient_consumed_days_"
                                            "fallback_not_reached"
                                        ),
                                    )
                                )
                            if not dedupe_key:
                                continue
                        else:
                            if dry_run:
                                notifications.append(
                                    _low_balance_dry_run_payload(
                                        status="skipped",
                                        creator_bid=wallet.creator_bid,
                                        source_bid=wallet.creator_bid,
                                        dedupe_key=build_low_balance_estimated_days_dedupe_key(
                                            wallet.creator_bid,
                                            days=days,
                                            lookback_days=lookback_days,
                                            day=scan_now.date(),
                                        ),
                                        template_params=_low_balance_template_params(
                                            available=available,
                                            threshold_kind=(
                                                LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS
                                            ),
                                            trigger_days=days,
                                            lookback_days=lookback_days,
                                            avg_daily_consumption=(
                                                avg_daily_consumption
                                            ),
                                        ),
                                        reason="insufficient_consumed_days",
                                    )
                                )
                            continue
                    else:
                        estimated_remaining_days = _quantize_credit_amount(
                            available / avg_daily_consumption
                        )
                        dedupe_key = build_low_balance_estimated_days_dedupe_key(
                            wallet.creator_bid,
                            days=days,
                            lookback_days=lookback_days,
                            day=scan_now.date(),
                        )
                        template_params = _low_balance_template_params(
                            available=available,
                            threshold_kind=LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS,
                            trigger_days=days,
                            lookback_days=lookback_days,
                            avg_daily_consumption=avg_daily_consumption,
                            estimated_remaining_days=estimated_remaining_days,
                        )
                        metadata.update(
                            {
                                "threshold_kind": (
                                    LOW_BALANCE_THRESHOLD_KIND_ESTIMATED_DAYS
                                ),
                                "trigger_days": days,
                                "lookback_days": lookback_days,
                                "min_consumed_days": min_consumed_days,
                                "consumed_days": consumed_days,
                                "avg_daily_consumption": str(avg_daily_consumption),
                                "estimated_remaining_days": str(
                                    estimated_remaining_days
                                ),
                            }
                        )
                        if estimated_remaining_days > Decimal(days):
                            if dry_run:
                                notifications.append(
                                    _low_balance_dry_run_payload(
                                        status="skipped",
                                        creator_bid=wallet.creator_bid,
                                        source_bid=wallet.creator_bid,
                                        dedupe_key=dedupe_key,
                                        template_params=template_params,
                                        reason="remaining_days_above_threshold",
                                    )
                                )
                            continue
                else:
                    continue

                if dry_run:
                    notifications.append(
                        _low_balance_dry_run_payload(
                            status="candidate",
                            creator_bid=wallet.creator_bid,
                            source_bid=wallet.creator_bid,
                            dedupe_key=dedupe_key,
                            template_params=template_params,
                        )
                    )
                    continue
                result = _stage_notification_record(
                    app,
                    notification_type=CREDIT_NOTIFICATION_TYPE_LOW_BALANCE,
                    creator_bid=wallet.creator_bid,
                    source_type=SOURCE_TYPE_WALLET,
                    source_bid=wallet.creator_bid,
                    dedupe_key=dedupe_key,
                    template_params=template_params,
                    metadata=metadata,
                    policy=policy,
                )
                notifications.append(result.to_payload())
        if not dry_run:
            db.session.commit()
    enqueued_count = 0
    if not dry_run:
        for item in notifications:
            if item.get("status") != "pending":
                continue
            enqueue_result = enqueue_credit_notification(
                app,
                notification_bid=str(item.get("notification_bid") or ""),
            )
            item["enqueued"] = bool(enqueue_result.get("enqueued"))
            enqueued_count += int(bool(enqueue_result.get("enqueued")))
    candidate_count = sum(
        1
        for item in notifications
        if item.get("status")
        in {
            "candidate",
            "pending",
            "suppressed_duplicate",
        }
    )
    created_count = sum(1 for item in notifications if item.get("status") == "pending")
    return {
        "status": "created" if candidate_count else "noop",
        "candidate_count": candidate_count,
        "created_count": created_count,
        "enqueued_count": enqueued_count,
        "estimated_sms_cost": _estimated_sms_cost(
            policy,
            sum(1 for item in notifications if item.get("status") == "candidate"),
        )
        if dry_run
        else "0",
        "dry_run": dry_run,
        "notifications": notifications,
    }


def _today_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    resolved_now = now or datetime.now()
    start = datetime.combine(resolved_now.date(), time.min)
    end = start + timedelta(days=1)
    return start, end


def _is_quiet_hours(policy: dict[str, Any], now: datetime | None = None) -> bool:
    quiet = policy.get("quiet_hours")
    if not isinstance(quiet, dict) or not _coerce_bool(quiet.get("enabled")):
        return False
    current = now or datetime.now()
    timezone_name = str(quiet.get("timezone") or "").strip()
    if timezone_name:
        try:
            timezone = ZoneInfo(timezone_name)
            if now is None:
                current = datetime.now(timezone)
            elif current.tzinfo is None:
                current = current.replace(tzinfo=timezone)
            else:
                current = current.astimezone(timezone)
        except ZoneInfoNotFoundError:
            current = now or datetime.now()
    try:
        start_hour, start_minute = [
            int(part) for part in str(quiet.get("start")).split(":")[:2]
        ]
        end_hour, end_minute = [
            int(part) for part in str(quiet.get("end")).split(":")[:2]
        ]
    except (TypeError, ValueError):
        return False
    start_value = time(hour=start_hour, minute=start_minute)
    end_value = time(hour=end_hour, minute=end_minute)
    current_value = current.time()
    if start_value <= end_value:
        return start_value <= current_value < end_value
    return current_value >= start_value or current_value < end_value


def _is_blocked_by_policy(
    policy: dict[str, Any],
    *,
    notification: NotificationRecord,
    mobile: str,
    now: datetime,
) -> tuple[bool, str]:
    opt_out = policy.get("opt_out")
    if isinstance(opt_out, dict):
        creator_bids = {
            _normalize_bid(item)
            for item in opt_out.get("creator_bids", [])
            if _normalize_bid(item)
        }
        mobiles = {
            _normalize_bid(item)
            for item in opt_out.get("mobiles", [])
            if _normalize_bid(item)
        }
        if notification.creator_bid in creator_bids or mobile in mobiles:
            return True, "opt_out"

    blacklist = policy.get("blacklist")
    if isinstance(blacklist, dict):
        creator_bids = {
            _normalize_bid(item)
            for item in blacklist.get("creator_bids", [])
            if _normalize_bid(item)
        }
        mobiles = {
            _normalize_bid(item)
            for item in blacklist.get("mobiles", [])
            if _normalize_bid(item)
        }
        if notification.creator_bid in creator_bids or mobile in mobiles:
            return True, "blacklisted"
    if _is_quiet_hours(policy, now=now):
        return True, "quiet_hours"

    frequency = policy.get("frequency")
    if isinstance(frequency, dict):
        per_mobile = _coerce_positive_int(frequency.get("per_mobile_per_day"), 0)
        per_creator_type = _coerce_positive_int(
            frequency.get("per_creator_per_type_per_day"),
            0,
        )
        day_start, day_end = _today_bounds(now)
        if per_mobile > 0:
            mobile_count = NotificationRecord.query.filter(
                NotificationRecord.deleted == 0,
                NotificationRecord.channel == CREDIT_NOTIFICATION_CHANNEL_SMS,
                NotificationRecord.mobile_snapshot == mobile,
                NotificationRecord.status == CREDIT_NOTIFICATION_STATUS_SENT,
                NotificationRecord.sent_at >= day_start,
                NotificationRecord.sent_at < day_end,
            ).count()
            if mobile_count >= per_mobile:
                return True, "frequency_mobile_daily"
        if per_creator_type > 0:
            creator_type_count = NotificationRecord.query.filter(
                NotificationRecord.deleted == 0,
                NotificationRecord.creator_bid == notification.creator_bid,
                NotificationRecord.notification_type == notification.notification_type,
                NotificationRecord.status == CREDIT_NOTIFICATION_STATUS_SENT,
                NotificationRecord.sent_at >= day_start,
                NotificationRecord.sent_at < day_end,
            ).count()
            if creator_type_count >= per_creator_type:
                return True, "frequency_creator_type_daily"

    budget = policy.get("budget")
    if isinstance(budget, dict):
        daily_limit = _coerce_positive_int(budget.get("daily_sms_limit"), 0)
        if daily_limit > 0:
            day_start, day_end = _today_bounds(now)
            sent_count = NotificationRecord.query.filter(
                NotificationRecord.deleted == 0,
                NotificationRecord.channel == CREDIT_NOTIFICATION_CHANNEL_SMS,
                NotificationRecord.status == CREDIT_NOTIFICATION_STATUS_SENT,
                NotificationRecord.sent_at >= day_start,
                NotificationRecord.sent_at < day_end,
            ).count()
            if sent_count >= daily_limit:
                return True, "budget_daily_sms_limit"
    return False, ""


def _finalize_notification(
    notification: NotificationRecord,
    *,
    status: str,
    now: datetime,
    mobile: str = "",
    provider_response: dict[str, Any] | None = None,
    error_code: str = "",
    error_message: str = "",
) -> None:
    notification.status = status
    notification.mobile_snapshot = mobile or notification.mobile_snapshot or ""
    notification.attempted_at = now
    if status == CREDIT_NOTIFICATION_STATUS_SENT:
        notification.sent_at = now
    notification.provider_response_json = dict(provider_response or {})
    notification.error_code = str(error_code or "").strip()
    notification.error_message = str(error_message or "").strip()[:1024]
    notification.updated_at = now
    db.session.add(notification)
    record_credit_notification_event(
        "deliver",
        notification_type=notification.notification_type,
        channel=notification.channel,
        status=status,
    )


def deliver_credit_notification(
    app: Flask,
    *,
    notification_bid: str,
) -> dict[str, Any]:
    normalized_notification_bid = _normalize_bid(notification_bid)
    if not normalized_notification_bid:
        return {"status": "invalid_notification_bid", "notification_bid": None}

    with app.app_context():
        notification = (
            NotificationRecord.query.filter(
                NotificationRecord.deleted == 0,
                NotificationRecord.notification_bid == normalized_notification_bid,
            )
            .with_for_update()
            .order_by(NotificationRecord.id.desc())
            .first()
        )
        if notification is None:
            return {
                "status": "not_found",
                "notification_bid": normalized_notification_bid,
            }
        if notification.status not in CREDIT_NOTIFICATION_PROCESSABLE_STATUSES:
            return {
                "status": "noop",
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
            }

        now = datetime.now()
        policy = load_credit_notification_policy()
        if not _notification_type_enabled(policy, notification.notification_type):
            _finalize_notification(
                notification,
                status=CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
                now=now,
                error_code="policy_disabled",
                error_message="Notification policy is disabled.",
            )
            db.session.commit()
            return {
                "status": CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
            }

        mobile = load_creator_mobile_snapshot(notification.target_user_bid)
        if not mobile:
            _finalize_notification(
                notification,
                status=CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE,
                now=now,
                error_code="missing_mobile",
                error_message="Creator mobile is empty.",
            )
            db.session.commit()
            return {
                "status": CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE,
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
            }
        if not _is_valid_sms_mobile(mobile):
            _finalize_notification(
                notification,
                status=CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE,
                now=now,
                mobile=mobile,
                error_code="invalid_mobile",
                error_message="Creator mobile is invalid.",
            )
            db.session.commit()
            return {
                "status": CREDIT_NOTIFICATION_STATUS_SKIPPED_NO_MOBILE,
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
            }

        blocked, reason = _is_blocked_by_policy(
            policy,
            notification=notification,
            mobile=mobile,
            now=now,
        )
        if blocked:
            _finalize_notification(
                notification,
                status=CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
                now=now,
                mobile=mobile,
                error_code=reason,
                error_message=f"Notification blocked by policy: {reason}.",
            )
            db.session.commit()
            return {
                "status": CREDIT_NOTIFICATION_STATUS_SKIPPED_OPT_OUT,
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
                "reason": reason,
            }

        template_code = str(notification.template_code or "").strip() or _template_code(
            policy,
            notification.notification_type,
        )
        if not template_code:
            _finalize_notification(
                notification,
                status=CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
                now=now,
                mobile=mobile,
                error_code="missing_template_code",
                error_message="Notification SMS template code is empty.",
            )
            db.session.commit()
            return {
                "status": CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
            }

        try:
            response = send_sms_ali(
                app,
                mobile,
                template_code=template_code,
                template_params=dict(notification.template_params_json or {}),
            )
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            _finalize_notification(
                notification,
                status=CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
                now=now,
                mobile=mobile,
                error_code="provider_exception",
                error_message=str(exc),
                provider_response={"message": str(exc)},
            )
            db.session.commit()
            return {
                "status": CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
                "mobile": mobile,
                "error_code": "provider_exception",
            }
        if response is not None:
            _finalize_notification(
                notification,
                status=CREDIT_NOTIFICATION_STATUS_SENT,
                now=now,
                mobile=mobile,
                provider_response=_provider_response_payload(response),
            )
            db.session.commit()
            return {
                "status": CREDIT_NOTIFICATION_STATUS_SENT,
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
                "mobile": mobile,
            }

        _finalize_notification(
            notification,
            status=CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
            now=now,
            mobile=mobile,
            error_code="provider_failed",
            error_message="SMS provider returned no accepted response.",
        )
        db.session.commit()
        return {
            "status": CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER,
            "notification_bid": notification.notification_bid,
            "notification_status": notification.status,
            "mobile": mobile,
        }


def enqueue_credit_notification(app: Flask, *, notification_bid: str) -> dict[str, Any]:
    normalized_notification_bid = _normalize_bid(notification_bid)
    if not normalized_notification_bid:
        return {"status": "invalid_notification_bid", "enqueued": False}
    try:
        from flaskr.common.celery_app import get_celery_app

        celery_app = get_celery_app(flask_app=app)
        task = celery_app.tasks.get(TASK_NAME)
        if task is None:
            app.logger.warning(
                "%s is unavailable for notification_bid=%s",
                TASK_NAME,
                normalized_notification_bid,
            )
            return {
                "status": "task_unavailable",
                "notification_bid": normalized_notification_bid,
                "enqueued": False,
            }
        task.apply_async(kwargs={"notification_bid": normalized_notification_bid})
        return {
            "status": "enqueued",
            "notification_bid": normalized_notification_bid,
            "enqueued": True,
        }
    except Exception as exc:
        app.logger.error(
            "Failed to enqueue %s for notification_bid=%s: %s",
            TASK_NAME,
            normalized_notification_bid,
            exc,
            exc_info=True,
        )
        return {
            "status": "enqueue_failed",
            "notification_bid": normalized_notification_bid,
            "message": str(exc),
            "enqueued": False,
        }


def requeue_credit_notification(app: Flask, *, notification_bid: str) -> dict[str, Any]:
    normalized_notification_bid = _normalize_bid(notification_bid)
    if not normalized_notification_bid:
        return {"status": "invalid_notification_bid", "enqueued": False}
    with app.app_context():
        notification = (
            NotificationRecord.query.filter(
                NotificationRecord.deleted == 0,
                NotificationRecord.notification_bid == normalized_notification_bid,
            )
            .order_by(NotificationRecord.id.desc())
            .first()
        )
        if notification is None:
            return {
                "status": "not_found",
                "notification_bid": normalized_notification_bid,
                "enqueued": False,
            }
        if notification.status != CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER:
            return {
                "status": "not_requeueable",
                "notification_bid": notification.notification_bid,
                "notification_status": notification.status,
                "enqueued": False,
            }
    enqueue_result = enqueue_credit_notification(
        app,
        notification_bid=normalized_notification_bid,
    )
    if not enqueue_result.get("enqueued"):
        enqueue_result["notification_status"] = (
            CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER
        )
        return enqueue_result
    with app.app_context():
        notification = (
            NotificationRecord.query.filter(
                NotificationRecord.deleted == 0,
                NotificationRecord.notification_bid == normalized_notification_bid,
            )
            .order_by(NotificationRecord.id.desc())
            .first()
        )
        if (
            notification is not None
            and notification.status == CREDIT_NOTIFICATION_STATUS_FAILED_PROVIDER
        ):
            notification.status = CREDIT_NOTIFICATION_STATUS_PENDING
            notification.error_code = ""
            notification.error_message = ""
            notification.provider_response_json = {}
            notification.attempted_at = None
            notification.sent_at = None
            notification.updated_at = datetime.now()
            db.session.add(notification)
            db.session.commit()
            record_credit_notification_event(
                "requeue",
                notification_type=notification.notification_type,
                channel=notification.channel,
                status=CREDIT_NOTIFICATION_STATUS_PENDING,
            )
            enqueue_result["notification_status"] = CREDIT_NOTIFICATION_STATUS_PENDING
        elif notification is not None:
            enqueue_result["notification_status"] = notification.status
        else:
            enqueue_result["notification_status"] = "not_found"
    return enqueue_result


def _parse_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def list_credit_notifications(
    app: Flask,
    *,
    page_index: int = 1,
    page_size: int = 20,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_page_index = _parse_positive_int(page_index, 1)
    safe_page_size = min(100, _parse_positive_int(page_size, 20))
    normalized_filters = filters or {}
    with app.app_context():
        query = NotificationRecord.query.filter(NotificationRecord.deleted == 0)
        for field in (
            "creator_bid",
            "target_user_bid",
            "notification_type",
            "channel",
            "status",
            "source_type",
            "source_bid",
        ):
            value = _normalize_bid(normalized_filters.get(field))
            if value:
                query = query.filter(getattr(NotificationRecord, field) == value)
        mobile = _normalize_bid(normalized_filters.get("mobile"))
        if mobile:
            query = query.filter(NotificationRecord.mobile_snapshot == mobile)
        start_time = normalized_filters.get("start_time")
        end_time = normalized_filters.get("end_time")
        if isinstance(start_time, datetime):
            query = query.filter(NotificationRecord.created_at >= start_time)
        if isinstance(end_time, datetime):
            query = query.filter(NotificationRecord.created_at <= end_time)
        total = query.count()
        rows = (
            query.order_by(
                NotificationRecord.created_at.desc(), NotificationRecord.id.desc()
            )
            .offset((safe_page_index - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        items = [_serialize_notification_record(row) for row in rows]
    return {
        "page": safe_page_index,
        "page_size": safe_page_size,
        "page_count": math_ceil(total, safe_page_size),
        "total": total,
        "items": items,
    }


def math_ceil(total: int, page_size: int) -> int:
    return int((total + page_size - 1) // page_size) if total > 0 else 0


def _serialize_notification_record(row: NotificationRecord) -> dict[str, Any]:
    return {
        "notification_bid": row.notification_bid,
        "notification_type": row.notification_type,
        "channel": row.channel,
        "creator_bid": row.creator_bid,
        "target_user_bid": row.target_user_bid,
        "mobile_snapshot": row.mobile_snapshot,
        "source_type": row.source_type,
        "source_bid": row.source_bid,
        "dedupe_key": row.dedupe_key,
        "status": row.status,
        "template_code": row.template_code,
        "template_params": row.template_params_json or {},
        "policy_snapshot": row.policy_snapshot_json or {},
        "provider_response": row.provider_response_json or {},
        "error_code": row.error_code,
        "error_message": row.error_message,
        "requested_at": row.requested_at.isoformat() if row.requested_at else "",
        "attempted_at": row.attempted_at.isoformat() if row.attempted_at else "",
        "sent_at": row.sent_at.isoformat() if row.sent_at else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        "metadata": row.metadata_json or {},
    }


def dry_run_credit_notifications(
    app: Flask,
    *,
    notification_type: str = "",
    creator_bid: str = "",
) -> dict[str, Any]:
    normalized_type = _normalize_bid(notification_type)
    if normalized_type == CREDIT_NOTIFICATION_TYPE_EXPIRING:
        return scan_credit_expiring_notifications(
            app,
            creator_bid=creator_bid,
            dry_run=True,
        )
    if normalized_type == CREDIT_NOTIFICATION_TYPE_LOW_BALANCE:
        return scan_low_balance_notifications(
            app,
            creator_bid=creator_bid,
            dry_run=True,
        )
    if normalized_type == CREDIT_NOTIFICATION_TYPE_GRANTED:
        return {
            "status": "event_trigger_only",
            "candidate_count": 0,
            "created_count": 0,
            "estimated_sms_cost": "0",
            "dry_run": True,
            "notifications": [],
        }
    expiring = scan_credit_expiring_notifications(
        app, creator_bid=creator_bid, dry_run=True
    )
    low_balance = scan_low_balance_notifications(
        app, creator_bid=creator_bid, dry_run=True
    )
    return {
        "status": "dry_run",
        "candidate_count": int(expiring.get("candidate_count") or 0)
        + int(low_balance.get("candidate_count") or 0),
        "created_count": 0,
        "estimated_sms_cost": str(
            _quantize_credit_amount(
                _to_decimal(expiring.get("estimated_sms_cost"))
                + _to_decimal(low_balance.get("estimated_sms_cost"))
            )
        ),
        "dry_run": True,
        "notifications": [
            *(expiring.get("notifications") or []),
            *(low_balance.get("notifications") or []),
        ],
        "sections": {
            CREDIT_NOTIFICATION_TYPE_EXPIRING: expiring,
            CREDIT_NOTIFICATION_TYPE_LOW_BALANCE: low_balance,
        },
    }


def resolve_creator_limit_state(app: Flask, creator_bid: str) -> dict[str, Any]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if not normalized_creator_bid or not is_billing_enabled():
        return {
            "state": LIMIT_STATE_NORMAL,
            "debug_allowed": True,
            "available_credits": "0",
        }
    with app.app_context():
        wallet = (
            CreditWallet.query.filter(
                CreditWallet.deleted == 0,
                CreditWallet.creator_bid == normalized_creator_bid,
            )
            .order_by(CreditWallet.id.desc())
            .first()
        )
        available = _to_decimal(getattr(wallet, "available_credits", _ZERO))
        policy = load_credit_notification_policy()
        softlimit = policy.get("softlimit")
        softlimit_enabled = isinstance(softlimit, dict) and _coerce_bool(
            softlimit.get("enabled")
        )
        disable_debug = isinstance(softlimit, dict) and _coerce_bool(
            softlimit.get("disable_debug", True)
        )
        threshold_payload = (
            softlimit.get("threshold") if isinstance(softlimit, dict) else {}
        )
        threshold = _ZERO
        if isinstance(threshold_payload, dict):
            threshold = _decimal_from_policy(threshold_payload.get("value"), _ZERO)
        if available <= _ZERO:
            state = LIMIT_STATE_HARDLIMIT
        elif softlimit_enabled and available <= threshold:
            state = LIMIT_STATE_SOFTLIMIT
        else:
            state = LIMIT_STATE_NORMAL
    return {
        "state": state,
        "debug_allowed": not (state == LIMIT_STATE_SOFTLIMIT and disable_debug),
        "available_credits": str(_quantize_credit_amount(available)),
        "softlimit_threshold": str(threshold),
    }


def assert_creator_debug_allowed(app: Flask, creator_bid: str) -> None:
    state = resolve_creator_limit_state(app, creator_bid)
    if not bool(state.get("debug_allowed", True)):
        raise_error("server.billing.debugDisabledBySoftLimit")
