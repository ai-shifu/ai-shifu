import json
from types import SimpleNamespace

import pytest
from flask import Flask, has_app_context

from flaskr.service.learn import runscript_v2
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)


class FakeLock:
    def __init__(self, acquire_results: list[bool]):
        self._acquire_results = list(acquire_results)
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self, blocking=True):
        self.acquire_calls += 1
        if self._acquire_results:
            return self._acquire_results.pop(0)
        return False

    def release(self):
        self.release_calls += 1


class FakeCacheProvider:
    def __init__(self, lock: FakeLock):
        self._lock = lock
        self.values: dict[str, bytes] = {}

    def lock(self, *_args, **_kwargs):
        return self._lock

    def setex(self, key: str, _time_in_seconds: int, value):
        if isinstance(value, bytes):
            encoded = value
        else:
            encoded = str(value).encode("utf-8")
        self.values[key] = encoded
        return True

    def get(self, key: str):
        return self.values.get(key)

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
                self.values.pop(key, None)
        return deleted


class FakeListenElementAdapter:
    def __init__(self, *_args, **_kwargs):
        self._seq = 0
        self._run_session_bid = "run-session-1"

    def process(self, events):
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
        content,
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


def _patch_fake_element_adapter(monkeypatch):
    monkeypatch.setattr(
        runscript_v2, "ListenElementRunAdapter", FakeListenElementAdapter
    )


def test_run_script_retries_lock_then_streams(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([False, True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)
        monkeypatch.setattr(runscript_v2.time, "sleep", lambda *_args, **_kwargs: None)

        def fake_run_script_inner(**_kwargs):
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

        monkeypatch.setattr(runscript_v2, "run_script_inner", fake_run_script_inner)

        chunks = list(
            runscript_v2.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                input={"input": ["x"]},
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


def test_run_script_producer_owns_app_context(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)
        observed = {"has_app_context": None, "manage_app_context": None}

        def fake_run_script_inner(**_kwargs):
            observed["has_app_context"] = has_app_context()
            observed["manage_app_context"] = _kwargs.get("manage_app_context")
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="generated-1",
                type=GeneratedType.CONTENT,
                content="hello",
            )

        monkeypatch.setattr(runscript_v2, "run_script_inner", fake_run_script_inner)

        chunks = list(
            runscript_v2.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                input={"input": ["x"]},
                input_type="normal",
            )
        )
        events = _parse_sse_events(chunks)

        assert observed == {
            "has_app_context": True,
            "manage_app_context": False,
        }
        assert [event["type"] for event in events] == ["element", "done"]


def test_run_script_read_mode_keeps_interaction_after_block_break(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)

        def fake_run_script_inner(**_kwargs):
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

        monkeypatch.setattr(runscript_v2, "run_script_inner", fake_run_script_inner)

        chunks = list(
            runscript_v2.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                input={"input": ["x"]},
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


def test_run_script_ask_mode_uses_element_protocol(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)

        def fake_run_script_inner(**_kwargs):
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

        monkeypatch.setattr(runscript_v2, "run_script_inner", fake_run_script_inner)

        chunks = list(
            runscript_v2.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                input="follow-up question",
                input_type="ask",
                listen=False,
            )
        )
        events = _parse_sse_events(chunks)

        assert [event["type"] for event in events] == ["element", "done"]
        assert events[1]["is_terminal"] is True


def test_run_script_inner_ask_mode_routes_events_through_element_adapter(monkeypatch):
    app = Flask(__name__)

    monkeypatch.setattr(
        runscript_v2,
        "db",
        SimpleNamespace(
            session=SimpleNamespace(commit=lambda: None, rollback=lambda: None)
        ),
    )
    monkeypatch.setattr(
        runscript_v2,
        "load_user_aggregate",
        lambda _user_bid: SimpleNamespace(user_id="user-1"),
    )

    outline_item_info = SimpleNamespace(
        bid="outline-1",
        shifu_bid="shifu-1",
        title="Lesson",
        __json__=lambda: {"bid": "outline-1"},
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_outline_item_dto",
        lambda *_args, **_kwargs: outline_item_info,
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_shifu_dto",
        lambda *_args, **_kwargs: SimpleNamespace(bid="shifu-1", price=0),
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_shifu_struct",
        lambda *_args, **_kwargs: object(),
    )

    class FakeRunScriptContext:
        def __init__(self, **_kwargs):
            self._has_next = True

        def set_input(self, *_args, **_kwargs):
            return None

        def reload(self, *_args, **_kwargs):
            return []

        def has_next(self):
            if self._has_next:
                self._has_next = False
                return True
            return False

        def run(self, _app):
            return [
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

    monkeypatch.setattr(runscript_v2, "RunScriptContextV2", FakeRunScriptContext)

    class FakeElementAdapter:
        def __init__(self):
            self.calls = []

        def process(self, events):
            captured = list(events)
            self.calls.append(captured)
            return iter([f"converted:{event.type.value}" for event in captured])

    element_adapter = FakeElementAdapter()

    emitted = list(
        runscript_v2.run_script_inner(
            app=app,
            user_bid="user-1",
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            input="follow-up question",
            input_type="ask",
            listen=False,
            element_adapter=element_adapter,
        )
    )

    assert emitted == ["converted:ask", "converted:content", "converted:break"]
    assert len(element_adapter.calls) == 1
    assert [event.type for event in element_adapter.calls[0]] == [
        GeneratedType.ASK,
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
    ]


def test_run_script_inner_rolls_back_on_unexpected_exception(monkeypatch):
    app = Flask(__name__)
    session_spy = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    rollback_calls = []
    commit_calls = []

    def _commit():
        commit_calls.append("commit")

    def _rollback():
        rollback_calls.append("rollback")

    session_spy.commit = _commit
    session_spy.rollback = _rollback

    monkeypatch.setattr(runscript_v2, "db", SimpleNamespace(session=session_spy))
    monkeypatch.setattr(
        runscript_v2,
        "load_user_aggregate",
        lambda _user_bid: SimpleNamespace(user_id="user-1"),
    )

    outline_item_info = SimpleNamespace(
        bid="outline-1",
        shifu_bid="shifu-1",
        title="Lesson",
        __json__=lambda: {"bid": "outline-1"},
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_outline_item_dto",
        lambda *_args, **_kwargs: outline_item_info,
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_shifu_dto",
        lambda *_args, **_kwargs: SimpleNamespace(bid="shifu-1", price=0),
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_shifu_struct",
        lambda *_args, **_kwargs: object(),
    )

    class FakeRunScriptContext:
        def __init__(self, **_kwargs):
            self._has_next = True

        def set_input(self, *_args, **_kwargs):
            return None

        def reload(self, *_args, **_kwargs):
            return []

        def has_next(self):
            if self._has_next:
                self._has_next = False
                return True
            return False

        def run(self, _app):
            raise RuntimeError("boom")

    monkeypatch.setattr(runscript_v2, "RunScriptContextV2", FakeRunScriptContext)

    with pytest.raises(RuntimeError) as exc_info:
        list(
            runscript_v2.run_script_inner(
                app=app,
                user_bid="user-1",
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                input={"input": ["x"]},
                input_type="normal",
            )
        )

    assert str(exc_info.value) == "boom"

    assert rollback_calls == ["rollback"]
    assert commit_calls == []


def test_run_script_inner_finalizes_langfuse_after_loop(monkeypatch):
    app = Flask(__name__)
    commit_calls = []

    monkeypatch.setattr(
        runscript_v2,
        "db",
        SimpleNamespace(
            session=SimpleNamespace(
                commit=lambda: commit_calls.append("commit"),
                rollback=lambda: None,
            )
        ),
    )
    monkeypatch.setattr(
        runscript_v2,
        "load_user_aggregate",
        lambda _user_bid: SimpleNamespace(user_id="user-1"),
    )

    outline_item_info = SimpleNamespace(
        bid="outline-1",
        shifu_bid="shifu-1",
        title="Lesson",
        __json__=lambda: {"bid": "outline-1"},
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_outline_item_dto",
        lambda *_args, **_kwargs: outline_item_info,
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_shifu_dto",
        lambda *_args, **_kwargs: SimpleNamespace(bid="shifu-1", price=0),
    )
    monkeypatch.setattr(
        runscript_v2,
        "get_shifu_struct",
        lambda *_args, **_kwargs: object(),
    )

    class FakeRunScriptContext:
        last_instance = None

        def __init__(self, **_kwargs):
            self._has_next = True
            self.finalize_calls = 0
            FakeRunScriptContext.last_instance = self

        def set_input(self, *_args, **_kwargs):
            return None

        def reload(self, *_args, **_kwargs):
            return []

        def has_next(self):
            if self._has_next:
                self._has_next = False
                return True
            return False

        def run(self, _app):
            return [
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

        def _finalize_langfuse_trace(self):
            self.finalize_calls += 1

    monkeypatch.setattr(runscript_v2, "RunScriptContextV2", FakeRunScriptContext)

    events = list(
        runscript_v2.run_script_inner(
            app=app,
            user_bid="user-1",
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            input="hello",
            input_type="text",
        )
    )

    assert [event.type for event in events] == [
        GeneratedType.CONTENT,
        GeneratedType.BREAK,
    ]
    assert FakeRunScriptContext.last_instance is not None
    assert FakeRunScriptContext.last_instance.finalize_calls == 1
    assert commit_calls == ["commit"]


def test_run_script_listen_keeps_interaction_after_block_done(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)

        def fake_run_script_inner(**_kwargs):
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

        monkeypatch.setattr(runscript_v2, "run_script_inner", fake_run_script_inner)

        chunks = list(
            runscript_v2.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                input={"input": ["x"]},
                input_type="normal",
                listen=True,
            )
        )
        events = _parse_sse_events(chunks)

        assert [event["type"] for event in events] == ["element", "element", "done"]
        assert events[2]["is_terminal"] is True


def test_run_script_lock_busy_returns_busy_and_done(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([False, False, False, False, False, False])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)
        monkeypatch.setattr(runscript_v2.time, "sleep", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(runscript_v2, "_", lambda key: f"translated:{key}")

        chunks = list(
            runscript_v2.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                input={"input": ["x"]},
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


def test_run_script_listen_lock_busy_returns_element_protocol(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([False, False, False, False, False, False])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)
        monkeypatch.setattr(runscript_v2.time, "sleep", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(runscript_v2, "_", lambda key: f"translated:{key}")

        chunks = list(
            runscript_v2.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                input={"input": ["x"]},
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


def test_run_script_listen_done_uses_element_protocol(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)

        def fake_run_script_inner(**_kwargs):
            if False:
                yield None

        monkeypatch.setattr(runscript_v2, "run_script_inner", fake_run_script_inner)

        chunks = list(
            runscript_v2.run_script(
                app=app,
                shifu_bid="shifu-1",
                outline_bid="outline-1",
                user_bid="user-1",
                input={"input": ["x"]},
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


def test_get_run_status_ignores_lock_when_running_marker_missing(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([False])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)

        status = runscript_v2.get_run_status(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
        )

        assert status.is_running is False
        assert status.running_time == 0
        assert lock.acquire_calls == 0


def test_get_run_status_reports_true_while_stream_is_open(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)
        monkeypatch.setattr(runscript_v2.time, "time", lambda: 120.0)

        def fake_run_script_inner(**_kwargs):
            with app.app_context():
                yield RunMarkdownFlowDTO(
                    outline_bid="outline-1",
                    generated_block_bid="generated-1",
                    type=GeneratedType.CONTENT,
                    content="hello",
                )

        monkeypatch.setattr(runscript_v2, "run_script_inner", fake_run_script_inner)

        stream = runscript_v2.run_script(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
            input={"input": ["x"]},
            input_type="normal",
        )

        first_chunk = next(stream)
        status_during = runscript_v2.get_run_status(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
        )
        remaining_chunks = list(stream)
        status_after = runscript_v2.get_run_status(
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


def test_run_script_close_during_data_yield_does_not_raise_runtime_error(monkeypatch):
    app = _make_test_app()
    _patch_fake_element_adapter(monkeypatch)
    with app.app_context():
        lock = FakeLock([True])
        cache = FakeCacheProvider(lock)
        monkeypatch.setattr(runscript_v2, "cache_provider", cache)

        def fake_run_script_inner(**_kwargs):
            yield RunMarkdownFlowDTO(
                outline_bid="outline-1",
                generated_block_bid="generated-1",
                type=GeneratedType.CONTENT,
                content="hello",
            )

        monkeypatch.setattr(runscript_v2, "run_script_inner", fake_run_script_inner)

        stream = runscript_v2.run_script(
            app=app,
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            user_bid="user-1",
            input={"input": ["x"]},
            input_type="normal",
        )

        first_chunk = next(stream)
        stream.close()

        assert first_chunk.startswith("data: ")
        assert lock.release_calls == 1
