import json
import sys
import types

from flask import Flask


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = types.ModuleType("litellm")
    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.completion = lambda *args, **kwargs: iter([])
    sys.modules["litellm"] = litellm_stub


def _install_openai_responses_stub() -> None:
    if "openai.types.responses" in sys.modules:
        return

    responses_pkg = types.ModuleType("openai.types.responses")
    responses_pkg.__path__ = []
    response_mod = types.ModuleType("openai.types.responses.response")
    response_create_mod = types.ModuleType(
        "openai.types.responses.response_create_params"
    )
    response_function_mod = types.ModuleType(
        "openai.types.responses.response_function_tool_call"
    )
    response_text_mod = types.ModuleType(
        "openai.types.responses.response_text_config_param"
    )

    for name in [
        "IncompleteDetails",
        "Response",
        "ResponseOutputItem",
        "Tool",
        "ToolChoice",
    ]:
        setattr(response_mod, name, type(name, (), {}))

    for name in [
        "Reasoning",
        "ResponseIncludable",
        "ResponseInputParam",
        "ToolChoice",
        "ToolParam",
        "Text",
    ]:
        setattr(response_create_mod, name, type(name, (), {}))

    response_function_tool_call = type("ResponseFunctionToolCall", (), {})
    response_text_config = type("ResponseTextConfigParam", (), {})
    setattr(
        response_function_mod,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )
    setattr(
        response_text_mod,
        "ResponseTextConfigParam",
        response_text_config,
    )
    setattr(
        responses_pkg,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )

    sys.modules["openai.types.responses"] = responses_pkg
    sys.modules["openai.types.responses.response"] = response_mod
    sys.modules["openai.types.responses.response_create_params"] = response_create_mod
    sys.modules["openai.types.responses.response_function_tool_call"] = (
        response_function_mod
    )
    sys.modules["openai.types.responses.response_text_config_param"] = response_text_mod


_install_litellm_stub()
_install_openai_responses_stub()


class _FakeSpan:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.end_kwargs = {}

    def end(self, **kwargs):
        self.end_kwargs = kwargs


class _FakeTrace:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.updated = {}
        self.last_span = None

    def span(self, **kwargs):
        self.last_span = _FakeSpan(**kwargs)
        return self.last_span

    def update(self, **kwargs):
        self.updated = kwargs


class _FakeLangfuseClient:
    def __init__(self):
        self.traces = []

    def trace(self, **kwargs):
        trace = _FakeTrace(**kwargs)
        self.traces.append(trace)
        return trace


def test_get_summary_updates_trace_and_span_output(monkeypatch):
    from flaskr.service.shifu import shifu_publish_funcs as module

    fake_langfuse = _FakeLangfuseClient()
    monkeypatch.setattr(
        module,
        "get_langfuse_client",
        lambda: fake_langfuse,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "invoke_llm",
        lambda *_args, **_kwargs: iter(
            [
                types.SimpleNamespace(result="summary "),
                types.SimpleNamespace(result="result"),
            ]
        ),
    )

    app = Flask("shifu-summary")
    summary = module._get_summary(
        app,
        prompt="Summarize this lesson",
        model_name="gpt-test",
        user_id="user-1",
        temperature=0.2,
    )

    assert summary == "summary result"
    assert len(fake_langfuse.traces) == 1
    trace = fake_langfuse.traces[0]
    assert trace.kwargs["name"] == "shifu_summary"
    assert trace.kwargs["input"] == "Summarize this lesson"
    assert trace.last_span is not None
    assert trace.last_span.kwargs["input"] == "Summarize this lesson"
    assert trace.last_span.end_kwargs["output"] == "summary result"
    assert trace.updated["output"] == "summary result"


def test_generate_profile_collection_prompt_config_saves_referenced_variables(
    monkeypatch,
):
    from flaskr.service.shifu import shifu_publish_funcs as module

    captured = {}

    def fake_get_config(
        app,
        *,
        prompt: str,
        model_name: str,
        user_id: str | None,
        temperature,
    ):
        captured["prompt"] = prompt
        captured["model_name"] = model_name
        captured["user_id"] = user_id
        captured["temperature"] = temperature
        return json.dumps(
            {
                "version": 1,
                "variables": {
                    "sys_user_nickname": {
                        "question": "Nickname?",
                        "placeholder": "Name",
                        "skip_label": "Skip",
                    },
                    "sys_user_background": {
                        "question": "What background helps with Python?",
                        "placeholder": "Your Python background",
                        "skip_label": "Skip",
                    },
                },
            }
        )

    monkeypatch.setattr(
        module,
        "_get_profile_collection_prompt_config",
        fake_get_config,
    )

    app = Flask("profile-collection-publish")
    app.config["DEFAULT_LLM_MODEL"] = "fallback-model"
    shifu = types.SimpleNamespace(
        shifu_bid="shifu-profile",
        title="Python Basics",
        description="Intro course",
        keywords="python,beginner",
        ask_llm="ask-model",
        llm="course-model",
        ask_llm_temperature=0.4,
        llm_temperature=0.8,
        created_user_bid="creator-1",
        profile_collection_prompt_config="{}",
    )
    outline_ids = ["section-1"]
    outline_item_map = {
        "section-1": types.SimpleNamespace(
            content="We adapt the lesson to {{sys_user_background}}."
        )
    }
    outline_summary_map = {
        "section-1": {
            "chapter_id": "chapter-1",
            "chapter_name": "Start",
            "section_id": "section-1",
            "section_name": "Intro",
            "content": "Python variables and first steps.",
        }
    }

    config = module._generate_profile_collection_prompt_config(
        app,
        shifu,
        outline_ids,
        outline_summary_map,
        outline_item_map,
        (
            "title={course_title}\n"
            "description={course_description}\n"
            "keywords={course_keywords}\n"
            "variables={profile_variables}\n"
            "summary={course_summary}"
        ),
    )

    saved_config = json.loads(shifu.profile_collection_prompt_config)
    assert "sys_user_background" in config["variables"]
    assert "sys_user_background" in saved_config["variables"]
    assert "sys_user_nickname" not in saved_config["variables"]
    assert captured["model_name"] == "ask-model"
    assert captured["user_id"] == "creator-1"
    assert captured["temperature"] == 0.4
    assert "Python Basics" in captured["prompt"]
    assert "sys_user_background" in captured["prompt"]


def test_generate_profile_collection_prompt_config_limits_course_summary(
    monkeypatch,
):
    from flaskr.service.shifu import shifu_publish_funcs as module

    captured = {}

    def fake_get_config(
        app,
        *,
        prompt: str,
        model_name: str,
        user_id: str | None,
        temperature,
    ):
        captured["prompt"] = prompt
        return json.dumps(
            {
                "version": 1,
                "variables": {
                    "sys_user_background": {
                        "question": "Background?",
                        "placeholder": "Your background",
                        "skip_label": "Skip",
                    },
                },
            }
        )

    monkeypatch.setattr(
        module,
        "_get_profile_collection_prompt_config",
        fake_get_config,
    )

    app = Flask("profile-collection-summary-limit")
    shifu = types.SimpleNamespace(
        shifu_bid="shifu-profile",
        title="Python Basics",
        description="Intro course",
        keywords="python",
        ask_llm="ask-model",
        llm="course-model",
        ask_llm_temperature=0.4,
        llm_temperature=0.8,
        created_user_bid="creator-1",
        profile_collection_prompt_config="{}",
    )
    long_summary = "A" * 3000 + "tail-marker"

    module._generate_profile_collection_prompt_config(
        app,
        shifu,
        ["section-1", "section-2"],
        {
            "section-1": {
                "chapter_id": "chapter-1",
                "chapter_name": "Start",
                "section_id": "section-1",
                "section_name": "Intro",
                "content": long_summary,
            },
            "section-2": {
                "chapter_id": "chapter-1",
                "chapter_name": "Start",
                "section_id": "section-2",
                "section_name": "Practice",
                "content": long_summary,
            },
        },
        {
            "section-1": types.SimpleNamespace(
                content="We adapt to {{sys_user_background}}."
            ),
            "section-2": types.SimpleNamespace(content="More practice."),
        },
        "{course_title}\n{profile_variables}\n{course_summary}",
    )

    assert "...[truncated]" in captured["prompt"]
    assert "tail-marker" not in captured["prompt"]
    assert len(captured["prompt"]) < 3000


def test_get_profile_collection_prompt_config_requests_json_with_timeout(monkeypatch):
    from flaskr.service.shifu import shifu_publish_funcs as module

    fake_langfuse = _FakeLangfuseClient()
    captured = {}

    monkeypatch.setattr(
        module,
        "get_langfuse_client",
        lambda: fake_langfuse,
        raising=False,
    )

    def fake_invoke_llm(*_args, **kwargs):
        captured.update(kwargs)
        return iter([types.SimpleNamespace(result='{"version":1,"variables":{}}')])

    monkeypatch.setattr(module, "invoke_llm", fake_invoke_llm)

    result = module._get_profile_collection_prompt_config(
        Flask("profile-collection-json"),
        prompt="generate json",
        model_name="model-1",
        user_id="creator-1",
        temperature=0.2,
    )

    assert result == '{"version":1,"variables":{}}'
    assert captured["json"] is True
    assert captured["timeout"] == module.PROFILE_COLLECTION_LLM_TIMEOUT_SECONDS


def test_generate_profile_collection_prompt_config_falls_back_on_failure(monkeypatch):
    from flaskr.service.shifu import shifu_publish_funcs as module

    monkeypatch.setattr(
        module,
        "_get_profile_collection_prompt_config",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("llm failed")),
    )

    app = Flask("profile-collection-publish-fallback")
    shifu = types.SimpleNamespace(
        shifu_bid="shifu-profile",
        title="Python Basics",
        description="Intro course",
        keywords="python,beginner",
        ask_llm="ask-model",
        llm="course-model",
        ask_llm_temperature=0.4,
        llm_temperature=0.8,
        created_user_bid="creator-1",
        profile_collection_prompt_config='{"old": true}',
    )

    config = module._generate_profile_collection_prompt_config(
        app,
        shifu,
        ["section-1"],
        {
            "section-1": {
                "chapter_id": "chapter-1",
                "chapter_name": "Start",
                "section_id": "section-1",
                "section_name": "Intro",
                "content": "Python variables.",
            }
        },
        {
            "section-1": types.SimpleNamespace(
                content="We adapt the lesson to {{sys_user_background}}."
            )
        },
        "{course_title} {profile_variables} {course_summary}",
    )

    assert config == {}
    assert shifu.profile_collection_prompt_config == "{}"
