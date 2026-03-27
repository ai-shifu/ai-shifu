import json
from types import SimpleNamespace

from flask import Flask

from flaskr.service.learn import runscript_v2
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO


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


def test_run_script_retries_lock_then_streams(app, monkeypatch):
    with app.app_context():
        app.config["REDIS_KEY_PREFIX"] = "test"
        monkeypatch.setitem(app.config, "SSE_HEARTBEAT_INTERVAL", 0)
        lock = FakeLock([False, True])
        monkeypatch.setattr(
            runscript_v2,
            "cache_provider",
            SimpleNamespace(lock=lambda *_args, **_kwargs: lock),
        )
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
        assert [event["type"] for event in events] == ["content", "break", "done"]
        assert events[0]["event_type"] == "content"
        assert events[0]["content"] == "hello"
        assert events[1]["event_type"] == "break"
        assert events[-1]["type"] == "done"
        assert events[2]["is_terminal"] is True


def test_run_script_read_mode_keeps_interaction_after_block_break(app, monkeypatch):
    with app.app_context():
        app.config["REDIS_KEY_PREFIX"] = "test"
        monkeypatch.setitem(app.config, "SSE_HEARTBEAT_INTERVAL", 0)
        lock = FakeLock([True])
        monkeypatch.setattr(
            runscript_v2,
            "cache_provider",
            SimpleNamespace(lock=lambda *_args, **_kwargs: lock),
        )

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
            "content",
            "break",
            "interaction",
            "done",
        ]
        assert events[2]["event_type"] == "interaction"
        assert events[2]["content"] == "?[%{{name}}...How should I call you?]"
        assert events[3]["is_terminal"] is True


def test_run_script_ask_mode_uses_element_protocol(app, monkeypatch):
    with app.app_context():
        app.config["REDIS_KEY_PREFIX"] = "test"
        monkeypatch.setitem(app.config, "SSE_HEARTBEAT_INTERVAL", 0)
        lock = FakeLock([True])
        monkeypatch.setattr(
            runscript_v2,
            "cache_provider",
            SimpleNamespace(lock=lambda *_args, **_kwargs: lock),
        )

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

        assert [event["type"] for event in events] == [
            "element",
            "element",
            "element",
            "done",
        ]
        assert events[0]["content"]["element_type"] == "ask"
        assert events[0]["content"]["content"] == "follow-up question"
        assert events[1]["content"]["element_type"] == "answer"
        assert events[1]["content"]["content"] == "answer chunk"
        assert events[1]["content"]["is_final"] is False
        assert events[2]["content"]["element_type"] == "answer"
        assert events[2]["content"]["content"] == "answer chunk"
        assert events[2]["content"]["is_final"] is True
        assert events[3]["is_terminal"] is True


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


def test_run_script_listen_keeps_interaction_after_block_done(app, monkeypatch):
    with app.app_context():
        app.config["REDIS_KEY_PREFIX"] = "test"
        monkeypatch.setitem(app.config, "SSE_HEARTBEAT_INTERVAL", 0)
        lock = FakeLock([True])
        monkeypatch.setattr(
            runscript_v2,
            "cache_provider",
            SimpleNamespace(lock=lambda *_args, **_kwargs: lock),
        )

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

        assert [event["type"] for event in events] == [
            "element",
            "element",
            "element",
            "done",
        ]
        assert events[2]["content"]["element_type"] == "interaction"
        assert (
            events[2]["content"]["content"] == "?[%{{name}}...How should I call you?]"
        )
        assert events[3]["is_terminal"] is True


def test_run_script_lock_busy_returns_busy_and_done(app, monkeypatch):
    with app.app_context():
        app.config["REDIS_KEY_PREFIX"] = "test"
        lock = FakeLock([False, False, False, False, False, False])
        monkeypatch.setattr(
            runscript_v2,
            "cache_provider",
            SimpleNamespace(lock=lambda *_args, **_kwargs: lock),
        )
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
        assert [event["type"] for event in events] == ["error", "break", "done"]
        assert [event["event_type"] for event in events] == ["error", "break", "done"]
        assert events[0]["content"] == "translated:server.learn.outputInProgress"


def test_run_script_listen_lock_busy_returns_element_protocol(app, monkeypatch):
    with app.app_context():
        app.config["REDIS_KEY_PREFIX"] = "test"
        lock = FakeLock([False, False, False, False, False, False])
        monkeypatch.setattr(
            runscript_v2,
            "cache_provider",
            SimpleNamespace(lock=lambda *_args, **_kwargs: lock),
        )
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


def test_run_script_listen_done_uses_element_protocol(app, monkeypatch):
    with app.app_context():
        app.config["REDIS_KEY_PREFIX"] = "test"
        monkeypatch.setitem(app.config, "SSE_HEARTBEAT_INTERVAL", 0)
        lock = FakeLock([True])
        monkeypatch.setattr(
            runscript_v2,
            "cache_provider",
            SimpleNamespace(lock=lambda *_args, **_kwargs: lock),
        )

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
