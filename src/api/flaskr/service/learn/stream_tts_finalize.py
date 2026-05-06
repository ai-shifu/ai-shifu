from __future__ import annotations

import queue
import threading
from typing import Any, Generator

from flaskr.common.shifu_context import (
    apply_shifu_context_snapshot,
    get_shifu_context_snapshot,
)
from flaskr.i18n import get_current_language, set_language
from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO


class _StreamTTSFinalizeJob:
    def __init__(
        self,
        *,
        event_queue: queue.Queue,
        thread: threading.Thread,
    ):
        self.event_queue = event_queue
        self.thread = thread
        self.done = False


class StreamTTSFinalizeDrainer:
    """Finalize switched-out text TTS without blocking mdflow visual chunks."""

    def __init__(self, run_context: Any, *, log_prefix: str):
        self._run_context = run_context
        self._app = run_context.app
        self._log_prefix = log_prefix
        self._jobs: list[_StreamTTSFinalizeJob] = []

    def submit(self, processor) -> None:
        if not processor:
            return

        event_queue: queue.Queue = queue.Queue()
        parent_language = get_current_language()
        parent_shifu_context = get_shifu_context_snapshot()

        def _produce() -> None:
            with self._app.app_context():
                set_language(parent_language)
                apply_shifu_context_snapshot(parent_shifu_context)
                try:
                    # The background worker owns a thread-local DB session. Audio
                    # records are sidecar artifacts, while RUN element events are
                    # still yielded by the main generator from this queue.
                    for event in processor.finalize(commit=True):
                        event_queue.put(("event", event))
                except Exception as exc:
                    event_queue.put(("error", exc))
                finally:
                    event_queue.put(
                        (
                            "done",
                            int(getattr(processor, "next_element_index", 0) or 0),
                        )
                    )

        thread = threading.Thread(
            target=_produce,
            name="stream_tts_finalize",
            daemon=True,
        )
        self._jobs.append(_StreamTTSFinalizeJob(event_queue=event_queue, thread=thread))
        thread.start()

    def drain(self, *, wait: bool = False) -> Generator[RunMarkdownFlowDTO, None, None]:
        while self._jobs:
            for job in list(self._jobs):
                yield from self._drain_job(job, wait=wait)
                if job.done:
                    job.thread.join(timeout=0)
            self._jobs = [job for job in self._jobs if not job.done]
            if not wait:
                break

    def close(self) -> None:
        for job in list(self._jobs):
            job.thread.join(timeout=0.1)

    def _drain_job(
        self,
        job: _StreamTTSFinalizeJob,
        *,
        wait: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        waited_once = False
        while True:
            try:
                if wait and not waited_once and not job.done:
                    kind, payload = job.event_queue.get(timeout=0.05)
                    waited_once = True
                else:
                    kind, payload = job.event_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "event":
                yield payload
                continue
            if kind == "error":
                self._app.logger.warning(
                    "%s: %s",
                    self._log_prefix,
                    payload,
                    exc_info=(
                        type(payload),
                        payload,
                        getattr(payload, "__traceback__", None),
                    ),
                )
                continue
            if kind == "done":
                job.done = True
                self._run_context._element_index_cursor = max(
                    int(getattr(self._run_context, "_element_index_cursor", 0) or 0),
                    int(payload or 0),
                )
