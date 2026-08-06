from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr import dao
from flaskr.api.langfuse import MockClient
from flaskr.common.cache_provider import (
    CacheUnavailableError,
    InMemoryCacheProvider,
    redis_cache,
)
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.profile_research import api
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PREVIEW_PURPOSE,
    PROFILE_ONBOARDING_PURPOSE,
    ProfileResearchRuntime,
    ProfileResearchSessionNotFound,
    ProfileResearchValidationError,
    _ProfileResearchLLMProvider,
    _ProfileResearchSessionStore,
    build_profile_research_sse_response,
    validate_profile_research_document,
)
from flaskr.util.prompt_loader import load_prompt_template
from markdown_flow import LLMProvider


class _FakeProvider(LLMProvider):
    def __init__(self, output_chunks: list[str]) -> None:
        self.output_chunks = output_chunks
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages, model=None, temperature=None):
        del model, temperature
        self.messages.append(messages)
        return "".join(self.output_chunks)

    def stream(self, messages, model=None, temperature=None):
        del model, temperature
        self.messages.append(messages)
        yield from self.output_chunks


def _make_runtime(
    output_chunks: list[str] | None = None,
) -> tuple[Flask, ProfileResearchRuntime, list[_FakeProvider]]:
    app = Flask("profile-research-tests")
    app.config.update(
        DEFAULT_LLM_MODEL="gpt-test",
        DEFAULT_LLM_TEMPERATURE=0.3,
        REDIS_KEY_PREFIX="test:",
    )
    providers: list[_FakeProvider] = []

    def provider_factory(_app, _session, _span):
        provider = _FakeProvider(output_chunks or ["- 称呼：小雨"])
        providers.append(provider)
        return provider

    store = _ProfileResearchSessionStore(app, cache=InMemoryCacheProvider())
    runtime = ProfileResearchRuntime(
        app,
        store=store,
        provider_factory=provider_factory,
    )
    return app, runtime, providers


def _terminal(events: list[dict]) -> dict:
    return next(event for event in reversed(events) if event.get("is_terminal"))


def test_service_has_no_learn_dependency():
    service_dir = Path(inspect.getsourcefile(ProfileResearchRuntime) or "").parent
    imports: list[str] = []
    for source_path in service_dir.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

    assert not any(name.startswith("flaskr.service.learn") for name in imports)


def test_validation_uses_markdownflow_public_parser():
    metadata = validate_profile_research_document(
        "欢迎。\n\n---\n\n?[%{{arbitrary_identity}}...请介绍你的经历]"
    )

    assert metadata == {
        "block_count": 2,
        "interaction_block_count": 1,
        "content_block_count": 1,
        "variables": ["arbitrary_identity"],
    }
    with pytest.raises(ProfileResearchValidationError):
        validate_profile_research_document("只有普通 Markdown")


@pytest.mark.parametrize(
    "user_input",
    [
        {f"key-{index}": [""] for index in range(101)},
        {"input": [""] * 101},
        {"first": ["x"] * 51, "second": ["x"] * 50},
        {"x" * 257: ["value"]},
        {"input": ["x" * 4_001]},
        {"input": ["x" * 10_001]},
        {"input": ["   "]},
    ],
)
def test_run_rejects_oversized_user_input(user_input):
    _app, runtime, _providers = _make_runtime()
    session = runtime.start_session(
        user_bid="user-1",
        document="?[...请回答]",
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )

    with pytest.raises(ProfileResearchValidationError):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=session["session_id"],
                user_input=user_input,
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            )
        )


def test_default_store_requires_shared_redis(monkeypatch):
    app = Flask("profile-research-shared-store")
    app.config.update(
        DEFAULT_LLM_MODEL="gpt-test",
        DEFAULT_LLM_TEMPERATURE=0.3,
        REDIS_KEY_PREFIX="test:",
    )
    monkeypatch.setattr(dao, "redis_client", None)
    runtime = ProfileResearchRuntime(app)

    assert runtime.store._cache is redis_cache
    with pytest.raises(CacheUnavailableError):
        runtime.start_session(
            user_bid="user-1",
            document="?[继续]",
            document_prompt=None,
            purpose=PROFILE_ONBOARDING_PURPOSE,
            config_revision=1,
            output_language="en-US",
        )


def test_session_runs_direct_markdownflow_and_returns_profile_draft():
    _app, runtime, providers = _make_runtime(["- 称呼：", "小雨"])
    session = runtime.start_session(
        user_bid="user-1",
        document="?[%{{role}} 学生//student | 老师//teacher]",
        document_prompt="只根据用户回答总结。",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=7,
        output_language=None,
    )
    session_id = session["session_id"]

    rendered = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session_id,
            user_input=None,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_block_index=0,
            request_id="render-1",
        )
    )
    assert rendered[0]["event_type"] == "interaction"
    assert _terminal(rendered)["content"]["next_block_index"] == 0
    assert _terminal(rendered)["content"]["awaiting_input"] is True

    answered = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session_id,
            user_input={"role": ["student"]},
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_block_index=0,
            request_id="answer-1",
        )
    )
    assert _terminal(answered)["content"]["next_block_index"] == 1

    completed = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session_id,
            user_input=None,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_block_index=1,
            request_id="summary-1",
        )
    )
    content_events = [event for event in completed if event["event_type"] == "content"]
    assert content_events[-1]["content"] == "- 称呼：小雨"
    summary = _terminal(completed)["content"]
    assert summary["done"] is True
    assert summary["profile_draft"] == "- 称呼：小雨"
    assert summary["config_revision"] == 7
    assert any(
        "student" in str(messages)
        for provider in providers
        for messages in provider.messages
    )


def test_identical_retry_replays_without_running_markdownflow_again():
    _app, runtime, providers = _make_runtime()
    session = runtime.start_session(
        user_bid="user-1",
        document="?[%{{role}} 学生//student | 老师//teacher]",
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )
    session_id = session["session_id"]
    original = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session_id,
            user_input={"role": ["student"]},
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_block_index=0,
            request_id="answer-1",
        )
    )
    provider_count = len(providers)

    replay = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session_id,
            user_input={"role": ["student"]},
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            expected_block_index=0,
            request_id="answer-1",
        )
    )

    assert replay == original
    assert runtime.store.load(session_id).block_index == 1
    assert len(providers) == provider_count
    with pytest.raises(ProfileResearchValidationError, match="expected_block_index"):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=session_id,
                user_input={"role": ["student"]},
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
                expected_block_index=0,
                request_id="answer-2",
            )
        )


def test_invalid_interaction_answer_keeps_the_question_available():
    _app, runtime, _providers = _make_runtime(["请选择已有选项"])
    session = runtime.start_session(
        user_bid="user-1",
        document="?[%{{role}} 学生//student | 老师//teacher]",
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )

    events = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session["session_id"],
            user_input={"role": ["unknown"]},
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
    )

    assert [event["event_type"] for event in events[:-1]] == [
        "content",
        "interaction",
    ]
    summary = _terminal(events)["content"]
    assert summary["advanced"] is False
    assert summary["awaiting_input"] is True
    assert summary["next_block_index"] == 0


def test_invalid_answer_rerenders_the_interaction_through_markdownflow():
    _app, runtime, _providers = _make_runtime(["请选择已有选项"])
    session = runtime.start_session(
        user_bid="user-1",
        document=("?[%{{choice}} 作为 {{role}} 的学生//student | 老师//teacher]"),
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )
    stored = runtime.store.load(session["session_id"])
    stored.variables["role"] = "产品经理"
    runtime.store.save(stored)

    events = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session["session_id"],
            user_input={"choice": ["unknown"]},
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
    )

    interaction = next(
        event for event in events if event["event_type"] == "interaction"
    )
    assert "产品经理" in interaction["content"]
    assert "{{role}}" not in interaction["content"]


def test_owner_and_purpose_are_enforced_for_run_and_delete():
    _app, runtime, _providers = _make_runtime()
    session = runtime.start_session(
        user_bid="operator-1",
        document="?[继续]",
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PREVIEW_PURPOSE,
        config_revision=3,
        output_language=None,
    )

    with pytest.raises(ProfileResearchSessionNotFound):
        list(
            runtime.stream_session(
                user_bid="other-user",
                session_id=session["session_id"],
                user_input=None,
                expected_purpose=PROFILE_ONBOARDING_PREVIEW_PURPOSE,
            )
        )
    with pytest.raises(ProfileResearchSessionNotFound):
        runtime.delete_session(
            user_bid="operator-1",
            session_id=session["session_id"],
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )


def test_delete_uses_the_run_lock_before_removing_a_session():
    _app, runtime, _providers = _make_runtime()
    session = runtime.start_session(
        user_bid="user-1",
        document="?[继续]",
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )
    lock = runtime.store.lock(session["session_id"])
    assert lock.acquire(blocking=False)

    try:
        with pytest.raises(api.ProfileResearchSessionBusy):
            runtime.delete_session(
                user_bid="user-1",
                session_id=session["session_id"],
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            )
        assert (
            runtime.store.load(session["session_id"]).session_id
            == session["session_id"]
        )
    finally:
        lock.release()

    runtime.delete_session(
        user_bid="user-1",
        session_id=session["session_id"],
        expected_purpose=PROFILE_ONBOARDING_PURPOSE,
    )
    with pytest.raises(ProfileResearchSessionNotFound):
        runtime.store.load(session["session_id"])


def test_content_context_keeps_the_exact_prompt_built_by_markdownflow():
    _app, runtime, providers = _make_runtime(["收到"])
    session = runtime.start_session(
        user_bid="user-1",
        document=(
            "请称呼我为 {{name}}，并参考：\n"
            "```python\n"
            "print('profile')\n"
            "```\n\n---\n\n?[继续]"
        ),
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language="zh-CN",
    )
    stored = runtime.store.load(session["session_id"])
    stored.variables["name"] = "小雨"
    runtime.store.save(stored)

    list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session["session_id"],
            user_input=None,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
    )

    context = runtime.store.load(session["session_id"]).context
    sent_prompt = providers[0].messages[0][-1]["content"]
    assert context[0] == {"role": "user", "content": sent_prompt}
    assert "```python\nprint('profile')\n```" in context[0]["content"]
    assert "__MDFLOW_CODE_BLOCK_" not in context[0]["content"]


def test_preserved_content_context_uses_markdownflow_output_without_placeholders():
    _app, runtime, providers = _make_runtime(["结合完成"])
    session = runtime.start_session(
        user_bid="user-1",
        document=(
            "!===\n"
            "```python\n"
            "print('profile')\n"
            "```\n"
            "!===\n\n---\n\n"
            "结合上面的示例回应。\n\n---\n\n?[继续]"
        ),
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )

    list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session["session_id"],
            user_input=None,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
    )
    preserved_context = runtime.store.load(session["session_id"]).context[0]
    list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session["session_id"],
            user_input=None,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
    )

    assert preserved_context == {
        "role": "assistant",
        "content": "```python\nprint('profile')\n```",
    }
    sent_messages = providers[-1].messages[0]
    assert preserved_context in sent_messages
    assert "__MDFLOW_CODE_BLOCK_" not in str(sent_messages)


def test_non_assignment_answer_reaches_the_next_markdownflow_content_block():
    _app, runtime, providers = _make_runtime(["个性化回应"])
    session = runtime.start_session(
        user_bid="user-1",
        document=("?[产品经理//pm | 教师//teacher]\n\n---\n\n根据用户刚才的选择回应。"),
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )

    list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session["session_id"],
            user_input={"choice": ["pm"]},
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
    )
    list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session["session_id"],
            user_input=None,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
    )

    assert any(
        message == {"role": "user", "content": "pm"}
        for provider in providers
        for messages in provider.messages
        for message in messages
    )


def test_session_snapshots_summary_prompt_and_model_settings():
    app, runtime, _providers = _make_runtime()
    document = "欢迎\n\n---\n\n?[继续]"
    view = runtime.start_session(
        user_bid="user-1",
        document=document,
        document_prompt="只依据回答",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=9,
        output_language="zh-CN",
    )
    stored = runtime.store.load(view["session_id"])
    app.config.update(DEFAULT_LLM_MODEL="changed-model", DEFAULT_LLM_TEMPERATURE=1.7)

    assert stored.document == (
        f"{document}\n\n---\n\n"
        f"{load_prompt_template('profile_research_summary').strip()}"
    )
    assert stored.document_prompt == "只依据回答"
    assert stored.model == "gpt-test"
    assert stored.temperature == 0.3
    assert stored.output_language == "zh-CN"
    assert stored.config_revision == 9


def test_profile_summary_prompt_requires_plain_text_without_placeholders():
    summary_prompt = load_prompt_template("profile_research_summary")

    assert "plain-text profile" in summary_prompt
    assert "Do not use Markdown, JSON, XML, YAML" in summary_prompt
    assert "template or variable placeholder syntax" in summary_prompt
    assert "How to address the user" in summary_prompt
    assert "Preferred slide style" in summary_prompt
    assert "{{" not in summary_prompt


def test_markdownflow_receives_a_language_name_instead_of_a_locale_code():
    _app, runtime, _providers = _make_runtime()
    view = runtime.start_session(
        user_bid="user-1",
        document="?[继续]",
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language="zh-CN",
    )
    session = runtime.store.load(view["session_id"])

    flow = runtime._build_flow(session, _FakeProvider([]))

    assert flow.get_output_language() == "简体中文"


def test_llm_provider_uses_shared_non_billable_route_without_redaction(monkeypatch):
    _app, runtime, _providers = _make_runtime()
    view = runtime.start_session(
        user_bid="user-1",
        document="?[继续]",
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )
    session = runtime.store.load(view["session_id"])
    calls = []

    def fake_chat_llm(app, user_id, span, **kwargs):
        calls.append((app, user_id, span, kwargs))
        yield SimpleNamespace(result="画像结果")

    monkeypatch.setattr(
        "flaskr.service.profile_research.runtime.chat_llm",
        fake_chat_llm,
    )
    provider = _ProfileResearchLLMProvider(runtime.app, session, MockClient())

    assert provider.complete([{"role": "user", "content": "整理画像"}]) == "画像结果"
    call_app, user_id, _span, kwargs = calls[0]
    assert call_app is runtime.app
    assert user_id == "user-1"
    assert kwargs["usage_scene"] == BILL_USAGE_SCENE_DEBUG
    assert kwargs["usage_context"].billable == 0
    assert kwargs["billable"] == 0
    assert "usage_metadata" not in kwargs


def test_sse_response_emits_public_error_without_course_dtos(monkeypatch):
    app = Flask("profile-research-sse")
    monkeypatch.setattr(
        "flaskr.service.profile_research.runtime._release_stream_db_session",
        lambda _app: None,
    )

    def fail():
        raise ProfileResearchValidationError("private detail")
        yield  # pragma: no cover

    with app.test_request_context("/"):
        response = build_profile_research_sse_response(
            app,
            event_iter_factory=fail,
            log_context="test",
        )
        body = "".join(response.response)

    assert "transient_markdownflow_invalid" in body
    assert "private detail" not in body
    assert '"event_type": "error"' in body
    assert '"event_type": "done"' not in body


def test_public_api_exports_profile_research_boundary():
    assert api.PROFILE_ONBOARDING_PURPOSE == PROFILE_ONBOARDING_PURPOSE
    assert callable(api.validate_profile_research_document)
    assert callable(api.start_profile_research_session)
    assert callable(api.stream_profile_research_session)
    assert callable(api.delete_profile_research_session)
    assert callable(api.build_profile_research_sse_response)
