"""Native request-local language policy and model-context projection."""

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

_CONTEXT_KEY = "mdf_output_language_context"


def output_language_instructions(language: str | None) -> str:
    """None keeps engine defaults; an empty string selects the authored language."""
    if language is None:
        return ""
    if not language:
        return (
            "# Course output language\n"
            "Multilingual teaching is disabled. Teach in the author's original "
            "script language, including generated HTML and interaction display text. "
            "The learner's profile language, interface language and prior translated "
            "teaching do not select a translation of this course."
        )
    name = language
    return (
        "# Course output language\n"
        f"The current output language is {name}. "
        f"Write all generated learner-facing display text in {name}. "
        "Use this language throughout all newly generated teaching, feedback, "
        "HTML visible text and accessible labels, interaction prompts, option "
        "display labels, navigation labels and input placeholders. Translate "
        "authored display wording into this language while preserving its meaning, "
        "order, teaching criteria and interaction boundaries. This current language "
        "specializes the script notation's exact-wording rule: translate display "
        "labels and placeholders, while preserving submission values. It "
        "takes precedence over language hints in the learner memory, earlier "
        "conversation, script examples and teaching brief. Do not repeat or "
        "translate previously delivered teaching just because the language changed.\n"
        "Only display wording is translated: keep variable names, identifiers, "
        "option submission values, URLs, executable code and explicitly verbatim "
        "preserved content unchanged. For Display//value translate only Display. "
        "For an option without //value, keep its original authored wording as "
        "the submission value and translate only its display label. When translating "
        "a display label, explicitly set option.value to the original submission "
        "value; do not omit it or use null, which would submit the translated label. "
        "Use the same "
        "interact tool, option order, types and authored input boundaries."
    )


def language_request_history(
    messages: list[ModelMessage], language: str | None
) -> list[ModelMessage]:
    """Project current configuration after the latest answer, without mutating history."""
    projected = [
        message
        for message in messages
        if not (
            isinstance(message, ModelRequest)
            and message.metadata
            and message.metadata.get(_CONTEXT_KEY)
        )
    ]
    instructions = output_language_instructions(language)
    if instructions:
        projected.append(
            ModelRequest(
                parts=[UserPromptPart(content=instructions)],
                metadata={_CONTEXT_KEY: True},
            )
        )
    return projected
