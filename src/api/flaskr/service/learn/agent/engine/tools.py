"""Built-in tools: `interact` (deferred; pauses the run) and `remember` (writes memory)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic_ai import CallDeferred, ModelRetry, RunContext
from pydantic_ai.messages import ModelResponse, TextPart

from .interaction import InteractionSpec, InteractionType, Option

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class Deps:
    """What the tools need from the turn they are running in."""

    memory: dict[str, Any]  # session scope (mutated in place)
    user_memory: dict[str, Any]  # user scope (mutated in place)
    listen_mode: bool = False
    uses_v1_syntax: bool = False
    memory_updates: list[tuple[str, str, Any]] = field(
        default_factory=list
    )  # (scope, key, value)
    finished: str | None = None  # set by `finish`; the summary the model gave
    # len(message history) when this turn started; anything after it belongs to this turn.
    history_len: int = 0
    # The host's answer to "can the learner be shown this question?": None if it can, otherwise
    # why not. See `Engine(interaction_check=)`.
    interaction_check: Callable[[InteractionSpec], str | None] | None = None


def text_in_turn(ctx: RunContext[Deps]) -> int:
    """Non-whitespace characters of content the model produced so far in this turn.

    Whitespace does not count: a turn whose only output is a newline has presented nothing to the
    learner, and must not be able to pause on a `confirm`.
    """
    return sum(
        sum(1 for ch in part.content if not ch.isspace())
        for msg in ctx.messages[ctx.deps.history_len :]
        if isinstance(msg, ModelResponse)
        for part in msg.parts
        if isinstance(part, TextPart)
    )


async def interact(
    ctx: RunContext[Deps],
    type: InteractionType,  # noqa: A002 - the model sends this name; it is the tool's contract
    prompt: str,
    options: list[Option] | None = None,
    variable: str | None = None,
    placeholder: str | None = None,
) -> str:
    """Show an interaction to the learner and wait for the answer.

    `single`: exactly one choice. `multi`: several choices. `text`: free text only.
    `single_or_text` / `multi_or_text`: choices plus a text box for the learner's own answer.
    `confirm`: one "continue"-style button; use it ONLY when the script itself asks for a pause
    without a question -- never on your own judgement, not between steps, not after a visual --
    and only after you have presented content in this turn (a confirm on its own is rejected).
    A `confirm` never takes a `variable`: pressing it says "go on", not an answer, and it is
    dropped. To have the learner check something you wrote, ask it as `single`, or write the
    read-back as content and pause with a plain `confirm`.
    Give `options` for every type except `text`. `variable` is ONLY for a memory key the script
    explicitly names (e.g. `%{{name}}` or "store it as X"); leave it empty otherwise.
    The learner's answer is returned as the tool result; then continue the script.
    """
    if type == "confirm" and text_in_turn(ctx) == 0:
        msg = (
            "You asked the learner to continue without presenting anything in this turn. "
            "Deliver the next part of the script as content first; pause with `confirm` only "
            "after that content, and never answer a continue with another confirm."
        )
        raise ModelRetry(msg)
    spec = InteractionSpec(
        type=type,
        prompt=prompt,
        options=options or [],
        variable=variable,
        placeholder=placeholder,
    )
    problem = ctx.deps.interaction_check(spec) if ctx.deps.interaction_check else None
    if problem:
        # Deferred, the question would wait for an answer the learner has no controls to give.
        # Sent back instead, it is asked again in a form the host can show.
        msg = (
            f"The learner cannot be shown this question: {problem}. Call `interact` again "
            "with the same question, rewriting what the problem names: every option must be "
            "non-empty text without `%{{` or `}}`, and the variable must be a short plain name."
        )
        raise ModelRetry(msg)
    raise CallDeferred(metadata=spec.model_dump(mode="json"))


async def remember(
    ctx: RunContext[Deps],
    key: str,
    value: str,
    scope: Literal["session", "user"] = "session",
) -> str:
    """Store something about the learner.

    `key` is a short snake_case identifier; `value` is the learner's own words or the concrete
    fact. `scope="session"` (default) is for this script run (answers, collected variables);
    `scope="user"` is for things that should follow the learner into future sessions
    (preferences, stable facts, requests like "keep answers short"). Overwrites an existing key.
    """
    target = ctx.deps.user_memory if scope == "user" else ctx.deps.memory
    target[key] = value
    ctx.deps.memory_updates.append((scope, key, value))
    return f"remembered {key} ({scope})"


async def finish(ctx: RunContext[Deps], summary: str = "") -> str:
    """Mark the script as delivered to its end.

    Call this once, only after the last step of the script has been completed and nothing in
    it remains to do. `summary` is one short line about what the learner did. Do not call it
    when the script merely pauses, asks a question, or waits for the learner.
    """
    ctx.deps.finished = summary.strip() or "done"
    return "finished"
