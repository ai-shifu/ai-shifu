from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from flask import current_app

from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity
from flaskr.util.timezone import serialize_with_app_timezone


def coerce_operator_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            current_app.logger.warning(
                "Failed to parse operator datetime value '%s'",
                value,
            )
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    current_app.logger.warning(
        "Unexpected operator datetime value type '%s'",
        type(value).__name__,
    )
    return None


def format_operator_datetime(value: Any) -> str:
    normalized_value = coerce_operator_datetime(value)
    if not normalized_value:
        return ""
    serialized_value = serialize_with_app_timezone(
        current_app._get_current_object(),
        normalized_value,
        tz_name="UTC",
    )
    return str(serialized_value or "").replace("+00:00", "Z")


def load_operator_user_map(user_bids: Sequence[str]) -> Dict[str, Dict[str, str]]:
    if not user_bids:
        return {}

    normalized_user_bids = sorted(
        {str(user_bid or "").strip() for user_bid in user_bids if user_bid}
    )
    if not normalized_user_bids:
        return {}

    credentials = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(normalized_user_bids),
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
            AuthCredential.deleted == 0,
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    phone_map: Dict[str, str] = {}
    email_map: Dict[str, str] = {}
    for credential in credentials:
        user_bid = credential.user_bid or ""
        if not user_bid:
            continue
        if credential.provider_name == "phone" and user_bid not in phone_map:
            phone_map[user_bid] = credential.identifier or ""
        if (
            credential.provider_name in {"email", "google"}
            and user_bid not in email_map
        ):
            email_map[user_bid] = credential.identifier or ""

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(normalized_user_bids),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.asc())
        .all()
    )
    user_map: Dict[str, Dict[str, str]] = {}
    for user in users:
        mobile = phone_map.get(user.user_bid, "")
        email = email_map.get(user.user_bid, "")
        identify = user.user_identify or ""
        if not mobile and identify.isdigit():
            mobile = identify
        if not email and "@" in identify:
            email = identify
        user_map[user.user_bid] = {
            "mobile": mobile or "",
            "email": email or "",
            "identify": identify,
            "nickname": user.nickname or "",
        }
    return user_map
