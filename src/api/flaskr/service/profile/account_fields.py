"""Account-backed learner profile fields: nickname, language and learner profile.

These system keys live on the user entity. Their historical variable rows are
compatibility data written alongside; reads always come from the user entity.
"""

from flask import Flask
from flaskr.api.check import CHECK_RESULT_REJECT
from flaskr.i18n import _, get_locale_labels
from flaskr.service.check_risk.api import check_and_record_text
from flaskr.service.user.dtos import UserProfileLabelDTO, UserProfileLabelItemDTO
from flaskr.service.user.repository import (
    UserAggregate,
    load_user_aggregate,
    update_user_entity_fields,
)
from flaskr.service.user.repository import (
    _ensure_user_entity as ensure_user_entity,
)
from flaskr.util.uuid import generate_id

from .constants import (
    ACTIVE_SYSTEM_PROFILE_KEYS,
    SYS_USER_BACKGROUND,
    SYS_USER_LANGUAGE,
    SYS_USER_NICKNAME,
)
from .learner_profile import (
    apply_learner_profile_system_value,
    load_learner_profile_user,
)
from .models import VariableValue


def load_user_aggregate_without_credentials(user_id: str) -> UserAggregate | None:
    """Load the user aggregate without credentials, never creating a missing user."""
    return load_user_aggregate(user_id, with_credentials=False)


def ensure_user_aggregate(user_id: str) -> UserAggregate | None:
    """Load the user aggregate, creating the user entity first if it is missing."""
    aggregate = load_user_aggregate(user_id)
    if aggregate:
        return aggregate
    ensure_user_entity(user_id)
    return load_user_aggregate(user_id)


def update_aggregate_field(
    aggregate: UserAggregate | None, mapping: str, value: object
) -> None:
    """Mirror a written account field into the loaded aggregate."""
    if not aggregate:
        return
    if mapping == "name":
        aggregate.nickname = value or ""
    elif mapping == "user_language":
        aggregate.language = value or ""
    elif mapping == "learner_profile":
        aggregate.learner_profile = str(value or "")


def apply_core_mapping(
    user_id: str,
    mapping: str,
    value: str | None,
) -> str | None:
    """Write one account field to the user entity and return its stored value."""
    if mapping == "learner_profile":
        return apply_learner_profile_system_value(
            user_id=user_id,
            learner_profile=str(value or ""),
        )
    entity = ensure_user_entity(user_id)
    normalized = value or ""
    if mapping == "name":
        update_user_entity_fields(entity, nickname=normalized)
    elif mapping == "user_language":
        update_user_entity_fields(entity, language=normalized)
    return normalized


def current_core_value(aggregate: UserAggregate | None, mapping: str) -> str | None:
    """Read one account field from the aggregate, or None without one."""
    if not aggregate:
        return None
    if mapping == "name":
        return aggregate.nickname
    if mapping == "user_language":
        return aggregate.language
    if mapping == "learner_profile":
        return str(aggregate.learner_profile or "")
    return None


def check_text_content(
    app: Flask,
    user_id: str,
    user_input: str,
) -> bool:
    """Check text content."""
    res = check_and_record_text(
        app, generate_id(app), user_id, user_input, "check_text"
    )
    return res.check_result != CHECK_RESULT_REJECT


def get_profile_labels() -> dict[str, dict[str, object]]:
    """Return profile labels."""
    locale_labels = get_locale_labels()
    return {
        SYS_USER_NICKNAME: {
            "label": _("server.profile.nickname"),
            "mapping": "name",
            "default": "",
        },
        SYS_USER_LANGUAGE: {
            "label": _("server.profile.language"),
            "items": list(locale_labels.values()),
            "mapping": "user_language",
            "items_mapping": locale_labels,
            "default": "zh-CN",
        },
        SYS_USER_BACKGROUND: {
            "label": _("server.profile.userBackground"),
            "mapping": "learner_profile",
            "default": "",
        },
    }


def get_global_profile_keys() -> frozenset[str]:
    """Return keys that the shared profile writer routes to global/account storage."""
    return ACTIVE_SYSTEM_PROFILE_KEYS


def global_profile_value_versions(
    user_id: str, *, lock: bool = False
) -> dict[str, tuple[int, str | None]]:
    """Version registered global rows and canonical fields before delayed writes.

    Settings update the user row before appending compatibility values. Lock in
    that order and use current reads so newer settings or direct canonical edits
    cannot be overwritten by an older model proposal.
    """
    if lock:
        load_learner_profile_user(user_id, for_update=True)
    aggregate = load_user_aggregate(user_id)
    labels = get_profile_labels()
    query = (
        VariableValue.query.filter(
            VariableValue.user_bid == user_id,
            VariableValue.shifu_bid == "",
            VariableValue.key.in_(labels),
        )
        .with_entities(VariableValue.id, VariableValue.key)
        .order_by(VariableValue.id)
    )
    if lock:
        query = query.populate_existing().with_for_update()
    rows = {row.key: row.id for row in query.all()}
    versions = {}
    for key, label in labels.items():
        value = current_core_value(aggregate, str(label.get("mapping", "")))
        versions[key] = (rows.get(key, 0), str(value) if value is not None else None)
    return versions


def _resolve_profile_language_label(
    language: str | None,
    locale_labels: dict[str, str],
    default: str,
) -> str:
    """Resolve legacy codes without treating locale insertion order as a default."""
    normalized = str(language or "").strip().replace("_", "-").casefold()
    for code, label in locale_labels.items():
        if normalized in (code.casefold(), label.casefold()):
            return label

    primary = normalized.split("-", maxsplit=1)[0]
    for code, label in locale_labels.items():
        if code.casefold().split("-", maxsplit=1)[0] == primary:
            return label

    return locale_labels.get(default, "")


def get_user_profile_labels(
    app: Flask,
    user_id: str,
    course_id: str,
    *,
    include_nickname: bool = True,
    include_background: bool = True,
) -> UserProfileLabelDTO:
    """Get user profile labels.

    Args:
        app: Flask application instance
        user_id: User id
        course_id: Course id
        include_nickname: Whether to include the stored nickname label.
        include_background: Whether to include the canonical learner profile.

    Returns:
        UserProfileLabelDTO: User profile labels and resolved language.

    """
    app.logger.info("get user profile labels:%s", course_id)
    profile_labels = get_profile_labels()
    aggregate = load_user_aggregate(user_id)
    result = UserProfileLabelDTO(
        profiles=[], language=aggregate.user_language if aggregate else "en-US"
    )
    if aggregate:
        for key, meta in profile_labels.items():
            value = current_core_value(aggregate, meta["mapping"])
            if key == SYS_USER_LANGUAGE:
                value = _resolve_profile_language_label(
                    value, meta["items_mapping"], meta["default"]
                )
            result.profiles.append(
                UserProfileLabelItemDTO(
                    key=key,
                    label=meta["label"],
                    type="select" if "items" in meta else "text",
                    value=value,
                    items=meta.get("items"),
                )
            )

    if not include_nickname:
        result.profiles = [
            profile for profile in result.profiles if profile.key != SYS_USER_NICKNAME
        ]
    if not include_background:
        result.profiles = [
            profile for profile in result.profiles if profile.key != SYS_USER_BACKGROUND
        ]
    return result
