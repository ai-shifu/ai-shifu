"""Verify native language labels reach generated prompts."""

from collections.abc import Iterator

from flaskr.common.i18n_utils import resolve_markdownflow_output_language
from markdown_flow import MarkdownFlow, ProcessMode


def test_french_locale_uses_native_language_name() -> None:
    assert resolve_markdownflow_output_language("fr-FR") == "Français"
    assert resolve_markdownflow_output_language("fr_FR") == "Français"


def test_existing_english_and_chinese_names_are_unchanged() -> None:
    assert resolve_markdownflow_output_language("en-US") == "English"
    assert resolve_markdownflow_output_language("zh-CN") == "简体中文"


def test_french_native_name_reaches_content_and_interaction_prompts() -> None:
    class CapturingProvider:
        def __init__(self) -> None:
            self.calls = []

        def complete(self, messages, **_kwargs: object) -> str:
            self.calls.append(messages)
            if "JSON Interaction Translation Task" in messages[0]["content"]:
                return '{"buttons":["Continuer"]}'
            return "Réponse"

        def stream(self, _messages, **_kwargs: object) -> Iterator[object]:
            return iter(())

    provider = CapturingProvider()
    output_language = resolve_markdownflow_output_language("fr-FR")
    markdown_flow = MarkdownFlow(
        "生成正文\n\n?[继续]",
        llm_provider=provider,
    ).set_output_language(output_language)

    markdown_flow.process(block_index=0, mode=ProcessMode.COMPLETE)
    markdown_flow.process(block_index=1, mode=ProcessMode.COMPLETE)

    content_messages, interaction_messages = provider.calls
    assert "OUTPUT: 100% Français" in content_messages[-1]["content"]
    assert "100% Français OUTPUT REQUIRED" in interaction_messages[0]["content"]
