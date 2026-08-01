from markdown_flow import LLMProvider

_FRENCH_RUNTIME_INSTRUCTION = (
    "<runtime_output_language>\n"
    "本次输出必须全部使用法语（French）。\n"
    "Translate all requested course content and every learner-visible HTML, "
    "Markdown, or JSON string into natural French. Translate Chinese source "
    "text instead of copying it. For JSON, preserve keys, machine values, and "
    "structure. Keep URLs, HTML/CSS, code, and identifiers unchanged. Example: "
    "“不会编程” → “Je ne sais pas programmer”. Do not output Chinese "
    "learner-visible text.\n"
    "</runtime_output_language>"
)


def _runtime_instruction(output_language: str) -> str:
    if (output_language or "").strip().casefold() == "french":
        return _FRENCH_RUNTIME_INSTRUCTION
    return ""


def _append_runtime_instruction(
    messages: list[dict[str, str]],
    instruction: str,
) -> list[dict[str, str]]:
    resolved_messages = [dict(message) for message in messages]
    for index in range(len(resolved_messages) - 1, -1, -1):
        if resolved_messages[index].get("role") != "system":
            continue
        existing_content = str(resolved_messages[index].get("content") or "").rstrip()
        resolved_messages[index]["content"] = (
            f"{existing_content}\n\n{instruction}" if existing_content else instruction
        )
        return resolved_messages

    resolved_messages.insert(0, {"role": "system", "content": instruction})
    return resolved_messages


class RuntimeOutputLanguageProvider(LLMProvider):
    def __init__(self, delegate: LLMProvider, instruction: str):
        self._delegate = delegate
        self._instruction = instruction

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        return self._delegate.complete(
            _append_runtime_instruction(messages, self._instruction),
            model=model,
            temperature=temperature,
        )

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ):
        return self._delegate.stream(
            _append_runtime_instruction(messages, self._instruction),
            model=model,
            temperature=temperature,
        )


def with_runtime_output_language(
    provider: LLMProvider | None,
    output_language: str,
) -> LLMProvider | None:
    instruction = _runtime_instruction(output_language)
    if provider is None or not instruction:
        return provider
    return RuntimeOutputLanguageProvider(provider, instruction)
