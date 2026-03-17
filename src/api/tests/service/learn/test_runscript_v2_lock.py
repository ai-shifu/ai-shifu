import json
from types import SimpleNamespace

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
            )
        )
        events = _parse_sse_events(chunks)

        assert lock.acquire_calls == 2
        assert lock.release_calls == 1
        assert [event["type"] for event in events] == [
            "element",
            "element",
            "break",
            "done",
        ]
        assert events[0]["event_type"] == "element"
        assert events[0]["content"]["is_final"] == 0
        assert events[1]["content"]["is_final"] == 1
        assert events[1]["content"]["content_text"] == "hello"
        assert events[-1]["type"] == "done"


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
        assert [event["type"] for event in events] == ["error", "break", "done"]
        assert [event["event_type"] for event in events] == ["error", "break", "done"]
        assert events[0]["content"] == "translated:server.learn.outputInProgress"
        assert events[0]["run_event_seq"] == 1
        assert events[1]["run_event_seq"] == 2
        assert events[2]["run_event_seq"] == 3
        assert events[0]["run_session_bid"] == events[1]["run_session_bid"]
        assert events[1]["run_session_bid"] == events[2]["run_session_bid"]


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
