"""Compile and localize public onboarding assistant prompts at configuration save."""

from __future__ import annotations

import json
import re
from contextlib import suppress
from typing import TYPE_CHECKING

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm import invoke_llm
from flaskr.i18n import get_locale_labels
from flaskr.service.common.models import raise_error
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.util.prompt_loader import load_prompt_template

if TYPE_CHECKING:
    from flask import Flask

_SOURCE_LOCALE_PATTERN = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z")
_SUCCESSFUL_FINISH_REASON = "stop"
_MARKDOWNFLOW_SOURCE_MARKER = "--- UNTRUSTED MARKDOWNFLOW SOURCE DATA STARTS BELOW ---"


def _prepare_compiler_input(document: str) -> str:
    """Mark the start of source data without adding a closable boundary."""
    return f"{_MARKDOWNFLOW_SOURCE_MARKER}\n{document}"


def _json_object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """Reject duplicate fields instead of silently accepting the last value."""
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            message = f"Duplicate JSON field: {key}"
            raise ValueError(message)
        payload[key] = value
    return payload


def _parse_completed_localizations(
    raw: str,
    *,
    master_prompt: str,
    locale_labels: dict[str, str],
) -> dict[str, str]:
    """Validate the complete locale map before exposing any generated prompt."""
    payload = json.loads(raw, object_pairs_hook=_json_object_without_duplicate_keys)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"source_locale", "assistant_prompts", "complete"}
        or payload["complete"] is not True
    ):
        message = "Assistant prompt localizer returned an invalid envelope"
        raise ValueError(message)

    source_locale = payload["source_locale"]
    assistant_prompts = payload["assistant_prompts"]
    expected_locales = set(locale_labels)
    if (
        not isinstance(source_locale, str)
        or not source_locale
        or source_locale != source_locale.strip()
        or _SOURCE_LOCALE_PATTERN.fullmatch(source_locale) is None
        or not isinstance(assistant_prompts, dict)
        or set(assistant_prompts) != expected_locales
    ):
        message = "Assistant prompt localizer returned invalid locales"
        raise ValueError(message)

    normalized_prompts: dict[str, str] = {}
    for locale in locale_labels:
        localized_prompt = assistant_prompts[locale]
        if not isinstance(localized_prompt, str) or not localized_prompt.strip():
            message = f"Assistant prompt localizer returned an empty {locale} prompt"
            raise ValueError(message)
        normalized_prompts[locale] = localized_prompt.strip()

    canonical_source_locale = next(
        (
            locale
            for locale in locale_labels
            if locale.casefold() == source_locale.casefold()
        ),
        None,
    )
    if canonical_source_locale is None:
        source_primary_language = source_locale.split("-", 1)[0].casefold()
        primary_matches = [
            locale
            for locale in locale_labels
            if locale.split("-", 1)[0].casefold() == source_primary_language
        ]
        if len(primary_matches) == 1:
            canonical_source_locale = primary_matches[0]
        elif primary_matches:
            message = "Assistant prompt localizer returned an ambiguous source locale"
            raise ValueError(message)
    if canonical_source_locale is not None:
        source_prompt = assistant_prompts[canonical_source_locale]
        if source_prompt.encode("utf-8") != master_prompt.encode("utf-8"):
            message = "Assistant prompt localizer changed the source prompt"
            raise ValueError(message)
    return normalized_prompts


def _prepare_localization_inputs(
    assistant_prompt: str,
) -> tuple[str, dict[str, str]]:
    """Resolve and validate the source prompt and current locale registry."""
    master_prompt = assistant_prompt.strip()
    locale_labels = get_locale_labels()
    if not master_prompt or not locale_labels:
        message = "Assistant prompt localization requires a prompt and locales"
        raise ValueError(message)
    return master_prompt, locale_labels


def compile_profile_onboarding_assistant_prompt(app: Flask, document: str) -> str:
    """Compile only the source document; no learner or UI language is provided."""
    trace = None
    span = None
    prompt = ""
    truncated = False
    completed = False
    try:
        trace, span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={"name": "profile_onboarding_assistant_compiler"},
            root_span_payload={"name": "profile_onboarding_assistant_compiler"},
        )
        responses = invoke_llm(
            app,
            "",
            span,
            str(app.config.get("DEFAULT_LLM_MODEL", "") or ""),
            _prepare_compiler_input(document),
            system=load_prompt_template("profile_onboarding_assistant_compiler"),
            json=False,
            generation_name="profile_onboarding_assistant_compiler",
            temperature=0,
            timeout=120,
            max_tokens=8192,
            usage_context=UsageContext(usage_scene=BILL_USAGE_SCENE_DEBUG, billable=0),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        )
        parts: list[str] = []
        # Consume the stream before rejecting so the shared wrapper can finish
        # usage accounting and tracing even for incomplete output.
        for chunk in responses:
            parts.append(chunk.result)
            finish_reason = getattr(chunk, "finish_reason", None)
            if finish_reason is not None:
                completed = finish_reason == _SUCCESSFUL_FINISH_REASON
            truncated = (
                truncated
                or bool(getattr(chunk, "is_truncated", False))
                or finish_reason == "length"
            )
        if completed and not truncated:
            prompt = "".join(parts).strip()
    except Exception as exc:
        app.logger.warning(
            "Onboarding assistant compilation failed: %s", type(exc).__name__
        )
        raise_error("server.profile.profileOnboardingPromptGenerationFailed")
    finally:
        if trace is not None:
            with suppress(Exception):
                finalize_langfuse_trace(
                    trace=trace,
                    root_span=span,
                    trace_payload={"output": prompt},
                    root_span_payload={"output": prompt},
                )
    if truncated or not completed or not prompt:
        raise_error("server.profile.profileOnboardingPromptGenerationFailed")
    return prompt


def localize_profile_onboarding_assistant_prompt(
    app: Flask, assistant_prompt: str
) -> dict[str, str]:
    """Generate one validated prompt for every locale in the shared registry."""
    trace = None
    span = None
    localized_prompts: dict[str, str] = {}
    truncated = False
    try:
        master_prompt, locale_labels = _prepare_localization_inputs(assistant_prompt)
        trace, span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={"name": "profile_onboarding_assistant_localizer"},
            root_span_payload={"name": "profile_onboarding_assistant_localizer"},
        )
        responses = invoke_llm(
            app,
            "",
            span,
            str(app.config.get("DEFAULT_LLM_MODEL", "") or ""),
            json.dumps(
                {
                    "assistant_prompt": master_prompt,
                    "target_locales": locale_labels,
                },
                ensure_ascii=False,
            ),
            system=load_prompt_template("profile_onboarding_assistant_localizer"),
            json=True,
            generation_name="profile_onboarding_assistant_localizer",
            temperature=0,
            timeout=120,
            max_tokens=16384,
            usage_context=UsageContext(usage_scene=BILL_USAGE_SCENE_DEBUG, billable=0),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        )
        parts: list[str] = []
        # Always consume the stream so accounting and tracing can finish even
        # when a chunk already proves that the response was truncated.
        for chunk in responses:
            parts.append(chunk.result)
            truncated = (
                truncated
                or bool(getattr(chunk, "is_truncated", False))
                or (getattr(chunk, "finish_reason", None) == "length")
            )
        if not truncated:
            localized_prompts = _parse_completed_localizations(
                "".join(parts),
                master_prompt=master_prompt,
                locale_labels=locale_labels,
            )
    except Exception as exc:
        app.logger.warning(
            "Onboarding assistant localization failed: %s", type(exc).__name__
        )
        raise_error("server.profile.profileOnboardingPromptGenerationFailed")
    finally:
        if trace is not None:
            with suppress(Exception):
                finalize_langfuse_trace(
                    trace=trace,
                    root_span=span,
                    trace_payload={"output": localized_prompts},
                    root_span_payload={"output": localized_prompts},
                )
    if truncated or not localized_prompts:
        raise_error("server.profile.profileOnboardingPromptGenerationFailed")
    return localized_prompts
