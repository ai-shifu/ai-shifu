"""Editor debug sessions resume safely without touching lesson sessions."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flaskr import dao
from flaskr.common.cache_provider import CacheUnavailableError, InMemoryCacheProvider
from flaskr.service.common.models import AppError
from flaskr.service.learn import routes
from flaskr.service.learn.agent import debug_session
from flaskr.service.learn.agent.rewind import (
    RewindUnavailableError,
    checkpoint_of,
    turn_record,
)
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    PlaygroundPreviewRequest,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from markdownflow.engine.interaction import InteractionSpec
from markdownflow.engine.script import ScriptBundle
from markdownflow.engine.session import PendingInteraction, Session
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.lock import Lock

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class _Cache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.locks = InMemoryCacheProvider()

    def lock(self, key: str, **_kwargs: object) -> object:
        return self.locks.lock(key, **_kwargs)

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def getex(self, key: str, ex: int | None = None) -> str | None:
        if ex is not None and key in self.values:
            self.ttls[key] = ex
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


@pytest.fixture(autouse=True)
def local_debug_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the existing cache regressions independent from the global Redis fixture."""
    monkeypatch.setattr(debug_session, "get_redis_client", lambda: None)


@pytest.fixture
def configured_debug_cache(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    primary = InMemoryCacheProvider()
    strict = Mock(wraps=primary)
    local = Mock(wraps=InMemoryCacheProvider())
    monkeypatch.setattr(debug_session, "get_redis_client", object)
    monkeypatch.setattr(debug_session, "redis_cache", strict)
    monkeypatch.setattr(debug_session, "cache", local)
    return SimpleNamespace(primary=primary, strict=strict, local=local)


def _store(app: object, run: str = "one") -> debug_session.DebugSessionStore:
    return debug_session.DebugSessionStore(
        app, user_bid="teacher", shifu_bid="course", outline_bid="lesson", run_bid=run
    )


def _record(session: Session, values: list[str] | None = None) -> str:
    checkpoint = checkpoint_of(session)
    checkpoint["user_memory"] = dict(session.user_memory)
    return turn_record(checkpoint, values or [])


def _request_messages(
    app: object, factory: Callable[[], Iterator[RunElementSSEMessageDTO]]
) -> list[SimpleNamespace]:
    # HTTP completion belongs to the request boundary, not the lesson generator.
    with app.test_request_context("/"):
        response = routes._stream_sse_response(
            app,
            message_iter_factory=factory,
            close_log="closed",
            error_log="failed",
            terminal_event_factory=lambda: RunElementSSEMessageDTO(
                type="done", event_type="done", content="", is_terminal=True
            ),
        )
        try:
            return [
                SimpleNamespace(**json.loads(chunk.removeprefix("data: ")))
                for chunk in response.response
            ]
        finally:
            response.close()


def test_debug_session_resumes_only_the_same_run_and_script(
    app: object, monkeypatch: object
) -> None:
    cache = _Cache()
    monkeypatch.setattr(debug_session, "cache", cache)
    first = debug_session.DebugSessionStore(
        app, user_bid="teacher", shifu_bid="course", outline_bid="lesson", run_bid="one"
    )
    other = debug_session.DebugSessionStore(
        app, user_bid="teacher", shifu_bid="course", outline_bid="lesson", run_bid="two"
    )
    session = Session(script=ScriptBundle(script="Current draft"))
    session.memory["answer"] = "yes"

    first.save(session)

    assert first.load(script="Current draft").memory["answer"] == "yes"
    assert first.load(script="Edited draft") is None
    assert other.load(script="Current draft") is None
    assert list(cache.ttls.values()) == [debug_session.DebugSessionStore.TTL_SECONDS]
    restarted = Session(script=ScriptBundle(script="Current draft"))
    restarted.memory["answer"] = "fresh answer"
    other.save(restarted)
    assert other.load(script="Current draft").memory["answer"] == "fresh answer"
    assert first.load(script="Current draft").memory["answer"] == "yes"
    assert cache.ttls[other._key] == debug_session.DebugSessionStore.TTL_SECONDS
    cache.values[first._key] = "invalid history"
    assert first.load(script="Current draft") is None
    assert other.load(script="Current draft").memory["answer"] == "fresh answer"


def test_configured_debug_redis_reports_a_deferred_lock_connection_failure(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redis creates its lock successfully and connects only when acquiring it."""
    client = Mock(spec=Redis)
    client.lock.side_effect = lambda key, **kwargs: Lock(client, key, **kwargs)
    client.set.side_effect = RedisConnectionError("Redis is unavailable")
    local = Mock(wraps=InMemoryCacheProvider())
    monkeypatch.setattr(debug_session, "get_redis_client", lambda: client)
    monkeypatch.setattr(dao, "get_redis_client", lambda: client)
    monkeypatch.setattr(debug_session, "cache", local)
    store = _store(app)

    with pytest.raises(AppError) as exc_info:
        store.begin_request()

    assert exc_info.value.code == 4023
    assert store._request_bid is None
    client.lock.assert_called_once()
    client.set.assert_called_once()
    client.setex.assert_not_called()
    assert local.mock_calls == []


@pytest.mark.parametrize(
    "error_type", [RedisConnectionError, RedisTimeoutError, CacheUnavailableError]
)
@pytest.mark.parametrize(
    "operation", ["read", "token_write", "token_read", "session_write"]
)
def test_debug_cache_failure_preserves_saved_state_until_redis_recovers(
    app: object,
    configured_debug_cache: SimpleNamespace,
    operation: str,
    error_type: type[Exception],
) -> None:
    backend = configured_debug_cache.primary
    strict = configured_debug_cache.strict
    store = _store(app)
    session = Session(
        script=ScriptBundle(script="Current draft"), memory={"prefix": "kept"}
    )
    store.save(session)
    store.begin_request()
    session_before = backend.get(store._key)
    token_before = backend.get(f"{store._key}:request")
    method = (
        "setex"
        if operation in {"token_write", "session_write"}
        # The session is read with getex (it refreshes the TTL); the token with get.
        else "getex"
        if operation == "read"
        else "get"
    )
    failed_key = (
        f"{store._key}:request" if operation.startswith("token_") else store._key
    )

    def fail(*args: object, **kwargs: object) -> object:
        if args[0] == failed_key:
            msg = "Redis is unavailable"
            raise error_type(msg)
        return getattr(backend, method)(*args, **kwargs)

    getattr(strict, method).side_effect = fail
    session.memory["uncommitted"] = "discard"

    def perform() -> None:
        if operation == "read":
            store.load(script="Current draft")
        elif operation == "token_write":
            store.begin_request()
        else:
            store.save(session)

    with pytest.raises(AppError) as exc_info:
        perform()

    assert exc_info.value.code == 4023
    assert backend.get(store._key) == session_before
    assert backend.get(f"{store._key}:request") == token_before
    assert configured_debug_cache.local.mock_calls == []

    getattr(strict, method).side_effect = None
    recovered = _store(app)
    resumed = recovered.load(script="Current draft")
    assert resumed.memory == {"prefix": "kept"}
    recovered.begin_request()
    recovered.save(resumed)
    assert recovered.load(script="Current draft").memory == {"prefix": "kept"}
    assert configured_debug_cache.local.mock_calls == []


@pytest.mark.parametrize("failure", ["construction", "contention"])
def test_unavailable_debug_lock_does_not_claim_a_request(
    app: object, configured_debug_cache: SimpleNamespace, failure: str
) -> None:
    strict = configured_debug_cache.strict
    if failure == "construction":
        strict.lock.side_effect = CacheUnavailableError("Redis is not configured")
    else:
        lock = Mock()
        lock.acquire.return_value = False
        strict.lock.return_value = lock

    with pytest.raises(AppError) as exc_info:
        _store(app).begin_request()

    assert exc_info.value.code == 4023
    strict.setex.assert_not_called()
    assert configured_debug_cache.local.mock_calls == []


@pytest.mark.parametrize("failure", ["release", "save_acknowledgement"])
def test_saved_debug_session_survives_a_cache_acknowledgement_error(
    app: object, configured_debug_cache: SimpleNamespace, failure: str
) -> None:
    store = _store(app)
    session = Session(script=ScriptBundle(script="Current draft"))
    store.save(session)
    store.begin_request()
    session.memory["saved"] = "answer"
    lock = Mock()
    lock.acquire.return_value = True
    configured_debug_cache.strict.lock.return_value = lock
    if failure == "release":
        lock.release.side_effect = RedisConnectionError("Redis disconnected on release")
    else:

        def lose_acknowledgement(*args: object) -> None:
            configured_debug_cache.primary.setex(*args)
            msg = "Redis disconnected after saving"
            raise RedisConnectionError(msg)

        configured_debug_cache.strict.setex.side_effect = lose_acknowledgement

    with pytest.raises(AppError) as exc_info:
        store.save(session)

    assert exc_info.value.code == 4023
    recovered = _store(app)
    assert recovered.load(script="Current draft").memory == {"saved": "answer"}
    assert set(recovered._payload(script="Current draft")) == {
        "script_hash",
        "session",
        "turns",
    }
    lock.release.side_effect = None
    configured_debug_cache.strict.setex.side_effect = None
    recovered.begin_request()
    session.memory["continued"] = "next answer"
    recovered.save(session)
    assert recovered.load(script="Current draft").memory == {
        "saved": "answer",
        "continued": "next answer",
    }
    assert configured_debug_cache.local.mock_calls == []


def test_debug_lock_release_failure_does_not_undo_a_request_claim(
    app: object, configured_debug_cache: SimpleNamespace
) -> None:
    lock = Mock()
    lock.acquire.return_value = True
    lock.release.side_effect = RedisConnectionError("Redis disconnected on release")
    configured_debug_cache.strict.lock.return_value = lock
    store = _store(app)

    with pytest.raises(AppError) as exc_info:
        store.begin_request()

    assert exc_info.value.code == 4023
    assert store._request_bid
    assert configured_debug_cache.primary.get(f"{store._key}:request").decode() == (
        store._request_bid
    )
    assert configured_debug_cache.local.mock_calls == []


@pytest.mark.parametrize(
    "error_type", [RewindUnavailableError, ValueError, GeneratorExit]
)
def test_debug_lock_release_failure_preserves_the_original_error(
    app: object,
    configured_debug_cache: SimpleNamespace,
    error_type: type[BaseException],
) -> None:
    lock = Mock()
    lock.acquire.return_value = True
    lock.release.side_effect = RedisConnectionError("Redis disconnected on release")
    configured_debug_cache.strict.lock.return_value = lock
    original = error_type("Original failure")

    with pytest.raises(error_type) as exc_info, _store(app)._write_lock():
        raise original

    assert exc_info.value is original


def test_debug_cache_errors_do_not_hide_invalid_turn_metadata(
    app: object, configured_debug_cache: SimpleNamespace
) -> None:
    store = _store(app)
    store.begin_request()
    with pytest.raises(json.JSONDecodeError):
        store.save(
            Session(script=ScriptBundle(script="Current draft")),
            generated_block_bid="invalid",
            turn_record="invalid JSON",
        )
    configured_debug_cache.strict.getex.side_effect = ValueError("Unexpected cache bug")
    with pytest.raises(ValueError, match="Unexpected cache bug"):
        store.load(script="Current draft")
    assert configured_debug_cache.local.mock_calls == []


def test_debug_cache_provider_stays_fixed_for_each_store(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    configured_debug_cache: SimpleNamespace,
) -> None:
    distributed = _store(app)
    assert distributed._cache is configured_debug_cache.strict
    distributed.save(
        Session(
            script=ScriptBundle(script="Current draft"), memory={"backend": "Redis"}
        )
    )
    monkeypatch.setattr(debug_session, "get_redis_client", lambda: None)
    local = _store(app)
    assert local._cache is configured_debug_cache.local
    assert local.load(script="Current draft") is None
    local.begin_request()
    local.save(
        Session(
            script=ScriptBundle(script="Current draft"), memory={"backend": "local"}
        )
    )
    distributed.begin_request()
    assert distributed.load(script="Current draft").memory == {"backend": "Redis"}

    monkeypatch.setattr(debug_session, "get_redis_client", object)
    assert local.load(script="Current draft").memory == {"backend": "local"}
    local.begin_request()
    assert _store(app).load(script="Current draft").memory == {"backend": "Redis"}


def test_editor_debug_uses_the_existing_lesson_and_element_pipeline(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    calls: list[dict[str, object]] = []

    def lesson_events(_app: object, **kwargs: object) -> object:
        calls.append(kwargs)
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="turn",
            type=GeneratedType.CONTENT,
            content="Taught by the agent",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="turn",
            type=GeneratedType.DONE,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current editor draft",
                block_index=0,
                variables={"goal": "learn"},
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="run-one",
        ),
    )

    assert messages[0].type == "preview_engine"
    assert messages[0].content == "2.0"
    assert any(message.type == "element" for message in messages)
    assert messages[-1].type == "done"
    assert calls[0]["script_override"] == "Current editor draft"
    assert calls[0]["preview_mode"] is True
    assert isinstance(calls[0]["debug_store"], debug_session.DebugSessionStore)


@pytest.mark.parametrize(
    ("scope", "boundary"),
    [
        ("user", "finished"),
        ("user", "interaction"),
        ("user", "continue"),
        ("session", "interaction"),
        ("user", "failure"),
    ],
)
def test_editor_debug_exports_only_committed_cross_lesson_memory(
    app: object, monkeypatch: pytest.MonkeyPatch, scope: str, boundary: str
) -> None:
    """Exercise the named answer, model overwrite, saved session and wire boundary."""
    from flaskr.service.learn.agent import lesson_entry, run_agent
    from markdownflow.engine import Engine
    from pydantic_ai.models.function import DeltaToolCall

    from tests.service.learn.agent.test_lesson_entry_contracts import _entry_with_runner
    from tests.service.learn.agent.test_memory_integration import _drive

    label, topic = "Choose a topic for me", "Cache coherence"
    script = f"?[ {{{{topic}}}} {label} | ...Enter a topic]\n%{{{{pace}}}}"
    phase = 0

    def call(name: str, **args: object) -> dict[int, DeltaToolCall]:
        return {
            0: DeltaToolCall(
                name=name, tool_call_id=f"call-{phase}", json_args=json.dumps(args)
            )
        }

    async def model(_messages: list, _info: object) -> object:
        nonlocal phase
        phase += 1
        if phase == 1:
            yield call(
                "interact",
                type="single_or_text",
                variable="topic",
                prompt="Which topic?",
                options=[{"display": label}],
            )
        elif phase == 2:
            yield call("remember", key="topic", value=topic, scope=scope)
        elif phase == 3:
            yield call("remember", key="pace", value="slow", scope="user")
        elif phase == 4 and boundary == "interaction":
            yield call("interact", type="text", prompt="What should we try next?")
        elif phase == 4 and boundary == "continue":
            yield "Let us look at cache coherence."
        elif phase == 4 and boundary == "failure":
            message = "Synthetic provider failure after remembering the topic"
            raise RuntimeError(message)
        else:
            yield call("finish", summary="Topic selected")

    monkeypatch.setattr(debug_session, "cache", _Cache())
    _entry_with_runner(monkeypatch)
    lesson_entry.CourseTrace.return_value.observe.side_effect = lambda events: events
    monkeypatch.setattr(lesson_entry, "GatewayModel", Mock(return_value=Mock()))
    engine = Engine(FunctionModel(stream_function=model), memory_admission=True)
    monkeypatch.setattr(lesson_entry, "Engine", lambda *_a, **_kw: engine)
    monkeypatch.setattr(
        lesson_entry,
        "run_agent_lesson",
        lambda *args, **kwargs: run_agent.run_agent_lesson(
            *args, **kwargs, iter_turn=_drive
        ),
    )

    def debug(**kwargs: object) -> Iterator[RunElementSSEMessageDTO]:
        return debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content=script, block_index=0, **kwargs
            ),
            user_bid="teacher",
            shifu_bid="course",
            outline_bid="lesson",
            run_bid="one",
        )

    _request_messages(app, lambda: debug(variables={"pace": "fast"}))
    seed = {"topic": label, "pace": "fast"}
    if boundary == "failure":
        seen = []
        with app.test_request_context("/"), pytest.raises(AppError):
            seen.extend(
                message.type
                for message in debug(user_input={"topic": [label]}, variables=seed)
            )
        assert "debug_variables_committed" not in seen
        assert _store(app).load(script=script).all_memory()["topic"] == topic
        return

    messages = _request_messages(
        app, lambda: debug(user_input={"topic": [label]}, variables=seed)
    )
    committed = [
        (index, json.loads(message.content))
        for index, message in enumerate(messages)
        if message.type == "debug_variables_committed"
    ]
    assert len(committed) == (2 if boundary == "continue" else 1)
    assert all("user_variables" not in snapshot for _, snapshot in committed)
    index, payload = committed[0]
    assert messages[index + 1].type == "done"
    assert messages[index + 1].is_terminal == (boundary == "finished")
    assert (
        payload["variables"] | {"topic": topic, "pace": "slow"} == payload["variables"]
    )
    assert payload["course_updates"] == {
        "topic": topic if scope == "user" else label,
        "pace": "slow",
    }
    saved = _store(app).load(script=script)
    assert saved.all_memory() == committed[-1][1]["variables"]
    assert saved.user_memory["pace"] == "slow"
    if boundary == "continue":
        assert committed[-1][1]["course_updates"] == {}


def test_expired_debug_answer_does_not_start_a_new_lesson(
    app: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(debug_session, "cache", _Cache())
    stream = debug_session.stream_debug_preview(
        app,
        preview_request=PlaygroundPreviewRequest(
            content="Current draft",
            block_index=0,
            user_input={"answer": ["yes"]},
        ),
        shifu_bid="course",
        outline_bid="lesson",
        user_bid="teacher",
        run_bid="expired-run",
    )

    with pytest.raises(AppError) as exc_info:
        next(stream)
    assert exc_info.value.code == 4019


def test_an_answer_follows_the_edited_draft_only_when_asked(
    app: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(debug_session, "cache", _Cache())
    session = Session(script=ScriptBundle(script="Current draft"))
    session.memory["answer"] = "yes"
    _store(app).save(session)

    assert _store(app).load(script="Edited draft") is None
    following = debug_session.DebugSessionStore(
        app,
        user_bid="teacher",
        shifu_bid="course",
        outline_bid="lesson",
        run_bid="one",
        follow_script_edits=True,
    )
    resumed = following.load(script="Edited draft")
    assert resumed is not None
    assert resumed.memory["answer"] == "yes"


@pytest.mark.parametrize(
    ("user_input", "follows"),
    [({"answer": ["continue"]}, True), (None, False)],
    ids=["answer", "start"],
)
def test_only_an_answer_resumes_across_a_draft_edit(
    app: object,
    monkeypatch: object,
    user_input: dict | None,
    follows: bool,
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    monkeypatch.setattr(debug_session, "cache", _Cache())
    _store(app, "edited-run").save(Session(script=ScriptBundle(script="Old draft")))
    stores: list[debug_session.DebugSessionStore] = []

    def lesson_events(_app: object, **kwargs: object) -> object:
        stores.append(kwargs["debug_store"])
        assert kwargs["reload_generated_block_bid"] is None
        assert kwargs["reload_element_bid"] is None
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="turn",
            type=GeneratedType.DONE,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    list(
        debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Edited draft", block_index=0, user_input=user_input
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="edited-run",
        )
    )
    assert stores[0]._follow_script_edits is follows


def test_an_answer_after_a_draft_edit_continues_under_the_edited_script(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import run_agent

    monkeypatch.setattr(debug_session, "cache", _Cache())
    from markdownflow import render_first_prompt

    session = Session(script=ScriptBundle(script="Old draft"))
    session.messages = [
        ModelRequest(
            parts=[
                UserPromptPart(render_first_prompt(session.script, {"goal": "learn"}))
            ]
        )
    ]
    session.pending = [
        PendingInteraction("pause", InteractionSpec(type="confirm", prompt="Ready?")),
        PendingInteraction("next", InteractionSpec(type="text", prompt="Next answer?")),
    ]
    session.record_answer("kept", "earlier answer")
    session.answers = {"completed": "Learner wrote: earlier answer"}
    _store(app).save(session)
    following = debug_session.DebugSessionStore(
        app,
        user_bid="teacher",
        shifu_bid="course",
        outline_bid="lesson",
        run_bid="one",
        follow_script_edits=True,
    )

    factory, finished = run_agent._load_or_start(
        app,
        SimpleNamespace(),
        user_bid="teacher",
        shifu_bid="course",
        outline_bid="lesson",
        script="Edited draft",
        preview_mode=True,
        debug_store=following,
    )
    resumed = asyncio.run(factory())

    assert not finished
    assert resumed.id == session.id
    assert [pending.tool_call_id for pending in resumed.pending] == ["pause", "next"]
    assert resumed.answers == session.answers
    assert resumed.answer_hashes == session.answer_hashes
    assert resumed.memory["kept"] == "earlier answer"
    assert resumed.script.script == "Edited draft"
    # The model reads the script from the first prompt, so it carries the edit too.
    first_prompt = resumed.messages[0].parts[0].content
    assert "<script>\nEdited draft\n</script>" in first_prompt
    assert "Old draft" not in first_prompt
    assert first_prompt.startswith(
        render_first_prompt(session.script, {"goal": "learn"}).split("\n\n<script>")[0]
    )
    following.save(resumed)
    # Saved under the edited draft, so the next answer resumes without the flag.
    assert _store(app).load(script="Edited draft").id == session.id


@pytest.mark.parametrize(
    "historical_turns",
    [
        [
            {
                "block_bid": "old-turn",
                "record": {"checkpoint": {}, "values": ["Old input"]},
            }
        ],
        "invalid old sidecar",
    ],
)
def test_saving_an_edited_debug_session_drops_content_regeneration_retry(
    app: object, monkeypatch: object, historical_turns: object
) -> None:
    cache = _Cache()
    monkeypatch.setattr(debug_session, "cache", cache)
    session = Session(
        script=ScriptBundle(script="Old draft"), memory={"answer": "kept"}
    )
    session.pending = [
        PendingInteraction("pause", InteractionSpec(type="confirm", prompt="Ready?")),
        PendingInteraction("next", InteractionSpec(type="text", prompt="Next answer?")),
    ]
    session.answers = {"completed": "Learner wrote: saved answer"}
    store = _store(app)
    store.save(session)
    historical = json.loads(cache.values[store._key])
    historical["turns"] = historical_turns
    historical["regeneration_retry"] = {
        "requested_block_bid": "old-turn",
        "replacement_block_bid": "replacement",
    }
    cache.values[store._key] = json.dumps(historical)
    following = debug_session.DebugSessionStore(
        app,
        user_bid="teacher",
        shifu_bid="course",
        outline_bid="lesson",
        run_bid="one",
        follow_script_edits=True,
    )
    resumed = following.load(script="Edited draft")
    assert resumed.id == session.id
    assert resumed.memory == {"answer": "kept"}
    assert [pending.tool_call_id for pending in resumed.pending] == ["pause", "next"]
    assert resumed.answers == session.answers
    resumed.script = ScriptBundle(script="Edited draft")
    following.begin_request()
    following.save(resumed)

    migrated = store._payload(script="Edited draft")
    assert set(migrated) == {"script_hash", "session", "turns"}
    assert migrated["turns"] == (
        historical_turns if isinstance(historical_turns, list) else []
    )
    assert store.load(script="Old draft") is None
    saved = store.load(script="Edited draft")
    assert saved.id == session.id
    assert [pending.tool_call_id for pending in saved.pending] == ["pause", "next"]
    assert saved.answers == session.answers
    assert cache.ttls[store._key] == debug_session.DebugSessionStore.TTL_SECONDS


def test_question_closes_editor_response_without_ending_the_lesson(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    monkeypatch.setattr(debug_session, "cache", _Cache())

    def lesson_events(_app: object, **_kwargs: object) -> object:
        session = Session(script=ScriptBundle(script="Current draft"))
        record = _record(session)
        session.pending = [
            PendingInteraction(
                "q", InteractionSpec(type="text", prompt="Which option?")
            )
        ]
        _kwargs["debug_store"].save(
            session,
            generated_block_bid="question",
            turn_record=record,
            question_ids=["q"],
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="question",
            type=GeneratedType.INTERACTION,
            content="Which option?",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="question",
            type=GeneratedType.BREAK,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft", block_index=0
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="question-run",
        ),
    )

    done_messages = [message for message in messages if message.type == "done"]
    assert [message.is_terminal for message in done_messages] == [False, True]


def test_a_shown_control_is_bound_even_if_the_run_stops_before_done(
    app: object, monkeypatch: object
) -> None:
    """Editing that answer must not be refused because "done" never arrived."""
    from flaskr.service.learn.agent import lesson_entry

    cache = _Cache()
    monkeypatch.setattr(debug_session, "cache", cache)

    def lesson_events(_app: object, **kwargs: object) -> object:
        session = Session(script=ScriptBundle(script="Current draft"))
        record = _record(session)
        session.pending = [
            PendingInteraction("q", InteractionSpec(type="text", prompt="Which?"))
        ]
        kwargs["debug_store"].save(
            session,
            generated_block_bid="question",
            turn_record=record,
            question_ids=["q"],
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="question",
            type=GeneratedType.INTERACTION,
            content="Which?",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="question",
            type=GeneratedType.BREAK,
            content="",
        )

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lesson_events)
    with app.test_request_context("/"):
        stream = debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft", block_index=0
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="stopped-run",
        )
        control = None
        for message in stream:
            if message.type == "element" and (
                getattr(message.content, "element_type", None)
                == ElementType.INTERACTION
            ):
                control = message.content.element_bid
                break
        # The author stops the run: "done" is never produced.
        stream.close()
    assert control
    store = _store(app, "stopped-run")
    plan = store.plan_rewind(
        script="Current draft",
        block_bid="question",
        element_bid=control,
        answering=True,
    )
    assert plan.checkpoint["pending"][0]["tool_call_id"] == "q"


def test_finished_debug_reopening_closes_the_empty_response(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    # Finished lessons deliberately produce no new block or model request.
    monkeypatch.setattr(lesson_entry, "agent_lesson_events", lambda *_a, **_k: iter(()))
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft", block_index=0
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="finished-run",
        ),
    )

    assert [message.type for message in messages] == ["preview_engine", "done"]
    assert messages[-1].is_terminal is True
    assert not getattr(messages[-1], "generated_block_bid", None)


@pytest.mark.parametrize(
    "invalid", ["unknown", "element-in-selected", "prefix-from-other-run"]
)
def test_debug_rewind_requires_a_current_run_checkpoint(
    app: object, monkeypatch: object, invalid: str
) -> None:
    monkeypatch.setattr(debug_session, "cache", _Cache())
    session = Session(script=ScriptBundle(script="Current draft"))
    store = _store(app)
    store.save(session, generated_block_bid="selected", turn_record=_record(session))
    _store(app, "other").save(
        session,
        generated_block_bid="prefix-from-other-run",
        turn_record=_record(session),
    )
    with pytest.raises(RewindUnavailableError):
        store.plan_rewind(script="Current draft", block_bid=invalid)
    with pytest.raises(RewindUnavailableError):
        store.plan_rewind(script="Edited draft", block_bid="selected")


@pytest.mark.parametrize("provider_error", [False, True])
def test_real_debug_turns_save_the_session_and_preserve_user_inputs(
    app: object, monkeypatch: object, provider_error: bool
) -> None:
    """Normal and failed continuations retain the actual free-text input history."""
    from flaskr.service.learn.agent import run_agent
    from markdownflow.engine import Engine
    from markdownflow.engine.events import ErrorEvent

    from tests.service.learn.agent.test_memory_integration import _drive

    monkeypatch.setattr(debug_session, "cache", _Cache())
    calls = 0
    engine_events: list[object] = []

    def drive(make_events: Callable, **kwargs: object) -> Iterator:
        events = list(_drive(make_events, **kwargs))
        engine_events.extend(events)
        return iter(events)

    async def model(_messages: list, _info: object) -> object:
        nonlocal calls
        calls += 1
        yield f"Teaching step {calls}."
        if calls == 3 and provider_error:
            msg = "Provider failed after partial content"
            raise RuntimeError(msg)

    engine = Engine(FunctionModel(stream_function=model))
    with app.app_context():
        saved_id = None
        events = []
        for user_input in (
            None,
            {"input": ["First answer"]},
            {"input": ["Next answer"]},
        ):
            store = _store(app)
            store.begin_request()
            events = list(
                run_agent.run_agent_lesson(
                    app,
                    engine=engine,
                    script="Current draft",
                    user_bid="teacher",
                    shifu_bid="course",
                    outline_bid="lesson",
                    preview_mode=True,
                    debug_store=store,
                    preview_variables={"goal": "original"},
                    user_input=user_input,
                    iter_turn=drive,
                )
            )
            saved = store.load(script="Current draft")
            assert saved is not None
            assert saved.user_memory == {"goal": "original"}
            assert set(store._payload(script="Current draft")) == {
                "script_hash",
                "session",
                "turns",
            }
            if saved_id is None:
                saved_id = saved.id
            assert saved.id == saved_id
    assert calls == 3
    assert (
        any(isinstance(event, ErrorEvent) for event in engine_events) is provider_error
    )
    assert any("Teaching step 3." in message.content for message in events)
    user_prompts = [
        part.content
        for message in saved.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]
    # The first prompt supplies the script; subsequent prompts are submitted inputs.
    assert user_prompts[1:] == ["First answer", "Next answer"]


def test_new_debug_request_prevents_a_stopped_stream_from_overwriting_its_save(
    app: object, monkeypatch: object
) -> None:
    """A late terminal event from a stopped stream cannot overwrite the newer session."""
    monkeypatch.setattr(debug_session, "cache", _Cache())
    older = _store(app)
    older.begin_request()
    old_session = Session(script=ScriptBundle(script="Current draft"))
    older.save(old_session)

    replacement = _store(app)
    replacement.begin_request()
    current = replacement.load(script="Current draft")
    current.memory["new"] = "current answer"
    replacement.save(current)
    old_session.memory["future"] = "stale terminal save"
    with pytest.raises(RewindUnavailableError):
        older.save(old_session)

    assert replacement.load(script="Current draft").memory == {"new": "current answer"}
    assert set(replacement._payload(script="Current draft")) == {
        "script_hash",
        "session",
        "turns",
    }


@pytest.mark.parametrize("answering", [False, True])
def test_debug_rewind_retires_a_turn_saved_before_the_replacement_claim(
    app: object, monkeypatch: object, answering: bool
) -> None:
    """The runtime re-plans after claiming the request, including a racing old save."""
    from flaskr.service.learn.agent.rewind import restore
    from flaskr.service.learn.agent.run_agent import TurnOutcome

    from tests.service.learn.agent.test_lesson_entry_contracts import _entry_with_runner

    monkeypatch.setattr(debug_session, "cache", _Cache())
    older = _store(app)
    older.begin_request()
    session = Session(script=ScriptBundle(script="Current draft"))
    first = _record(session)
    session.messages.append(ModelRequest(parts=[UserPromptPart("Teaching A")]))
    session.memory["prefix"] = "kept"
    if answering:
        session.pending = [
            PendingInteraction("q", InteractionSpec(type="text", prompt="Choose?"))
        ]
    older.save(
        session,
        generated_block_bid="A",
        turn_record=first,
        question_ids=["q"] if answering else [],
    )
    if answering:
        older.bind_interactions(script="Current draft", elements={"A": ["A-question"]})
    selected = _record(session, ["old answer"] if answering else [])
    if not answering:
        session.messages.append(ModelRequest(parts=[UserPromptPart("Teaching B")]))
        session.memory["selected"] = "old B"
        older.save(session, generated_block_bid="B", turn_record=selected)

    begin_request = debug_session.DebugSessionStore.begin_request

    def racing_claim(
        store: debug_session.DebugSessionStore, *, generation: int | None = None
    ) -> None:
        # The stopped host completes between the preview's early plan and token claim.
        racing = selected if answering else _record(session)
        session.messages.append(ModelRequest(parts=[UserPromptPart("Racing teaching")]))
        session.memory["future"] = "discard"
        if answering:
            session.pending = []
            session.answers["q"] = "old answer"
        older.save(
            session, generated_block_bid="B" if answering else "C", turn_record=racing
        )
        begin_request(store, generation=generation)

    monkeypatch.setattr(debug_session.DebugSessionStore, "begin_request", racing_claim)
    runner = _entry_with_runner(monkeypatch)
    retired: list[str] = []

    def replacement_turn(_app: object, **kwargs: object) -> object:
        store = kwargs["debug_store"]
        plan = kwargs["rewind"]
        retired.extend(plan.retired_block_bids)
        if answering:
            assert kwargs["user_input"] == {"input": ["new answer"]}
            assert plan.replay_values is None
        restored = store.load(script="Current draft")
        restore(restored, plan.checkpoint)
        restored.user_memory = dict(plan.checkpoint["user_memory"])
        assert restored.all_memory() == {"prefix": "kept"}
        # Once the replacement claims its token, the stopped host cannot save again.
        with pytest.raises(RewindUnavailableError):
            older.save(session)
        restored.memory["replacement"] = "new B"
        store.save(
            restored,
            generated_block_bid="replacement",
            turn_record=selected,
            rewind=plan,
        )
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            generated_block_bid="replacement",
            type=GeneratedType.DONE,
            content="",
        )
        return TurnOutcome(reason="interaction", taught=True)

    runner.side_effect = replacement_turn
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft",
                block_index=0,
                reload_generated_block_bid="A" if answering else "B",
                reload_element_bid="A-question" if answering else None,
                user_input={"input": ["new answer"]} if answering else None,
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="one",
        ),
    )
    assert retired == (["B"] if answering else ["B", "C"])
    snapshots = [
        json.loads(message.content)
        for message in messages
        if message.type == "debug_variables"
    ]
    assert snapshots == [
        {"prefix": "kept"},
        {"prefix": "kept", "replacement": "new B"},
    ]
    latest = _store(app)
    assert [
        turn["block_bid"] for turn in latest._payload(script="Current draft")["turns"]
    ] == ["A", "replacement"]
    with pytest.raises(RewindUnavailableError):
        latest.plan_rewind(script="Current draft", block_bid="B" if answering else "C")


def test_debug_automatic_continuation_preserves_restored_output_language(
    app: object, monkeypatch: object
) -> None:
    """Dropping the browser's future snapshot must keep the checkpoint's teaching language."""
    from flaskr.i18n import clear_language, set_language
    from flaskr.service.learn.agent import run_agent

    monkeypatch.setattr(debug_session, "cache", _Cache())
    session = Session(
        script=ScriptBundle(script="Current draft"),
        user_memory={"sys_user_language": "fr-FR", "goal": "retained"},
    )
    store = _store(app)
    store.save(session)
    engine = SimpleNamespace(output_language=None)
    set_language("en-US")
    try:
        factory, _finished = run_agent._load_or_start(
            app,
            engine,
            user_bid="teacher",
            shifu_bid="course",
            outline_bid="lesson",
            script="Current draft",
            preview_mode=True,
            debug_store=store,
            preview_variables=None,
            use_learner_language=True,
        )
        resumed = asyncio.run(factory())
    finally:
        clear_language()
    assert resumed.user_memory == {"sys_user_language": "fr-FR", "goal": "retained"}
    assert engine.output_language == "Français"


@pytest.mark.parametrize("selected", [0, 1])
def test_debug_answer_edits_share_the_exact_accepting_checkpoint(
    app: object, monkeypatch: object, selected: int
) -> None:
    from flaskr.service.learn.agent import run_agent

    monkeypatch.setattr(debug_session, "cache", _Cache())
    store = _store(app)
    session = Session(
        script=ScriptBundle(script="Current draft"), user_memory={"seed": "keep"}
    )
    prefix = _record(session)
    session.memory["prefix"] = "keep"
    session.pending = [
        PendingInteraction("q1", InteractionSpec(type="text", prompt="First?")),
        PendingInteraction("q2", InteractionSpec(type="text", prompt="Second?")),
    ]
    store.save(
        session,
        generated_block_bid="questions",
        turn_record=prefix,
        question_ids=["q1", "q2"],
    )
    store.bind_interactions(
        script="Current draft", elements={"questions": ["e1", "e2"]}
    )
    for index in range(2):
        record = _record(session, [f"old-{index}"])
        question = session.pending.pop(0)
        session.answers[question.tool_call_id] = f"old-{index}"
        session.memory[f"answer-{index}"] = f"old-{index}"
        store.save(session, generated_block_bid=f"answer-{index}", turn_record=record)
    session.finished = True
    store.save(session, generated_block_bid="future", turn_record=_record(session))

    plan = store.plan_rewind(
        script="Current draft",
        block_bid="questions",
        element_bid=f"e{selected + 1}",
        answering=True,
    )
    assert plan.replay_values is None
    assert plan.retired_block_bids == [f"answer-{i}" for i in range(selected, 2)] + [
        "future"
    ]
    factory, finished = run_agent._load_or_start(
        app,
        SimpleNamespace(),
        user_bid="teacher",
        shifu_bid="course",
        outline_bid="lesson",
        script="Current draft",
        preview_mode=True,
        debug_store=store,
        rewind=plan,
        preview_variables={"future": "discard", "seed": "wrong"},
    )
    restored = asyncio.run(factory())
    assert not finished
    assert restored.id == session.id
    assert restored.pending[0].tool_call_id == f"q{selected + 1}"
    assert restored.all_memory() == {
        "seed": "keep",
        "prefix": "keep",
        **({"answer-0": "old-0"} if selected else {}),
    }
    replacement = _record(restored, ["new answer"])
    restored.answers[restored.pending.pop(0).tool_call_id] = "new answer"
    store.save(
        restored,
        generated_block_bid="replacement",
        turn_record=replacement,
        rewind=plan,
    )
    repeated = store.plan_rewind(
        script="Current draft",
        block_bid="questions",
        element_bid=f"e{selected + 1}",
        answering=True,
    )
    assert repeated.retired_block_bids == ["replacement"]
    assert repeated.replay_values is None
    with pytest.raises(RewindUnavailableError):
        store.plan_rewind(
            script="Current draft",
            block_bid="questions",
            element_bid="unowned",
            answering=True,
        )


@pytest.mark.parametrize("include_block", [False, True])
def test_debug_answer_edit_passes_exact_anchor_and_new_input_through_the_request(
    app: object, monkeypatch: object, include_block: bool
) -> None:
    from flaskr.service.learn.agent.run_agent import TurnOutcome

    from tests.service.learn.agent.test_lesson_entry_contracts import _entry_with_runner

    monkeypatch.setattr(debug_session, "cache", _Cache())
    store = _store(app)
    session = Session(script=ScriptBundle(script="Current draft"))
    before = _record(session)
    session.pending = [
        PendingInteraction("q", InteractionSpec(type="text", prompt="Choose?"))
    ]
    store.save(
        session, generated_block_bid="question", turn_record=before, question_ids=["q"]
    )
    store.bind_interactions(script="Current draft", elements={"question": ["control"]})
    accepting = _record(session, ["old"])
    session.pending = []
    session.answers["q"] = "old"
    session.memory["future"] = "discard"
    store.save(session, generated_block_bid="old-answer", turn_record=accepting)
    runner = _entry_with_runner(monkeypatch)
    seen = []

    def produce(_app: object, **kwargs: object) -> Iterator:
        seen.append(kwargs)
        assert kwargs["user_input"] == {"input": ["new"]}
        assert kwargs["rewind"].replay_values is None
        assert kwargs["rewind"].retired_block_bids == ["old-answer"]
        assert kwargs["rewind"].checkpoint["pending"][0]["tool_call_id"] == "q"
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            type=GeneratedType.DONE,
            content="",
            generated_block_bid="replacement",
        )
        return TurnOutcome(reason="interaction", taught=True)

    runner.side_effect = produce
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Current draft",
                block_index=0,
                reload_generated_block_bid="question" if include_block else None,
                reload_element_bid="control",
                user_input={"input": ["new"]},
                variables={"future": "discard"},
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="one",
        ),
    )
    assert len(seen) == 1
    assert messages[0].type == "debug_variables"
    assert json.loads(messages[0].content) == {}
    assert not any(message.type == "error" for message in messages)


def test_debug_answer_edit_after_a_draft_edit_rewinds_instead_of_expiring(
    app: object, monkeypatch: object
) -> None:
    """Changing an earlier answer after editing the draft continues from that answer."""
    from flaskr.service.learn.agent.run_agent import TurnOutcome

    from tests.service.learn.agent.test_lesson_entry_contracts import _entry_with_runner

    monkeypatch.setattr(debug_session, "cache", _Cache())
    store = _store(app)
    session = Session(script=ScriptBundle(script="Old draft"))
    before = _record(session)
    session.pending = [
        PendingInteraction("q", InteractionSpec(type="text", prompt="Choose?"))
    ]
    store.save(
        session, generated_block_bid="question", turn_record=before, question_ids=["q"]
    )
    store.bind_interactions(script="Old draft", elements={"question": ["control"]})
    accepting = _record(session, ["old"])
    session.pending = []
    session.answers["q"] = "old"
    store.save(session, generated_block_bid="old-answer", turn_record=accepting)
    runner = _entry_with_runner(monkeypatch)
    seen = []

    def produce(_app: object, **kwargs: object) -> Iterator:
        seen.append(kwargs)
        assert kwargs["script"] == "Edited draft"
        assert kwargs["debug_store"]._follow_script_edits is True
        assert kwargs["rewind"].retired_block_bids == ["old-answer"]
        assert kwargs["rewind"].checkpoint["pending"][0]["tool_call_id"] == "q"
        yield RunMarkdownFlowDTO(
            outline_bid="lesson",
            type=GeneratedType.DONE,
            content="",
            generated_block_bid="replacement",
        )
        return TurnOutcome(reason="interaction", taught=True)

    runner.side_effect = produce
    messages = _request_messages(
        app,
        lambda: debug_session.stream_debug_preview(
            app,
            preview_request=PlaygroundPreviewRequest(
                content="Edited draft",
                block_index=0,
                reload_generated_block_bid="question",
                reload_element_bid="control",
                user_input={"input": ["new"]},
            ),
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            run_bid="one",
        ),
    )
    assert len(seen) == 1
    assert not any(message.type == "error" for message in messages)


def test_debug_session_reads_refresh_its_expiry(
    app: object, monkeypatch: object
) -> None:
    cache = _Cache()
    monkeypatch.setattr(debug_session, "cache", cache)
    store = _store(app)
    store.save(Session(script=ScriptBundle(script="Current draft")))
    cache.ttls[store._key] = 1
    assert store.load(script="Current draft") is not None
    assert cache.ttls[store._key] == debug_session.DebugSessionStore.TTL_SECONDS


def test_debug_pending_answer_edit_fences_a_running_turn_before_its_first_save(
    app: object, monkeypatch: object
) -> None:
    monkeypatch.setattr(debug_session, "cache", _Cache())
    old = _store(app)
    old.begin_request()
    session = Session(script=ScriptBundle(script="Current draft"))
    before = _record(session)
    session.pending = [
        PendingInteraction("q", InteractionSpec(type="text", prompt="Choose?"))
    ]
    old.save(
        session, generated_block_bid="question", turn_record=before, question_ids=["q"]
    )
    old.bind_interactions(script="Current draft", elements={"question": ["control"]})
    replacement = _store(app)
    replacement.begin_request()
    plan = replacement.plan_rewind(
        script="Current draft",
        block_bid="question",
        element_bid="control",
        answering=True,
    )
    assert plan.replay_values is None
    assert plan.checkpoint["pending"][0]["tool_call_id"] == "q"
    assert plan.retired_block_bids == []
    with pytest.raises(RewindUnavailableError):
        old.save(
            session, generated_block_bid="late", turn_record=_record(session, ["old"])
        )
    with pytest.raises(RewindUnavailableError):
        old.bind_interactions(script="Current draft", elements={"question": ["wrong"]})
    assert replacement._payload(script="Current draft")["turns"][0][
        "interaction_elements"
    ] == ["control"]


@pytest.mark.parametrize("question_count", [1, 2])
def test_real_debug_answer_edit_uses_new_input_and_keeps_only_the_original_prefix(
    app: object, monkeypatch: object, question_count: int
) -> None:
    """Send the restored user scope separately from replacement lesson memory."""
    from flaskr.service.learn.agent import lesson_entry, run_agent
    from markdownflow.engine import Engine
    from pydantic_ai.models.function import DeltaToolCall

    from tests.service.learn.agent.test_lesson_entry_contracts import _entry_with_runner
    from tests.service.learn.agent.test_memory_integration import _drive

    monkeypatch.setattr(debug_session, "cache", _Cache())
    _entry_with_runner(monkeypatch)
    lesson_entry.CourseTrace.return_value.observe.side_effect = lambda events: events
    calls = 0
    replacement_history = []

    async def model(messages: list, _info: object) -> object:
        nonlocal calls
        calls += 1
        # Admission is durable before output, even when the model has not finished.
        saved = _store(app)._payload(script="Current draft")
        assert len(saved["turns"]) >= 1
        if calls == 4:
            replacement_history.extend(
                str(part) for message in messages for part in message.parts
            )
        yield f"Teaching {calls}."
        tools = {
            i: DeltaToolCall(
                name="interact",
                tool_call_id=f"q{calls}-{i}",
                json_args=json.dumps(
                    {
                        "type": "text",
                        "prompt": f"Question {calls}-{i}?",
                        "placeholder": "Answer",
                    }
                ),
            )
            for i in range(question_count if calls == 1 else 1)
        }
        if calls == 4:
            tools[len(tools)] = DeltaToolCall(
                name="remember",
                tool_call_id="replacement-note",
                json_args=json.dumps(
                    {"key": "scratch", "value": "New working note", "scope": "session"}
                ),
            )
        yield tools

    engine = Engine(FunctionModel(stream_function=model))
    monkeypatch.setattr(lesson_entry, "GatewayModel", Mock(return_value=Mock()))
    monkeypatch.setattr(lesson_entry, "Engine", lambda *_a, **_k: engine)
    monkeypatch.setattr(
        lesson_entry,
        "run_agent_lesson",
        lambda *a, **kw: run_agent.run_agent_lesson(*a, **kw, iter_turn=_drive),
    )

    def run(**kwargs: object) -> list:
        return list(
            debug_session.stream_debug_preview(
                app,
                preview_request=PlaygroundPreviewRequest(
                    content="Current draft", block_index=0, **kwargs
                ),
                user_bid="teacher",
                shifu_bid="course",
                outline_bid="lesson",
                run_bid="one",
            )
        )

    with app.test_request_context("/"):
        first = run(variables={"seed": "keep"})
        controls = [
            message.content
            for message in first
            if message.type == "element"
            and message.content.element_type == ElementType.INTERACTION
        ]
        # Snapshots may repeat a control; retain the exact rendered identities.
        controls = list({control.element_bid: control for control in controls}.values())
        assert len(controls) == question_count
        control = controls[-1]
        original = _store(app).load(script="Current draft")
        if question_count == 2:
            run(user_input={"input": ["PREFIX ANSWER"]})
        run(user_input={"input": ["OLD ANSWER"]})
        run(user_input={"input": ["FUTURE ANSWER"]})
        result = run(
            reload_generated_block_bid=control.generated_block_bid,
            reload_element_bid=control.element_bid,
            user_input={"input": ["NEW ANSWER"]},
            variables={"seed": "wrong", "future": "discard"},
        )
        restored = _store(app).load(script="Current draft")
        turns = _store(app)._payload(script="Current draft")["turns"]
    assert calls == 4
    assert restored.id == original.id
    assert restored.user_memory == {"seed": "keep"}
    assert restored.pending[0].tool_call_id == "q4-0"
    assert len(turns) == question_count + 1
    assert turns[0]["block_bid"] == control.generated_block_bid
    assert turns[-1]["record"]["values"] == ["NEW ANSWER"]
    assert "NEW ANSWER" in " ".join(replacement_history)
    assert "OLD ANSWER" not in " ".join(replacement_history)
    assert "FUTURE ANSWER" not in " ".join(replacement_history)
    assert any(message.type == "debug_variables" for message in result)
    committed = next(
        message for message in result if message.type == "debug_variables_committed"
    )
    assert json.loads(committed.content) == {
        "variables": {"seed": "keep", "scratch": "New working note"},
        "user_variables": {"seed": "keep"},
        "course_updates": {},
    }
    assert result[-2] is committed
    assert result[-1].type == "done"


@pytest.mark.parametrize("expired_fence", [False, True])
def test_late_older_debug_admission_cannot_replace_newer_request(
    app: object, monkeypatch: object, expired_fence: bool
) -> None:
    backend = _Cache()
    monkeypatch.setattr(debug_session, "cache", backend)
    older, newer = _store(app), _store(app)
    session = Session(script=ScriptBundle(script="Current draft"))
    newer.begin_request(generation=2)
    admitted = dict(backend.values)
    with pytest.raises(RewindUnavailableError):
        older.begin_request(generation=1)
    assert backend.values == admitted
    session.memory["choice"] = "new answer"
    newer.save(session)
    if expired_fence:
        del backend.values[f"{newer._key}:request"]
    before = dict(backend.values)
    for generation in (1, 2, None):
        with pytest.raises(RewindUnavailableError):
            older.begin_request(generation=generation)
        assert backend.values == before
    if not expired_fence:
        newer.save(session)
        assert newer.load(script="Current draft").memory["choice"] == "new answer"
    latest = _store(app)
    latest.begin_request(generation=3)
    session.memory["choice"] = "latest answer"
    latest.save(session)
    with pytest.raises(RewindUnavailableError):
        newer.save(session)
    assert latest.load(script="Current draft").memory["choice"] == "latest answer"


@pytest.mark.parametrize("generation", [0, -1, True, 1.5, "2", 9007199254740992])
def test_debug_generation_rejects_non_positive_or_unsafe_integers(
    generation: object,
) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PlaygroundPreviewRequest(
            content="Draft", block_index=0, request_generation=generation
        )


def test_stale_debug_http_generation_is_rejected_before_starting_the_engine(
    app: object, monkeypatch: object
) -> None:
    from tests.service.learn.agent.test_lesson_entry_contracts import _entry_with_runner

    monkeypatch.setattr(debug_session, "cache", _Cache())
    latest = _store(app)
    latest.begin_request(generation=2)
    session = Session(
        script=ScriptBundle(script="Current draft"), memory={"choice": "new"}
    )
    latest.save(session)
    runner = _entry_with_runner(monkeypatch)
    with pytest.raises(AppError):
        _request_messages(
            app,
            lambda: debug_session.stream_debug_preview(
                app,
                preview_request=PlaygroundPreviewRequest(
                    content="Current draft",
                    block_index=0,
                    user_input={"input": ["old"]},
                    request_generation=1,
                ),
                user_bid="teacher",
                shifu_bid="course",
                outline_bid="lesson",
                run_bid="one",
            ),
        )
    runner.assert_not_called()
    latest.save(session)
    assert latest.load(script="Current draft").memory == {"choice": "new"}


@pytest.mark.parametrize("stored_session", [None, "{}", "invalid history", "missing"])
@pytest.mark.parametrize("follow_script_edits", [False, True])
def test_incompatible_debug_history_is_treated_as_expired(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    stored_session: str | None,
    follow_script_edits: bool,
) -> None:
    """A fresh conversation cannot inherit an expired conversation's checkpoints."""
    backend = _Cache()
    monkeypatch.setattr(debug_session, "cache", backend)
    old = _store(app)
    old.begin_request(generation=2)
    expired = Session(
        script=ScriptBundle(script="Current draft"),
        memory={"old_answer": "discard"},
        user_memory={"old_note": "discard"},
    )
    old.save(expired, generated_block_bid="old-turn", turn_record=_record(expired))
    assert old.plan_rewind(script="Current draft", block_bid="old-turn")
    payload = json.loads(backend.values[old._key])
    if stored_session == "missing":
        del payload["session"]
    else:
        payload["session"] = stored_session
    backend.values[old._key] = json.dumps(payload)

    store = debug_session.DebugSessionStore(
        app,
        user_bid="teacher",
        shifu_bid="course",
        outline_bid="lesson",
        run_bid="one",
        follow_script_edits=follow_script_edits,
    )
    script = "Edited draft" if follow_script_edits else "Current draft"
    assert store.load(script=script) is None
    fresh = Session(script=ScriptBundle(script=script), memory={"new_answer": "keep"})
    store.save(fresh)

    saved = store._payload(script=script)
    assert saved["turns"] == []
    assert store.load(script=script).id == fresh.id
    assert store.load(script=script).all_memory() == {"new_answer": "keep"}
    with pytest.raises(RewindUnavailableError):
        store.plan_rewind(script=script, block_bid="old-turn")

    # Expiring the conversation must not let an older request claim its run.
    assert saved["request_generation"] == 2
    del backend.values[f"{store._key}:request"]
    for generation in (None, 1, 2):
        with pytest.raises(RewindUnavailableError):
            store.begin_request(generation=generation)
    store.begin_request(generation=3)
    store.save(fresh, generated_block_bid="new-turn", turn_record=_record(fresh))
    assert [turn["block_bid"] for turn in store._payload(script=script)["turns"]] == [
        "new-turn"
    ]
    assert store.plan_rewind(script=script, block_bid="new-turn").checkpoint[
        "memory"
    ] == {"new_answer": "keep"}
    with pytest.raises(RewindUnavailableError):
        store.plan_rewind(script=script, block_bid="old-turn")
