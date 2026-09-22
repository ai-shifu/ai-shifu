"""Translate engine events into the events the 1.0 lesson stream already speaks.

The 1.0 run is two layers: it produces `RunMarkdownFlowDTO` events, and everything downstream --
persisting elements, binding TTS audio, assembling listen-mode slides, the SSE frames the browser
reads -- consumes those. Translating into that inner protocol rather than into the outer element
payload is what lets a 2.0 lesson reach the existing frontend without changing any of it.

Interactions translate back into MarkdownFlow's own `?[...]` syntax, because that is what 1.0 puts
on the wire and what the frontend parses. The engine took that syntax apart into an
`InteractionSpec` to show the model a typed tool; this puts it back together -- and then parses its
own output to prove the meaning survived, because that grammar cannot express every string.

Two kinds of event deliberately translate to nothing:

* listen mode (`segment.*`, `narration.*`) needs slide and audio mapping of its own, and belongs
  with the rest of listen mode in its own change;
* tool calls and their results are how the engine talks to the model, not something a learner is
  meant to see.

Nothing calls this yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.i18n import _
from flaskr.service.learn.agent.engine.events import (
    ContentDelta,
    ErrorEvent,
    InteractionRequest,
    MemoryUpdated,
    TurnDone,
)
from flaskr.service.learn.agent.engine.interaction import (
    DEFAULT_CONFIRM_LABEL,
    InteractionSpec,
    Option,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
    VariableUpdateDTO,
)

if TYPE_CHECKING:
    from flaskr.service.learn.agent.engine.events import Event

# MarkdownFlow separates choices with a single bar, and multiple-choice ones with a double bar.
_SINGLE_CHOICE_SEPARATOR = " | "
_MULTI_CHOICE_SEPARATOR = " || "
# A trailing `...placeholder` inside the brackets means free text is accepted as well.
_FREE_TEXT_MARKER = "..."
# `Display//value` shows one thing and stores another.
_DISPLAY_VALUE_SEPARATOR = "//"

_MULTI_CHOICE_TYPES = frozenset({"multi", "multi_or_text"})
# A confirm prompt up to this long is a button label ("继续"); longer, it is an instruction.
_CONFIRM_LABEL_MAX_CHARS = 12
_FREE_TEXT_TYPES = frozenset({"text", "single_or_text", "multi_or_text"})


class UnrepresentableInteractionError(Exception):
    """An interaction that MarkdownFlow cannot carry without changing what it asks.

    The grammar has no escape sequence, so option text carrying its delimiters reshapes the
    controls: a display holding `|` becomes two choices, one holding `//` loses half of itself to
    the stored value, one holding `...` turns the rest into a text box, and `]` ends the
    interaction early. Leading and trailing spaces disappear as well, which matters because the
    engine matches a submitted answer against the option string it was given, unmodified.

    Raised rather than rendered approximately: a learner answering controls that no longer match
    what the model asked produces an answer the engine will reject, and neither of them can see
    why. The caller decides what to do instead -- asking in plain text is one option.
    """


def _render_option(option: Option) -> str:
    """Render one choice, keeping a stored value distinct from the text the learner reads.

    The value is written whenever the spec carries one, including an empty string: `stored` on the
    spec returns exactly that, so omitting it would silently store the display instead.
    """
    if option.value is None:
        return option.display
    return f"{option.display}{_DISPLAY_VALUE_SEPARATOR}{option.value}"


def _compose(spec: InteractionSpec) -> str:
    separator = (
        _MULTI_CHOICE_SEPARATOR
        if spec.type in _MULTI_CHOICE_TYPES
        else _SINGLE_CHOICE_SEPARATOR
    )
    parts = [_render_option(option) for option in spec.options]
    if spec.type in _FREE_TEXT_TYPES:
        parts.append(f"{_FREE_TEXT_MARKER}{spec.placeholder or ''}")

    prefix = f"%{{{{{spec.variable}}}}} " if spec.variable else ""
    return f"?[{prefix}{separator.join(parts)}]"


def _verify_round_trip(spec: InteractionSpec, rendered: str) -> None:
    """Parse what was just rendered and require it to still ask the same thing.

    Checking against the parser the 1.0 path uses beats enumerating dangerous characters: it
    catches the delimiters, the whitespace the grammar drops, and whatever else the grammar does
    that this module does not know about.
    """
    from markdown_flow import InteractionParser

    parsed = InteractionParser().parse(rendered)
    if not parsed or parsed.get("type") is None:
        message = f"MarkdownFlow cannot parse {rendered!r}"
        raise UnrepresentableInteractionError(message)

    buttons = parsed.get("buttons") or []
    round_tripped = [(b.get("display"), b.get("value")) for b in buttons]
    expected = [(option.display, option.stored) for option in spec.options]
    if round_tripped != expected:
        message = f"options survive as {round_tripped!r}, not {expected!r}"
        raise UnrepresentableInteractionError(message)

    if parsed.get("variable") != spec.variable and (
        spec.variable or parsed.get("variable")
    ):
        message = (
            f"variable survives as {parsed.get('variable')!r}, not {spec.variable!r}"
        )
        raise UnrepresentableInteractionError(message)

    if spec.type in _FREE_TEXT_TYPES:
        placeholder = parsed.get("question")
        if (placeholder or "") != (spec.placeholder or ""):
            message = (
                f"placeholder survives as {placeholder!r}, not {spec.placeholder!r}"
            )
            raise UnrepresentableInteractionError(message)

    if bool(parsed.get("is_multi_select")) != (spec.type in _MULTI_CHOICE_TYPES):
        message = f"{rendered!r} does not preserve how many answers are allowed"
        raise UnrepresentableInteractionError(message)


def render_interaction(spec: InteractionSpec) -> str:
    """Rebuild the MarkdownFlow interaction the frontend expects from the engine's typed spec.

    Raises `UnrepresentableInteractionError` when the result would ask something other than the spec
    does. The variable prefix is emitted only when the script named one to store the answer under;
    a confirm carries none by construction, since pressing continue is not an answer.
    """
    rendered = _compose(spec)
    _verify_round_trip(spec, rendered)
    return rendered


def _in_the_learner_s_language(spec: InteractionSpec) -> InteractionSpec:
    """Give a confirm the host's word for carrying on, where the model named none.

    The engine fills an unlabelled confirm with an English default, and it reached learners as a
    `Continue` button under a lesson taught in Chinese. Only that default is replaced: a label the
    model did write is the lesson's own wording and is left exactly as it wrote it.

    Which is why this runs before a short prompt is turned into the button's text, and not after.
    Afterwards, a model that had written `Continue` itself would be indistinguishable from one
    that wrote nothing, and would have its own word swapped for the host's.
    """
    if spec.type != "confirm" or not spec.options:
        return spec
    if spec.options[0].display != DEFAULT_CONFIRM_LABEL:
        return spec
    return InteractionSpec(
        type="confirm",
        prompt=spec.prompt,
        options=[Option(display=_("server.learn.continueButton"), value="continue")],
    )


def translate(
    event: Event,
    *,
    outline_bid: str,
    generated_block_bid: str,
) -> list[RunMarkdownFlowDTO]:
    """Translate one engine event into the 1.0 events it corresponds to.

    Returns a list because the correspondence is not one to one: an interaction arrives as a
    question plus its controls and leaves as the text event the learner reads followed by the
    interaction event the frontend renders. Events that 1.0 has no place for return nothing.
    """
    if isinstance(event, ContentDelta):
        if not event.text:
            return []
        return [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.CONTENT,
                content=event.text,
            )
        ]

    if isinstance(event, InteractionRequest):
        events = []
        spec = event.spec
        # Stripped only to decide whether there is a question at all: the text itself goes out as
        # the model wrote it, because the frontend renders it as Markdown and leading indentation
        # or a trailing hard break changes what the learner sees.
        prompt = spec.prompt
        # Before the rewrite below, not after: that rewrite puts the model's own words on the
        # button, and a model that wrote `Continue` would otherwise have them taken for the
        # engine's default and replaced.
        spec = _in_the_learner_s_language(spec)
        if (
            spec.type == "confirm"
            and 0 < len(prompt.strip()) <= _CONFIRM_LABEL_MAX_CHARS
        ):
            # A confirm's prompt is what the button should say -- the model writes "继续" there --
            # not a line of lesson text. Sent as content it appeared after the lesson's last
            # sentence, followed by a button reading "Continue" in whatever language the lesson
            # was not in. A longer prompt is an instruction to the learner and stays as text.
            spec = InteractionSpec(
                type="confirm",
                prompt="",
                options=[Option(display=prompt.strip(), value="continue")],
            )
            prompt = ""
        if prompt.strip():
            events.append(
                RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.CONTENT,
                    content=prompt,
                )
            )
        events.append(
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.INTERACTION,
                content=render_interaction(spec),
            )
        )
        return events

    if isinstance(event, MemoryUpdated):
        return [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=GeneratedType.VARIABLE_UPDATE,
                content=VariableUpdateDTO(
                    variable_name=event.key,
                    variable_value="" if event.value is None else str(event.value),
                ),
            )
        ]

    if isinstance(event, TurnDone):
        # Every turn ends in a boundary, a turn that stopped to ask something included. The
        # browser never sees a BREAK -- the SSE framing suppresses it -- but the element adapter
        # finalises the block on it: every element the turn streamed is written then, with its
        # audio. Without it, a turn that ended on a question was never finalised, so its text
        # survived only where an audio patch happened to write it, and its cards not at all --
        # a learner reloading the lesson got the narration back over an empty page.
        #
        # `end` means this turn ran out of content, not that the lesson is over -- the model often
        # never calls `finish`, and the host decides from the script whether anything remains. The
        # element adapter marks DONE terminal and the browser closes the stream on it, so only a
        # finished lesson may use it; BREAK is the boundary a lesson can continue past.
        return [
            RunMarkdownFlowDTO(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                type=(
                    GeneratedType.DONE
                    if event.reason == "finished"
                    else GeneratedType.BREAK
                ),
                content="",
            )
        ]

    if isinstance(event, ErrorEvent):
        # Nothing: 1.0 has no error event, and its DONE is read by the browser as terminal
        # *success* -- it clears the failed flag and closes the stream. Reporting a failure that
        # way would be worse than silence. The host ends the request without a terminal event, so
        # the browser keeps the failure it already recorded.
        return []

    return []
