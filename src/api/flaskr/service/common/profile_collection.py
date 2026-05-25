from __future__ import annotations

import json
import re
from typing import Any

from flaskr.i18n import _
from flaskr.service.profile.models import VariableValue


SYS_USER_NICKNAME = "sys_user_nickname"
SYS_USER_BACKGROUND = "sys_user_background"
SYS_USER_STYLE = "sys_user_style"

PROFILE_COLLECTION_CONFIG_VERSION = 1
PROFILE_COLLECTION_BLOCK_PREFIX = "pc:"
PROFILE_COLLECTION_KEYS = (
    SYS_USER_NICKNAME,
    SYS_USER_BACKGROUND,
    SYS_USER_STYLE,
)
PROFILE_COLLECTION_KEY_SET = set(PROFILE_COLLECTION_KEYS)

_VARIABLE_RE = re.compile(r"\{{1,2}([^{}]+)\}{1,2}")
_VALID_VARIABLE_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_-]*")


def extract_profile_collection_keys(text: str | None) -> set[str]:
    if not text:
        return set()
    keys: set[str] = set()
    for match in _VARIABLE_RE.findall(text):
        key = match.strip()
        if key in PROFILE_COLLECTION_KEY_SET and _VALID_VARIABLE_RE.fullmatch(key):
            keys.add(key)
    return keys


def get_recorded_profile_collection_keys(user_bid: str) -> set[str]:
    if not user_bid:
        return set()
    rows = (
        VariableValue.query.filter(
            VariableValue.user_bid == user_bid,
            VariableValue.deleted == 0,
            VariableValue.shifu_bid == "",
            VariableValue.key.in_(PROFILE_COLLECTION_KEYS),
        )
        .order_by(VariableValue.id.desc())
        .all()
    )
    return {row.key for row in rows if row.key in PROFILE_COLLECTION_KEY_SET}


def profile_collection_block_bid(variable_key: str) -> str:
    return f"{PROFILE_COLLECTION_BLOCK_PREFIX}{variable_key}"


def is_profile_collection_block_bid(block_bid: str | None) -> bool:
    return bool(block_bid and block_bid.startswith(PROFILE_COLLECTION_BLOCK_PREFIX))


def profile_collection_key_from_block_bid(block_bid: str | None) -> str:
    if not is_profile_collection_block_bid(block_bid):
        return ""
    key = str(block_bid)[len(PROFILE_COLLECTION_BLOCK_PREFIX) :]
    return key if key in PROFILE_COLLECTION_KEY_SET else ""


def default_profile_collection_prompt(variable_key: str) -> dict[str, str]:
    if variable_key == SYS_USER_NICKNAME:
        return {
            "question": _("server.profile.collectionNicknameQuestion"),
            "placeholder": _("server.profile.collectionNicknamePlaceholder"),
            "skip_label": _("server.profile.collectionSkipLabel"),
        }
    if variable_key == SYS_USER_STYLE:
        return {
            "question": _("server.profile.collectionStyleQuestion"),
            "placeholder": _("server.profile.collectionStylePlaceholder"),
            "skip_label": _("server.profile.collectionSkipLabel"),
        }
    return {
        "question": _("server.profile.collectionBackgroundQuestion"),
        "placeholder": _("server.profile.collectionBackgroundPlaceholder"),
        "skip_label": _("server.profile.collectionSkipLabel"),
    }


def normalize_profile_collection_prompt_config(raw: Any) -> dict[str, Any]:
    if raw in (None, ""):
        return {"version": PROFILE_COLLECTION_CONFIG_VERSION, "variables": {}}
    parsed = raw
    if isinstance(raw, str):
        parsed = _parse_json_object(raw)
    if not isinstance(parsed, dict):
        return {"version": PROFILE_COLLECTION_CONFIG_VERSION, "variables": {}}

    raw_variables = parsed.get("variables", {})
    if not isinstance(raw_variables, dict):
        raw_variables = {}

    variables: dict[str, dict[str, str]] = {}
    for key in PROFILE_COLLECTION_KEYS:
        item = raw_variables.get(key)
        if not isinstance(item, dict):
            continue
        normalized_item: dict[str, str] = {}
        for field in ("question", "placeholder", "skip_label"):
            value = item.get(field)
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    normalized_item[field] = normalized
        if normalized_item:
            variables[key] = normalized_item

    return {
        "version": PROFILE_COLLECTION_CONFIG_VERSION,
        "variables": variables,
    }


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def serialize_profile_collection_prompt_config(raw: Any) -> str:
    return json.dumps(
        normalize_profile_collection_prompt_config(raw),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def get_profile_collection_prompt(
    config: dict[str, Any] | str | None, variable_key: str
) -> dict[str, str]:
    normalized = normalize_profile_collection_prompt_config(config)
    configured = normalized.get("variables", {}).get(variable_key, {})
    if not isinstance(configured, dict):
        configured = {}
    default_prompt = default_profile_collection_prompt(variable_key)
    return {
        "question": str(
            configured.get("question") or default_prompt["question"]
        ).strip(),
        "placeholder": str(
            configured.get("placeholder") or default_prompt["placeholder"]
        ).strip(),
        "skip_label": str(
            configured.get("skip_label") or default_prompt["skip_label"]
        ).strip(),
    }


def build_profile_collection_interaction_md(
    config: dict[str, Any] | str | None, variable_key: str
) -> str:
    prompt = get_profile_collection_prompt(config, variable_key)
    question = _sanitize_interaction_text(
        prompt.get("question") or prompt.get("placeholder") or variable_key
    )
    skip_label = _sanitize_interaction_text(prompt.get("skip_label") or "")
    if not skip_label:
        skip_label = _sanitize_interaction_text(
            default_profile_collection_prompt(variable_key)["skip_label"]
        )
    return f"?[%{{{{{variable_key}}}}}{skip_label}|...{question}]"


def is_profile_collection_skip_value(
    value: str | None, config: dict[str, Any] | str | None, variable_key: str
) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return True
    prompt = get_profile_collection_prompt(config, variable_key)
    skip_values = {
        prompt.get("skip_label", "").strip(),
        default_profile_collection_prompt(variable_key)["skip_label"].strip(),
    }
    return normalized in {item for item in skip_values if item}


def _sanitize_interaction_text(value: str) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = text.replace("[", "(").replace("]", ")").replace("|", "/")
    return re.sub(r"\s+", " ", text)
