"""Interaction specs (what the model asks for) and answers (what the learner sends back)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Mapping

InteractionType = Literal[
    "single", "multi", "text", "single_or_text", "multi_or_text", "confirm"
]


class Option(BaseModel):
    """One choice offered to the learner."""

    display: str = Field(description="Text shown to the learner.")
    value: str | None = Field(
        default=None, description="Stored value when different from display."
    )

    @property
    def stored(self) -> str:
        """Return the value to keep when the learner picks this option."""
        return self.value if self.value is not None else self.display


# What a confirm's button says when the model names nothing for it. The host replaces this with
# a label in the learner's own language; it is a constant so that replacement can recognise the
# default rather than guess at any English word it finds on a button.
DEFAULT_CONFIRM_LABEL = "Continue"


class InteractionSpec(BaseModel):
    """What the model is asking the learner for, and how to show it."""

    type: InteractionType
    prompt: str = Field(
        description="The question or instruction shown above the controls."
    )
    options: list[Option] = Field(
        default_factory=list, description="Choices; empty for text."
    )
    variable: str | None = Field(
        default=None,
        description="Memory key to store the answer under. Only when the script names one.",
    )
    placeholder: str | None = Field(
        default=None, description="Placeholder for the text box."
    )
    # Set by the engine, never by the model: the model does not see this field. It records that
    # the confirm's button label is the engine's own default rather than anything the model
    # wrote, so a host can replace exactly that and nothing else -- including a model that
    # happened to write the same word itself.
    # Carried in every dump on purpose: the engine hands the spec to the host as JSON and reads
    # pending ones back from the session the same way, and a flag that did not survive that
    # round trip would tell the host nothing.
    labelled_by_engine: bool = False

    @model_validator(mode="after")
    def _check(self) -> InteractionSpec:
        if (
            self.type in ("single", "multi", "single_or_text", "multi_or_text")
            and not self.options
        ):
            msg = f"type {self.type!r} needs at least one option"
            raise ValueError(msg)
        if self.type == "text" and self.options:
            msg = "type 'text' takes no options"
            raise ValueError(msg)
        if self.type == "confirm":
            if not self.options:
                self.options = [Option(display=DEFAULT_CONFIRM_LABEL, value="continue")]
                self.labelled_by_engine = True
            # Every confirm answer means the same thing, so a second button would offer the
            # learner a choice that cannot reach the model. Keep the first one only.
            self.options = self.options[:1]
            # A confirm carries no answer, only "go on", so its button text must never be stored.
            # Models do attach a variable to it -- often the one the previous question filled --
            # and pressing continue then overwrites a real answer with the button's label.
            self.variable = None
        return self


class InteractionAnswer(BaseModel):
    """What the learner submitted. `values` are option values (or displays); `text` is free text."""

    values: list[str] = Field(default_factory=list)
    text: str | None = None

    @classmethod
    def coerce(
        cls, raw: Mapping[str, Any] | InteractionAnswer | str | list[str]
    ) -> InteractionAnswer:
        """Accept the shapes a host may send an answer in."""
        if isinstance(raw, InteractionAnswer):
            return raw
        if isinstance(raw, str):
            return cls(text=raw)
        if isinstance(raw, list):
            return cls(values=[str(v) for v in raw])
        return cls.model_validate(dict(raw))


def normalize_answer(
    spec: InteractionSpec, answer: InteractionAnswer
) -> InteractionAnswer:
    """Map displays to stored values; drop values that are not options for choice types."""
    if not spec.options:
        return answer
    by_display = {o.display: o.stored for o in spec.options}
    stored = {o.stored for o in spec.options}
    values = [by_display.get(v, v) for v in answer.values]
    if spec.type in ("single", "multi", "confirm"):
        values = [v for v in values if v in stored]
    if spec.type in ("single", "single_or_text", "confirm"):
        values = values[:1]
    return InteractionAnswer(values=values, text=answer.text)


def answer_is_usable(spec: InteractionSpec, answer: InteractionAnswer) -> bool:
    """Whether a normalized answer actually answers this interaction.

    A `confirm` carries no answer, only "go on", so it is always usable. The choice types need an
    option that survived normalization -- unknown values are dropped there, and resuming on what
    is left would tell the model the learner continued without answering. The text-bearing types
    accept free text instead.
    """
    if spec.type == "confirm":
        return True
    if spec.type in ("single", "multi"):
        return bool(answer.values)
    return bool(answer.values or answer.text)


def stored_value(spec: InteractionSpec, answer: InteractionAnswer) -> str | None:
    """Pick the value to put in memory for `spec.variable`, or None if nothing usable came back."""
    if (
        answer.values
        and answer.text
        and spec.type in ("single_or_text", "multi_or_text")
    ):
        return ", ".join(answer.values) + f"; {answer.text}"
    if answer.values:
        return ", ".join(answer.values)
    return answer.text or None


def format_answer_for_model(spec: InteractionSpec, answer: InteractionAnswer) -> str:
    """Phrase the answer as the tool result the model sees when the run resumes."""
    if spec.type == "confirm":
        return (
            "Learner pressed continue. Go on with the next part of the script now: present its "
            "content before pausing again."
        )
    if answer.values and answer.text:
        return f"Learner chose: {', '.join(answer.values)}; and wrote: {answer.text}"
    if answer.values:
        return f"Learner chose: {', '.join(answer.values)}"
    if answer.text:
        return f"Learner wrote: {answer.text}"
    return "Learner continued without answering."
