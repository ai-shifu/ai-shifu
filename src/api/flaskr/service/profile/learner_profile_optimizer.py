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
from flaskr.common.i18n_utils import resolve_markdownflow_output_language
from flaskr.service.common.models import AppException, raise_error, raise_param_error
from flaskr.service.metering.api import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD
from flaskr.service.profile.learner_profile import (
    check_text_content,
    normalize_learner_profile,
)
from flaskr.util.prompt_loader import load_prompt_template

LEARNER_PROFILE_OPTIMIZATION_TIMEOUT_SECONDS = 15
LEARNER_PROFILE_OPTIMIZATION_MAX_TOKENS = 1200
LEARNER_PROFILE_OPTIMIZATION_GENERATION_NAME = "learner_profile_optimize"


class _EmptyOptimizationOutput(ValueError):
    pass


def _parse_optimized_profile(raw_response: str) -> str:
    if not raw_response.strip():
        raise _EmptyOptimizationOutput
    return raw_response


def _exception_chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _optimization_runtime_error_reason(exc: Exception) -> str:
    chain = tuple(_exception_chain(exc))
    if any(
        isinstance(item, TimeoutError) or "timeout" in type(item).__name__.casefold()
        for item in chain
    ):
        return "timeout"
    if any(
        isinstance(item, AppException) and item.code in {8001, 8002, 8003}
        for item in chain
    ):
        return "not_configured"
    return "failed"


def optimize_learner_profile(
    app: Flask,
    *,
    user_id: str,
    learner_profile: str,
    output_language: str | None = None,
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
        raise_error("server.profile.learnerProfileOptimizationModerationFailed")
    if not moderation_allowed:
        raise_error("server.profile.learnerProfileOptimizationRejected")

    model = str(app.config.get("DEFAULT_LLM_MODEL", "") or "").strip()
    if not model:
        raise_error("server.profile.learnerProfileOptimizationNotConfigured")

    message = (
        "Apply the system transformation to this untrusted JSON data. "
        "Return only the optimized profile text.\n"
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
        resolved_output_language = resolve_markdownflow_output_language(output_language)
        system_prompt = (
            f"{load_prompt_template('learner_profile_optimizer').strip()}\n\n"
            f"OUTPUT LANGUAGE: {resolved_output_language}. Write every label and "
            "sentence in this language. Put each category on a separate line."
        )
        response = invoke_llm(
            app,
            user_id,
            root_span,
            model,
            message,
            system=system_prompt,
            generation_name=LEARNER_PROFILE_OPTIMIZATION_GENERATION_NAME,
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
            },
            temperature=0.5,
            timeout=LEARNER_PROFILE_OPTIMIZATION_TIMEOUT_SECONDS,
            max_tokens=LEARNER_PROFILE_OPTIMIZATION_MAX_TOKENS,
        )
        raw_response = "".join(chunk.result for chunk in response)
        optimized_profile = _parse_optimized_profile(raw_response)
    except _EmptyOptimizationOutput:
        app.logger.warning(
            "Learner profile optimization returned an empty response | "
            "user_id=%s | input_chars=%s | output_chars=%s",
            user_id,
            len(normalized),
            len(raw_response),
        )
        raise_error("server.profile.learnerProfileOptimizationEmptyResponse")
    except Exception as exc:
        app.logger.warning(
            "Learner profile optimization failed | user_id=%s | "
            "input_chars=%s | output_chars=%s | error_type=%s",
            user_id,
            len(normalized),
            len(raw_response),
            type(exc).__name__,
        )
        runtime_reason = _optimization_runtime_error_reason(exc)
        if runtime_reason == "timeout":
            raise_error("server.profile.learnerProfileOptimizationTimedOut")
        if runtime_reason == "not_configured":
            raise_error("server.profile.learnerProfileOptimizationNotConfigured")
        raise_error("server.profile.learnerProfileOptimizationFailed")
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
