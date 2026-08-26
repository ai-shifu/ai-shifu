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


def compile_profile_onboarding_assistant_prompt(app: Flask, document: str) -> str:
    """Compile only the source document; no learner or UI language is provided."""
    trace = None
    span = None
    prompt = ""
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
            generation_name="profile_onboarding_assistant_compiler",
            temperature=0,
            timeout=120,
            max_tokens=8192,
            usage_context=UsageContext(usage_scene=BILL_USAGE_SCENE_DEBUG, billable=0),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            billable=0,
        )
        prompt = "".join(chunk.result for chunk in responses).strip()
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
    if not prompt:
        raise_error("server.profile.profileOnboardingPromptGenerationFailed")
    return prompt
