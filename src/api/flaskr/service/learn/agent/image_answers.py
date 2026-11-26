"""Preserve image attachments beside an optional single-choice answer."""

from flaskr.api.llm.learner_images import split_learner_images
from flaskr.api.markdownflow import InteractionAnswer, InteractionSpec


def answer_with_images(spec: InteractionSpec, values: list[str]) -> InteractionAnswer:
    """Keep image-bearing free text outside a single-choice value truncation."""
    if spec.type != "single_or_text" or not any(
        split_learner_images(value)[1] for value in values
    ):
        return InteractionAnswer(values=values)
    choices = {option.stored for option in spec.options} | {
        option.display for option in spec.options
    }
    return InteractionAnswer(
        values=[value for value in values if value in choices],
        text=", ".join(value for value in values if value not in choices),
    )
