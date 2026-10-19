"""Streaming helpers (TTS, idle polling, ask streams) for the learning run."""

import contextlib
import queue
import threading
from collections.abc import Callable, Generator, Iterable
from typing import TYPE_CHECKING, Any

from flask import Flask
from flaskr.common.shifu_context import (
    apply_shifu_context_snapshot,
    get_shifu_context_snapshot,
)
from flaskr.dao import cleanup_session_after, db, invalidate_session
from flaskr.dao.uow import unit_of_work
from flaskr.i18n import get_current_language, set_language
from flaskr.service.learn.const import (
    INPUT_TYPE_ASK,
)
from flaskr.service.learn.handle_input_ask import handle_input_ask
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.memory import (
    load_memory,
)

if TYPE_CHECKING:
    from flaskr.service.tts.streaming_tts import StreamingTTSProcessor
from flaskr.service.learn.context_v2_mdflow import (
    RunScriptInfo,
)


class RunStreamingMixin:
    """Streaming TTS and ask-stream helpers mixed into ``RunScriptContextV2``."""

    def _should_stream_tts(self) -> bool:
        return (
            (not self._preview_mode)
            and getattr(self, "_input_type", None) != INPUT_TYPE_ASK
            and bool(getattr(self, "_listen", False))
        )

    def _try_create_tts_processor(
        self,
        generated_block_bid: str,
        *,
        shifu_bid: str = "",
        position: int = 0,
        stream_element_number: int | None = None,
        stream_element_type: str | None = None,
    ) -> "StreamingTTSProcessor | None":
        """Create StreamingTTSProcessor if TTS is configured, else return None."""
        from flaskr.service.learn.lesson_tts import create_tts_processor

        return create_tts_processor(
            self.app,
            shifu_model=self._shifu_model,
            shifu_bid=shifu_bid or self._outline_item_info.shifu_bid,
            outline_bid=self._outline_item_info.bid,
            progress_record_bid=self._current_attend.progress_record_bid,
            user_bid=self._user_info.user_id,
            generated_block_bid=generated_block_bid,
            learning_mode=self._get_learning_mode(),
            position=position,
            stream_element_number=stream_element_number,
            stream_element_type=stream_element_type,
        )

    def _finalize_stream_tts_processor(
        self,
        tts_processor: object,
        *,
        log_prefix: str,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        if not tts_processor:
            return
        try:
            yield from tts_processor.finalize(commit=False)
            self._element_index_cursor = max(
                int(getattr(self, "_element_index_cursor", 0) or 0),
                int(getattr(tts_processor, "next_element_index", 0) or 0),
            )
        except Exception as exc:
            self.app.logger.warning("%s: %s", log_prefix, exc, exc_info=True)
            cleanup_session_after(exc, source="finalize stream tts processor")

    def _teardown_stream_tts_state(
        self,
        *,
        tts_processor: object = None,
        flush_content_cache: Callable[[], Iterable[RunMarkdownFlowDTO]] | None = None,
        log_prefix: str,
        skip_emit: bool = False,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        if skip_emit:
            return
        if flush_content_cache is not None:
            try:
                yield from flush_content_cache()
            except Exception as exc:
                self.app.logger.warning(
                    "Flush streaming content cache failed: %s",
                    exc,
                    exc_info=True,
                )
                cleanup_session_after(exc, source="flush streaming content cache")
        if tts_processor:
            yield from self._finalize_stream_tts_processor(
                tts_processor,
                log_prefix=log_prefix,
            )

    def _iter_stream_result_with_idle_callback(
        self,
        stream_result: Generator[Any, None, None],
        *,
        idle_callback: Callable[[], Iterable[object]] | None = None,
        idle_poll_interval: float = 0.05,
    ) -> Generator[tuple[str, object], None, None]:
        """Poll a blocking stream generator while allowing idle side-channel output."""
        result_queue: queue.Queue = queue.Queue()
        parent_language = get_current_language()
        parent_shifu_context = get_shifu_context_snapshot()
        poll_timeout = max(float(idle_poll_interval or 0.0), 0.01)
        # Consumer-side stop signal: without it a producer that outlives the
        # 1s join below keeps streaming until the LLM response ends, holding
        # its DB session and connection long after the caller moved on.
        consumer_stopped = threading.Event()

        def _produce() -> None:
            with self.app.app_context():
                set_language(parent_language)
                apply_shifu_context_snapshot(parent_shifu_context)
                produce_exc: BaseException | None = None
                exhausted = False
                try:
                    for item in stream_result:
                        if consumer_stopped.is_set() or self._stop_requested():
                            break
                        result_queue.put(("item", item))
                    else:
                        # for/else: only natural exhaustion reaches here.
                        exhausted = True
                except Exception as exc:
                    produce_exc = exc
                    result_queue.put(("error", exc))
                except BaseException as exc:
                    produce_exc = exc
                    raise
                finally:
                    with contextlib.suppress(Exception):
                        stream_result.close()
                    if not exhausted or produce_exc is not None:
                        # The close above (or the interruption itself) may
                        # have landed mid-DB-exchange in this thread's own
                        # session; discard its connection rather than letting
                        # remove() roll back on a possibly desynced stream.
                        # NOTE: consumer_stopped is deliberately NOT part of
                        # this predicate - the consumer's finally sets it
                        # unconditionally, and a natural completion racing
                        # that set must not discard a healthy connection
                        # (exhausted stays True in that case).
                        invalidate_session(source="mdflow stream producer abort")
                    with contextlib.suppress(Exception):
                        db.session.remove()
                    result_queue.put(("done", None))

        producer_thread = threading.Thread(
            target=_produce,
            name="mdflow_stream_result_producer",
            daemon=True,
        )
        producer_thread.start()

        try:
            while True:
                self._stop_if_requested()
                try:
                    kind, payload = result_queue.get(timeout=poll_timeout)
                except queue.Empty:
                    if idle_callback is None:
                        continue
                    self._stop_if_requested()
                    for idle_item in idle_callback():
                        yield ("idle", idle_item)
                    continue

                if kind == "item":
                    yield ("item", payload)
                    continue
                if kind == "error":
                    raise payload
                break
        finally:
            consumer_stopped.set()
            producer_thread.join(timeout=5.0)
            if producer_thread.is_alive():
                self.app.logger.warning(
                    "mdflow stream producer thread did not stop in time; "
                    "it will exit at the next stream chunk boundary"
                )

    def _phase_handle_ask_input(
        self, app: Flask, run_script_info: RunScriptInfo
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Delegate an ask-type input to handle_input_ask (with optional TTS)."""
        if self._last_position == -1:
            self._last_position = run_script_info.block_position
        ask_input = self._input
        if isinstance(ask_input, dict):
            ask_input = ask_input.get("input", "")
        if isinstance(ask_input, list):
            ask_input = ",".join(ask_input)
        app.logger.info("Ask input normalized: input_chars=%s", len(ask_input))
        from flaskr.service.learn.agent.routing import uses_agent_engine

        runtime_profiles = load_memory(
            app,
            self._user_info.user_id,
            self._outline_item_info.shifu_bid,
            reference_text=self.get_system_prompt(self._outline_item_info.bid) or "",
            **(
                {"include_course_variables": True}
                if uses_agent_engine(self._outline_item_info.shifu_bid)
                else {}
            ),
        ).as_variables()
        from flaskr.service.learn.follow_up_memory_writer import (
            FollowUpMemoryPatch,
            stage_follow_up_memory,
        )

        memory_patch = (
            FollowUpMemoryPatch()
            if uses_agent_engine(self._outline_item_info.shifu_bid)
            else None
        )
        res = handle_input_ask(
            app,
            self,
            self._user_info,
            self._current_attend.progress_record_bid,
            ask_input,
            self._outline_item_info,
            self._trace_args,
            self._trace,
            self._preview_mode,
            self._last_position,
            anchor_element_bid=getattr(self, "_anchor_element_bid", ""),
            parent_observation=self._trace_root_span,
            runtime_profiles=runtime_profiles,
            memory_patch=memory_patch,
        )

        if self._should_stream_tts():
            tts_processor = None
            ask_stream_exc: BaseException | None = None
            try:
                for event in self._iter_until_active(res):
                    if event.type == GeneratedType.CONTENT and isinstance(
                        event.content, str
                    ):
                        if tts_processor is None:
                            tts_processor = self._try_create_tts_processor(
                                event.generated_block_bid,
                            )
                        yield event
                        if tts_processor:
                            yield from tts_processor.process_chunk(event.content)
                    elif event.type == GeneratedType.BREAK:
                        if tts_processor:
                            yield from self._finalize_stream_tts_processor(
                                tts_processor,
                                log_prefix="Ask TTS finalize failed",
                            )
                            tts_processor = None
                        yield event
                    else:
                        yield event
            except BaseException as exc:
                ask_stream_exc = exc
                raise
            finally:
                if tts_processor:
                    yield from self._teardown_stream_tts_state(
                        tts_processor=tts_processor,
                        log_prefix="Ask TTS finalize failed",
                        skip_emit=isinstance(ask_stream_exc, GeneratorExit),
                    )
        else:
            yield from self._iter_until_active(res)

        self._can_continue = False
        # Ask-history rows are written by handle_input_ask with plain
        # flushes; commit them as one step now that the ask stream has
        # fully completed (durability moves from the producer's outer
        # commit to here — same post-stream point of the request).
        if (
            memory_patch is not None
            and memory_patch.variables
            and not self._preview_mode
        ):
            with unit_of_work():
                stage_follow_up_memory(
                    app,
                    user_bid=self._user_info.user_id,
                    shifu_bid=self._outline_item_info.shifu_bid,
                    outline_bid=self._outline_item_info.bid,
                    progress_record_bid=self._current_attend.progress_record_bid,
                    patch=memory_patch,
                )
                self._recorder.commit_pending_step()
        else:
            self._recorder.commit_pending_step()
