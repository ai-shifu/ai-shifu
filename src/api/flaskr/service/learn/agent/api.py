"""Reusable MarkdownFlow 2.0 primitives for hosts outside course execution."""

from .bridge import iter_turn
from .engine import (
    ContentDelta,
    ContinueTurn,
    Engine,
    ErrorEvent,
    Event,
    InteractionRequest,
    InteractionResponseTurn,
    InteractionSpec,
    MemoryUpdated,
    MessageTurn,
    PendingInteraction,
    ScriptBundle,
    Session,
    StartTurn,
    TurnDone,
)
from .engine.interaction import normalize_answer
from .engine.script import substitute_variables
from .gateway_model import GatewayModel
from .legacy_protocol import render_interaction, render_question, unrenderable_reason
from .pagination import LessonPager

__all__ = [
    "ContentDelta",
    "ContinueTurn",
    "Engine",
    "ErrorEvent",
    "Event",
    "GatewayModel",
    "InteractionRequest",
    "InteractionResponseTurn",
    "InteractionSpec",
    "LessonPager",
    "MemoryUpdated",
    "MessageTurn",
    "PendingInteraction",
    "ScriptBundle",
    "Session",
    "StartTurn",
    "TurnDone",
    "iter_turn",
    "normalize_answer",
    "render_interaction",
    "render_question",
    "substitute_variables",
    "unrenderable_reason",
]
