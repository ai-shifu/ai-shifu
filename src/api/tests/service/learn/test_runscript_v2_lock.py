"""Verify runscript v2 lock behavior."""

import contextlib
import json
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from flask import Flask, has_app_context
from flaskr.service.common.models import AppError
from flaskr.service.learn.host import db_session as host_db_session
from flaskr.service.learn.host import lesson as host_lesson
from flaskr.service.learn.host import run as host_run
from flaskr.service.learn.host import sse as host_sse
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)


@pytest.fixture(autouse=True)
def _route_checkpoint_commit_to_patched_session(monkeypatch: object) -> None:
    """Make the step checkpoint call ``host_db_session.db.session.commit()``.

    The checkpoint goes through ``unit_of_work()`` (which commits the real
    scoped session); tests here observe commits on a patched
    ``host_db_session.db`` instead, so route the commit there.
    """

    @contextlib.contextmanager
    def _fake_unit_of_work() -> Iterator[None]:
        yield
        host_db_session.db.session.commit()

    monkeypatch.setattr(host_db_session, "unit_of_work", _fake_unit_of_work)


@pytest.fixture(autouse=True)
def _skip_connection_probe(monkeypatch: object) -> None:
    # These tests exercise run-script locking and orchestration with minimal
    # fake sessions; the connection health probe has its own dedicated tests
    # in test_runscript_v2_connection_probe.py.
    monkeypatch.setattr(host_lesson, "_ensure_healthy_db_connection", lambda _app: None)


class FakeLock:
    """Simulate lock behavior for tests."""

    def __init__(self, acquire_results: list[bool]) -> None:
        """Queue acquisition outcomes and reset acquire and release counters."""
        self._acquire_results = list(acquire_results)
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self, blocking: object = True) -> object:
        _ = blocking
        self.acquire_calls += 1
        if self._acquire_results:
            return self._acquire_results.pop(0)
        return False

    def release(self) -> None:
        self.release_calls += 1


class FakeCacheProvider:
    """Simulate cache provider behavior for tests."""

    def __init__(self, lock: FakeLock) -> None:
        """Bind a test lock and initialize the cached byte values."""
        self._lock = lock
        self.values: dict[str, bytes] = {}

    def lock(self, *_args: object, **_kwargs: object) -> object:
        return self._lock

    def setex(self, key: str, _time_in_seconds: int, value: object) -> object:
        encoded = value if isinstance(value, bytes) else str(value).encode("utf-8")
        self.values[key] = encoded
        return True

    def get(self, key: str) -> object:
        return self.values.get(key)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
                self.values.pop(key, None)
        return deleted


class FakeListenElementAdapter:
    """Simulate listen element adapter behavior for tests."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Initialize event sequencing for a fixed run session."""
        self._seq = 0
        self._run_session_bid = "run-session-1"

    def process(self, events: object) -> Iterator[RunElementSSEMessageDTO]:
        for event in events:
            if event.type == GeneratedType.ASK:
                continue
            if event.type == GeneratedType.BREAK:
                yield self.make_ephemeral_message(
                    event_type=GeneratedType.DONE.value,
                    content="",
                    is_terminal=False,
                )
                continue
            yield self.make_ephemeral_message(
                event_type="element",
                content=event.content,
                is_terminal=False,
            )

    def make_ephemeral_message(
        self,
        *,
        event_type: str,
        content: object,
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        self._seq += 1
        return RunElementSSEMessageDTO(
            type=event_type,
            event_type=event_type,
            content=content,
            run_event_seq=self._seq,
            run_session_bid=self._run_session_bid,
            is_terminal=is_terminal,
        )


def _parse_sse_events(chunks: list[str]) -> list[dict]:
    events: list[dict] = []
    prefix = "data: "
    for chunk in chunks:
        if not isinstance(chunk, str) or not chunk.startswith(prefix):
            continue
        payload = chunk[len(prefix) :].strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    return events


def _make_test_app() -> Flask:
    app = Flask(__name__)
    app.config["REDIS_KEY_PREFIX"] = "test"
    app.config["SSE_HEARTBEAT_INTERVAL"] = 0
    return app


def test_sse_chunk_serializes_datetime_as_utc_iso_z() -> None:
    chunk = host_sse._to_sse_chunk(
        {
            "created_at": datetime(
                2026, 6, 30, 19, 57, 3, tzinfo=timezone(timedelta(hours=8))
            )
        }
    )

    events = _parse_sse_events([chunk])

    assert events == [{"created_at": "2026-06-30T11:57:03Z"}]


def _patch_fake_element_adapter(monkeypatch: object) -> None:
    monkeypatch.setattr(host_run, "ListenElementRunAdapter", FakeListenElementAdapter)


def test_run_script_retries_lock_then_streams(monkeypatch: object) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([False, True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)
        monkeypatch.setattr(host_run.time, "sleep", lambda *_args, **_kwargs: None)

        def fake_lesson_events(**_kwargs: object) -> object:
            with app.app_context():
                yield from [
                    RunMarkdownFlowDTO(
                        outline_bid="outline-1",
                        generated_block_bid="generated-1",
                        type=GeneratedType.CONTENT,
                        content="hello",
                    ),
                    RunMarkdownFlowDTO(
                        outline_bid="outline-1",
                        generated_block_bid="generated-1",
                        type=GeneratedType.BREAK,
                        content="",
                    ),
                ]

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
            )
        )
        events = _parse_sse_events(chunks)

        assert lock.acquire_calls == 2
        assert lock.release_calls == 1
        assert [event["type"] for event in events] == ["element", "done"]
        assert events[0]["content"] == "hello"
        assert events[-1]["type"] == "done"
        assert events[-1]["is_terminal"] is True


def test_run_script_producer_owns_app_context(monkeypatch: object) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)
        observed = {"has_app_context": None}

        def fake_lesson_events(**_kwargs: object) -> object:
            observed["has_app_context"] = has_app_context()
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="generated-1",
                type=GeneratedType.CONTENT,
                content="hello",
            )

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
            )
        )
        events = _parse_sse_events(chunks)

        assert observed == {"has_app_context": True}
        assert [event["type"] for event in events] == ["element", "done"]


def test_run_script_removes_producer_db_session(monkeypatch: object) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        remove_calls = []
        monkeypatch.setattr(host_run, "cache_provider", cache)
        monkeypatch.setattr(
            host_db_session,
            "db",
            SimpleNamespace(
                session=SimpleNamespace(remove=lambda: remove_calls.append("remove"))
            ),
        )

        def fake_lesson_events(**_kwargs: object) -> object:
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="generated-1",
                type=GeneratedType.CONTENT,
                content="hello",
            )

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
            )
        )

        assert _parse_sse_events(chunks)
        assert remove_calls == ["remove"]


def test_run_script_producer_done_survives_db_session_remove_failure(
    monkeypatch: object,
) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        remove_calls = []
        monkeypatch.setattr(host_run, "cache_provider", cache)

        def _remove() -> None:
            remove_calls.append("remove")
            message = "remove failed"
            raise RuntimeError(message)

        monkeypatch.setattr(
            host_db_session,
            "db",
            SimpleNamespace(session=SimpleNamespace(remove=_remove)),
        )

        def fake_lesson_events(**_kwargs: object) -> object:
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="generated-1",
                type=GeneratedType.CONTENT,
                content="hello",
            )

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
            )
        )
        events = _parse_sse_events(chunks)

        assert [event["type"] for event in events] == ["element", "done"]
        assert remove_calls == ["remove"]


def test_run_script_read_mode_keeps_interaction_after_block_break(
    monkeypatch: object,
) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)

        def fake_lesson_events(**_kwargs: object) -> object:
            with app.app_context():
                yield from [
                    RunMarkdownFlowDTO(
                        outline_bid="outline-1",
                        generated_block_bid="generated-1",
                        type=GeneratedType.CONTENT,
                        content="hello",
                    ),
                    RunMarkdownFlowDTO(
                        outline_bid="outline-1",
                        generated_block_bid="generated-1",
                        type=GeneratedType.BREAK,
                        content="",
                    ),
                    RunMarkdownFlowDTO(
                        outline_bid="outline-1",
                        generated_block_bid="generated-2",
                        type=GeneratedType.INTERACTION,
                        content="?[%{{name}}...How should I call you?]",
                    ),
                ]

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
                listen=False,
            )
        )
        events = _parse_sse_events(chunks)

        assert [event["type"] for event in events] == [
            "element",
            "element",
            "done",
        ]
        assert events[1]["content"] == "?[%{{name}}...How should I call you?]"


def test_run_script_ask_mode_uses_element_protocol(monkeypatch: object) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)

        def fake_follow_up(**_kwargs: object) -> object:
            with app.app_context():
                element_adapter = _kwargs["element_adapter"]
                yield from element_adapter.process(
                    [
                        RunMarkdownFlowDTO(
                            outline_bid="outline-1",
                            generated_block_bid="generated-ask",
                            type=GeneratedType.ASK,
                            content="follow-up question",
                            anchor_element_bid="element-1",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid="outline-1",
                            generated_block_bid="generated-ask",
                            type=GeneratedType.CONTENT,
                            content="answer chunk",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid="outline-1",
                            generated_block_bid="generated-ask",
                            type=GeneratedType.BREAK,
                            content="",
                        ),
                    ]
                )

        monkeypatch.setattr(host_lesson, "_follow_up_events", fake_follow_up)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input="follow-up question",
                input_type="ask",
                listen=False,
            )
        )
        events = _parse_sse_events(chunks)

        assert [event["type"] for event in events] == ["element", "done"]
        assert events[1]["is_terminal"] is True


def test_run_script_ask_mode_ignores_listen_flag(monkeypatch: object) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        observed: dict[str, object] = {}
        monkeypatch.setattr(host_run, "cache_provider", cache)

        def fake_follow_up(**_kwargs: object) -> object:
            observed["listen"] = _kwargs["listen"]
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="generated-ask",
                type=GeneratedType.CONTENT,
                content="answer chunk",
            )
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="generated-ask",
                type=GeneratedType.BREAK,
                content="",
            )

        monkeypatch.setattr(host_lesson, "_follow_up_events", fake_follow_up)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input="follow-up question",
                input_type="ask",
                listen=True,
            )
        )
        events = _parse_sse_events(chunks)

        assert observed["listen"] is False
        assert [event["type"] for event in events] == ["element", "done"]
        assert events[-1]["is_terminal"] is True


def test_follow_up_events_route_through_element_adapter_and_commit(
    monkeypatch: object,
) -> None:
    from flaskr.service.learn.ask import follow_up_run as ask

    app = Flask(__name__)
    commits = []
    removed = []
    monkeypatch.setattr(host_lesson, "_ensure_healthy_db_connection", lambda _app: None)
    monkeypatch.setattr(
        host_lesson, "_commit_pending_step", lambda: commits.append(True)
    )
    monkeypatch.setattr(
        host_lesson,
        "_remove_db_session_safely",
        lambda _app, *, source: removed.append(source),
    )
    seen = {}

    def fake_follow_up_events(_app: object, **kwargs: object) -> object:
        seen.update(kwargs)
        yield RunMarkdownFlowDTO(
            outline_bid="outline-1",
            generated_block_bid="generated-ask",
            type=GeneratedType.ASK,
            content="follow-up question",
            anchor_element_bid="element-1",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="outline-1",
            generated_block_bid="generated-ask",
            type=GeneratedType.CONTENT,
            content="answer chunk",
        )
        yield RunMarkdownFlowDTO(
            outline_bid="outline-1",
            generated_block_bid="generated-ask",
            type=GeneratedType.BREAK,
            content="",
        )

    monkeypatch.setattr(ask, "follow_up_events", fake_follow_up_events)

    class FakeElementAdapter:
        def __init__(self) -> None:
            self.calls = []

        def process(self, events: object) -> object:
            captured = list(events)
            self.calls.append(captured)
            return iter([f"converted:{event.type.value}" for event in captured])

    element_adapter = FakeElementAdapter()
    stop_event = threading.Event()

    emitted = list(
        host_lesson._follow_up_events(
            app=app,
            user_bid="user-1",
            outline_bid="outline-1",
            user_input="follow-up question",
            reload_generated_block_bid=None,
            reload_element_bid="element-1",
            listen=False,
            learning_mode="read",
            preview_mode=False,
            stop_event=stop_event,
            element_adapter=element_adapter,
        )
    )

    assert emitted == ["converted:ask", "converted:content", "converted:break"]
    assert [event.type for event in element_adapter.calls[0]] == [
        GeneratedType.ASK,
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
    ]
    assert seen["reload_element_bid"] == "element-1"
    assert seen["stop_event"] is stop_event
    assert commits == [True]
    assert removed == ["follow-up"]


def test_cancelled_follow_up_discards_the_connection_without_committing(
    monkeypatch: object,
) -> None:
    from flaskr.service.learn.ask import follow_up_run as ask

    app = Flask(__name__)
    commits = []
    discarded = []
    monkeypatch.setattr(host_lesson, "_ensure_healthy_db_connection", lambda _app: None)
    monkeypatch.setattr(
        host_lesson, "_commit_pending_step", lambda: commits.append(True)
    )
    monkeypatch.setattr(
        host_lesson,
        "_discard_session_connection",
        lambda *, source: discarded.append(source),
    )
    monkeypatch.setattr(
        host_lesson, "_remove_db_session_safely", lambda _app, **_kwargs: None
    )

    def cancelled(_app: object, **_kwargs: object) -> object:
        raise ask.FollowUpCancelledError
        yield  # pragma: no cover - makes this a generator

    monkeypatch.setattr(ask, "follow_up_events", cancelled)
    adapter = SimpleNamespace(process=lambda events: events)

    emitted = list(
        host_lesson._follow_up_events(
            app=app,
            user_bid="user-1",
            outline_bid="outline-1",
            user_input="question",
            reload_generated_block_bid=None,
            reload_element_bid=None,
            listen=False,
            learning_mode="read",
            preview_mode=False,
            stop_event=threading.Event(),
            element_adapter=adapter,
        )
    )

    assert emitted == []
    assert commits == []
    assert discarded == ["follow-up cancelled"]


def test_failed_follow_up_cleans_the_session_through_the_dao(
    monkeypatch: object,
) -> None:
    from flaskr.service.learn.ask import follow_up_run as ask

    app = Flask(__name__)
    cleaned = []
    monkeypatch.setattr(host_lesson, "_ensure_healthy_db_connection", lambda _app: None)
    monkeypatch.setattr(
        host_lesson,
        "cleanup_session_after",
        lambda exc, *, source: cleaned.append((exc, source)),
    )
    monkeypatch.setattr(
        host_lesson, "_remove_db_session_safely", lambda _app, **_kwargs: None
    )
    failure = RuntimeError("provider failed")

    def failing(_app: object, **_kwargs: object) -> object:
        raise failure
        yield  # pragma: no cover - makes this a generator

    monkeypatch.setattr(ask, "follow_up_events", failing)

    with pytest.raises(RuntimeError) as raised:
        list(
            host_lesson._follow_up_events(
                app=app,
                user_bid="user-1",
                outline_bid="outline-1",
                user_input="question",
                reload_generated_block_bid=None,
                reload_element_bid=None,
                listen=False,
                learning_mode="read",
                preview_mode=False,
                stop_event=threading.Event(),
                element_adapter=SimpleNamespace(process=lambda events: events),
            )
        )

    assert raised.value is failure
    assert cleaned == [(failure, "follow-up stream error")]


def test_log_run_script_stream_error_does_not_error_for_app_exception() -> None:
    app = Flask(__name__)
    info_calls = []
    error_calls = []
    app.logger.info = lambda *args, **_kwargs: info_calls.append(args)
    app.logger.error = lambda *args, **_kwargs: error_calls.append(args)

    host_sse._log_run_script_stream_error(
        app, AppError("outline unit does not exist", status_code=1001)
    )

    assert error_calls == []
    assert info_calls[0] == ("run_script handled app exception",)
    assert info_calls[1][0]["description"] == "outline unit does not exist"


def test_log_run_script_stream_error_keeps_error_for_unexpected_exception() -> None:
    app = Flask(__name__)
    info_calls = []
    error_calls = []
    app.logger.info = lambda *args, **_kwargs: info_calls.append(args)
    app.logger.error = lambda *args, **_kwargs: error_calls.append(args)

    host_sse._log_run_script_stream_error(app, RuntimeError("boom"))

    assert info_calls == []
    assert error_calls[0] == ("run_script error",)
    assert error_calls[1][0]["description"] == "boom"


def test_run_script_listen_keeps_interaction_after_block_done(
    monkeypatch: object,
) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)

        def fake_lesson_events(**_kwargs: object) -> object:
            with app.app_context():
                element_adapter = _kwargs["element_adapter"]
                yield from element_adapter.process(
                    [
                        RunMarkdownFlowDTO(
                            outline_bid="outline-1",
                            generated_block_bid="generated-1",
                            type=GeneratedType.CONTENT,
                            content="hello",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid="outline-1",
                            generated_block_bid="generated-1",
                            type=GeneratedType.BREAK,
                            content="",
                        ),
                        RunMarkdownFlowDTO(
                            outline_bid="outline-1",
                            generated_block_bid="generated-2",
                            type=GeneratedType.INTERACTION,
                            content="?[%{{name}}...How should I call you?]",
                        ),
                    ]
                )

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
                listen=True,
            )
        )
        events = _parse_sse_events(chunks)

        assert [event["type"] for event in events] == ["element", "element", "done"]
        assert events[2]["is_terminal"] is True


def test_run_script_lock_busy_returns_busy_and_done(monkeypatch: object) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([False, False, False, False, False, False])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)
        monkeypatch.setattr(host_run.time, "sleep", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(host_run, "_", lambda key: f"translated:{key}")

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
            )
        )
        events = _parse_sse_events(chunks)

        assert lock.acquire_calls == 6
        assert lock.release_calls == 0
        assert [event["type"] for event in events] == ["error", "done"]
        assert [event["event_type"] for event in events] == ["error", "done"]
        assert events[0]["content"] == "translated:server.learn.outputInProgress"
        assert events[1]["is_terminal"] is True


def test_run_script_listen_lock_busy_returns_element_protocol(
    monkeypatch: object,
) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([False, False, False, False, False, False])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)
        monkeypatch.setattr(host_run.time, "sleep", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(host_run, "_", lambda key: f"translated:{key}")

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
                listen=True,
            )
        )
        events = _parse_sse_events(chunks)

        assert lock.acquire_calls == 6
        assert lock.release_calls == 0
        assert [event["type"] for event in events] == ["error", "done"]
        assert [event["event_type"] for event in events] == ["error", "done"]
        assert events[0]["content"] == "translated:server.learn.outputInProgress"
        assert events[0]["run_event_seq"] == 1
        assert events[1]["run_event_seq"] == 2
        assert events[0]["run_session_bid"] == events[1]["run_session_bid"]
        assert events[1]["is_terminal"] is True


def test_run_script_maps_llm_stream_connection_error_to_retryable_message(
    monkeypatch: object,
) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)
        monkeypatch.setattr(host_run, "_", lambda key: f"translated:{key}")

        def fake_lesson_events(**_kwargs: object) -> object:
            message = "litellm.APIConnectionError: APIConnectionError: OpenAIException - [SSL] record layer failure (_ssl.c:2590)"
            raise RuntimeError(message)
            yield  # pragma: no cover

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
                listen=True,
            )
        )
        events = _parse_sse_events(chunks)

        assert [event["type"] for event in events] == ["error", "break", "done"]
        assert events[0]["content"] == "translated:server.learn.llmStreamInterrupted"
        assert events[2]["is_terminal"] is True


def test_run_script_maps_standard_timeout_error_to_retryable_message(
    monkeypatch: object,
) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)
        monkeypatch.setattr(host_run, "_", lambda key: f"translated:{key}")

        def fake_lesson_events(**_kwargs: object) -> object:
            message = "stream failed"
            raise RuntimeError(message) from TimeoutError(
                "The read operation timed out"
            )
            yield  # pragma: no cover

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
                listen=True,
            )
        )
        events = _parse_sse_events(chunks)

        assert [event["type"] for event in events] == ["error", "break", "done"]
        assert events[0]["content"] == "translated:server.learn.llmStreamInterrupted"
        assert events[2]["is_terminal"] is True


def test_run_script_listen_done_uses_element_protocol(monkeypatch: object) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)

        def fake_lesson_events(**_kwargs: object) -> object:
            if False:
                yield None

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        chunks = list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
                listen=True,
            )
        )
        events = _parse_sse_events(chunks)

        assert lock.acquire_calls == 1
        assert lock.release_calls == 1
        assert [event["type"] for event in events] == ["done"]
        assert events[0]["event_type"] == "done"
        assert events[0]["content"] == ""
        assert events[0]["run_event_seq"] == 1
        assert events[0]["run_session_bid"]
        assert events[0]["is_terminal"] is True


def test_get_run_status_ignores_lock_when_running_marker_missing(
    monkeypatch: object,
) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([False])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)

        status = host_run.get_run_status(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
        )

        assert status.is_running is False
        assert status.running_time == 0
        assert lock.acquire_calls == 0


def test_get_run_status_reports_true_while_stream_is_open(monkeypatch: object) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)
        monkeypatch.setattr(host_run.time, "time", lambda: 120.0)

        def fake_lesson_events(**_kwargs: object) -> object:
            with app.app_context():
                yield RunMarkdownFlowDTO(
                    outline_bid="outline-1",
                    generated_block_bid="generated-1",
                    type=GeneratedType.CONTENT,
                    content="hello",
                )

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        stream = host_run.run_script(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
            user_input={"input": ["x"]},
            input_type="normal",
        )

        first_chunk = next(stream)
        status_during = host_run.get_run_status(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
        )
        remaining_chunks = list(stream)
        status_after = host_run.get_run_status(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
        )

        assert first_chunk.startswith("data: ")
        assert remaining_chunks
        assert status_during.is_running is True
        assert status_during.running_time == 0
        assert status_after.is_running is False
        assert status_after.running_time == 0


def test_run_script_close_during_data_yield_does_not_raise_runtime_error(
    monkeypatch: object,
) -> None:
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)

        def fake_lesson_events(**_kwargs: object) -> object:
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="generated-1",
                type=GeneratedType.CONTENT,
                content="hello",
            )

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        stream = host_run.run_script(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
            user_input={"input": ["x"]},
            input_type="normal",
        )

        first_chunk = next(stream)
        stream.close()

        assert first_chunk.startswith("data: ")
        assert lock.release_calls == 1


def test_run_script_propagates_explicit_language_to_producer(
    monkeypatch: object,
) -> None:
    """The route handler must hand the request language in explicitly.

    On Flask >= 3.1 the request teardown (which clears the request-scoped
    language) runs before the streaming generator body executes, so
    run_script can no longer read the language from the request thread.
    This pins the handoff: an explicit ``language=`` reaches the producer
    thread even when the caller's language context is already cleared.
    """
    from flaskr.i18n import clear_language, get_current_language

    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(host_run, "cache_provider", cache)

        seen_languages: list[str] = []

        def fake_lesson_events(**_kwargs: object) -> object:
            with app.app_context():
                seen_languages.append(get_current_language())
                yield RunMarkdownFlowDTO(
                    outline_bid="outline-1",
                    generated_block_bid="generated-1",
                    type=GeneratedType.CONTENT,
                    content="hello",
                )

        monkeypatch.setattr(host_run, "_lesson_events", fake_lesson_events)

        # Simulate the post-teardown state the generator actually runs in.
        clear_language()

        list(
            host_run.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                user_input={"input": ["x"]},
                input_type="normal",
                language="zh-CN",
            )
        )

        assert seen_languages == ["zh-CN"]
