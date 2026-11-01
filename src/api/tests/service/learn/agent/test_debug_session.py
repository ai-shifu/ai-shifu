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
from flaskr.service.learn.agent.rewind import RewindUnavailableError
from flaskr.service.learn.learn_dtos import (
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
    assert list(cache.ttls.values()) == [30 * 60]
    restarted = Session(script=ScriptBundle(script="Current draft"))
    restarted.memory["answer"] = "fresh answer"
    other.save(restarted)
    assert other.load(script="Current draft").memory["answer"] == "fresh answer"
    assert first.load(script="Current draft").memory["answer"] == "yes"
    assert cache.ttls[other._key] == 30 * 60
    cache.values[first._key] = "invalid history"
    assert first.load(script="Current draft") is None
    assert other.load(script="Current draft").memory["answer"] == "fresh answer"


@pytest.mark.parametrize("serialized", [None, "{}", "invalid history"])
def test_incompatible_debug_history_is_treated_as_expired(
    app: object, monkeypatch: object, serialized: str | None
) -> None:
    cache = _Cache()
    monkeypatch.setattr(debug_session, "cache", cache)
    store = _store(app)
    store.save(Session(script=ScriptBundle(script="Current draft")))
    payload = json.loads(cache.values[store._key])
    payload["session"] = serialized
    cache.values[store._key] = json.dumps(payload)

    assert store.load(script="Current draft") is None
    store.save(
        Session(script=ScriptBundle(script="Current draft"), memory={"new": "run"})
    )
    assert store.load(script="Current draft").memory == {"new": "run"}


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
    method = "setex" if operation in {"token_write", "session_write"} else "get"
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
    assert set(recovered._payload(script="Current draft")) == {"script_hash", "session"}
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


def test_debug_cache_errors_do_not_hide_unexpected_failures(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    configured_debug_cache: SimpleNamespace,
) -> None:
    store = _store(app)
    store.begin_request()
    monkeypatch.setattr(
        Session, "dumps", Mock(side_effect=ValueError("Unexpected serialization bug"))
    )
    with pytest.raises(ValueError, match="Unexpected serialization bug"):
        store.save(Session(script=ScriptBundle(script="Current draft")))
    configured_debug_cache.strict.get.side_effect = ValueError("Unexpected cache bug")
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
        assert "reload_generated_block_bid" not in kwargs
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
def test_saving_an_edited_debug_session_drops_historical_regeneration_sidecars(
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
    assert set(migrated) == {"script_hash", "session"}
    assert store.load(script="Old draft") is None
    saved = store.load(script="Edited draft")
    assert saved.id == session.id
    assert [pending.tool_call_id for pending in saved.pending] == ["pause", "next"]
    assert saved.answers == session.answers
    assert cache.ttls[store._key] == 30 * 60


def test_question_closes_editor_response_without_ending_the_lesson(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.learn.agent import lesson_entry

    def lesson_events(_app: object, **_kwargs: object) -> object:
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


@pytest.mark.parametrize("provider_error", [False, True])
def test_real_debug_turns_save_only_the_session_and_preserve_answers(
    app: object, monkeypatch: object, provider_error: bool
) -> None:
    """Normal and failed continuations persist without per-turn replay metadata."""
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
            }
            if saved_id is None:
                saved_id = saved.id
            assert saved.id == saved_id
    assert calls == 3
    assert (
        any(isinstance(event, ErrorEvent) for event in engine_events) is provider_error
    )
    assert any("Teaching step 3." in message.content for message in events)
    history = saved.dumps()
    assert "First answer" in history
    assert "Next answer" in history


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
    }


def test_debug_automatic_continuation_preserves_saved_output_language(
    app: object, monkeypatch: object
) -> None:
    """A resumed Debug session keeps its saved teaching language without a browser snapshot."""
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
