"""Stable public service contracts for learning integrations."""

from flaskr.service.learn.agent.routing import uses_agent_engine
from flaskr.service.learn.learner_profile_prompt import (
    build_course_prompt,
    render_course_prompt_identity_variables,
)
from flaskr.service.learn.live_follow_up_config import (
    GEMINI_LIVE_MODEL_ID,
    is_live_follow_up_model,
    normalize_live_follow_up_course_config,
    normalize_live_follow_up_provider_config,
)

__all__ = [
    "GEMINI_LIVE_MODEL_ID",
    "build_course_prompt",
    "is_live_follow_up_model",
    "normalize_live_follow_up_course_config",
    "normalize_live_follow_up_provider_config",
    "render_course_prompt_identity_variables",
    "uses_agent_engine",
]
