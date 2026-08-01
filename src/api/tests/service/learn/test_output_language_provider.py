from flaskr.service.learn.output_language_provider import (
    RuntimeOutputLanguageProvider,
    with_runtime_output_language,
)
from markdown_flow import MarkdownFlow, ProcessMode


class _CapturingProvider:
    def __init__(self):
        self.complete_messages = None
        self.complete_calls = []
        self.stream_messages = None

    def complete(self, messages, **_kwargs):
        self.complete_messages = messages
        self.complete_calls.append(messages)
        if "JSON Interaction Translation Task" in messages[0]["content"]:
            return '{"buttons":["Continuer"]}'
        return "Réponse"

    def stream(self, messages, **_kwargs):
        self.stream_messages = messages
        return iter(["Ré", "ponse"])


def test_french_instruction_follows_the_existing_course_system_prompt():
    delegate = _CapturingProvider()
    provider = with_runtime_output_language(delegate, "French")
    original_messages = [
        {"role": "system", "content": "请使用中文讲课。"},
        {"role": "user", "content": "生成课程正文"},
    ]

    result = provider.complete(original_messages)

    assert result == "Réponse"
    assert original_messages[0]["content"] == "请使用中文讲课。"
    system_content = delegate.complete_messages[0]["content"]
    assert system_content.startswith("请使用中文讲课。")
    assert system_content.index("请使用中文讲课。") < system_content.index(
        "本次输出必须全部使用法语"
    )
    assert "Translate Chinese source text instead of copying it" in system_content
    assert delegate.complete_messages[-1] == original_messages[-1]


def test_french_instruction_is_inserted_when_messages_have_no_system_role():
    delegate = _CapturingProvider()
    provider = with_runtime_output_language(delegate, "French")

    list(provider.stream([{"role": "user", "content": '{"buttons":["不会编程"]}'}]))

    assert delegate.stream_messages[0]["role"] == "system"
    assert (
        "every learner-visible HTML, Markdown, or JSON string"
        in (delegate.stream_messages[0]["content"])
    )
    assert delegate.stream_messages[-1] == {
        "role": "user",
        "content": '{"buttons":["不会编程"]}',
    }


def test_non_french_languages_keep_the_original_provider():
    delegate = _CapturingProvider()

    assert with_runtime_output_language(delegate, "English") is delegate
    assert with_runtime_output_language(delegate, "简体中文") is delegate
    assert with_runtime_output_language(None, "French") is None


def test_french_wrapper_implements_the_markdownflow_provider_contract():
    delegate = _CapturingProvider()

    provider = with_runtime_output_language(delegate, "French")

    assert isinstance(provider, RuntimeOutputLanguageProvider)


def test_markdownflow_content_and_interaction_receive_the_runtime_instruction():
    delegate = _CapturingProvider()
    provider = with_runtime_output_language(delegate, "French")
    markdown_flow = MarkdownFlow(
        "生成正文\n\n?[不会编程]",
        document_prompt="请始终使用中文输出。",
        llm_provider=provider,
    ).set_output_language("French")

    markdown_flow.process(block_index=0, mode=ProcessMode.COMPLETE)
    markdown_flow.process(block_index=1, mode=ProcessMode.COMPLETE)

    content_messages, interaction_messages = delegate.complete_calls
    content_system = content_messages[0]["content"]
    assert content_system.rfind("请始终使用中文输出。") < content_system.rfind(
        "本次输出必须全部使用法语"
    )
    assert "本次输出必须全部使用法语" in interaction_messages[0]["content"]
