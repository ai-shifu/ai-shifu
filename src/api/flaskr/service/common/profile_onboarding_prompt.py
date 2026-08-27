"""Compile a public, document-language assistant prompt at configuration save."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import TYPE_CHECKING

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm import invoke_llm
from flaskr.service.common.models import raise_error
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.util.prompt_loader import load_prompt_template

if TYPE_CHECKING:
    from flask import Flask


def _parse_completed_prompt(raw: str) -> str:
    """Require a complete compiler envelope before exposing its plain text."""
    payload = json.loads(raw)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"assistant_prompt", "complete"}
        or payload["complete"] is not True
        or not isinstance(payload["assistant_prompt"], str)
    ):
        message = "Assistant prompt compiler returned an invalid envelope"
        raise ValueError(message)
    return payload["assistant_prompt"].strip()


def compile_profile_onboarding_assistant_prompt(app: Flask, document: str) -> str:
    """Compile only the source document; no learner or UI language is provided."""
    trace = None
    span = None
    prompt = ""
    truncated = False
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
            json.dumps({"markdownflow": document}, ensure_ascii=False),
            system=load_prompt_template("profile_onboarding_assistant_compiler"),
            json=True,
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
            truncated = (
                truncated
                or bool(getattr(chunk, "is_truncated", False))
                or (getattr(chunk, "finish_reason", None) == "length")
            )
        if not truncated:
            # The shared wrapper may omit a content-free terminal chunk and
            # its finish reason. An unfinished JSON envelope still fails here.
            prompt = _parse_completed_prompt("".join(parts))
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
    if truncated or not prompt:
        raise_error("server.profile.profileOnboardingPromptGenerationFailed")
    return prompt
