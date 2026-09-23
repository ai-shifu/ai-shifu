"""MarkdownFlow 2.0 engine: run an authored script as an agent.

This is product code and is edited here. It began as ai-shifu/markdown-flow-agent at commit
c31d64f, and that repository still exists to serve the playground and the open-source
release, but it is not an upstream: there is no sync back and forth, and the two are expected to
diverge. Changing how a 2.0 lesson teaches means changing this directory.

The offline tests that came with it live in tests/service/learn/agent/engine/ and run in CI. They
drive the engine with pydantic-ai's FunctionModel, so they need no network and no API key. Keep
them green: they cover the parts that are easy to break and hard to notice, such as pausing and
resuming an interaction, writing a variable to memory, splitting listen mode into segments,
detecting 1.0 syntax and the guard against an empty confirm.

What this package must not do is reach back into the rest of the service. It takes a model, a
script and a session; the host supplies the model (see gateway_model) and decides what to do with
the events.
"""

from .engine import (
    ContinueTurn,
    Engine,
    InteractionResponseTurn,
    MessageTurn,
    Prompts,
    RenderProfile,
    Runner,
    StartTurn,
    TurnInput,
)
from .events import (
    ContentDelta,
    ErrorEvent,
    Event,
    InteractionRequest,
    MemoryUpdated,
    NarrationDelta,
    SegmentEnd,
    SegmentStart,
    ToolCall,
    ToolResult,
    TurnDone,
    Visual,
    parse_event,
    to_sse,
)
from .interaction import InteractionAnswer, InteractionSpec, InteractionType, Option
from .memory import InMemoryMemoryStore, MemoryStore
from .script import (
    ScriptBundle,
    collected_names,
    detect_v1_syntax,
    render_first_prompt,
    substitute_variables,
)
from .segmenter import Narration, Segmenter, SegmentPiece, plain_narration
from .session import (
    InMemorySessionStore,
    PendingInteraction,
    Session,
    SessionStore,
    SQLiteSessionStore,
)

__version__ = '2.3.3'

__all__ = [
    "ContentDelta",
    "ContinueTurn",
    "Engine",
    "ErrorEvent",
    "Event",
    "InMemoryMemoryStore",
    "InMemorySessionStore",
    "InteractionAnswer",
    "InteractionRequest",
    "InteractionResponseTurn",
    "InteractionSpec",
    "InteractionType",
    "MemoryStore",
    "MemoryUpdated",
    "MessageTurn",
    "Narration",
    "NarrationDelta",
    "Option",
    "PendingInteraction",
    "Prompts",
    "RenderProfile",
    "Runner",
    "SQLiteSessionStore",
    "ScriptBundle",
    "SegmentEnd",
    "SegmentPiece",
    "SegmentStart",
    "Segmenter",
    "Session",
    "SessionStore",
    "StartTurn",
    "ToolCall",
    "ToolResult",
    "TurnDone",
    "TurnInput",
    "Visual",
    "collected_names",
    "detect_v1_syntax",
    "parse_event",
    "plain_narration",
    "render_first_prompt",
    "substitute_variables",
    "to_sse",
]
