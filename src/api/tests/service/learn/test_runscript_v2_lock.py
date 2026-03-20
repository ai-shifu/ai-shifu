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
        lock = FakeLock([False, True])
        monkeypatch.setattr(
            runscript_v2,
            "cache_provider",
            SimpleNamespace(lock=lambda *_args, **_kwargs: lock),
        )
        monkeypatch.setattr(runscript_v2.time, "sleep", lambda *_args, **_kwargs: None)

        def fake_run_script_inner(**_kwargs):
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

        assert lock.acquire_calls == 2
        assert lock.release_calls == 1
        assert events[0]["type"] == "content"
        assert events[0]["content"] == "hello"
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
        assert [event["type"] for event in events] == ["content", "break", "done"]
        assert events[0]["content"] == "translated:server.learn.outputInProgress"
