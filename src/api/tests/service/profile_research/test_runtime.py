from __future__ import annotations

import ast
import inspect
import json
import sys
from dataclasses import replace
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
from flaskr.service.profile_research import runtime as profile_research_runtime
from flaskr.service.profile_research.runtime import (
    PROFILE_ONBOARDING_PREVIEW_PURPOSE,
    PROFILE_ONBOARDING_PURPOSE,
    PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS,
    PROFILE_RESEARCH_SESSION_TTL_SECONDS,
    ProfileResearchError,
    ProfileResearchRuntime,
    ProfileResearchSessionNotFound,
    ProfileResearchValidationError,
    _compact_replay_events,
    _expand_replay_events,
    _ProfileResearchLLMProvider,
    _ProfileResearchSessionStore,
    build_profile_research_sse_response,
    validate_profile_research_document,
)
from flaskr.util.prompt_loader import load_prompt_template
from markdown_flow import LLMProvider
from sqlalchemy.exc import ResourceClosedError


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


def _save_session_without_active_pointer(runtime: ProfileResearchRuntime, session):
    runtime.store._cache.setex(
        runtime.store._key(session.session_id),
        PROFILE_RESEARCH_SESSION_TTL_SECONDS,
        json.dumps(session.to_cache_payload(), ensure_ascii=False),
    )


def _start_test_session(
    runtime: ProfileResearchRuntime,
    *,
    purpose: str = PROFILE_ONBOARDING_PURPOSE,
    document: str = "?[继续]",
    revision: int = 1,
) -> dict:
    return runtime.start_session(
        user_bid="user-1",
        document=document,
        document_prompt=None,
        purpose=purpose,
        config_revision=revision,
        output_language=None,
    )


def _active_test_session_id(
    runtime: ProfileResearchRuntime,
    *,
    purpose: str = PROFILE_ONBOARDING_PURPOSE,
) -> str | None:
    return runtime.store.active_session_id(user_bid="user-1", purpose=purpose)


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


def test_validation_rejects_interaction_variable_longer_than_runtime_input_key():
    variable_name = "x" * 257

    with pytest.raises(ProfileResearchValidationError, match="variable name"):
        validate_profile_research_document(f"?[%{{{{{variable_name}}}}}...请回答]")


@pytest.mark.parametrize(
    "document",
    [
        "?[]",
        "?[ | ]",
        "?[...]",
        "?[%{{learning_goal}}]",
    ],
)
def test_validation_rejects_interactions_without_answerable_input(document):
    with pytest.raises(ProfileResearchValidationError, match="answerable input"):
        validate_profile_research_document(document)


@pytest.mark.parametrize(
    "document",
    [
        f"?[Short//{'x' * 4_001} | Detailed//full]",
        "?[" + " | ".join(f"Option {index}" for index in range(101)) + "]",
        "?["
        + " || ".join(
            [
                f"First//{'a' * 3_500}",
                f"Second//{'b' * 3_500}",
                f"Third//{'c' * 3_500}",
            ]
        )
        + "]",
    ],
)
def test_validation_rejects_options_outside_runtime_input_limits(document):
    with pytest.raises(ProfileResearchValidationError, match="runtime input limits"):
        validate_profile_research_document(document)


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
    stored_session = runtime.store.load(session_id)
    session_key = runtime.store._key(session_id)
    active_key = runtime.store._active_key(
        stored_session.user_bid,
        stored_session.purpose,
    )
    cache = runtime.store._cache
    cache._store[session_key].expires_at = cache._now() + 1
    cache._store[active_key].expires_at = cache._now() + 1

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
    assert cache.ttl(session_key) > PROFILE_RESEARCH_SESSION_TTL_SECONDS - 5
    assert cache.ttl(active_key) > PROFILE_RESEARCH_SESSION_TTL_SECONDS - 5
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


def test_retry_cache_stores_stream_content_as_linear_deltas():
    chunks = ["甲" * 100, "乙" * 100, "丙" * 100]
    original = [
        {
            "type": "content",
            "event_type": "content",
            "content": "".join(chunks[: index + 1]),
            "generated_block_bid": "block-1",
            "run_session_bid": "session-1",
            "is_terminal": False,
        }
        for index in range(len(chunks))
    ]
    original.append(
        {
            "type": "done",
            "event_type": "done",
            "content": {"done": False},
            "run_session_bid": "session-1",
            "is_terminal": True,
        }
    )

    stored = _compact_replay_events(original)
    stored_content = [
        event["content"] for event in stored if event["event_type"] == "content"
    ]

    assert stored_content == chunks
    assert sum(len(content) for content in stored_content) == len("".join(chunks))
    assert _expand_replay_events(stored) == original


def test_empty_initial_interaction_fails_without_advancing(monkeypatch):
    _app, runtime, _providers = _make_runtime()
    session = runtime.start_session(
        user_bid="user-1",
        document="?[继续]",
        document_prompt=None,
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )
    stored = runtime.store.load(session["session_id"])
    parsed_flow = runtime._build_flow(stored, _FakeProvider([]))

    class _EmptyInteractionFlow:
        def get_all_blocks(self):
            return parsed_flow.get_all_blocks()

        def process(self, **_kwargs):
            return []

    monkeypatch.setattr(
        runtime,
        "_build_flow",
        lambda _session, _provider: _EmptyInteractionFlow(),
    )

    with pytest.raises(ProfileResearchError, match="empty interaction"):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=session["session_id"],
                user_input=None,
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            )
        )

    unchanged = runtime.store.load(session["session_id"])
    assert unchanged.block_index == 0
    assert unchanged.awaiting_input is False


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


def test_start_replaces_the_previous_idle_session_for_the_same_scope():
    _app, runtime, _providers = _make_runtime()
    first = _start_test_session(runtime)
    second = _start_test_session(
        runtime,
        document="?[重新开始]",
        revision=2,
    )

    assert first["session_id"] != second["session_id"]
    with pytest.raises(ProfileResearchSessionNotFound):
        runtime.store.load(first["session_id"])
    assert runtime.store.load(second["session_id"]).config_revision == 2
    assert _active_test_session_id(runtime) == second["session_id"]


def test_start_keeps_the_previous_session_when_its_old_worker_lock_is_busy():
    _app, runtime, _providers = _make_runtime()
    previous = _start_test_session(runtime)
    previous_lock = runtime.store.lock(previous["session_id"])
    assert previous_lock.acquire(blocking=False)

    try:
        with pytest.raises(api.ProfileResearchSessionBusy):
            _start_test_session(
                runtime,
                document="?[重新开始]",
                revision=2,
            )
    finally:
        previous_lock.release()

    assert runtime.store.load(previous["session_id"]).config_revision == 1
    assert _active_test_session_id(runtime) == previous["session_id"]


def test_owner_scope_lock_blocks_concurrent_runs_across_session_ids():
    _app, runtime, providers = _make_runtime()
    active = _start_test_session(runtime)
    stale = replace(
        runtime.store.load(active["session_id"]),
        session_id="f" * 32,
    )
    _save_session_without_active_pointer(runtime, stale)
    active_events = runtime.stream_session(
        user_bid="user-1",
        session_id=active["session_id"],
        user_input=None,
        expected_purpose=PROFILE_ONBOARDING_PURPOSE,
    )

    try:
        assert next(active_events)["event_type"] == "interaction"
        with pytest.raises(api.ProfileResearchSessionBusy):
            list(
                runtime.stream_session(
                    user_bid="user-1",
                    session_id=stale.session_id,
                    user_input=None,
                    expected_purpose=PROFILE_ONBOARDING_PURPOSE,
                )
            )
        assert len(providers) == 1
    finally:
        active_events.close()


def test_first_run_claims_a_session_created_before_active_pointers():
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    session = runtime.store.load(view["session_id"])
    runtime.store.clear_active(session)

    assert _active_test_session_id(runtime) is None
    events = list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=view["session_id"],
            user_input=None,
            expected_purpose=PROFILE_ONBOARDING_PURPOSE,
        )
    )

    assert _terminal(events)["content"]["awaiting_input"] is True
    assert _active_test_session_id(runtime) == view["session_id"]


def test_stale_session_is_rejected_before_a_provider_is_created():
    _app, runtime, providers = _make_runtime()
    active = _start_test_session(runtime)
    stale = replace(
        runtime.store.load(active["session_id"]),
        session_id="e" * 32,
    )
    _save_session_without_active_pointer(runtime, stale)

    with pytest.raises(ProfileResearchSessionNotFound):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=stale.session_id,
                user_input=None,
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            )
        )

    assert providers == []
    assert _active_test_session_id(runtime) == active["session_id"]


def test_owner_admission_is_isolated_by_purpose():
    _app, runtime, _providers = _make_runtime()
    learner = _start_test_session(runtime)
    learner_owner_lock = runtime.store.owner_lock(
        user_bid="user-1",
        purpose=PROFILE_ONBOARDING_PURPOSE,
    )
    assert learner_owner_lock.acquire(blocking=False)

    try:
        with pytest.raises(api.ProfileResearchSessionBusy):
            _start_test_session(runtime, document="?[重新开始]")
        preview = _start_test_session(
            runtime,
            document="?[预览]",
            purpose=PROFILE_ONBOARDING_PREVIEW_PURPOSE,
        )
    finally:
        learner_owner_lock.release()

    assert runtime.store.load(learner["session_id"]).purpose == (
        PROFILE_ONBOARDING_PURPOSE
    )
    assert runtime.store.load(preview["session_id"]).purpose == (
        PROFILE_ONBOARDING_PREVIEW_PURPOSE
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
    assert _active_test_session_id(runtime) is None


def test_stale_cleanup_does_not_clear_the_replacement_active_pointer():
    _app, runtime, _providers = _make_runtime()
    first = _start_test_session(runtime)
    stale = runtime.store.load(first["session_id"])
    replacement = _start_test_session(
        runtime,
        document="?[重新开始]",
        revision=2,
    )
    _save_session_without_active_pointer(runtime, stale)

    runtime.delete_session(
        user_bid="user-1",
        session_id=stale.session_id,
        expected_purpose=PROFILE_ONBOARDING_PURPOSE,
    )

    assert _active_test_session_id(runtime) == replacement["session_id"]
    assert runtime.store.load(replacement["session_id"]).config_revision == 2


def test_save_refreshes_session_and_active_pointer_ttl_together():
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    session = runtime.store.load(view["session_id"])
    session_key = runtime.store._key(session.session_id)
    active_key = runtime.store._active_key(session.user_bid, session.purpose)
    cache = runtime.store._cache
    cache._store[session_key].expires_at = cache._now() + 1
    cache._store[active_key].expires_at = cache._now() + 1

    runtime.store.save(session)

    assert cache.ttl(session_key) > PROFILE_RESEARCH_SESSION_TTL_SECONDS - 5
    assert cache.ttl(active_key) > PROFILE_RESEARCH_SESSION_TTL_SECONDS - 5


def test_invalid_run_does_not_refresh_session_or_active_pointer_ttl():
    _app, runtime, _providers = _make_runtime()
    view = _start_test_session(runtime)
    session = runtime.store.load(view["session_id"])
    session_key = runtime.store._key(session.session_id)
    active_key = runtime.store._active_key(session.user_bid, session.purpose)
    cache = runtime.store._cache
    session_expiry = cache._store[session_key].expires_at
    active_expiry = cache._store[active_key].expires_at

    with pytest.raises(ProfileResearchValidationError):
        list(
            runtime.stream_session(
                user_bid="user-1",
                session_id=session.session_id,
                user_input={"answer": ["   "]},
                expected_purpose=PROFILE_ONBOARDING_PURPOSE,
            )
        )

    assert cache._store[session_key].expires_at == session_expiry
    assert cache._store[active_key].expires_at == active_expiry


def test_run_lock_lease_has_worker_cleanup_headroom_without_using_session_ttl():
    app = Flask("profile-research-lock-lease")
    app.config["REDIS_KEY_PREFIX"] = "test:"
    lock_calls = []
    expected_lock = object()

    def record_lock(key, *, timeout=None, blocking_timeout=None):
        lock_calls.append(
            {
                "key": key,
                "timeout": timeout,
                "blocking_timeout": blocking_timeout,
            }
        )
        return expected_lock

    store = _ProfileResearchSessionStore(
        app,
        cache=SimpleNamespace(lock=record_lock),
    )

    assert store.lock("session-1") is expected_lock
    assert (
        store.owner_lock(
            user_bid="user-1",
            purpose=PROFILE_ONBOARDING_PURPOSE,
        )
        is expected_lock
    )
    assert lock_calls == [
        {
            "key": "test:profile_research:session-1:lock",
            "timeout": 6 * 60,
            "blocking_timeout": 0,
        },
        {
            "key": (
                "test:profile_research:active:profile-onboarding:"
                "c6c289e49e9c05b2145860387b73bcb18df43fb09a1e4a4a9713c76c88bb541b:lock"
            ),
            "timeout": 6 * 60,
            "blocking_timeout": 0,
        },
    ]
    assert PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS > 5 * 60
    assert (
        PROFILE_RESEARCH_RUN_LOCK_LEASE_SECONDS < PROFILE_RESEARCH_SESSION_TTL_SECONDS
    )


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


def test_locked_summary_does_not_inherit_operator_document_prompt():
    _app, runtime, providers = _make_runtime(["称呼：小雨"])
    session = runtime.start_session(
        user_bid="user-1",
        document="?[%{{role}} 学生//student | 老师//teacher]",
        document_prompt="OPERATOR OVERRIDE: return JSON only",
        purpose=PROFILE_ONBOARDING_PURPOSE,
        config_revision=1,
        output_language=None,
    )

    list(
        runtime.stream_session(
            user_bid="user-1",
            session_id=session["session_id"],
            user_input={"role": ["student"]},
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

    summary_messages = providers[-1].messages[0]
    assert "OPERATOR OVERRIDE" not in str(summary_messages)
    assert "plain-text profile" in str(summary_messages)


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
    releases = []
    invalidations = []
    monkeypatch.setattr(
        profile_research_runtime,
        "release_session_classified",
        lambda *, source: releases.append(source),
    )
    monkeypatch.setattr(
        profile_research_runtime,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
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
    assert invalidations == []
    assert releases == ["profile research stream", "profile research stream"]


def test_sse_response_normal_completion_releases_without_invalidation(monkeypatch):
    app = Flask("profile-research-sse-normal")
    releases = []
    invalidations = []

    def record_release(*, source):
        releases.append((source, sys.exc_info()[1]))

    monkeypatch.setattr(
        profile_research_runtime,
        "release_session_classified",
        record_release,
    )
    monkeypatch.setattr(
        profile_research_runtime,
        "invalidate_session",
        lambda *, source, session=None: invalidations.append(source) or True,
    )

    def events():
        yield {"event_type": "done", "is_terminal": True}

    with app.test_request_context("/"):
        response = build_profile_research_sse_response(
            app,
            event_iter_factory=events,
            log_context="test",
        )
        body = "".join(response.response)

    assert '"event_type": "done"' in body
    assert invalidations == []
    assert releases == [
        ("profile research stream", None),
        ("profile research stream", None),
    ]


def test_sse_disconnect_reaches_classified_release_with_generator_exit(monkeypatch):
    app = Flask("profile-research-sse-close")
    releases = []

    def record_release(*, source):
        releases.append((source, sys.exc_info()[1]))

    monkeypatch.setattr(
        profile_research_runtime,
        "release_session_classified",
        record_release,
    )

    def events():
        yield {"event_type": "content", "is_terminal": False}
        yield {"event_type": "done", "is_terminal": True}

    with app.test_request_context("/"):
        response = build_profile_research_sse_response(
            app,
            event_iter_factory=events,
            log_context="test",
        )
        stream = iter(response.response)
        next(stream)
        stream.close()

    assert releases[0] == ("profile research stream", None)
    assert releases[1][0] == "profile research stream"
    assert isinstance(releases[1][1], GeneratorExit)


def test_sse_protocol_error_invalidates_before_final_release(monkeypatch):
    app = Flask("profile-research-sse-protocol-error")
    cleanup_events = []

    monkeypatch.setattr(
        profile_research_runtime,
        "release_session_classified",
        lambda *, source: cleanup_events.append(("release", source)),
    )
    monkeypatch.setattr(
        profile_research_runtime,
        "invalidate_session",
        lambda *, source, session=None: (
            cleanup_events.append(("invalidate", source)) or True
        ),
    )

    def events():
        yield {"event_type": "content", "is_terminal": False}
        raise ResourceClosedError("private protocol detail")

    with app.test_request_context("/"):
        response = build_profile_research_sse_response(
            app,
            event_iter_factory=events,
            log_context="test",
        )
        body = "".join(response.response)

    assert "transient_markdownflow_error" in body
    assert "private protocol detail" not in body
    assert cleanup_events == [
        ("release", "profile research stream"),
        ("invalidate", "profile research stream protocol interrupt"),
        ("release", "profile research stream"),
    ]


def test_public_api_exports_profile_research_boundary():
    assert api.PROFILE_ONBOARDING_PURPOSE == PROFILE_ONBOARDING_PURPOSE
    assert callable(api.validate_profile_research_document)
    assert callable(api.start_profile_research_session)
    assert callable(api.stream_profile_research_session)
    assert callable(api.delete_profile_research_session)
    assert callable(api.build_profile_research_sse_response)
