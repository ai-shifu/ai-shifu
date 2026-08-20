"""The TTS thread pool must never be shared across a process fork.

An executor created at import time in the gunicorn master (preload) is
inherited by every forked worker; its gevent-patched internals then carry
wakeup links bound to the parent's hub, which can crash in
AbstractLinkable._notify_links and interrupt unrelated greenlets. The lazy
accessor with a pid guard gives each process its own executor.
"""

import ast
import inspect

from flaskr.service.tts import streaming_tts


def test_module_does_not_create_an_executor_at_import_time():
    # The import-time instance is the fork-inheritance hazard; only the
    # lazy accessor may create one.
    module_ast = ast.parse(inspect.getsource(streaming_tts))
    for node in module_ast.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if (
                isinstance(value, ast.Call)
                and getattr(value.func, "id", None) == "ThreadPoolExecutor"
            ):
                message = (
                    "module-level ThreadPoolExecutor recreates the "
                    "fork-inheritance hazard; use _get_tts_executor()"
                )
                raise AssertionError(message)


def test_executor_is_cached_within_one_process(monkeypatch):
    monkeypatch.setattr(streaming_tts._tts_executor_state, "executor", None)
    monkeypatch.setattr(streaming_tts._tts_executor_state, "pid", None)

    first = streaming_tts._get_tts_executor()
    second = streaming_tts._get_tts_executor()

    assert first is second
    first.shutdown(wait=False)


def test_directly_injected_executor_is_honored(monkeypatch):
    # Existing tests patch the registry executor with a mock and leave the pid
    # unset; the accessor must return the injection instead of clobbering
    # it with a real executor.
    sentinel = object()
    monkeypatch.setattr(streaming_tts._tts_executor_state, "executor", sentinel)
    monkeypatch.setattr(streaming_tts._tts_executor_state, "pid", None)

    assert streaming_tts._get_tts_executor() is sentinel


def test_executor_is_rebuilt_after_fork(monkeypatch):
    monkeypatch.setattr(streaming_tts._tts_executor_state, "executor", None)
    monkeypatch.setattr(streaming_tts._tts_executor_state, "pid", None)

    parent_executor = streaming_tts._get_tts_executor()

    # Simulate the child process: same module state, different pid.
    monkeypatch.setattr(
        streaming_tts.os,
        "getpid",
        lambda: streaming_tts._tts_executor_state.pid + 1,
    )
    child_executor = streaming_tts._get_tts_executor()

    assert child_executor is not parent_executor
    parent_executor.shutdown(wait=False)
    child_executor.shutdown(wait=False)
