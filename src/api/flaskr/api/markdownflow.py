"""Shared application binding for the independent MarkdownFlow engine library.

Both course and Profile hosts use these native engine objects and the same LLM
adapter. Persistence, authorization and product policies belong to the caller.
"""

from __future__ import annotations

from markdownflow import (
    ContentDelta,
    ContinueTurn,
    Engine,
    ErrorEvent,
    Event,
    InputBudgetExceededError,
    InteractionAnswer,
    InteractionRequest,
    InteractionResponseTurn,
    InteractionSpec,
    LessonPager,
    MemoryUpdated,
    MessageTurn,
    Option,
    PendingInteraction,
    QuestionLabels,
    QuestionRenderer,
    ScriptBundle,
    Session,
    StartTurn,
    TurnCapacityError,
    TurnDone,
    TurnInput,
    UnrepresentableInteractionError,
    answer_is_usable,
    collected_names,
    iter_turn,
    normalize_answer,
)

from flaskr.api.llm.markdownflow_model import GatewayModel
from flaskr.i18n import _

__all__ = [
    "ContentDelta",
    "ContinueTurn",
    "Engine",
    "ErrorEvent",
    "Event",
    "GatewayModel",
    "InputBudgetExceededError",
    "InteractionAnswer",
    "InteractionRequest",
    "InteractionResponseTurn",
    "InteractionSpec",
    "LessonPager",
    "MemoryUpdated",
    "MessageTurn",
    "Option",
    "PendingInteraction",
    "QuestionLabels",
    "QuestionRenderer",
    "ScriptBundle",
    "Session",
    "StartTurn",
    "TurnCapacityError",
    "TurnDone",
    "TurnInput",
    "UnrepresentableInteractionError",
    "answer_is_usable",
    "collected_names",
    "iter_turn",
    "normalize_answer",
    "render_interaction",
    "render_narrated_interaction",
    "render_question",
    "unrenderable_reason",
]


def _question_renderer() -> QuestionRenderer:
    """Bind default control labels to the current application's locale."""
    return QuestionRenderer(
        QuestionLabels(
            continue_label=_("server.learn.continueButton"),
            free_text_placeholder=_("server.learn.freeTextPlaceholder"),
        )
    )


def render_interaction(spec: InteractionSpec) -> str:
    """Render native controls with application-supplied labels."""
    return _question_renderer().render_interaction(spec)


def render_question(spec: InteractionSpec) -> tuple[str, str]:
    """Render the question and controls under the same validation policy."""
    return _question_renderer().render_question(spec)


def unrenderable_reason(spec: InteractionSpec) -> str | None:
    """Validate the exact localized controls the caller will present."""
    return _question_renderer().unrenderable_reason(spec)


def render_narrated_interaction(span: str) -> str:
    """Fill missing narrated input hints without changing authored controls."""
    return _question_renderer().render_narrated_interaction(span)
