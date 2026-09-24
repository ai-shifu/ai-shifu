"""Built-in tools: `interact` (deferred; pauses the run) and `remember` (writes memory)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError
from pydantic_ai import CallDeferred, ModelRetry, RunContext
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

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
    # Each option of the script's own `?[...]` questions, as written -> as the grammar reads it,
    # when the script is in the 1.0 notation; see `_as_the_script_writes_it`.
    script_options: dict[str, str] = field(default_factory=dict)
    # Set when the host's scripts pause only where their notation puts a button and this lesson's
    # script has none: a `confirm` is then answered without asking the learner. See
    # `script_pauses` and `Engine(pauses_from_notation=)`.
    no_pauses: bool = False


# The characters a backslash escapes inside `?[...]`, as MarkdownFlow's grammar has it.
_ESCAPABLE = "|/.]"
_FENCED = re.compile(
    r"^[ ]{0,3}(`{3,}|~{3,})[^\n]*\n.*?^[ ]{0,3}\1[ \t]*$", re.MULTILINE | re.DOTALL
)
_VARIABLE = re.compile(r"^\s*%\{\{[^}]*\}\}")


def _is_escape(text: str, index: int) -> bool:
    return (
        index + 1 < len(text) and text[index] == "\\" and text[index + 1] in _ESCAPABLE
    )


def _find_unescaped(text: str, needle: str, start: int = 0) -> int:
    index = start
    while index < len(text):
        if _is_escape(text, index):
            index += 2
            continue
        if text.startswith(needle, index):
            return index
        index += 1
    return -1


def _split_unescaped(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    while (found := _find_unescaped(text, separator, start)) >= 0:
        parts.append(text[start:found])
        start = found + len(separator)
    parts.append(text[start:])
    return parts


def _split_on_single_pipe(text: str) -> list[str]:
    """Split on each unescaped `|` that is not part of a `||`, as the grammar does."""
    parts: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if _is_escape(text, index):
            index += 2
            continue
        if text[index] == "|":
            if text.startswith("||", index):
                index += 2
                continue
            if index and text[index - 1] == "|" and not _is_escape(text, index - 1):
                index += 1
                continue
            parts.append(text[start:index])
            start = index + 1
        index += 1
    parts.append(text[start:])
    return parts


def _unescape(text: str) -> str:
    """Resolve the grammar's escapes in `text`, leaving every other backslash alone."""
    out: list[str] = []
    index = 0
    while index < len(text):
        if _is_escape(text, index):
            out.append(text[index + 1])
            index += 2
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


def script_options(script_text: str) -> dict[str, str]:
    """Map every option of the script's `?[...]` questions, as written, to what it means.

    Split the way MarkdownFlow splits them: a leading `%{{variable}}` and a trailing `...`
    placeholder are not options, `||` separates the choices of a multiple choice and `|` those of
    a single one, and `//` separates what is shown from what is stored. Questions shown inside a
    code fence are examples, not questions. Both halves of `display//value` are entries of their
    own, since the model passes them separately.
    """
    options: dict[str, str] = {}
    for question in _script_questions(script_text):
        for choice in question.choices:
            for half in _split_unescaped(choice, "//")[:2]:
                written = half.strip()
                if written:
                    options[written] = _unescape(written)
    return options


def script_pauses(script_text: str) -> int:
    """Count the places the script pauses the lesson: a `?[...]` that is a single button.

    One choice, no variable to store it in and no text box -- `?[继续]`, `?[准备好了//continue]` --
    is how MarkdownFlow writes "wait here until the learner goes on". A 1.0 lesson pauses there
    and nowhere else.
    """
    return sum(
        1
        for question in _script_questions(script_text)
        if not question.variable
        and not question.text
        and len([c for c in question.choices if c.strip()]) == 1
    )


@dataclass
class _Question:
    """One `?[...]` of a script, split the way MarkdownFlow splits it."""

    variable: bool
    text: bool
    choices: list[str]


def _script_questions(script_text: str) -> list[_Question]:
    """Return the script's `?[...]` questions, outside code fences, in order."""
    text = _FENCED.sub("", script_text)
    questions: list[_Question] = []
    at = 0
    while (start := text.find("?[", at)) >= 0:
        at = start + 2
        if start and text[start - 1] == "\\":
            continue
        end = _find_unescaped(text, "]", at)
        if end < 0:
            break
        at = end + 1
        if text[end + 1 : end + 2] == "(":
            continue  # `?[text](url)` is a link
        raw = text[start + 2 : end]
        body = _VARIABLE.sub("", raw)
        first_line = body.split("\n", 1)[0]
        ellipsis = _find_unescaped(first_line, "...")
        if ellipsis >= 0:
            body = body[:ellipsis]
        # A single bar anywhere makes it single choice, with any `||` left inside an option;
        # otherwise `||` separates the choices of a multiple choice.
        choices = _split_on_single_pipe(body)
        if len(choices) == 1:
            choices = _split_unescaped(body, "||")
        questions.append(
            _Question(
                variable=bool(_VARIABLE.match(raw)),
                text=ellipsis >= 0,
                choices=choices,
            )
        )
    return questions


def _as_the_script_writes_it(option: Option, written: dict[str, str]) -> Option:
    r"""Return a script's option as the script means it, without the escapes of its notation.

    Copying a question from the script, the model copies it character for character, escapes
    included: `a\|b` reached the learner as a button reading `a\|b`, where the author had
    written the option `a|b`. A field the model passed exactly as one of the script's options is
    written is read the way the grammar reads it, so the learner sees what a 1.0 lesson shows.

    Each field is judged on its own, and only against the script's own options: text the model
    already read correctly, text that merely appears in the script's prose or code, and a value
    the model made up are all left as it wrote them.
    """
    return Option(
        display=written.get(option.display, option.display),
        value=(
            written.get(option.value, option.value)
            if option.value is not None
            else None
        ),
    )


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


NO_PAUSE = (
    "No pause here: the script does not ask the learner to stop at this point, so they were not "
    "asked. Go straight on with the next part of the script now."
)


# Below this many visible characters, the same words before the same question are not taken as a
# loop: a short lead-in such as "好的。" can legitimately come before a question asked again.
_LOOP_FLOOR_CHARS = 40


def _visible(text: str) -> str:
    return "".join(text.split())


def _question(
    kind: str,
    prompt: str,
    variable: str | None,
    options: list[Option] | None,
    placeholder: str | None,
) -> tuple[object, ...]:
    """Everything that makes up the question an `interact` call puts to the learner."""
    return (
        kind,
        prompt.strip(),
        variable or None,
        tuple((o.display, o.value or None) for o in options or []),
        (placeholder or "").strip() or None,
    )


def _asked(call: ToolCallPart) -> tuple[object, ...] | None:
    """Return the question an earlier `interact` call put, or None if its arguments do not read."""
    args = call.args_as_dict()
    try:
        options = [Option.model_validate(o) for o in args.get("options") or []]
    except ValidationError:
        return None
    return _question(
        args.get("type"),
        args.get("prompt") or "",
        args.get("variable"),
        options,
        args.get("placeholder"),
    )


def asks_the_answered_question_again(
    ctx: RunContext[Deps],
    kind: str,
    prompt: str,
    variable: str | None,
    options: list[Option] | None = None,
    placeholder: str | None = None,
) -> bool:
    """Whether this call repeats, word for word, the turn that asked a question just answered.

    Seen on the general-education course (2026-09-24): the learner named a book, and the model
    wrote the same paragraph and asked "which book?" again, with the same variable -- every answer
    after that got the identical paragraph and question, 14 times. A question put again after a
    wrong answer is not this: the model says something about the answer first, so the words
    before it differ.

    The questions just answered are all those the last asking response put: a response can ask
    several, and every one is answered before the model goes on.
    """
    messages = ctx.messages
    start = ctx.deps.history_len
    now = _visible(
        "".join(
            part.content
            for msg in messages[start:]
            if isinstance(msg, ModelResponse)
            for part in msg.parts
            if isinstance(part, TextPart)
        )
    )
    if len(now) < _LOOP_FLOOR_CHARS:
        return False
    question = _question(kind, prompt, variable, options, placeholder)
    for index in range(min(start, len(messages)) - 1, -1, -1):
        msg = messages[index]
        if not isinstance(msg, ModelResponse):
            continue
        calls = [
            p
            for p in msg.parts
            if isinstance(p, ToolCallPart) and p.tool_name == "interact"
        ]
        if not calls:
            continue
        if not any(_asked(call) == question for call in calls):
            return False
        return _turn_text_before(messages, index) == now
    return False


def _turn_text_before(messages: list, index: int) -> str:
    """Return the model's text in the turn whose response at `index` asked a question.

    A turn begins with the learner's message or an answer to a question, so the text is
    collected back to the request that carried one.
    """
    parts: list[str] = []
    for msg in reversed(messages[: index + 1]):
        if isinstance(msg, ModelRequest) and any(
            isinstance(p, UserPromptPart)
            or (isinstance(p, ToolReturnPart) and p.tool_name == "interact")
            for p in msg.parts
        ):
            break
        if isinstance(msg, ModelResponse):
            parts[:0] = [p.content for p in msg.parts if isinstance(p, TextPart)]
    return _visible("".join(parts))


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
    if type != "confirm" and asks_the_answered_question_again(
        ctx, type, prompt, variable, options, placeholder
    ):
        # Not a flat refusal: a script can ask again after a wrong answer, with the same
        # correction each time. Put that way, it is said to this answer and so reads differently.
        msg = (
            "The learner has just answered this question, and you have written the same text "
            "as before and asked it again, word for word -- to the learner that is the lesson "
            "stuck in a loop. If their answer completes this step, do not ask again: go on with "
            "the next step of the script, or call `finish` if nothing in it remains. If the "
            "script has you ask again, first say what about this particular answer falls short, "
            "then ask."
        )
        raise ModelRetry(msg)
    if type == "confirm" and text_in_turn(ctx) == 0:
        msg = (
            "You asked the learner to continue without presenting anything in this turn. "
            "Deliver the next part of the script as content first; pause with `confirm` only "
            "after that content, and never answer a continue with another confirm."
        )
        raise ModelRetry(msg)
    if type == "confirm" and ctx.deps.no_pauses:
        # A pause in a lesson whose script has none. The learner is not asked: the lesson simply
        # goes on, as a 1.0 lesson does. Answered rather than refused, so the model carries on in
        # the same turn instead of spending its retries on a call it cannot make.
        return NO_PAUSE
    if ctx.deps.script_options:
        options = [
            _as_the_script_writes_it(o, ctx.deps.script_options) for o in options or []
        ]
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
