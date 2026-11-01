"""Batch contact lookups for reporting views that list many users."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity

if TYPE_CHECKING:
    from collections.abc import Sequence


def load_user_contact_map(
    user_bids: Sequence[str],
) -> dict[str, dict[str, str]]:
    """Return ``{"mobile", "email"}`` contact details for each user bid.

    Phone/email/google credentials win (newest first); legacy
    ``user_identify`` values only fill fields that are still empty.
    """
    normalized_user_bids = [
        str(user_bid or "").strip()
        for user_bid in user_bids
        if str(user_bid or "").strip()
    ]
    if not normalized_user_bids:
        return {}

    credential_rows = (
        AuthCredential.query.filter(
            AuthCredential.user_bid.in_(normalized_user_bids),
            AuthCredential.deleted == 0,
            AuthCredential.provider_name.in_(["phone", "email", "google"]),
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )
    contact_map: dict[str, dict[str, str]] = {
        user_bid: {"mobile": "", "email": ""} for user_bid in normalized_user_bids
    }
    for credential in credential_rows:
        user_bid = str(credential.user_bid or "").strip()
        if not user_bid:
            continue
        resolved = contact_map.setdefault(user_bid, {"mobile": "", "email": ""})
        identifier = str(credential.identifier or "").strip()
        if (
            credential.provider_name == "phone"
            and not resolved["mobile"]
            and identifier
        ):
            resolved["mobile"] = identifier
        if (
            credential.provider_name in {"email", "google"}
            and not resolved["email"]
            and identifier
        ):
            resolved["email"] = identifier

    users = (
        UserEntity.query.filter(
            UserEntity.user_bid.in_(normalized_user_bids),
            UserEntity.deleted == 0,
        )
        .order_by(UserEntity.id.asc())
        .all()
    )
    for user in users:
        user_bid = str(user.user_bid or "").strip()
        if not user_bid:
            continue
        resolved = contact_map.setdefault(user_bid, {"mobile": "", "email": ""})
        identify = str(user.user_identify or "").strip()
        if len(identify) == 11 and identify.isdigit() and not resolved["mobile"]:
            resolved["mobile"] = identify
        elif "@" in identify and not resolved["email"]:
            resolved["email"] = identify
    return contact_map
