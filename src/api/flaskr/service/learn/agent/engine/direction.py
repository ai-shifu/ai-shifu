"""Validate and render model-selected direction feedback before displaying it.

This binds a model's selected stage and focus to original evidence. It does not
grade an answer or prove that a free-form question has only one semantic focus.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage


class DirectionFocus(BaseModel):
    """One model-selected missing or contradicted authored requirement."""

    criterion_quote: str = Field(min_length=1, description="Exact authored criterion.")
    submission_quote: str | None = Field(
        default=None,
        description="Exact submitted evidence for a contradiction; null for an omission.",
    )
    observed_issue: str = Field(
        min_length=1, description="Brief actual gap, without its solution."
    )
    guiding_question: str = Field(
        min_length=1,
        description="One unanswered question about this focus, without subquestions or reasoning.",
    )


class FeedbackReview(BaseModel):
    """An explicit model judgment authorizing ordinary answer feedback.

    Checking-direction feedback uses DirectionFeedback instead. These fields
    make the branch decision reviewable; provenance checks do not grade it.
    """

    answer_id: str
    phase: Literal["accepted", "clarification", "authored_help"]
    submission_quote: str = Field(
        min_length=1, description="Exact evidence from the actual returned submission."
    )
    rule_quote: str | None = Field(
        default=None,
        description="For authored_help, exact current author text permitting this help now.",
    )
    reason: str = Field(
        min_length=1,
        description="Internal branch justification using actual submission and correction history.",
    )

    def problem(self, answers: dict[str, str], sections: dict[str, str]) -> str | None:
        """Validate actual answer provenance and an authored help source."""
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
        if self.phase == "authored_help" and (
            not self.rule_quote
            or not self.rule_quote.strip()
            or self.rule_quote not in sections[self.answer_id]
        ):
            return (
                "authored_help needs exact current author text permitting this help now"
            )
        return None


class DirectionFeedback(BaseModel):
    """A checking-direction stage selected by the model under the author's rules."""

    answer_id: str = Field(description="ID of the actual interaction being answered.")
    rule_quote: str = Field(
        min_length=1,
        description="Exact author text permitting this checking-direction stage.",
    )
    aspect_limit: int | None = Field(
        default=None,
        ge=1,
        description="Authored aspect/question limit; null when no count is authored.",
    )
    focuses: list[DirectionFocus] = Field(min_length=1)

    def problem(self, authored: str, answers: dict[str, str]) -> str | None:
        """Check provenance and declared cardinality without interpreting a grade."""
        if self.answer_id not in answers:
            return "direction.answer_id must name an interaction returned in this turn"
        if not self.rule_quote.strip() or self.rule_quote not in authored:
            return "direction.rule_quote must copy original author text exactly"
        if self.aspect_limit is not None and len(self.focuses) > self.aspect_limit:
            return "direction.focuses exceeds the declared authored aspect limit"
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
        """Display submitted quotes, selected issues and questions, never author criteria."""
        issues = "\n\n".join(
            (
                "> " + focus.submission_quote.replace("\n", "\n> ") + "\n\n"
                if focus.submission_quote is not None
                else ""
            )
            + focus.observed_issue
            for focus in self.focuses
        )
        questions = "\n".join(focus.guiding_question for focus in self.focuses)
        return issues + "\n\n" + questions


def has_direction(call: ToolCallPart) -> bool:
    """Recognize the structured interaction without interpreting its model arguments."""
    if call.tool_name != "interact":
        return False
    try:
        return call.args_as_dict().get("direction") is not None
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
