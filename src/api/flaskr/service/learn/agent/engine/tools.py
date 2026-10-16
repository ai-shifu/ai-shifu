"""Built-in tools: `interact` (deferred; pauses the run) and `remember` (writes memory)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError
from pydantic_ai import CallDeferred, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from .computed_example import (
    ComputedExample,
    ExampleError,
    has_computed_example,
    render_example,
)
from .direction import (
    DirectionFeedback,
    FeedbackReview,
    feedback_arguments,
    has_direction,
)
from .interaction import InteractionSpec, InteractionType, Option
from .interaction_markup import INTERACTION_MARKUP_RETRY, contains_interaction_markup
from .session import answer_fingerprint

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic_ai.capabilities import RawToolArgs
    from pydantic_ai.tools import ToolDefinition


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
    # Transient request guidance; never persisted as learner evidence or a grade.
    resuming_interaction: bool = False
    authored_text: str = ""
    authored_answer_reference: str | None = None
    direction_answers: dict[str, str] = field(default_factory=dict)
    direction_inputs: dict[str, InteractionSpec] = field(default_factory=dict)
    direction_sections: dict[str, str] = field(default_factory=dict)
    direction_rendered: dict[str, str] = field(default_factory=dict)
    computed_examples: bool = False
    example_rendered: dict[str, str] = field(default_factory=dict)
    feedback_contract: bool = False
    feedback_review: FeedbackReview | None = None
    hidden_feedback_responses: set[int] = field(default_factory=set)
    _hidden_feedback_objects: dict[int, ModelResponse] = field(
        default_factory=dict, init=False, repr=False
    )
    feedback_text_pending: bool = False
    feedback_text_delivered: bool = False
    # The host's answer to "can the learner be shown this question?": None if it can, otherwise
    # why not. See `Engine(interaction_check=)`.
    interaction_check: Callable[[InteractionSpec], str | None] | None = None
    # Each option of the script's own `?[...]` questions, as written -> as the grammar reads it,
    # when the script is in the 1.0 notation; see `_as_the_script_writes_it`.
    script_options: dict[str, str] = field(default_factory=dict)
    # Authored text-input questions, used only to repair an extra placeholder button.
    script_text_inputs: tuple[_Question, ...] = ()
    literal_interaction_markup: frozenset[str] = frozenset()
    interaction_markup_pending: bool = False
    # Set when the host's scripts pause only where their notation puts a button and this lesson's
    # script has none: a `confirm` is then answered without asking the learner. See
    # `script_pauses` and `Engine(pauses_from_notation=)`.
    no_pauses: bool = False
    # None preserves a portable host's existing unrestricted memory contract.
    memory_keys: frozenset[str] | None = None
    memory_reserved_keys: frozenset[str] = frozenset()
    memory_readonly_prefixes: tuple[str, ...] = ()
    memory_deleted_keys: frozenset[str] = frozenset()
    request_inputs: tuple[str, ...] = ()
    memory_current_inputs: tuple[str, ...] = ()
    memory_request_check: Callable[[str, str, str], Awaitable[bool]] | None = None
    # Match the initial prompt's exclusion of answers this lesson collects again.
    memory_recall_excluded_keys: frozenset[str] = frozenset()
    answer_hashes: dict[str, str] = field(default_factory=dict)
    memory_recall_blocked_keys: frozenset[str] = frozenset()
    # Exact original teaching available only for this run's request projection.
    teaching_history: dict[str, str] = field(default_factory=dict)
    # Original messages before request projection.
    exercise_history: tuple[Any, ...] = ()
    exercise_evidence: list[dict[str, Any]] | None = None  # Frozen within this run.
    exercise_read_offset: int | None = 0  # Next contiguous original-evidence page.
    exercise_report_totals: dict[str, int | None] | None = None

    def hide_feedback_response(self, response: ModelResponse) -> None:
        """Track withheld prose until a successful replacement actually supplies it."""
        # SDK history projection can release the original response. Keep its ID
        # unique until this turn's Deps is discarded, including final projection.
        self._hidden_feedback_objects[id(response)] = response
        self.hidden_feedback_responses.add(id(response))
        if any(isinstance(p, TextPart) and p.content.strip() for p in response.parts):
            self.feedback_text_pending = True

    def accept_feedback_response(
        self, response: ModelResponse, review: FeedbackReview | None
    ) -> None:
        """Commit delivery state only after every tool succeeds or truly defers."""
        if review is not None:
            self.feedback_review = review
        if any(isinstance(p, TextPart) and p.content.strip() for p in response.parts):
            self.feedback_text_pending = False
            self.feedback_text_delivered = True


# The characters a backslash escapes inside `?[...]`, as MarkdownFlow's grammar has it.
_ESCAPABLE = "|/.]"


def recall_exclusions(deps: Deps) -> frozenset[str]:
    """Exclude unanswered or replaced answer copies and deleted historical replays."""
    answered = {
        key
        for key, digest in deps.answer_hashes.items()
        if isinstance(digest, str)
        and key in deps.memory
        and answer_fingerprint(deps.memory[key]) == digest
    }
    return (
        deps.memory_recall_excluded_keys.difference(answered)
        | deps.memory_recall_blocked_keys
    )


_FENCED = re.compile(
    r"^[ ]{0,3}(`{3,}|~{3,})[^\n]*\n.*?^[ ]{0,3}\1[ \t]*$", re.MULTILINE | re.DOTALL
)
_VARIABLE = re.compile(r"^\s*%\{\{([^}]*)\}\}")


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

    variable: str | None
    text: bool
    choices: list[str]
    placeholder: str | None
    written_placeholder: str | None
    multi: bool


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
        multi = len(choices) == 1 and len(_split_unescaped(body, "||")) > 1
        if len(choices) == 1:
            choices = _split_unescaped(body, "||")
        questions.append(
            _Question(
                variable=(match.group(1).strip() or None)
                if (match := _VARIABLE.match(raw))
                else None,
                text=ellipsis >= 0,
                choices=choices,
                placeholder=_unescape(first_line[ellipsis + 3 :].strip())
                if ellipsis >= 0
                else None,
                written_placeholder=first_line[ellipsis + 3 :].strip()
                if ellipsis >= 0
                else None,
                multi=multi,
            )
        )
    return questions


def script_text_inputs(script_text: str) -> tuple[_Question, ...]:
    """Read authored input hints; examples in comments do not define a learner question."""
    lines: list[str] = []
    opening: str | None = None
    for line in script_text.splitlines():
        fence = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$", line)
        if opening is not None:
            if (
                fence
                and fence.group(1)[0] == opening[0]
                and len(fence.group(1)) >= len(opening)
                and not fence.group(2).strip()
            ):
                opening = None
        elif fence:
            opening = fence.group(1)
        elif line.expandtabs(4).startswith("    "):
            lines.append("")  # Indented Markdown code cannot declare lesson controls.
        else:
            lines.append(line)
    text = re.sub(r"<!--.*?-->", "", "\n".join(lines), flags=re.DOTALL)
    return tuple(q for q in _script_questions(text) if q.placeholder)


def normalize_script_text_input(
    spec: InteractionSpec,
    questions: tuple[_Question, ...],
) -> InteractionSpec:
    """Restore a missing text hint or remove its duplicate generated choice.

    The remaining display/value pairs must be the author's exact ordered choices. A hint that
    the author also wrote as a real choice, another question, or a model-created option is kept.
    Text-only questions must match the copied prompt and the same variable.
    Ambiguous questions and explicitly supplied placeholders are left unchanged.
    """
    if spec.type == "text" and not spec.options and not spec.placeholder:
        hints = {
            q.placeholder
            for q in questions
            if q.variable == spec.variable
            and not any(c.strip() for c in q.choices)
            and spec.prompt.strip() in (q.placeholder, q.written_placeholder)
        }
        if len(hints) == 1 and (hint := next(iter(hints))):
            return spec.model_copy(update={"placeholder": hint})
    candidates: dict[str, InteractionSpec] = {}
    submitted = [(o.display, o.stored) for o in spec.options]
    for question in questions:
        if question.variable != spec.variable:
            continue
        kinds = (
            ("multi", "multi_or_text")
            if question.multi
            else ("single", "single_or_text", "text")
        )
        if spec.type not in kinds or spec.placeholder not in (
            None,
            "",
            question.placeholder,
            question.written_placeholder,
        ):
            continue
        authored: list[tuple[str, str]] = []
        for choice in question.choices:
            if not choice.strip():
                continue
            halves = [
                _unescape(half.strip()) for half in _split_unescaped(choice, "//")[:2]
            ]
            authored.append((halves[0], halves[1] if len(halves) > 1 else halves[0]))
        hint = question.placeholder or ""
        forms = {hint, question.written_placeholder or hint}
        extras = {
            (marker + display, marker + value)
            for marker in ("", "...")
            if (marker + hint, marker + hint) not in authored
            for display in forms
            for value in forms
            if (marker + display, marker + value) not in authored
        }
        remaining = [pair for pair in submitted if pair not in extras]
        if submitted == authored:
            candidate = spec
        elif remaining == authored and len(remaining) < len(submitted):
            kind: InteractionType = (
                "multi_or_text" if question.multi else "single_or_text"
            )
            candidate = spec.model_copy(
                update={
                    "type": kind if authored else "text",
                    "options": [
                        o for o in spec.options if (o.display, o.stored) not in extras
                    ],
                    "placeholder": hint,
                }
            )
        else:
            continue
        candidates[candidate.model_dump_json()] = candidate
    return next(iter(candidates.values())) if len(candidates) == 1 else spec


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


LESSON_OVER = (
    "The lesson is over: you called `finish`, so the learner is not asked anything more. Write "
    "nothing further."
)


# Like the host's `continue`, this tells a model to go on, and one that has delivered the whole
# script has nothing to go on with: told only to carry on, it wrote the entire lesson over again,
# on 3 of 21 pauses answered this way in local sweeps of the general-education course.
NO_PAUSE = (
    "No pause here: the script does not ask the learner to stop at this point, so they were not "
    "asked. Go straight on with the next part of the script: the first step you have not "
    "delivered yet. Do not repeat, summarise or restate anything you already delivered. If "
    "nothing in the script remains to be delivered, write nothing at all and call `finish`."
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
    written: dict[str, str],
) -> tuple[object, ...]:
    r"""Return everything that makes up the question an `interact` call puts to the learner.

    Its choices as the learner sees them: `a\|b` copied from a 1.0 script and `a|b` are one
    button (see `_as_the_script_writes_it`).
    """
    if written:
        options = [_as_the_script_writes_it(o, written) for o in options or []]
    return (
        kind,
        prompt.strip(),
        variable or None,
        tuple((o.display, o.value or None) for o in options or []),
        (placeholder or "").strip() or None,
    )


def _asked(call: ToolCallPart, written: dict[str, str]) -> tuple[object, ...] | None:
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
        written,
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
    several, and every one is answered before the model goes on. On both sides only the text
    written before the call counts: a response can go on writing after a call, and text between
    two calls came before the second one only.
    """
    messages = ctx.messages
    start = ctx.deps.history_len
    now = _visible("".join(_text_up_to(messages[start:], ctx.tool_call_id)))
    if len(now) < _LOOP_FLOOR_CHARS:
        return False
    written = ctx.deps.script_options
    question = _question(kind, prompt, variable, options, placeholder, written)
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
        matching = [call for call in calls if _asked(call, written) == question]
        return any(
            _turn_text_before(messages, index, call.tool_call_id) == now
            for call in matching
        )
    return False


def _text_up_to(messages: list, call_id: str | None) -> list[str]:
    """Return the model's text in `messages`, stopping at the call `call_id` if they hold it."""
    parts: list[str] = []
    for msg in messages:
        if not isinstance(msg, ModelResponse):
            continue
        for part in msg.parts:
            if isinstance(part, ToolCallPart) and part.tool_call_id == call_id:
                return parts
            if isinstance(part, TextPart):
                parts.append(part.content)
    return parts


def _turn_text_before(messages: list, index: int, call_id: str) -> str:
    """Return the model's text in the turn that asked the call `call_id`, up to that call.

    `index` is the response holding the call. A turn begins with the learner's message or an
    answer to a question, so the text is collected back to the request that carried one.
    """
    begin = 0
    for i in range(index, -1, -1):
        msg = messages[i]
        if isinstance(msg, ModelRequest) and any(
            isinstance(p, UserPromptPart)
            or (isinstance(p, ToolReturnPart) and p.tool_name == "interact")
            for p in msg.parts
        ):
            begin = i + 1
            break
    return _visible("".join(_text_up_to(messages[begin : index + 1], call_id)))


def current_tool_response(ctx: RunContext[Deps]) -> ModelResponse | None:
    """Find the complete response containing this tool, including concurrent siblings."""
    return next(
        (
            m
            for m in reversed(ctx.messages)
            if isinstance(m, ModelResponse)
            and any(
                isinstance(p, ToolCallPart) and p.tool_call_id == ctx.tool_call_id
                for p in m.parts
            )
        ),
        None,
    )


def validate_computed_call(ctx: RunContext[Deps]) -> None:
    """Reject the complete computed batch before any tool can change state."""
    response = current_tool_response(ctx)
    if (
        response is not None
        and any(
            isinstance(part, ToolCallPart)
            and has_computed_example(
                part, include_unparseable=ctx.deps.computed_examples
            )
            for part in response.parts
        )
        and sum(isinstance(part, ToolCallPart) for part in response.parts) != 1
    ):
        if ctx.deps.direction_sections:
            ctx.deps.hide_feedback_response(response)
        message = "computed_example must use the sole existing interact call; do not add a planning or memory call"
        raise ModelRetry(message)


class ComputedExampleGuard(AbstractCapability[Deps]):
    """Apply computed sole-call validation to built-in and supplied toolsets."""

    async def before_tool_validate(
        self,
        ctx: RunContext[Deps],
        *,
        args: RawToolArgs,
        **_tool_metadata: object,
    ) -> RawToolArgs:
        """Guard before native argument validators and external tool dispatch."""
        validate_computed_call(ctx)
        return args


def validate_direction_call(
    ctx: RunContext[Deps], *_args: object, **_kwargs: object
) -> None:
    """Reject mixed direction calls before any built-in tool can change state."""
    validate_computed_call(ctx)
    response = current_tool_response(ctx)
    if (
        response is not None
        and any(
            isinstance(p, ToolCallPart) and has_direction(p) for p in response.parts
        )
        and sum(isinstance(p, ToolCallPart) for p in response.parts) != 1
    ):
        message = "structured direction must be the sole tool call in its response"
        raise ModelRetry(message)
    if response is not None and ctx.deps.feedback_contract:
        problem, _ = feedback_response_problem(ctx.deps, response)
        if problem:
            ctx.deps.hide_feedback_response(response)
            raise ModelRetry(
                problem + "; correct the whole response before any display"
            )


def feedback_response_problem(
    deps: Deps, response: ModelResponse
) -> tuple[str | None, FeedbackReview | None]:
    """Gate visible feedback and terminal tools, without making semantic judgments."""
    if not deps.feedback_contract or not deps.direction_sections:
        return None, None
    calls = [p for p in response.parts if isinstance(p, ToolCallPart)]
    reviews = []
    for call in calls:
        try:
            value = feedback_arguments(call).get("review")
            if value is not None:
                reviews.append(FeedbackReview.model_validate(value))
        except (TypeError, ValueError):
            return "invalid feedback branch declaration", None
    # Schema-required sibling declarations must represent one identical decision.
    if reviews and any(review != reviews[0] for review in reviews[1:]):
        return "declare one feedback branch for this response", None
    if any(has_direction(call) for call in calls):
        if reviews or deps.feedback_review is not None:
            return (
                "checking direction cannot be mixed with an ordinary feedback branch",
                None,
            )
        return (
            None,
            None,
        )  # interact validates its entire structured call before display.
    delivery_problem = None
    if (
        deps.feedback_text_pending
        and any(call.tool_name in ("interact", "finish") for call in calls)
        and not any(
            isinstance(p, TextPart) and p.content.strip() for p in response.parts
        )
    ):
        delivery_problem = (
            "Earlier feedback prose was not displayed. Regenerate complete authored "
            "feedback as content with its valid tool/branch before pausing or finishing; "
            "a replacement control or internal review reason alone cannot deliver it. "
            "Do not restore rejected prose verbatim or skip the author's stage"
        )
    review = None
    if reviews:
        review = reviews[0]
        if problem := review.problem(
            deps.direction_answers, deps.direction_sections, deps.authored_text
        ):
            if review.answer_id not in deps.direction_sections:
                problem += "; supported answer_id values: " + json.dumps(
                    sorted(deps.direction_sections)
                )
            return "; ".join(p for p in (problem, delivery_problem) if p), None
        if deps.feedback_review is not None and review != deps.feedback_review:
            return (
                "do not change an already displayed feedback branch in this turn",
                None,
            )
    if delivery_problem:
        return delivery_problem, None
    if (
        deps.feedback_review is None
        and (
            any(isinstance(p, TextPart) and p.content.strip() for p in response.parts)
            or any(call.tool_name in ("interact", "finish") for call in calls)
        )
        and review is None
    ):
        return (
            "Declare the feedback branch in interact/finish.feedback: a checking direction object "
            "for authored correction; otherwise an ordinary review object with "
            "the actual answer_id, phase accepted/clarification/authored_help, exact "
            "submission_quote and internal reason. authored_help also requires exact "
            "current rule_quote permitting that help now. Do not skip the author's stage. "
            "A read-only lookup without free content can precede the declaration",
            None,
        )
    selected = review or deps.feedback_review
    if (
        selected is not None
        and selected.phase == "accepted"
        and any(call.tool_name in ("interact", "finish") for call in calls)
        and not deps.feedback_text_delivered
        and not any(
            isinstance(p, TextPart) and p.content.strip() for p in response.parts
        )
        and not selected.rule_quote
    ):
        return (
            "Accepted feedback needs the author's confirmation and explanation as content "
            "before navigation or finish; an internal reason or control prompt is not "
            "teaching. For explicitly authored control-only acceptance, supply its exact "
            "rule_quote and explain that exception in reason. Otherwise deliver the "
            "authored feedback with the valid branch and tool in this response",
            None,
        )
    return None, review


async def interact(
    ctx: RunContext[Deps],
    type: InteractionType,  # noqa: A002 - the model sends this name; it is the tool's contract
    prompt: str,
    options: list[Option] | None = None,
    variable: str | None = None,
    placeholder: str | None = None,
    direction: DirectionFeedback | None = None,
    review: FeedbackReview | None = None,
    feedback: DirectionFeedback | FeedbackReview | None = None,
    computed_example: ComputedExample | None = None,
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
    explicitly names; follow the host memory policy for eligible declarations. Leave it empty
    otherwise.
    The learner's answer is returned as the tool result; then continue the script.
    Before personal feedback and the next interaction, cite the original submission
    supporting each claimed misconception. A quoted denial of prior storage does not
    establish confusion about disk files; present an unsupported authored distinction
    generally, never as "your earlier mistake". Describe omissions without inventing
    beliefs, habits or causes. Apply this after corrections as well as wrong answers.
    Judge coverage by the authored acceptance rule and the full submitted meaning:
    do not ask again for a point already supplied through equivalent wording or
    concrete examples. A missing category label alone is not a missing concept.
    For corrections, apply the current hint stage and aspect limit from the author
    across content and every interaction field. A one-aspect hint must not expose
    other gaps in the question, options or placeholder. Ask for the authored correction,
    not every internally identified gap; do not supply a complete answer when the
    author calls for a graduated hint. Do not impose these limits when not authored.
    When complete-answer disclosure is forbidden, a worked answer or an ordered
    answer checklist followed by "try again" still violates that limit. Keep
    direction-only hints about what to examine rather than what answer to copy.
    At an authored checking-direction stage, leave the guiding question unanswered:
    briefly identify the issue and follow the authored aspect and question limits.
    Ask one bounded question only when the author limits the turn to one aspect or
    one question. Preserve authored multiplicity when several are permitted or
    required; do not invent a one-question limit when no count is authored. Then
    wait without worked reasoning or several explanatory paragraphs. Later steps or examples
    require the author's next help stage; reporting prior knowledge help as a
    hint does not itself authorize skipping a correction stage. Follow explicit
    author rules that permit immediate explanation or a different progression.
    An authored navigation with one choice is still `single`, not an optional `confirm`.
    Do not replace an unanswered navigation with the following question's input. If the
    author puts navigation after answer feedback/explanation, call this tool for that
    navigation alone and wait; only its returned selection permits the following step.
    Do not include the following question in the same response as that explanation.
    When no intervening navigation is authored, follow the author's next step normally.

    For an authored checking-direction correction of a uniquely anchored text input
    with an authored aspect/question count,
    send `direction` in this same tool call instead of writing free content. Copy
    `answer_id` from the returned interaction, `rule_quote` from the author's stage
    rule, and each criterion from the current authored section. Select only the
    genuinely unmatched focus or focuses allowed now. Copy the authored aspect
    positive limit; null is invalid. Never invent or relax it. Each focus
    has an internal observed issue and one unanswered guiding question, without worked
    reasoning, compound checks or a list of the other gaps. Quote actual submitted
    evidence for a contradiction; use null for an omission, never an authored sample
    mistake. `accepted_quotes` contains unique exact correct answer excerpts for
    authored acknowledgement, or []. Only accepted/contradicted answer quotes and
    unanswered questions are displayed; diagnoses/criteria stay internal. The host
    checks provenance, not correctness or semantic focus.
    Use type `text`, an empty `prompt`, and the same authored placeholder and eligible
    variable as the answered input. Do not add another tool call or any free
    content to that model response. This collects the correction directly, without
    a planning request. For passing answers, later authored help, navigation,
    clarification, stages without an authored count, multiple questions within one
    aspect, or an input without an
    exact authored anchor, omit `direction`
    and follow the ordinary authored behavior.
    When the host requires an explicit feedback branch for supported returned
    text, ordinary feedback attaches `review` here or to its first existing read,
    memory or finish call. A direction uses `direction` alone. Follow the host's
    source/phase instructions without an additional planning request.
    """
    if ctx.deps.finished is not None:
        # Nothing is asked once the lesson is over; see the `finished` branch of `run_turn`.
        return LESSON_OVER
    if feedback is not None:
        if direction is not None or review is not None:
            message = "Use feedback without legacy direction/review fields"
            raise ModelRetry(message)
        if isinstance(feedback, DirectionFeedback):
            direction = feedback
        else:
            review = feedback
    validate_direction_call(ctx, review=review)
    response = current_tool_response(ctx)
    example_text = None
    if computed_example is not None:
        if (
            not ctx.deps.computed_examples
            or not ctx.deps.direction_sections
            or direction is not None
            or (type == "confirm" and ctx.deps.no_pauses)
        ):
            if response is not None and ctx.deps.direction_sections:
                ctx.deps.hide_feedback_response(response)
            message = "computed_example requires a supported returned text input and an available authored interaction; it cannot accompany a checking direction or an unavailable confirm"
            raise ModelRetry(message)
        try:
            example_text = "\n\n" + render_example(computed_example)
        except ExampleError as exc:
            if response is not None:
                ctx.deps.hide_feedback_response(response)
            raise ModelRetry(
                str(exc) + "; correct the complete interaction before display"
            ) from exc
    if variable and variable.startswith(ctx.deps.memory_readonly_prefixes):
        message = "This variable is a read-only reference. Ask using a local variable instead."
        raise ModelRetry(message)
    if ctx.deps.memory_keys is not None and variable not in ctx.deps.memory_keys:
        variable = None
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
    if type == "confirm" and text_in_turn(ctx) == 0 and example_text is None:
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
    spec = normalize_script_text_input(spec, ctx.deps.script_text_inputs)
    if direction is not None:
        problem = direction.problem(ctx.deps.authored_text, ctx.deps.direction_answers)
        if direction.answer_id not in ctx.deps.direction_sections:
            problem = (
                "direction.answer_id must name an interaction returned in this turn; "
                "supported answer_id values: "
                + json.dumps(sorted(ctx.deps.direction_sections))
            )
        section = ctx.deps.direction_sections.get(direction.answer_id)
        previous = ctx.deps.direction_inputs.get(direction.answer_id)
        if not problem and (
            section is None
            or any(f.criterion_quote not in section for f in direction.focuses)
        ):
            problem = "direction criteria require the exact current authored section"
        if not problem and (
            previous is None
            or spec.type != "text"
            or spec.prompt != ""
            or spec.placeholder != previous.placeholder
            or spec.variable != previous.variable
        ):
            problem = (
                "direction requires an empty prompt and the original text input binding"
            )
        if not problem and contains_interaction_markup(
            direction.render(), ctx.deps.literal_interaction_markup
        ):
            problem = "direction must not contain unexecuted interaction markup"
        if not problem and (
            response is None
            or any(
                isinstance(p, TextPart) and p.content.strip() for p in response.parts
            )
            or sum(isinstance(p, ToolCallPart) for p in response.parts) != 1
        ):
            problem = "direction must be the sole tool call, without free content in its response"
        if problem:
            raise ModelRetry(
                problem + "; correct the whole call before anything is displayed"
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
    ctx.deps.interaction_markup_pending = False
    if direction is not None:
        ctx.deps.direction_rendered[ctx.tool_call_id] = direction.render()
    if example_text is not None:
        ctx.deps.example_rendered[ctx.tool_call_id] = example_text
    raise CallDeferred(metadata=spec.model_dump(mode="json"))


# Bound model-authored notes, not author-named interaction answers or loaded history.
# Key length matches the host's variable storage; lengths count Unicode characters.
_MEMORY_KEY_LIMIT = 255
_MEMORY_VALUE_LIMIT = 2000
_MEMORY_ENTRY_LIMIT = 100
# Match the JSON character count used by the initial memory prompt, including escaping.
_MEMORY_SCOPE_LIMIT = 32_768


def _memory_capacity_error(target: dict[str, Any], key: str, value: str) -> str | None:
    """Check the current scope immediately before and after asynchronous admission."""
    if key not in target and len(target) >= _MEMORY_ENTRY_LIMIT:
        return "Not remembered: this scope has 100 or more entries. Continue teaching."
    candidate_size = len(
        json.dumps({**target, key: value}, ensure_ascii=False, indent=2)
    )
    if candidate_size > _MEMORY_SCOPE_LIMIT and candidate_size > len(
        json.dumps(target, ensure_ascii=False, indent=2)
    ):
        return (
            "Not remembered: this would grow the scope beyond its 32768-character JSON budget. "
            "Continue teaching."
        )
    return None


async def memory_admission_error(
    deps: Deps, key: str, value: str, request: str | None
) -> str | None:
    """Require declared permission or a verified, real learner request before a write."""
    if key.startswith(deps.memory_readonly_prefixes):
        return "this key is a read-only reference"
    if deps.memory_keys is None or (
        key in deps.memory_keys and key not in deps.memory_deleted_keys
    ):
        return None
    if key.startswith("sys_") or key in deps.memory_reserved_keys:
        return "only the script can declare a system-profile key"
    if key in deps.memory_deleted_keys and request not in deps.memory_current_inputs:
        return "restoring deleted memory requires a new explicit request in this turn"
    if not request or request not in deps.request_inputs or len(request) > 4096:
        return "quote a complete current learner request of at most 4096 characters"
    if deps.memory_request_check is not None:
        try:
            if await deps.memory_request_check(request, key, value):
                return None
        except Exception:
            # A failed admission service must not fail teaching or authorize a write.
            return "the learner's explicit request could not be verified"
    return "the learner's explicit request could not be verified"


async def prepare_feedback_tool(
    ctx: RunContext[Deps], definition: ToolDefinition
) -> ToolDefinition:
    """Expose the current reply's required branch without changing native validation."""
    schema = definition.parameters_json_schema
    properties = dict(schema["properties"])
    if not ctx.deps.computed_examples or not ctx.deps.direction_sections:
        properties.pop("computed_example", None)
        if "$defs" in schema:
            schema = {
                **schema,
                "$defs": {
                    key: value
                    for key, value in schema["$defs"].items()
                    if key not in {"ComputedExample", "Instruction", "MemoryCell"}
                },
            }
    elif "computed_example" in properties:
        original_example = properties["computed_example"]
        properties["computed_example"] = {
            **{
                key: value
                for key, value in original_example.items()
                if key not in ("anyOf", "default")
            },
            "type": "object",
            "anyOf": [
                value
                for value in original_example["anyOf"]
                if value.get("type") != "null"
            ],
        }
    if (
        not ctx.deps.feedback_contract
        or not ctx.deps.direction_sections
        or ctx.deps.feedback_review is not None
    ):
        properties.pop("feedback", None)
        return replace(
            definition,
            parameters_json_schema={**schema, "properties": properties},
        )
    for name in ("direction", "review"):
        properties.pop(name, None)
    original = properties["feedback"]
    # A required property survives provider conversion; a root anyOf may not.
    properties["feedback"] = {
        **{k: v for k, v in original.items() if k not in ("anyOf", "default")},
        "type": "object",
        "anyOf": [v for v in original["anyOf"] if v.get("type") != "null"],
    }
    description = (definition.description or "").partition(
        "When the host requires an explicit feedback branch"
    )[0]
    description = description.replace(
        "send `direction` in this same tool call instead of writing free content.",
        "send its direction object in `feedback` without free content.",
    ).replace("omit `direction`", "choose ordinary review")
    kind = "direction or review" if definition.name == "interact" else "review"
    description += (
        f"For supported returned text, put the {kind} object in `feedback`. "
        "Read/memory calls retain `review`. Follow the offered schema and authored stage "
        "without a planning request."
    )
    return replace(
        definition,
        description=description,
        parameters_json_schema={
            **schema,
            "properties": properties,
            "required": list(dict.fromkeys([*schema.get("required", []), "feedback"])),
        },
    )


async def prepare_memory_tool(
    _ctx: RunContext[Deps], definition: ToolDefinition
) -> ToolDefinition:
    """Make evidence explicit in the enabled host's schema without changing portable calls."""
    schema = definition.parameters_json_schema
    properties = schema["properties"]
    request_schema = dict(properties["request"])
    request_schema.pop("default", None)
    request_schema["description"] = (
        "Required field. For an undeclared key, copy the learner's complete current free-text "
        "input EXACTLY, including the request to remember and punctuation. Do not omit it or "
        "supply a paraphrase. For a non-deleted main-script-declared key only, null is allowed."
    )
    return replace(
        definition,
        parameters_json_schema={
            **schema,
            "properties": {**properties, "request": request_schema},
            "required": list(dict.fromkeys([*schema.get("required", []), "request"])),
        },
    )


async def remember(
    ctx: RunContext[Deps],
    key: str,
    value: str,
    scope: Literal["session", "user"] = "session",
    request: str | None = None,
    review: FeedbackReview | None = None,
) -> str:
    """Store something about the learner.

    `key` is a short snake_case identifier; `value` is the learner's own words or the concrete
    fact. `scope="session"` (default) is for this script run (answers, collected variables);
    `scope="user"` is for things that should follow the learner into future sessions
    (preferences, stable facts, requests like "keep answers short"). Overwrites an existing key.

    A nonblank key can contain at most 255 characters and a value at most 2000. A scope with
    100 or more entries accepts updates to existing keys only. Each scope has a budget of 32768
    characters of pretty-printed JSON. A larger existing scope accepts only non-growing updates.
    A refused note changes nothing; continue teaching instead of repeatedly trying to store it.
    Existing history and answers recorded by `interact(variable=...)` are preserved without
    these model-note limits.
    Record required notes before `finish`; a finished lesson accepts no further model notes.

    """
    if review is not None:
        validate_direction_call(ctx, review=review)
    if ctx.deps.finished is not None:
        return LESSON_OVER
    if not key.strip() or len(key) > _MEMORY_KEY_LIMIT:
        return "Not remembered: use a nonblank key of at most 255 characters. Continue teaching."
    if len(value) > _MEMORY_VALUE_LIMIT:
        return "Not remembered: the value exceeds 2000 characters. Continue teaching."
    if ctx.deps.memory_keys is not None and (
        key not in ctx.deps.memory_keys or key in ctx.deps.memory_deleted_keys
    ):
        scope = "user"
    target = ctx.deps.user_memory if scope == "user" else ctx.deps.memory
    if problem := _memory_capacity_error(target, key, value):
        return problem
    if problem := await memory_admission_error(ctx.deps, key, value, request):
        return f"Not remembered: {problem}. Continue teaching."
    # A semantic check yields control: another tool may have written or finished meanwhile.
    if ctx.deps.finished is not None:
        return LESSON_OVER
    if problem := _memory_capacity_error(target, key, value):
        return problem
    target[key] = value
    if (
        scope == "user"
        and isinstance(ctx.deps.answer_hashes.get(key), str)
        and answer_fingerprint(ctx.deps.memory.get(key)) == ctx.deps.answer_hashes[key]
    ):
        # A named answer is mirrored in session scope; an accepted correction wins now.
        ctx.deps.memory[key] = value
        ctx.deps.answer_hashes[key] = answer_fingerprint(value)
    elif scope == "session":
        ctx.deps.answer_hashes.pop(key, None)
    ctx.deps.memory_updates.append((scope, key, value))
    return f"remembered {key} ({scope})"


async def finish(
    ctx: RunContext[Deps],
    summary: str = "",
    review: FeedbackReview | None = None,
    feedback: FeedbackReview | None = None,
) -> str:
    """Mark the script as delivered to its end.

    Call this once, only after the last step of the script has been completed and nothing in
    it remains to do. `summary` is one short line about what the learner did. Do not call it
    when the script merely pauses, asks a question, or waits for the learner.
    """
    if feedback is not None:
        if review is not None:
            message = "Use feedback without a legacy review field"
            raise ModelRetry(message)
        review = feedback
    if review is not None:
        validate_direction_call(ctx, review=review)
    current = [
        m for m in ctx.messages[ctx.deps.history_len :] if isinstance(m, ModelResponse)
    ]
    if ctx.deps.interaction_markup_pending or contains_interaction_markup(
        "".join(p.content for m in current for p in m.parts if isinstance(p, TextPart)),
        ctx.deps.literal_interaction_markup,
    ):
        ctx.deps.interaction_markup_pending = True
        raise ModelRetry(INTERACTION_MARKUP_RETRY)
    ctx.deps.finished = summary.strip() or "done"
    return "finished. The lesson is over: write nothing more and call no other tool."
