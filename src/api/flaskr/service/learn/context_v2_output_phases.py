"""OUTPUT-mode run phases: interaction rendering and content-block streaming."""

import inspect
from collections.abc import Generator, Iterator

from flask import Flask
from flaskr.dao import db
from flaskr.service.learn.context_v2_mdflow import (
    RunType,
    _iter_llm_result_content_parts,
    _RunStepState,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
)
from flaskr.service.learn.stream_tts_finalize import StreamTTSFinalizeDrainer
from flaskr.service.learn.utils_v2 import init_generated_block
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from markdown_flow import (
    BlockType,
    InteractionParser,
    ProcessMode,
    replace_variables_in_text,
)


class RunOutputPhasesMixin:
    """OUTPUT-mode ``_phase_*`` steps mixed into ``RunScriptContextV2``."""

    def _phase_render_output(
        self, app: Flask, state: _RunStepState
    ) -> Generator[RunMarkdownFlowDTO, None, bool]:
        """OUTPUT-mode step: render an interaction or stream a content block.

        Returns True when run_inner must stop after this phase; False when
        a content block finished streaming and the step falls through to
        the completion tail.
        """
        run_script_info = state.run_script_info
        block = state.block
        generated_block: LearnGeneratedBlock = init_generated_block(
            app,
            shifu_bid=run_script_info.attend.shifu_bid,
            outline_item_bid=run_script_info.outline_bid,
            progress_record_bid=run_script_info.attend.progress_record_bid,
            user_bid=self._user_info.user_id,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            mdflow=block.content,
            block_index=block.index,
        )
        if block.block_type == BlockType.INTERACTION:
            yield from self._phase_emit_output_interaction(app, state, generated_block)
            return True
        else:
            # Guard against replaying the same fixed-output block right after
            # processing an interaction input in the same request.
            if state.has_effective_input:
                existing_content_block: LearnGeneratedBlock | None = (
                    LearnGeneratedBlock.query.filter(
                        LearnGeneratedBlock.progress_record_bid
                        == run_script_info.attend.progress_record_bid,
                        LearnGeneratedBlock.outline_item_bid
                        == run_script_info.outline_bid,
                        LearnGeneratedBlock.user_bid == self._user_info.user_id,
                        LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
                        LearnGeneratedBlock.position == run_script_info.block_position,
                        LearnGeneratedBlock.status == 1,
                        LearnGeneratedBlock.deleted == 0,
                    )
                    .order_by(LearnGeneratedBlock.id.desc())
                    .first()
                )
                if existing_content_block:
                    app.logger.warning(
                        "Skip duplicated fixed output block: progress=%s outline=%s position=%s generated_block=%s",
                        run_script_info.attend.progress_record_bid,
                        run_script_info.outline_bid,
                        run_script_info.block_position,
                        existing_content_block.generated_block_bid,
                    )
                    self._can_continue = True
                    self._run_type = RunType.OUTPUT
                    self._recorder.update_progress_pointer(
                        self._current_attend,
                        status=LEARN_STATUS_IN_PROGRESS,
                        block_position=self._current_attend.block_position + 1,
                    )
                    return True
            yield from self._phase_stream_content_block(app, state, generated_block)
            return False

    def _phase_emit_output_interaction(
        self,
        app: Flask,
        state: _RunStepState,
        generated_block: LearnGeneratedBlock,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Render and emit an interaction block in OUTPUT mode.

        Skips satisfied pay/login gates by advancing the cursor; otherwise
        persists the rendered interaction and pauses for user action.
        """
        run_script_info = state.run_script_info
        block = state.block
        block_list = state.block_list
        interaction_parser: InteractionParser = InteractionParser()
        parsed_interaction = interaction_parser.parse(block.content)
        if (
            parsed_interaction.get("buttons")
            and len(parsed_interaction.get("buttons")) > 0
        ):
            for button in parsed_interaction.get("buttons"):
                if button.get("value") == "_sys_pay" and self._is_paid:
                    self._can_continue = True
                    self._recorder.update_progress_pointer(
                        self._current_attend,
                        block_position=(self._current_attend.block_position + 1),
                    )
                    self._run_type = RunType.OUTPUT
                    return
                if button.get("value") == "_sys_login" and bool(
                    self._user_info.mobile or self._user_info.email
                ):
                    # Same logged-in definition as the emitter's
                    # is_access_gate_blocking_interaction.
                    self._can_continue = True
                    self._recorder.update_progress_pointer(
                        self._current_attend,
                        block_position=(self._current_attend.block_position + 1),
                    )
                    self._run_type = RunType.OUTPUT
                    return

        # Render interaction content with translation (markdown-flow 0.2.34+)
        # Call process() without user_input to trigger interaction rendering
        # Note: Do NOT pass variables here - we only want translation, not variable replacement
        app.logger.info("render_interaction: %s", run_script_info.block_position)
        state.llm_provider.set_usage_generated_block_bid(
            generated_block.generated_block_bid
        )

        interaction_result = state.mdflow_context.process(
            block_index=run_script_info.block_position,
            mode=ProcessMode.COMPLETE,
            context=state.message_list,
            variables=state.user_profile,
        )

        # Get rendered interaction content
        rendered_content = (
            interaction_result.content if interaction_result else block.content
        )

        generated_block.type = BLOCK_TYPE_MDINTERACTION_VALUE
        # Store translated interaction block for future retrieval
        generated_block.block_content_conf = rendered_content
        # Keep generated_content empty, will be filled with user input later
        generated_block.generated_content = ""
        self._persist_generated_block_for_events(generated_block)
        self.append_langfuse_output(rendered_content)
        yield RunMarkdownFlowDTO(
            outline_bid=run_script_info.outline_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=rendered_content,
        )
        yield from self._maybe_emit_feedback_after_access_gate(
            parsed_interaction=parsed_interaction,
            progress_record=run_script_info.attend,
            is_tail_gate=run_script_info.block_position >= len(block_list) - 1,
        )
        self._can_continue = False
        self._recorder.update_progress_pointer(
            self._current_attend, status=LEARN_STATUS_IN_PROGRESS
        )
        # For interaction blocks we should stop here and wait for explicit user action.
        # Continuing into outline completion fallback may incorrectly append
        # `_sys_next_chapter` after access-gate interactions such as pay/login.
        return

    def _phase_stream_content_block(
        self,
        app: Flask,
        state: _RunStepState,
        generated_block: LearnGeneratedBlock,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Stream one LLM content block (with optional streaming TTS).

        Stages the block row, streams the MDF/LLM output chunk by chunk,
        emits the BREAK, and finalizes block content + cursor advance as
        one recorder step.
        """
        run_script_info = state.run_script_info
        block_list = state.block_list
        user_profile = state.user_profile
        generated_block.type = BLOCK_TYPE_MDCONTENT_VALUE
        # Stage only (no unit_of_work): the LLM stream for this block
        # is about to run and the row must not become durable until
        # finalize_streamed_block below. A disconnect mid-stream
        # discards the staged row via the producer rollback, so the
        # re-run regenerates the block exactly as before PR2.
        if not getattr(generated_block, "id", None):
            db.session.add(generated_block)
        db.session.flush()
        state.llm_provider.set_usage_generated_block_bid(
            generated_block.generated_block_bid
        )
        stream = _ContentBlockStream(
            self,
            app,
            run_script_info=run_script_info,
            generated_block=generated_block,
            tts_enabled=bool(self._should_stream_tts()),
            tts_finalize_drainer=StreamTTSFinalizeDrainer(
                self,
                log_prefix="Finalize streaming TTS failed",
            ),
        )

        # Direct synchronous stream processing (markdown-flow 0.2.27+)
        app.logger.info("process_stream: %s", run_script_info.block_position)
        app.logger.info("variables: %s", user_profile)

        stream_exc: BaseException | None = None
        try:
            yield from self._iter_content_block_stream(app, state, stream)
        except BaseException as exc:
            stream_exc = exc
            raise
        finally:
            if not isinstance(stream_exc, GeneratorExit):
                yield from stream.tts_finalize_drainer.drain(wait=True)
            else:
                stream.tts_finalize_drainer.close()
            yield from self._teardown_stream_tts_state(
                tts_processor=stream.tts_processor,
                flush_content_cache=stream.drain_current_tts_ready_events,
                log_prefix="Finalize streaming TTS failed",
                skip_emit=isinstance(stream_exc, GeneratorExit),
            )
            stream.tts_processor = None
            stream.current_tts_stream_key = None
        generated_content = stream.generated_content
        sent_prompt = stream.sent_prompt

        yield RunMarkdownFlowDTO(
            outline_bid=run_script_info.outline_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.BREAK,
            content="",
        )
        next_block_position = run_script_info.block_position + 1
        # Continue the same run across subsequent blocks until we hit
        # an interaction block or reach outline completion.
        self._can_continue = next_block_position < len(block_list)
        # Preserved-content blocks stream without an LLM prompt
        # (LLMResult.prompt is unset); freeze today's rebuild rendering at
        # generation time so future rebuilds stay byte-stable even after
        # the referenced variables change.
        if not sent_prompt:
            sent_prompt = (
                replace_variables_in_text(state.block.content or "", user_profile) or ""
            )
        # Block-finalize step: streamed content + cursor advance
        # commit atomically once the stream has fully completed
        # (pending TTS/listen-element sidecar rows ride along).
        self._recorder.finalize_streamed_block(
            generated_block,
            generated_content,
            self._current_attend,
            status=LEARN_STATUS_IN_PROGRESS,
            block_position=next_block_position,
            generation_prompt=sent_prompt,
        )

    def _iter_content_block_stream(
        self,
        app: Flask,
        state: _RunStepState,
        stream: "_ContentBlockStream",
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Run the MDF STREAM call and route every chunk through ``stream``."""
        run_script_info = state.run_script_info
        stream_result = state.mdflow_context.process(
            block_index=run_script_info.block_position,
            mode=ProcessMode.STREAM,
            variables=state.user_profile,
            context=state.message_list,
        )

        # Handle both Generator and single LLMResult (markdown-flow 0.2.27+)
        # In some edge cases (e.g., no LLM provider), returns a single LLMResult instead of Generator
        if inspect.isgenerator(stream_result):
            idle_poll_interval = float(
                app.config.get("STREAM_TTS_IDLE_DRAIN_INTERVAL", 0.05)
            )
            for (
                source,
                payload,
            ) in self._iter_stream_result_with_idle_callback(
                stream_result,
                idle_callback=(
                    stream.drain_tts_ready_events if stream.tts_enabled else None
                ),
                idle_poll_interval=idle_poll_interval,
            ):
                if source == "idle":
                    yield payload
                    continue
                stream.sent_prompt = (
                    getattr(payload, "prompt", None) or stream.sent_prompt
                )
                for (
                    chunk_content,
                    stream_element_type,
                    normalized_number,
                ) in _iter_llm_result_content_parts(payload):
                    yield from stream.process_stream_chunk(
                        chunk_content,
                        stream_element_type=stream_element_type or None,
                        stream_element_number=normalized_number,
                    )
        else:
            # markdown-flow still returns a single LLMResult for some
            # STREAM edge cases, such as preserved content.
            stream.sent_prompt = (
                getattr(stream_result, "prompt", None) or stream.sent_prompt
            )
            for (
                chunk_content,
                stream_element_type,
                normalized_number,
            ) in _iter_llm_result_content_parts(stream_result):
                yield from stream.process_stream_chunk(
                    chunk_content,
                    stream_element_type=stream_element_type or None,
                    stream_element_number=normalized_number,
                )


class _ContentBlockStream:
    """Per-block streaming state: accumulated content and the live TTS processor.

    Holds what used to be the ``nonlocal`` closure state of
    ``_phase_stream_content_block`` so each step is a named method.
    """

    def __init__(
        self,
        run_context: object,
        app: Flask,
        *,
        run_script_info: object,
        generated_block: LearnGeneratedBlock,
        tts_enabled: bool,
        tts_finalize_drainer: StreamTTSFinalizeDrainer,
    ) -> None:
        self.run_context = run_context
        self.app = app
        self.run_script_info = run_script_info
        self.generated_block = generated_block
        self.generated_content = ""
        # Exact user message markdown-flow sent to the LLM for this block
        # (LLMResult.prompt); persisted so context rebuilds replay the sent
        # bytes verbatim and provider-side prefix caching keeps matching.
        self.sent_prompt = ""
        self.tts_processor = None
        self.tts_enabled = tts_enabled
        self.current_tts_stream_key: tuple[str, int] | None = None
        self.next_tts_position = 0
        self.tts_finalize_drainer = tts_finalize_drainer

    def build_content_event(
        self,
        chunk_text: str,
        stream_element_type: str | None = None,
        stream_element_number: int | None = None,
    ) -> RunMarkdownFlowDTO:
        event = RunMarkdownFlowDTO(
            outline_bid=self.run_script_info.outline_bid,
            generated_block_bid=self.generated_block.generated_block_bid,
            type=GeneratedType.CONTENT,
            content=chunk_text,
        )
        if stream_element_type and stream_element_number is not None:
            event.set_mdflow_stream_parts(
                [(chunk_text, stream_element_type, stream_element_number)]
            )
        return event

    @staticmethod
    def normalize_tts_stream_key(
        stream_element_type: str | None = None,
        stream_element_number: int | None = None,
    ) -> tuple[str, int] | None:
        normalized_type = (stream_element_type or "").strip().lower()
        if normalized_type != "text" or stream_element_number is None:
            return None
        return normalized_type, int(stream_element_number)

    def switch_tts_processor(
        self,
        stream_element_type: str | None = None,
        stream_element_number: int | None = None,
    ) -> None:
        next_key = self.normalize_tts_stream_key(
            stream_element_type=stream_element_type,
            stream_element_number=stream_element_number,
        )
        if self.current_tts_stream_key == next_key:
            return
        if self.tts_processor:
            self.tts_finalize_drainer.submit(self.tts_processor)
            self.tts_processor = None
            self.current_tts_stream_key = None
        if not self.tts_enabled or next_key is None:
            return
        self.tts_processor = self.run_context._try_create_tts_processor(
            self.generated_block.generated_block_bid,
            shifu_bid=self.run_script_info.attend.shifu_bid,
            position=self.next_tts_position,
            stream_element_number=stream_element_number,
            stream_element_type=stream_element_type,
        )
        if not self.tts_processor:
            return
        self.current_tts_stream_key = next_key
        self.next_tts_position += 1

    def process_stream_chunk(
        self,
        chunk_content: str,
        stream_element_type: str | None = None,
        stream_element_number: int | None = None,
    ) -> Iterator[RunMarkdownFlowDTO]:
        if not chunk_content:
            return
        self.generated_content += chunk_content
        self.run_context.append_langfuse_output(chunk_content)
        yield self.build_content_event(
            chunk_content,
            stream_element_type=stream_element_type,
            stream_element_number=stream_element_number,
        )
        self.switch_tts_processor(
            stream_element_type=stream_element_type,
            stream_element_number=stream_element_number,
        )
        if not self.tts_processor or self.current_tts_stream_key is None:
            yield from self.drain_tts_ready_events()
            return
        try:
            yield from self.tts_processor.process_chunk(chunk_content)
            yield from self.drain_tts_ready_events()
        except Exception as exc:
            self.app.logger.warning(
                "Streaming TTS failed; disable for this block: %s",
                exc,
                exc_info=True,
            )
            self.tts_processor = None
            self.current_tts_stream_key = None
            self.tts_enabled = False

    def disable_current_tts_processor(self) -> None:
        self.tts_processor = None
        self.current_tts_stream_key = None

    def disable_all_tts(self) -> None:
        self.disable_current_tts_processor()
        self.tts_enabled = False

    def handle_current_tts_drain_error(self, exc: Exception) -> None:
        self.app.logger.warning(
            "Idle streaming TTS drain failed; disable for this block: %s",
            exc,
            exc_info=exc,
        )
        self.disable_all_tts()

    def drain_current_tts_ready_events(self) -> Iterator[RunMarkdownFlowDTO]:
        if not self.tts_processor:
            return
        if not hasattr(self.tts_processor, "drain_ready_segments"):
            return
        try:
            yield from self.tts_processor.drain_ready_segments()
        except Exception as exc:
            self.handle_current_tts_drain_error(exc)

    def drain_tts_ready_events(self) -> Iterator[RunMarkdownFlowDTO]:
        yield from self.tts_finalize_drainer.drain()
        yield from self.drain_current_tts_ready_events()
        yield from self.tts_finalize_drainer.drain()
