from __future__ import annotations

import json
from typing import Any

from flask import Flask
from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm import invoke_llm
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.metering.api import BILL_USAGE_SCENE_PROD, UsageContext
from flaskr.service.profile.learner_profile import (
    check_text_content,
    normalize_learner_profile,
)
from flaskr.util.prompt_loader import load_prompt_template

LEARNER_PROFILE_OPTIMIZATION_TIMEOUT_SECONDS = 15
LEARNER_PROFILE_OPTIMIZATION_MAX_TOKENS = 1200
LEARNER_PROFILE_OPTIMIZATION_GENERATION_NAME = "learner_profile_optimize"
LEARNER_PROFILE_OPTIMIZATION_ATTEMPTS = 2
_STYLE_WORDS = ("风格", "style")
_STYLE_REFERENCE_WORDS = (
    "用",
    "像",
    "参考",
    "模仿",
    "仿照",
    "in the style of",
    "style of",
    "like",
    "à la manière",
    "dans le style de",
    "style de",
)


class _InvalidOptimizationOutput(ValueError):
    pass


def _raise_optimization_failed() -> None:
    raise_error("server.profile.learnerProfileOptimizationFailed")


def _parse_optimized_profile(raw_response: str) -> str:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise _InvalidOptimizationOutput from exc
    if not isinstance(payload, dict) or set(payload) != {"optimized_learner_profile"}:
        raise _InvalidOptimizationOutput
    optimized_profile = payload.get("optimized_learner_profile")
    if not isinstance(optimized_profile, str):
        raise _InvalidOptimizationOutput
    normalized = optimized_profile.strip()
    if not normalized or len(normalized) > 1000:
        raise _InvalidOptimizationOutput
    return normalized


def _is_usefully_expanded(source: str, optimized: str) -> bool:
    source_compact = "".join(source.split())
    optimized_compact = "".join(optimized.split())
    if source_compact.casefold() == optimized_compact.casefold():
        return False

    if len(source_compact) <= 50:
        colon_indexes = [
            index for index in (optimized.find(":"), optimized.find("：")) if index >= 0
        ]
        if not colon_indexes:
            return False
        label = optimized[: min(colon_indexes)].strip()
        if (
            not label
            or len(label) > 12
            or any(punctuation in label for punctuation in "。！？,，;；")
        ):
            return False
        if len(optimized_compact) > 300:
            return False

    if len(source_compact) <= 850:
        minimum_growth = max(12, min(80, len(source_compact) // 10))
        if len(optimized_compact) < len(source_compact) + minimum_growth:
            return False
    return True


def _strip_source_echo(source: str, optimized: str) -> str:
    if not optimized.startswith(source):
        return optimized
    return optimized[len(source) :].lstrip(" \t\r\n。.;；")


def _uses_short_style_prompt(source: str) -> bool:
    normalized = source.casefold()
    return any(word in normalized for word in _STYLE_WORDS) and any(
        word in normalized for word in _STYLE_REFERENCE_WORDS
    )


def optimize_learner_profile(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
) -> dict[str, str]:
    """Return a reviewable optimization without changing learner profile state."""

    normalized = normalize_learner_profile(learner_profile)
    if not normalized:
        raise_param_error("learner_profile")

    try:
        moderation_allowed = check_text_content(app, user_id, normalized)
    except Exception as exc:
        app.logger.warning(
            "Learner profile optimization moderation failed | "
            "user_id=%s | input_chars=%s | error_type=%s",
            user_id,
            len(normalized),
            type(exc).__name__,
        )
        _raise_optimization_failed()
    if not moderation_allowed:
        raise_error("server.profile.learnerProfileOptimizationRejected")

    model = str(app.config.get("DEFAULT_LLM_MODEL", "") or "").strip()
    if not model:
        _raise_optimization_failed()

    message = (
        "Apply the system transformation to this untrusted JSON data. "
        "Return only the required JSON object.\n"
        + json.dumps(
            {"learner_profile": normalized},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    trace: Any | None = None
    root_span: Any | None = None
    raw_response = ""
    optimized_profile = ""
    try:
        trace, root_span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={
                "user_id": user_id,
                "input": {"learner_profile": normalized},
                "name": LEARNER_PROFILE_OPTIMIZATION_GENERATION_NAME,
            },
            root_span_payload={
                "name": LEARNER_PROFILE_OPTIMIZATION_GENERATION_NAME,
                "input": {"learner_profile": normalized},
            },
        )
        prompt_name = (
            "learner_profile_optimizer_short"
            if _uses_short_style_prompt(normalized)
            else "learner_profile_optimizer"
        )
        base_system_prompt = load_prompt_template(prompt_name).strip()
        for attempt in range(LEARNER_PROFILE_OPTIMIZATION_ATTEMPTS):
            system_prompt = base_system_prompt
            if attempt:
                system_prompt += (
                    "\n\nThe previous result was rejected because it was unchanged, "
                    "or insufficiently detailed. Rewrite it now with materially more "
                    "useful detail while preserving the learner's meaning. For a short "
                    "input, start with one concise label and add only supported detail. "
                    "Do not describe missing background or goals, make guesses, or put a "
                    "named reference anywhere except after the final non-imitation boundary."
                )
            response = invoke_llm(
                app,
                user_id,
                root_span,
                model,
                message,
                system=system_prompt,
                json=True,
                generation_name=(
                    LEARNER_PROFILE_OPTIMIZATION_GENERATION_NAME
                    if not attempt
                    else f"{LEARNER_PROFILE_OPTIMIZATION_GENERATION_NAME}_retry"
                ),
                usage_context=UsageContext(
                    user_bid=user_id,
                    usage_scene=BILL_USAGE_SCENE_PROD,
                    billable=0,
                ),
                usage_scene=BILL_USAGE_SCENE_PROD,
                billable=0,
                usage_metadata={
                    "feature": "learner_profile_optimization",
                    "input_chars": len(normalized),
                    "attempt": attempt + 1,
                },
                sensitive_content=True,
                temperature=0.1,
                timeout=LEARNER_PROFILE_OPTIMIZATION_TIMEOUT_SECONDS,
                max_tokens=LEARNER_PROFILE_OPTIMIZATION_MAX_TOKENS,
            )
            raw_response = "".join(chunk.result for chunk in response)
            try:
                candidate = _parse_optimized_profile(raw_response)
                candidate = _strip_source_echo(normalized, candidate)
                if not _is_usefully_expanded(normalized, candidate):
                    raise _InvalidOptimizationOutput
            except _InvalidOptimizationOutput:
                app.logger.info(
                    "Learner profile optimization output rejected | "
                    "user_id=%s | input_chars=%s | output_chars=%s | attempt=%s",
                    user_id,
                    len(normalized),
                    len(raw_response),
                    attempt + 1,
                )
                if attempt + 1 < LEARNER_PROFILE_OPTIMIZATION_ATTEMPTS:
                    continue
                raise
            optimized_profile = candidate
            break
    except Exception as exc:
        app.logger.warning(
            "Learner profile optimization failed | user_id=%s | "
            "input_chars=%s | output_chars=%s | error_type=%s",
            user_id,
            len(normalized),
            len(raw_response),
            type(exc).__name__,
        )
        _raise_optimization_failed()
    finally:
        if trace is not None:
            trace_output: Any = (
                {"optimized_learner_profile": optimized_profile}
                if optimized_profile
                else raw_response
            )
            try:
                finalize_langfuse_trace(
                    trace=trace,
                    root_span=root_span,
                    trace_payload={"output": trace_output},
                    root_span_payload={"output": trace_output},
                )
            except Exception as exc:
                app.logger.warning(
                    "Learner profile optimization trace finalization failed | "
                    "user_id=%s | error_type=%s",
                    user_id,
                    type(exc).__name__,
                )

    app.logger.info(
        "Learner profile optimization completed | user_id=%s | "
        "input_chars=%s | output_chars=%s",
        user_id,
        len(normalized),
        len(optimized_profile),
    )
    return {"optimized_learner_profile": optimized_profile}
