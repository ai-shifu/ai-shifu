"""Validate and render model-selected direction feedback before displaying it.

This binds a model's selected stage and focus to original evidence. It does not
grade an answer or prove that a free-form question has only one semantic focus.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage


class DirectionFocus(BaseModel):
    """One model-selected missing or contradicted authored requirement."""

    criterion_quote: str = Field(
        min_length=1,
        description=(
            "Exact clause for one authored requirement; do not copy a compound sentence, "
            "heading or checklist."
        ),
    )
    submission_quote: str | None = Field(
        default=None,
        description="Exact submitted evidence for a contradiction; null for an omission.",
    )
    observed_issue: str = Field(
        min_length=1,
        description=(
            "Internal issue for this clause alone; never list other gaps or copy an "
            "unmatched sample diagnosis. Cite actual input."
        ),
    )
    guiding_question: str = Field(
        min_length=1,
        description=(
            "One unanswered check of the selected clause only; no subquestions, other "
            "requirements, worked reasoning or broad completion request."
        ),
    )


class FeedbackReview(BaseModel):
    """Bind ordinary feedback to the actual submission and authored stage."""

    answer_id: str
    phase: Literal["accepted", "clarification", "authored_help"] = Field(
        description=(
            "authored_help cannot use local samples to waive global checking counts. "
            "Knowledge help is not a failed attempt. First counted failures use direction."
        )
    )
    submission_quote: str = Field(
        min_length=1, description="Exact excerpt of this returned input."
    )
    rule_quote: str | None = Field(
        default=None,
        description="Exact authored rule permitting this help/control-only stage now.",
    )
    reason: str = Field(
        min_length=1,
        description="Justify this stage from actual correction history.",
    )

    def problem(
        self, answers: dict[str, str], sections: dict[str, str], authored: str = ""
    ) -> str | None:
        """Validate actual answer provenance and any supplied authored rule source."""
        if self.answer_id not in sections or self.answer_id not in answers:
            return (
                "review.answer_id must name a supported interaction returned this turn"
            )
        if (
            not self.submission_quote.strip()
            or self.submission_quote not in answers[self.answer_id]
        ):
            return "review.submission_quote must copy actual returned input exactly"
        if not self.reason.strip():
            return "review.reason must explain the chosen feedback branch"
        if (self.phase == "authored_help" or self.rule_quote is not None) and (
            not self.rule_quote
            or not self.rule_quote.strip()
            or (
                self.rule_quote not in sections[self.answer_id]
                and self.rule_quote not in authored
            )
        ):
            return "rule_quote needs exact current author text permitting this feedback"
        return None


class DirectionFeedback(BaseModel):
    """A checking-direction stage selected by the model under the author's rules."""

    answer_id: str = Field(description="ID of the actual interaction being answered.")
    rule_quote: str = Field(
        min_length=1,
        description="Exact author text permitting this checking-direction stage.",
    )
    aspect_limit: int = Field(
        ge=1,
        description=(
            "Applicable count across lesson-wide and local rules; local examples cannot "
            "waive it. Must be positive; never omit or use null. Without an authored "
            "count, use ordinary review-authored feedback; never invent one."
        ),
    )
    accepted_quotes: list[str] = Field(
        description=(
            "Unique exact correct excerpts from this answer; [] if none. Do not also "
            "use them as contradiction evidence. Shown with a check for authored "
            "acknowledgement; never invent learner wording."
        )
    )
    focuses: list[DirectionFocus] = Field(min_length=1)

    def problem(self, authored: str, answers: dict[str, str]) -> str | None:
        """Check provenance and declared cardinality without interpreting a grade."""
        if self.answer_id not in answers:
            return "direction.answer_id must name an interaction returned in this turn"
        if not self.rule_quote.strip() or self.rule_quote not in authored:
            return "direction.rule_quote must copy original author text exactly"
        if len(self.focuses) > self.aspect_limit:
            return "direction.focuses exceeds the declared authored aspect limit"
        if len(set(self.accepted_quotes)) != len(self.accepted_quotes):
            return "accepted_quotes must contain unique actual submission excerpts"
        if any(
            not quote.strip() or quote not in answers[self.answer_id]
            for quote in self.accepted_quotes
        ):
            return "accepted_quotes must copy actual returned input exactly"
        if set(self.accepted_quotes).intersection(
            focus.submission_quote for focus in self.focuses
        ):
            return (
                "The same exact excerpt cannot be both accepted and contradiction evidence. "
                "Select genuinely correct distinct excerpts, or [] if none; do not label "
                "a contradicted claim as correct merely to acknowledge the learner"
            )
        for focus in self.focuses:
            if (
                not focus.criterion_quote.strip()
                or focus.criterion_quote not in authored
            ):
                return "each direction criterion must copy original author text exactly"
            if focus.submission_quote is not None and (
                not focus.submission_quote.strip()
                or focus.submission_quote not in answers[self.answer_id]
            ):
                return "a direction submission quote must occur in the actual returned answer"
            if not focus.observed_issue.strip() or not focus.guiding_question.strip():
                return (
                    "each direction focus needs a nonempty observed issue and question"
                )
        return None

    def render(self) -> str:
        """Display actual evidence and unanswered questions, not internal diagnoses.

        Correctness of the selected excerpts remains the model's judgment. The
        host formats source-bound evidence; it never generates a replacement hint.
        """
        quotes = [
            "> ✓ " + quote.replace("\n", "\n> ") for quote in self.accepted_quotes
        ]
        quotes.extend(
            "> " + focus.submission_quote.replace("\n", "\n> ")
            for focus in self.focuses
            if focus.submission_quote is not None
        )
        questions = "\n\n".join(focus.guiding_question for focus in self.focuses)
        return "\n\n".join([*quotes, questions])


def feedback_arguments(call: ToolCallPart) -> dict[str, Any]:
    """Read canonical delivery feedback without rewriting original tool evidence."""
    args = call.args_as_dict()
    value = args.get("feedback")
    if value is None:
        return args
    if (
        call.tool_name not in ("interact", "finish")
        or not isinstance(value, dict)
        or ("phase" in value) == ("focuses" in value)
        or any(args.get(name) is not None for name in ("direction", "review"))
    ):
        message = "feedback must declare one direction or review without legacy fields"
        raise ValueError(message)
    return {**args, "review" if "phase" in value else "direction": value}


def has_direction(call: ToolCallPart) -> bool:
    """Recognize the structured interaction without interpreting its model arguments."""
    if call.tool_name != "interact":
        return False
    try:
        return feedback_arguments(call).get("direction") is not None
    except (TypeError, ValueError):
        return False


def direction_history(
    messages: list[ModelMessage],
    rendered: dict[str, str],
    hidden: set[int] | None = None,
) -> list[ModelMessage]:
    """Keep only displayed direction text in new teaching, retaining all tool/user evidence.

    A rejected structured response's free prose was never displayed. Accepted
    tool arguments remain original, and their exact rendered text is also stored
    as teaching so existing history, summaries and reports see what was shown.
    """
    result = []
    for message in messages:
        calls = (
            [
                p
                for p in message.parts
                if isinstance(p, ToolCallPart) and has_direction(p)
            ]
            if isinstance(message, ModelResponse)
            else []
        )
        if not calls and (hidden is None or id(message) not in hidden):
            result.append(message)
            continue
        if (
            hidden is not None
            and id(message) in hidden
            and not any(isinstance(part, ToolCallPart) for part in message.parts)
        ):
            # A pure-text rejection has no tool evidence to retain. Its retry
            # remains, but an empty assistant would be invalid provider history.
            continue
        parts = [p for p in message.parts if not isinstance(p, TextPart)]
        shown = [rendered[p.tool_call_id] for p in calls if p.tool_call_id in rendered]
        result.append(
            replace(
                message,
                parts=[*([TextPart("\n\n".join(shown))] if shown else []), *parts],
            )
        )
    return result


def feedback_retry_history(
    messages: list[ModelMessage],
    hidden: set[int],
    *,
    feedback_text_pending: bool = False,
) -> list[ModelMessage]:
    """Tell a retry what was withheld, preserving tool/error and accepted evidence.

    The SDK processes this request copy before each model call. Rejected prose
    cannot serve as already-delivered teaching during the same run, either.
    Pending delivery keeps the recovery notice on later retries even after an
    earlier projection has removed the rejected response from SDK history.
    """
    rejected = [
        i
        for i, message in enumerate(messages)
        if id(message) in hidden
        and isinstance(message, ModelResponse)
        and any(isinstance(p, TextPart) and p.content.strip() for p in message.parts)
    ]
    last_retry = max(
        (
            i
            for i, message in enumerate(messages)
            if isinstance(message, ModelRequest)
            and any(isinstance(p, RetryPromptPart) for p in message.parts)
        ),
        default=-1,
    )
    if not rejected and (not feedback_text_pending or last_retry < 0):
        return messages
    result = []
    for i, message in enumerate(messages):
        if i in rejected:
            parts = [p for p in message.parts if not isinstance(p, TextPart)]
            if any(isinstance(p, ToolCallPart) for p in parts):
                result.append(replace(message, parts=parts))
        elif (
            (
                (bool(rejected) and i > rejected[-1])
                or (feedback_text_pending and i == last_retry)
            )
            and isinstance(message, ModelRequest)
            and any(isinstance(p, RetryPromptPart) for p in message.parts)
        ):
            notice = (
                "\n\nThe rejected response was not displayed to the learner. "
                "Regenerate the complete authored feedback together with its valid "
                "native tool call and applicable branch in the same response; "
                "do not send only a replacement control assuming prior prose was shown. "
                "Use actual tool calls, not textual interaction tags. A checking "
                "direction still uses direction alone, without free prose. Preserve "
                "earlier successfully displayed pages and the author's navigation boundary. "
                "For clarification, keep the actual question's requested examples or "
                "walkthroughs within the author's brevity and disclosure limits; do not "
                "replace them with a generic definition."
            )
            result.append(
                replace(
                    message,
                    parts=[
                        replace(
                            p,
                            content=(
                                p.content
                                if isinstance(p.content, str)
                                else p.model_response()
                            ).removesuffix(notice)
                            + notice,
                        )
                        if isinstance(p, RetryPromptPart)
                        else p
                        for p in message.parts
                    ],
                )
            )
        else:
            result.append(message)
    return result
