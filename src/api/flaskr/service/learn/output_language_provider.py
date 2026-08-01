from markdown_flow import LLMProvider

_FRENCH_RUNTIME_INSTRUCTION = (
    "<runtime_output_language>\n"
    "本次输出必须全部使用法语（French）。\n"
    "Translate all requested course content and every learner-visible HTML, "
    "Markdown, or JSON string into natural French. Translate Chinese source "
    "text instead of copying it. For JSON, preserve keys, machine values, and "
    "structure. Keep only URLs, HTML/CSS syntax, code, and machine identifiers "
    "unchanged. Example: "
    "“不会编程” → “Je ne sais pas programmer”. Do not output Chinese "
    "learner-visible text.\n"
    "</runtime_output_language>\n\n"
    "<runtime_output_language_final>\n"
    "FINAL RUNTIME LANGUAGE RULE — HIGHEST PRIORITY:\n"
    "本次所有面向学员的可见文本必须使用自然法语（French）。All "
    "learner-visible output MUST be French, including course titles, headings, "
    "badges, names, roles, labels, image alt/title text, HTML text nodes, and "
    "Markdown prose.\n"
    "ONLY URLs, HTML/CSS syntax, source code, and machine identifiers may "
    "remain unchanged. Product names, proper names, course names, roles, and "
    "labels are learner-visible text, not machine identifiers, and must be "
    "translated or transliterated into French.\n"
    "Required examples:\n"
    "- “OPC · 一人公司” → “OPC · Entreprise individuelle”\n"
    "- “一人公司创业实战课” → “Cours pratique d’entrepreneuriat en solo”\n"
    "- “孙志岗 · 创始人” → “Sun Zhigang · Fondateur”\n"
    "- “AI 师傅” → “AI Shifu”\n"
    "- “不会编程” → “Je ne sais pas programmer”\n"
    "Before responding, scan every learner-visible string for Chinese "
    "characters and translate any remaining Chinese into French. Return zero "
    "Chinese learner-visible text. Do not translate learner-visible source "
    "text into English when French is required. For display//value, translate or "
    "transliterate the display before // and preserve the machine value after "
    "//.\n"
    "</runtime_output_language_final>"
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
