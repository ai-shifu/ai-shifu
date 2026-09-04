"""Build the shared course and conversation context for learner follow-ups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flaskr.common.i18n_utils import resolve_markdownflow_output_language
from flaskr.service.learn.learner_profile_prompt import (
    build_course_prompt,
    render_course_prompt_identity_variables,
)
from flaskr.service.learn.listen_element_payloads import _deserialize_payload
from flaskr.service.learn.listen_element_queries import (
    _load_latest_active_element_row,
    find_follow_up_element_rows,
)
from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.service.learn.utils_v2 import FollowUpInfo, get_fmt_prompt
from flaskr.service.profile.api import get_user_profiles
from flaskr.service.shifu.api import find_node_with_parents, get_shifu_struct
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from markdown_flow import replace_variables_in_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask
    from flaskr.service.user.api import UserAggregate


@dataclass(frozen=True)
class FollowUpConversationContext:
    """Prompt and history shared by text and Live follow-up transports."""

    system_instruction: str
    llm_messages: list[dict[str, str]]
    provider_messages: list[dict[str, str]]
    use_learner_language: bool
    output_language: str


def resolve_course_system_prompt(
    app: Flask,
    *,
    shifu_bid: str,
    outline_item_bid: str,
    preview_mode: bool,
    outline_path: list[object] | None = None,
    outline_model: object | None = None,
    shifu_model: object | None = None,
) -> str | None:
    """Return the nearest inherited Course Prompt for one lesson."""
    path = outline_path
    if path is None:
        struct = get_shifu_struct(app, shifu_bid, preview_mode)
        path = find_node_with_parents(struct, outline_item_bid)
    if not path:
        return None

    nearest_first = list(reversed(path))
    outline_ids = [item.id for item in nearest_first if item.type == "outline"]
    shifu_ids = [item.id for item in nearest_first if item.type == "shifu"]
    resolved_outline_model = outline_model or (
        DraftOutlineItem if preview_mode else PublishedOutlineItem
    )
    resolved_shifu_model = shifu_model or (
        DraftShifu if preview_mode else PublishedShifu
    )

    outline_rows = resolved_outline_model.query.filter(
        resolved_outline_model.id.in_(outline_ids),
        resolved_outline_model.deleted == 0,
    ).all()
    outline_by_id = {row.id: row for row in outline_rows}
    for outline_id in outline_ids:
        prompt = str(
            getattr(outline_by_id.get(outline_id), "llm_system_prompt", "") or ""
        )
        if prompt:
            return prompt

    shifu_row = (
        resolved_shifu_model.query.filter(
            resolved_shifu_model.id.in_(shifu_ids),
            resolved_shifu_model.deleted == 0,
        )
        .order_by(resolved_shifu_model.id.desc())
        .first()
    )
    prompt = str(getattr(shifu_row, "llm_system_prompt", "") or "")
    return prompt or None


def is_complete_follow_up_asks(asks: object) -> bool:
    """Return whether a legacy embedded history contains both conversation roles."""
    if not isinstance(asks, list) or not asks:
        return False
    has_student = any(
        isinstance(item, dict) and item.get("role") == "student" for item in asks
    )
    has_teacher = any(
        isinstance(item, dict) and item.get("role") == "teacher" for item in asks
    )
    return has_student and has_teacher


def build_legacy_follow_up_history(
    anchor_element: object,
    ask_element: object,
    max_history_messages: int,
) -> list[dict[str, str]] | None:
    """Build anchor-bound history from a legacy embedded ASK payload."""
    payload = _deserialize_payload(getattr(ask_element, "payload", "") or "")
    if not is_complete_follow_up_asks(payload.asks):
        return None
    messages: list[dict[str, str]] = []
    anchor_content = str(getattr(anchor_element, "content_text", "") or "")
    if anchor_content:
        messages.append({"role": "assistant", "content": anchor_content})
    recent_entries = (
        (payload.asks or [])[-max_history_messages:] if max_history_messages > 0 else []
    )
    for entry in recent_entries:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = str(entry.get("content", "") or "")
        if role == "student":
            messages.append({"role": "user", "content": content})
        elif role == "teacher":
            messages.append({"role": "assistant", "content": content})
    return messages


def build_follow_up_element_history(
    anchor_element: object,
    follow_up_elements: object,
    max_history_messages: int,
) -> list[dict[str, str]] | None:
    """Build anchor-bound history from canonical or legacy sidecar elements."""
    if anchor_element is None or not isinstance(follow_up_elements, (list, tuple)):
        return None
    if not follow_up_elements:
        return None

    history_limit = max(0, int(max_history_messages))
    messages: list[dict[str, str]] = []
    anchor_content = str(getattr(anchor_element, "content_text", "") or "")
    if anchor_content:
        messages.append({"role": "assistant", "content": anchor_content})

    row_messages: list[dict[str, str]] = []
    legacy_ask_element = None
    for row in follow_up_elements:
        element_type = str(getattr(row, "element_type", "") or "")
        payload = _deserialize_payload(getattr(row, "payload", "") or "")
        if element_type == "ask" and is_complete_follow_up_asks(payload.asks):
            legacy_ask_element = row
            continue
        content = str(getattr(row, "content_text", "") or "")
        if not content:
            continue
        if element_type == "ask":
            row_messages.append({"role": "user", "content": content})
        elif element_type == "answer":
            row_messages.append({"role": "assistant", "content": content})

    if row_messages:
        if history_limit > 0:
            messages.extend(row_messages[-history_limit:])
        return messages
    if legacy_ask_element is not None:
        return build_legacy_follow_up_history(
            anchor_element,
            legacy_ask_element,
            history_limit,
        )
    return None


def load_follow_up_history(
    *,
    progress_record_bid: str,
    anchor_element_bid: str,
    max_history_messages: int,
    latest_element_loader: Callable[[str], object | None] | None = None,
    element_rows_loader: Callable[[str, str], list[object]] | None = None,
    generated_block_model: object | None = None,
) -> list[dict[str, str]]:
    """Load anchor plus recent ASK/ANSWER history using the canonical order."""
    history_limit = max(0, int(max_history_messages))
    load_latest = latest_element_loader or _load_latest_active_element_row
    load_element_rows = element_rows_loader or find_follow_up_element_rows
    block_model = generated_block_model or LearnGeneratedBlock
    anchor_element = None
    follow_up_elements: list[object] = []
    if anchor_element_bid:
        anchor_element = load_latest(anchor_element_bid)
        if anchor_element is not None:
            follow_up_elements = list(
                load_element_rows(
                    progress_record_bid,
                    anchor_element_bid,
                )
            )

    element_history = build_follow_up_element_history(
        anchor_element,
        follow_up_elements,
        history_limit,
    )
    if element_history is not None:
        return element_history

    rows: list[LearnGeneratedBlock] = (
        block_model.query.filter(
            block_model.progress_record_bid == progress_record_bid,
            block_model.deleted == 0,
        )
        .order_by(block_model.id.desc())
        .limit(history_limit)
        .all()
    )
    rows.reverse()
    history: list[dict[str, str]] = []
    for row in rows:
        content = str(row.generated_content or "")
        if row.type in (BLOCK_TYPE_MDASK_VALUE, BLOCK_TYPE_MDINTERACTION_VALUE):
            history.append({"role": "user", "content": content})
        elif row.type in (BLOCK_TYPE_MDANSWER_VALUE, BLOCK_TYPE_MDCONTENT_VALUE):
            history.append({"role": "assistant", "content": content})
    return history


def build_follow_up_conversation_context(
    app: Flask,
    *,
    user_info: UserAggregate,
    shifu_bid: str,
    outline_item_bid: str,
    progress_record_bid: str,
    follow_up_info: FollowUpInfo,
    course_system_prompt: str | None,
    use_learner_language: bool,
    runtime_language: str,
    runtime_profiles: dict[str, Any] | None = None,
    anchor_element_bid: str = "",
    max_history_messages: int = 10,
    latest_element_loader: Callable[[str], object | None] | None = None,
    element_rows_loader: Callable[[str, str], list[object]] | None = None,
    generated_block_model: object | None = None,
    format_prompt: Callable[..., str] | None = None,
    output_language: str | None = None,
    fallback_system_prompt: str | None = None,
) -> FollowUpConversationContext:
    """Compose the effective prompt and history for either follow-up transport."""
    if not str(outline_item_bid or "").strip():
        message = "Follow-up context requires an outline item BID"
        raise ValueError(message)
    profiles = dict(
        runtime_profiles
        if runtime_profiles is not None
        else (get_user_profiles(app, user_info.user_id, shifu_bid) or {})
    )
    if use_learner_language and runtime_language:
        profiles.update(
            {
                "sys_user_language": runtime_language,
                "language": runtime_language,
            }
        )

    context_prompt = course_system_prompt or fallback_system_prompt
    if context_prompt:
        variable_course_prompt = build_course_prompt(
            context_prompt,
            variables=profiles,
            nickname_identifiers=(
                getattr(user_info, "user_bid", ""),
                getattr(user_info, "user_id", ""),
                getattr(user_info, "identify", ""),
            ),
        )
        variable_course_prompt = render_course_prompt_identity_variables(
            variable_course_prompt,
            profiles,
        )
        markdownflow_prompt = replace_variables_in_text(
            variable_course_prompt or "",
            profiles,
        )
        format_course_prompt = format_prompt or get_fmt_prompt
        base_system_prompt = format_course_prompt(
            app,
            user_info.user_id,
            shifu_bid,
            markdownflow_prompt,
            resolved_profiles=profiles,
        )
    else:
        base_system_prompt = None

    ask_prompt = str(follow_up_info.ask_prompt or "")
    # Blank follow-up prompts use the transport's base instruction: inherited
    # course instructions for text, or an explicit voice fallback for Live.
    system_instruction = (
        ask_prompt if ask_prompt.strip() else "{shifu_system_message}"
    ).replace(
        "{shifu_system_message}",
        base_system_prompt or "",
    )
    resolved_output_language = output_language or resolve_markdownflow_output_language(
        runtime_language
    )
    if use_learner_language:
        system_instruction += (
            f"\n\nIMPORTANT: You MUST respond in {resolved_output_language}."
        )

    history = load_follow_up_history(
        progress_record_bid=progress_record_bid,
        anchor_element_bid=anchor_element_bid,
        max_history_messages=max_history_messages,
        latest_element_loader=latest_element_loader,
        element_rows_loader=element_rows_loader,
        generated_block_model=generated_block_model,
    )
    llm_messages = [{"role": "system", "content": system_instruction}, *history]
    provider_messages = list(history)
    if base_system_prompt:
        provider_messages.insert(0, {"role": "system", "content": base_system_prompt})
    return FollowUpConversationContext(
        system_instruction=system_instruction,
        llm_messages=llm_messages,
        provider_messages=provider_messages,
        use_learner_language=use_learner_language,
        output_language=resolved_output_language,
    )
