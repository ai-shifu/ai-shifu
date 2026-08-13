from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from typing import Any, TypeVar

from flask import Flask
from flaskr.api.check import (
    CHECK_RESULT_PASS,
    CHECK_RESULT_REJECT,
    check_text,
)
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.check_risk.api import add_risk_control_result
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.common.phone_numbers import normalize_phone_identifier
from flaskr.service.profile.constants import (
    LEGACY_LEARNER_PROFILE_KEYS,
    SYS_USER_NICKNAME,
)
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_UNREGISTERED,
)
from flaskr.service.user.models import (
    AuthCredential,
    UserOnboardingState,
)
from flaskr.service.user.models import (
    UserInfo as UserEntity,
)
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id
from sqlalchemy.exc import IntegrityError

LEARNER_PROFILE_MAX_LENGTH = 1000
LEARNER_PROFILE_NICKNAME_MAX_LENGTH = 64
LEARNER_PROFILE_CHECK_STRATEGY = "check_learner_profile"
LEARNER_PROFILE_STATUS_COMPLETED = "completed"
LEARNER_PROFILE_TRIGGER_SOURCES = frozenset({"guided", "pasted", "settings"})
PROFILE_ONBOARDING_SCENE_KEY = "profile_onboarding"
PROFILE_ONBOARDING_VERSION = "profile-v2"

_T = TypeVar("_T")

_NICKNAME_CAPTURE = r"[\"'“”‘’«»「」『』]?([^\n\r，,。.!！?？；;：:]{1,96})"
_SENTENCE_BOUNDARY = r"(?:^|[\n\r，,。.!！?？；;])\s*"

# A direct preference outranks an identity statement. Within the same priority,
# the last declaration wins so natural corrections such as "My name is
# Alexander. Please call me Alex." resolve to the requested form of address.
_EXPLICIT_NICKNAME_PATTERNS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (
        30,
        re.compile(
            _SENTENCE_BOUNDARY + r"(?:(?:关于称呼|称呼方面)\s*[，,]?\s*)?"
            r"(?:(?:现在|以后|今后|接下来)\s*)?"
            r"(?:(?:(?:你|大家|AI\s*老师|AI\s*师傅)\s*)?"
            r"(?:(?:可以|可|请|就|直接|平时)\s*)?"
            r"|(?:我\s*)?(?:希望|想让)\s*"
            r"(?:你|大家|AI\s*老师|AI\s*师傅)?\s*)"
            r"(?:叫我|称呼我(?:为)?|称我为)\s*[：:]?\s*" + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        30,
        re.compile(
            _SENTENCE_BOUNDARY
            + r"(?:称呼|昵称|名字|姓名)\s*[：:]\s*"
            + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        30,
        re.compile(
            _SENTENCE_BOUNDARY + r"(?:(?:you\s+can|please|just)\s+)?"
            r"(?:call\s+me|address\s+me\s+as)\s+" + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        30,
        re.compile(
            _SENTENCE_BOUNDARY
            + r"i\s+(?:go\s+by|(?:would\s+)?(?:like|prefer)\s+to\s+be\s+called)\s+"
            + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        30,
        re.compile(
            _SENTENCE_BOUNDARY
            + r"(?:vous\s+pouvez|tu\s+peux)\s+m['’]appeler\s+"
            + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        30,
        re.compile(
            _SENTENCE_BOUNDARY + r"(?:appelez|appelle)[-\s]moi\s+" + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        30,
        re.compile(
            _SENTENCE_BOUNDARY + r"je\s+pr[ée]f[èe]re\s+(?:qu['’]on\s+m['’]appelle|"
            r"(?:être|etre)\s+appel[ée]e?)\s+" + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        20,
        re.compile(
            _SENTENCE_BOUNDARY
            + r"(?:我的(?:名字|姓名|昵称)\s*(?:是|叫)|我叫)\s*[：:]?\s*"
            + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        20,
        re.compile(
            _SENTENCE_BOUNDARY
            + r"(?:my\s+name\s+is|mon\s+pr[ée]nom\s+est|je\s+m['’]appelle)\s+"
            + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
    (
        20,
        re.compile(
            r"(?:^|[\n\r])\s*(?:preferred\s+name|display\s+name|pr[ée]nom)\s*"
            r"[：:]\s*" + _NICKNAME_CAPTURE,
            re.IGNORECASE,
        ),
    ),
)

_NICKNAME_TRAILING_CONTEXT_PATTERNS = (
    re.compile(
        r"\s+(?=(?:我|本人)?(?:是|在|目前|现在|想|希望|喜欢|偏好|有|从事|正在))"
    ),
    re.compile(
        r"\s+(?=(?:(?:请|多|少|先|再|不要|不用|别|帮我|给我|向我|为我)\s*)?"
        r"(?:回答|思考|解释|告诉|举|讲|提供|生成|使用|用|提醒|说明))"
    ),
    re.compile(r"\s+(?=(?:and|but)\s+i\b)", re.IGNORECASE),
    re.compile(r"\s+(?=(?:et|mais)\s+je\b)", re.IGNORECASE),
)

_NICKNAME_TRAILING_SOFTENERS = (
    re.compile(r"(?:就好|即可|就行|就可以|吧|哦|啦)$"),
    re.compile(r"\s+(?:please|thanks?|thank\s+you)$", re.IGNORECASE),
    re.compile(r"\s+(?:s['’]il\s+vous\s+pla[îi]t|merci)$", re.IGNORECASE),
)

_REJECTED_LATIN_PREFIXES = frozenset(
    {
        "a",
        "about",
        "after",
        "an",
        "at",
        "before",
        "for",
        "if",
        "later",
        "never",
        "not",
        "on",
        "the",
        "to",
        "when",
        "whenever",
        "again",
        "un",
        "une",
        "le",
        "la",
        "les",
        "quand",
        "si",
        "après",
        "avant",
        "pour",
        "au",
        "aux",
        "pas",
        "jamais",
    }
)
_REJECTED_CJK_PREFIXES = (
    "你",
    "您",
    "他",
    "她",
    "它",
    "大家",
    "老师",
    "AI老师",
    "AI 老师",
    "AI师傅",
    "AI 师傅",
    "课程",
)
_REJECTED_CJK_INSTRUCTION_PREFIXES = (
    "在",
    "不",
    "别",
    "先",
    "请",
    "帮",
    "给",
    "让",
    "继续",
    "开始",
    "停止",
    "避免",
    "回答",
    "解释",
    "告诉",
    "记得",
    "现在",
    "以后",
)
_REJECTED_CJK_STRONG_INSTRUCTION_PREFIXES = (
    "不要",
    "不用",
    "不必",
    "不得",
    "请勿",
)
_REJECTED_CJK_INSTRUCTION_TERMS = (
    "回答",
    "思考",
    "解释",
    "告诉",
    "公开",
    "场合",
    "问题",
    "之前",
    "之后",
    "开始",
    "继续",
    "停止",
    "避免",
    "提供",
    "生成",
    "使用",
    "帮我",
)
_LATIN_ABBREVIATION_PREFIXES = frozenset(
    {"dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st"}
)


def _looks_like_cjk_instruction(candidate: str) -> bool:
    compact_candidate = candidate.replace(" ", "")
    if compact_candidate.startswith(_REJECTED_CJK_STRONG_INSTRUCTION_PREFIXES):
        return True
    if not compact_candidate.startswith(_REJECTED_CJK_INSTRUCTION_PREFIXES):
        return False
    return len(compact_candidate) > 3 or any(
        term in compact_candidate for term in _REJECTED_CJK_INSTRUCTION_TERMS
    )


def _capture_truncated_a_latin_initialism(source: str, match: re.Match[str]) -> bool:
    """Reject a partial capture such as ``J`` or ``Dr`` instead of guessing."""

    candidate = match.group(1).strip()
    if not re.fullmatch(r"[A-Za-z]+", candidate):
        return False
    looks_like_prefix = (
        len(candidate) == 1 or candidate.casefold() in _LATIN_ABBREVIATION_PREFIXES
    )
    return looks_like_prefix and (
        re.match(r"\.\s*[A-Za-zÀ-ÖØ-öø-ÿ]", source[match.end() :]) is not None
    )


def _normalize_nickname_candidate(raw_candidate: str) -> str | None:
    surrounding_characters = " \t\"'“”‘’«»「」『』()[]（）【】"
    candidate = " ".join(raw_candidate.strip().split())
    for trailing_pattern in _NICKNAME_TRAILING_CONTEXT_PATTERNS:
        candidate = trailing_pattern.split(candidate, maxsplit=1)[0].strip()
    candidate = candidate.strip(surrounding_characters)
    for softener in _NICKNAME_TRAILING_SOFTENERS:
        candidate = softener.sub("", candidate).strip()
    candidate = candidate.strip(surrounding_characters)
    candidate = unicodedata.normalize("NFC", candidate)

    if not candidate or len(candidate) > LEARNER_PROFILE_NICKNAME_MAX_LENGTH:
        return None
    if len(candidate.split()) > 6 or candidate.isdigit():
        return None

    candidate_lower = candidate.casefold()
    if any(token in candidate_lower for token in ("@", "http://", "https://", "www.")):
        return None
    if sum(char.isdigit() for char in candidate) >= 7:
        return None

    first_word = candidate_lower.split(maxsplit=1)[0]
    if first_word in _REJECTED_LATIN_PREFIXES:
        return None
    compact_candidate = candidate.replace(" ", "")
    if compact_candidate.startswith(_REJECTED_CJK_PREFIXES):
        return None
    if _looks_like_cjk_instruction(candidate):
        return None
    if any(not (char.isalnum() or char in " -_'’·") for char in candidate):
        return None
    return candidate


def extract_learner_profile_nickname(learner_profile: str) -> str | None:
    """Recognize only an explicit preferred form of address from profile prose.

    The profile stays the source of truth. This conservative recognizer avoids a
    second provider call and never guesses a name from a role, email, or other
    background detail.
    """

    source = str(learner_profile or "").strip()
    if not source:
        return None

    candidates: list[tuple[int, int, str]] = []
    for priority, pattern in _EXPLICIT_NICKNAME_PATTERNS:
        for match in pattern.finditer(source):
            if _capture_truncated_a_latin_initialism(source, match):
                continue
            candidate = _normalize_nickname_candidate(match.group(1))
            if candidate is not None:
                candidates.append((priority, match.start(), candidate))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _learner_profile_audit_text(learner_profile: str) -> str:
    """Return linkage metadata without duplicating the learner's profile text."""

    return json.dumps(
        {
            "content": "[redacted]",
            "sha256": hashlib.sha256(learner_profile.encode("utf-8")).hexdigest(),
            "unicode_code_points": len(learner_profile),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _learner_profile_audit_response(result: Any) -> str:
    """Allowlist moderation verdict details and discard the provider raw payload."""

    return json.dumps(
        {
            "risk_label_ids": list(getattr(result, "risk_label_ids", []) or []),
            "risk_labels": [
                str(label) for label in (getattr(result, "risk_labels", []) or [])
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def check_text_content(app: Flask, user_id: str, learner_profile: str) -> bool:
    """Moderate a profile while keeping its canonical row as the only local raw copy."""

    check_id = generate_id(app)
    result = check_text(app, check_id, learner_profile, user_id)
    add_risk_control_result(
        app,
        check_id,
        user_id,
        _learner_profile_audit_text(learner_profile),
        result.provider,
        result.check_result,
        _learner_profile_audit_response(result),
        1 if result.check_result == CHECK_RESULT_PASS else 0,
        LEARNER_PROFILE_CHECK_STRATEGY,
    )
    return result.check_result != CHECK_RESULT_REJECT


def load_learner_profile_user(
    user_id: str,
    *,
    for_update: bool = False,
) -> UserEntity:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise_error("server.user.userNotLogin")
    query = UserEntity.query.filter(
        UserEntity.user_bid == normalized_user_id,
        UserEntity.deleted == 0,
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    user = query.first()
    if user is None:
        raise_error("server.user.userNotLogin")
    return user


def normalize_learner_profile(raw_profile: Any) -> str:
    if not isinstance(raw_profile, str):
        raise_param_error("learner_profile")
    normalized = raw_profile.strip()
    if not normalized or len(normalized) > LEARNER_PROFILE_MAX_LENGTH:
        raise_param_error("learner_profile")
    return normalized


def serialize_learner_profile(user: UserEntity) -> dict[str, Any]:
    profile = str(user.learner_profile or "")
    return {
        "learner_profile": profile,
        "learner_profile_updated_at": to_utc_iso(user.learner_profile_updated_at),
        "has_learner_profile": bool(profile),
        "max_length": LEARNER_PROFILE_MAX_LENGTH,
    }


def _load_legacy_learner_profile_values(user: UserEntity) -> dict[str, str]:
    rows = (
        VariableValue.query.filter(
            VariableValue.user_bid == user.user_bid,
            VariableValue.shifu_bid == "",
            VariableValue.key.in_(LEGACY_LEARNER_PROFILE_KEYS),
            VariableValue.deleted == 0,
        )
        .order_by(VariableValue.id.desc())
        .all()
    )
    latest_values: dict[str, str] = {}
    seen_keys: set[str] = set()
    for row in rows:
        if row.key in seen_keys:
            continue
        seen_keys.add(row.key)
        if row.key == SYS_USER_NICKNAME:
            continue
        value = str(row.value or "").strip()
        if value:
            latest_values[row.key] = value

    canonical_nickname = str(user.nickname or "").strip()
    if canonical_nickname:
        latest_values[SYS_USER_NICKNAME] = canonical_nickname
    return latest_values


def get_learner_profile(*, user_id: str) -> dict[str, Any]:
    user = load_learner_profile_user(user_id)
    serialized = serialize_learner_profile(user)
    has_handled_profile = (
        not serialized["has_learner_profile"]
        and load_learner_profile_state(user.user_bid) is not None
    )
    serialized["legacy_profile_values"] = (
        {}
        if serialized["has_learner_profile"] or has_handled_profile
        else _load_legacy_learner_profile_values(user)
    )
    return serialized


def apply_learner_profile(user: UserEntity, learner_profile: str) -> bool:
    if str(user.learner_profile or "") == learner_profile:
        return False
    user.learner_profile = learner_profile
    user.learner_profile_updated_at = now_utc()
    return True


def load_learner_profile_state(
    user_id: str,
    *,
    for_update: bool = False,
) -> UserOnboardingState | None:
    query = UserOnboardingState.query.filter(
        UserOnboardingState.user_bid == str(user_id or "").strip(),
        UserOnboardingState.scene_key == PROFILE_ONBOARDING_SCENE_KEY,
        UserOnboardingState.version == PROFILE_ONBOARDING_VERSION,
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    return query.first()


def merge_learner_profile_for_sign_in(
    *,
    source_user_id: str,
    target_user_id: str,
) -> None:
    """Copy canonical profile state into an existing signed-in account transaction."""

    normalized_source_id = str(source_user_id or "").strip()
    normalized_target_id = str(target_user_id or "").strip()
    if (
        not normalized_source_id
        or not normalized_target_id
        or normalized_source_id == normalized_target_id
    ):
        return

    target_user = (
        UserEntity.query.filter(
            UserEntity.user_bid == normalized_target_id,
            UserEntity.deleted == 0,
        )
        .with_for_update()
        .first()
    )
    if target_user is None:
        return

    if load_learner_profile_state(normalized_target_id, for_update=True) is not None:
        return

    source_user = (
        UserEntity.query.filter(
            UserEntity.user_bid == normalized_source_id,
            UserEntity.deleted == 0,
        )
        .with_for_update()
        .first()
    )
    if source_user is None:
        return

    if source_user.state != USER_STATE_UNREGISTERED:
        return

    source_identify = str(source_user.user_identify or "").strip()
    normalized_source_phone = normalize_phone_identifier(source_identify)
    source_has_account_identifier = bool(
        "@" in source_identify
        or normalized_source_phone.isdigit()
        or AuthCredential.query.filter(
            AuthCredential.user_bid == normalized_source_id,
            AuthCredential.provider_name.in_(["phone", "email"]),
            AuthCredential.state == CREDENTIAL_STATE_VERIFIED,
            AuthCredential.deleted == 0,
        ).first()
    )
    if source_has_account_identifier:
        return

    source_state = load_learner_profile_state(
        normalized_source_id,
        for_update=True,
    )
    source_profile = str(source_user.learner_profile or "").strip()
    target_profile = str(target_user.learner_profile or "").strip()
    if source_profile and not target_profile:
        target_user.learner_profile = source_user.learner_profile
        target_user.learner_profile_updated_at = source_user.learner_profile_updated_at
        target_user.nickname = extract_learner_profile_nickname(source_profile) or ""

    if source_state is None:
        return

    if not target_profile and not source_profile:
        target_user.nickname = ""

    db.session.add(
        UserOnboardingState(
            user_bid=normalized_target_id,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
            status=source_state.status,
            trigger_source=source_state.trigger_source,
            completed_at=source_state.completed_at,
        )
    )


def has_learner_profile_or_state(
    user_id: str,
    *,
    for_update: bool = False,
) -> bool:
    user = load_learner_profile_user(user_id, for_update=for_update)
    has_profile = bool(str(user.learner_profile or "").strip())
    if has_profile and not for_update:
        return True
    return has_profile or (
        load_learner_profile_state(user_id, for_update=for_update) is not None
    )


def _apply_completed_state(
    *,
    user_id: str,
    trigger_source: str,
) -> UserOnboardingState:
    state = load_learner_profile_state(user_id)
    now = now_utc()
    if state is None:
        state = UserOnboardingState(
            user_bid=user_id,
            scene_key=PROFILE_ONBOARDING_SCENE_KEY,
            version=PROFILE_ONBOARDING_VERSION,
            status=LEARNER_PROFILE_STATUS_COMPLETED,
            trigger_source=trigger_source,
            completed_at=now,
        )
        db.session.add(state)
        return state

    previous_status = state.status
    state.status = LEARNER_PROFILE_STATUS_COMPLETED
    state.trigger_source = trigger_source
    if (
        state.completed_at is None
        or previous_status != LEARNER_PROFILE_STATUS_COMPLETED
    ):
        state.completed_at = now
    return state


def _commit_with_state_race_retry(
    operation: Callable[[], _T],
    *,
    user_id: str,
) -> _T:
    def run_once() -> _T:
        with unit_of_work():
            result = operation()
            db.session.flush()
        return result

    try:
        return run_once()
    except IntegrityError:
        with unit_of_work():
            winner = load_learner_profile_state(user_id)
        if winner is None:
            raise
        return run_once()


def _serialize_completed_state(state: UserOnboardingState) -> dict[str, Any]:
    return {
        "handled": True,
        "completed": state.status == LEARNER_PROFILE_STATUS_COMPLETED,
        "skipped": False,
        "status": state.status,
        "trigger_source": state.trigger_source,
        "completed_at": to_utc_iso(state.completed_at),
        "version": state.version,
    }


def validate_learner_profile_content(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
) -> str:
    normalized = normalize_learner_profile(learner_profile)
    if not check_text_content(app, user_id, normalized):
        raise_error("server.check.checkRiskControlReject")
    return normalized


def save_learner_profile(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
    trigger_source: str,
) -> dict[str, Any]:
    normalized_trigger_source = str(trigger_source or "").strip()
    if normalized_trigger_source not in LEARNER_PROFILE_TRIGGER_SOURCES:
        raise_param_error("trigger_source")
    normalized = validate_learner_profile_content(
        app,
        user_id=user_id,
        learner_profile=learner_profile,
    )
    recognized_nickname = extract_learner_profile_nickname(normalized)

    def operation() -> tuple[UserEntity, UserOnboardingState]:
        user = load_learner_profile_user(user_id)
        apply_learner_profile(user, normalized)
        user.nickname = recognized_nickname or ""
        state = _apply_completed_state(
            user_id=user_id,
            trigger_source=normalized_trigger_source,
        )
        return user, state

    user, state = _commit_with_state_race_retry(operation, user_id=user_id)
    return {
        **_serialize_completed_state(state),
        **serialize_learner_profile(user),
    }


def replace_learner_profile(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
) -> dict[str, Any]:
    return save_learner_profile(
        app,
        user_id=user_id,
        learner_profile=learner_profile,
        trigger_source="settings",
    )


def clear_learner_profile(*, user_id: str) -> dict[str, Any]:
    def operation() -> tuple[UserEntity, UserOnboardingState]:
        user = load_learner_profile_user(user_id)
        if user.learner_profile or user.learner_profile_updated_at is not None:
            user.learner_profile = ""
            user.learner_profile_updated_at = None
        user.nickname = ""
        state = _apply_completed_state(user_id=user_id, trigger_source="settings")
        return user, state

    user, state = _commit_with_state_race_retry(operation, user_id=user_id)
    return {
        **_serialize_completed_state(state),
        **serialize_learner_profile(user),
    }
