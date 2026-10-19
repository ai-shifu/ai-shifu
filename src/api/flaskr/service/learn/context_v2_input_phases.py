"""INPUT-mode run phases: interaction input recording, moderation, validation."""

import inspect
from collections.abc import Generator
from dataclasses import replace

from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.check_text import check_text_with_llm_response
from flaskr.service.learn.const import (
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.context_v2_mdflow import (
    MdflowContextV2,
    RunType,
    _RunStepState,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
    VariableUpdateDTO,
)
from flaskr.service.learn.memory import (
    MemoryUpdate,
    VariableMemoryUpdate,
    stage_memory,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
)
from flaskr.service.learn.utils_v2 import init_generated_block
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
)
from flaskr.service.profile.api import is_course_reference
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.util import generate_id
from markdown_flow import (
    BlockType,
    InteractionParser,
    ProcessMode,
)


class RunInputPhasesMixin:
    """INPUT-mode ``_phase_*`` steps mixed into ``RunScriptContextV2``."""

    def _phase_process_input(
        self, app: Flask, state: _RunStepState
    ) -> Generator[RunMarkdownFlowDTO, None, bool]:
        """INPUT-mode step: realign, access gates, pause, record, validate.

        Returns True when run_inner must stop after this phase; False when
        the step falls through to the completion tail (validation-error
        replay).
        """
        run_script_info = state.run_script_info
        block = state.block
        if block.block_type != BlockType.INTERACTION:
            self._phase_resolve_noninteraction_input(app, state)
            return True
        interaction_parser: InteractionParser = InteractionParser()
        parsed_interaction = interaction_parser.parse(block.content)
        generated_block: LearnGeneratedBlock = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid
                == run_script_info.attend.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid == run_script_info.outline_bid,
                LearnGeneratedBlock.user_bid == self._user_info.user_id,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
                LearnGeneratedBlock.position == run_script_info.block_position,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.deleted == 0,
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        handled = yield from self._phase_reemit_access_gate_interaction(
            app, state, parsed_interaction, generated_block
        )
        if handled:
            return True
        if not generated_block:
            yield from self._phase_emit_interaction_pause(app, state)
            return True
        handled, user_input_param = yield from self._phase_record_input_and_moderate(
            app, state, generated_block, parsed_interaction
        )
        if handled:
            return True
        handled = yield from self._phase_validate_input_and_advance(
            app, state, generated_block, user_input_param
        )
        return handled

    def _phase_resolve_noninteraction_input(
        self, app: Flask, state: _RunStepState
    ) -> None:
        """Input arrived while the cursor sits on a non-interaction block.

        Realigns the cursor to a pending interaction (stale-position guard)
        or flips the run to OUTPUT mode. Pure pointer work — never emits.
        """
        run_script_info = state.run_script_info
        if state.has_effective_input:
            pending_interaction_block: LearnGeneratedBlock | None = (
                LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.progress_record_bid
                    == run_script_info.attend.progress_record_bid,
                    LearnGeneratedBlock.outline_item_bid == run_script_info.outline_bid,
                    LearnGeneratedBlock.user_bid == self._user_info.user_id,
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
                    LearnGeneratedBlock.status == 1,
                    LearnGeneratedBlock.deleted == 0,
                    LearnGeneratedBlock.position >= run_script_info.block_position,
                    LearnGeneratedBlock.generated_content == "",
                )
                .order_by(
                    LearnGeneratedBlock.position.asc(),
                    LearnGeneratedBlock.id.asc(),
                )
                .first()
            )
            if pending_interaction_block:
                app.logger.warning(
                    "Input received on non-interaction block. Realign index to pending interaction: progress=%s outline=%s from=%s to=%s generated_block=%s",
                    run_script_info.attend.progress_record_bid,
                    run_script_info.outline_bid,
                    run_script_info.block_position,
                    pending_interaction_block.position,
                    pending_interaction_block.generated_block_bid,
                )
                self._recorder.update_progress_pointer(
                    self._current_attend,
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=pending_interaction_block.position,
                )
                self._run_type = RunType.INPUT
                self._can_continue = True
                return
        self._can_continue = True
        self._run_type = RunType.OUTPUT
        self._recorder.update_progress_pointer(
            self._current_attend, status=LEARN_STATUS_IN_PROGRESS
        )

    def _phase_reemit_access_gate_interaction(
        self,
        app: Flask,
        state: _RunStepState,
        parsed_interaction: dict,
        generated_block: LearnGeneratedBlock | None,
    ) -> Generator[RunMarkdownFlowDTO, None, bool]:
        """Pay/login gate handling for an interaction that received input.

        Re-emits the gate interaction when access is still blocked, or
        advances the cursor when the gate is satisfied. Returns True when
        the gate consumed the step.
        """
        run_script_info = state.run_script_info
        block = state.block
        block_list = state.block_list
        if (
            parsed_interaction.get("buttons")
            and len(parsed_interaction.get("buttons")) > 0
        ):
            for button in parsed_interaction.get("buttons"):
                if button.get("value") == "_sys_pay":
                    if not self._is_paid:
                        # Use translated content from database if available
                        interaction_content = (
                            generated_block.block_content_conf
                            if generated_block and generated_block.block_content_conf
                            else block.content
                        )
                        if not generated_block:
                            generated_block = init_generated_block(
                                app,
                                shifu_bid=run_script_info.attend.shifu_bid,
                                outline_item_bid=run_script_info.outline_bid,
                                progress_record_bid=run_script_info.attend.progress_record_bid,
                                user_bid=self._user_info.user_id,
                                block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
                                mdflow=block.content,
                                block_index=run_script_info.block_position,
                            )
                            generated_block.role = ROLE_TEACHER
                        generated_block.block_content_conf = interaction_content
                        generated_block.generated_content = ""
                        self._persist_generated_block_for_events(generated_block)
                        self.append_langfuse_output(interaction_content)
                        yield RunMarkdownFlowDTO(
                            outline_bid=run_script_info.outline_bid,
                            generated_block_bid=generated_block.generated_block_bid,
                            type=GeneratedType.INTERACTION,
                            content=interaction_content,
                        )
                        yield from self._maybe_emit_feedback_after_access_gate(
                            parsed_interaction=parsed_interaction,
                            progress_record=run_script_info.attend,
                            is_tail_gate=run_script_info.block_position
                            >= len(block_list) - 1,
                        )
                        self._can_continue = False
                        return True
                    else:
                        self._can_continue = True
                        self._recorder.update_progress_pointer(
                            self._current_attend,
                            block_position=self._current_attend.block_position + 1,
                        )
                        self._run_type = RunType.OUTPUT
                        return True
                if button.get("value") == "_sys_login":
                    # Same logged-in definition as the emitter's
                    # access-gate check: email-only accounts are logged in too.
                    if bool(self._user_info.mobile or self._user_info.email):
                        self._can_continue = True
                        self._recorder.update_progress_pointer(
                            self._current_attend,
                            block_position=self._current_attend.block_position + 1,
                        )
                        self._run_type = RunType.OUTPUT
                        return True
                    else:
                        # Use translated content from database if available
                        interaction_content = (
                            generated_block.block_content_conf
                            if generated_block and generated_block.block_content_conf
                            else block.content
                        )
                        if not generated_block:
                            generated_block = init_generated_block(
                                app,
                                shifu_bid=run_script_info.attend.shifu_bid,
                                outline_item_bid=run_script_info.outline_bid,
                                progress_record_bid=run_script_info.attend.progress_record_bid,
                                user_bid=self._user_info.user_id,
                                block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
                                mdflow=block.content,
                                block_index=run_script_info.block_position,
                            )
                            generated_block.role = ROLE_TEACHER
                        generated_block.block_content_conf = interaction_content
                        generated_block.generated_content = ""
                        self._persist_generated_block_for_events(generated_block)
                        self.append_langfuse_output(interaction_content)
                        yield RunMarkdownFlowDTO(
                            outline_bid=run_script_info.outline_bid,
                            generated_block_bid=generated_block.generated_block_bid,
                            type=GeneratedType.INTERACTION,
                            content=interaction_content,
                        )
                        yield from self._maybe_emit_feedback_after_access_gate(
                            parsed_interaction=parsed_interaction,
                            progress_record=run_script_info.attend,
                            is_tail_gate=run_script_info.block_position
                            >= len(block_list) - 1,
                        )
                        self._can_continue = False
                        return True
        return False

    def _phase_emit_interaction_pause(
        self, app: Flask, state: _RunStepState
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """First arrival at an interaction with no cached block.

        Renders the interaction (translation only), persists it, emits it,
        and pauses the run to wait for user input.
        """
        run_script_info = state.run_script_info
        block = state.block
        generated_block = init_generated_block(
            app,
            shifu_bid=run_script_info.attend.shifu_bid,
            outline_item_bid=run_script_info.outline_bid,
            progress_record_bid=run_script_info.attend.progress_record_bid,
            user_bid=self._user_info.user_id,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            mdflow=block.content,
            block_index=run_script_info.block_position,
        )
        app.logger.info(
            "generated_block not found, init new one: %s",
            generated_block.generated_block_bid,
        )

        # Render interaction content with translation (INPUT mode, no cached block)
        # Note: Do NOT pass variables here - we only want translation, not variable replacement
        state.llm_provider.set_usage_generated_block_bid(
            generated_block.generated_block_bid
        )
        interaction_result = state.mdflow_context.process(
            block_index=run_script_info.block_position,
            mode=ProcessMode.COMPLETE,
            context=state.message_list,
            variables=state.user_profile,
        )
        rendered_content = (
            interaction_result.content if interaction_result else block.content
        )

        # Store translated interaction block for future retrieval
        generated_block.block_content_conf = rendered_content
        # Keep generated_content empty, will be filled with user input later
        generated_block.generated_content = ""
        generated_block.role = ROLE_TEACHER
        self._persist_generated_block_for_events(generated_block)
        self.append_langfuse_output(rendered_content)
        yield RunMarkdownFlowDTO(
            outline_bid=run_script_info.outline_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=rendered_content,
        )
        self._can_continue = False

    def _normalize_interaction_input(
        self, app: Flask, expected_variable: str
    ) -> dict[str, list[str]]:
        """Normalize the run input and remap legacy keys to the expected variable."""
        user_input_param = MdflowContextV2.normalize_user_input_map(
            self._input, expected_variable
        )
        # Backward compatible: some clients may still send `{input: [...]}` or a single
        # unnamed key even when the interaction expects a specific variable.
        # TODO(non-assignment rollout): markdown-flow >= 0.3.0 merges values
        # from any key for no-variable interactions, and the web client now
        # submits the canonical "input" key. Drop this remap once the
        # "input"-key frontend has been fully rolled out for one release
        # cycle (older cached clients may still send the legacy keys).
        if expected_variable and expected_variable not in user_input_param:
            if "input" in user_input_param and len(user_input_param) == 1:
                app.logger.warning(
                    "Remap interaction input key 'input' -> '%s'", expected_variable
                )
                user_input_param = {expected_variable: user_input_param["input"]}
            elif len(user_input_param) == 1:
                only_key, only_values = next(iter(user_input_param.items()))
                if only_values:
                    app.logger.warning(
                        "Remap interaction input key '%s' -> '%s'",
                        only_key,
                        expected_variable,
                    )
                    user_input_param = {expected_variable: only_values}

        return user_input_param

    def _phase_record_input_and_moderate(
        self,
        app: Flask,
        state: _RunStepState,
        generated_block: LearnGeneratedBlock,
        parsed_interaction: dict,
    ) -> Generator[RunMarkdownFlowDTO, None, tuple[bool, dict]]:
        """Record the student input on the interaction block and moderate it.

        Returns ``(handled, user_input_param)``: handled is True when the
        moderation result consumed the step (error content replayed and the
        interaction re-emitted), so run_inner must stop.
        """
        run_script_info = state.run_script_info
        block = state.block
        expected_variable = (parsed_interaction.get("variable") or "input").strip()
        if not expected_variable:
            expected_variable = "input"

        user_input_param = self._normalize_interaction_input(app, expected_variable)
        generated_block.generated_content = MdflowContextV2.flatten_user_input_map(
            user_input_param
        )
        generated_block.role = ROLE_STUDENT
        generated_block.position = run_script_info.block_position
        # For STUDENT records, also store translated interaction block
        # (in case this record is returned instead of TEACHER record)
        state.llm_provider.set_usage_generated_block_bid(
            generated_block.generated_block_bid
        )
        interaction_result = state.mdflow_context.process(
            block_index=run_script_info.block_position,
            mode=ProcessMode.COMPLETE,
            context=state.message_list,
            variables=state.user_profile,
        )
        generated_block.block_content_conf = (
            interaction_result.content if interaction_result else block.content
        )
        generated_block.status = 1
        # Commit the accumulated student-record mutations as one step,
        # after the COMPLETE render above has returned.
        self._recorder.save_generated_block(generated_block)
        trace_metadata = self._trace_args.get("metadata") or {}
        if not isinstance(trace_metadata, dict):
            trace_metadata = {}
        chapter_title = trace_metadata.get(
            "chapter_title",
            self._outline_item_info.title,
        )
        trace_scene = trace_metadata.get("scene", "lesson_runtime")
        # NOTE(uow cross-module leak): check_text_with_llm_response logs its
        # moderation verdict via check_risk.add_risk_control_result
        # (flaskr/service/check_risk/funcs.py), which opens a nested app
        # context and issues its own raw db.session.commit() from inside
        # this /run generator — outside the recorder's per-step
        # unit_of_work boundaries. Migrating that self-commit rider is
        # check_risk-module work, tracked in the ExecPlan Decision Log
        # (docs/exec-plans/completed/learn-run-decomposition.md).
        res = check_text_with_llm_response(
            app,
            user_info=self._user_info,
            log_script=generated_block,
            user_input=generated_block.generated_content,  # Use converted string value
            span=self._trace_root_span,
            outline_item_bid=self._outline_item_info.bid,
            shifu_bid=self._outline_item_info.shifu_bid,
            block_position=run_script_info.block_position,
            llm_settings=state.llm_settings,
            attend_id=self._current_attend.progress_record_bid,
            fmt_prompt="",
            usage_context=replace(
                state.usage_context,
                generated_block_bid=generated_block.generated_block_bid,
            ),
            chapter_title=chapter_title,
            scene=f"{trace_scene}_interaction",
        )
        # Check if the generator yields any content (not None)
        has_content = False
        for i in res:
            if i is not None and i != "":
                self.app.logger.info("check_text_with_llm_response: %s", i)
                has_content = True
                self.append_langfuse_output(i)
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.CONTENT,
                    content=i,
                )

        if has_content:
            self._can_continue = False
            yield RunMarkdownFlowDTO(
                outline_bid=run_script_info.outline_bid,
                generated_block_bid=generated_block.generated_block_bid,
                type=GeneratedType.BREAK,
                content="",
            )

            # Render interaction content with translation after risk check
            # Note: Do NOT pass variables here - we only want translation, not variable replacement
            interaction_result = state.mdflow_context.process(
                block_index=run_script_info.block_position,
                mode=ProcessMode.COMPLETE,
                context=state.message_list,
                variables=state.user_profile,
            )
            rendered_content = (
                interaction_result.content if interaction_result else block.content
            )

            # Store translated interaction block for future retrieval
            generated_block.block_content_conf = rendered_content
            # Keep generated_content empty, will be filled with user input later
            generated_block.generated_content = ""
            generated_block.generated_block_bid = generate_id(app)
            self._persist_generated_block_for_events(generated_block)
            self.append_langfuse_output(rendered_content)
            yield RunMarkdownFlowDTO(
                outline_bid=run_script_info.outline_bid,
                generated_block_bid=generated_block.generated_block_bid,
                type=GeneratedType.INTERACTION,
                content=rendered_content,
            )
            return True, user_input_param
        return False, user_input_param

    def _phase_validate_input_and_advance(
        self,
        app: Flask,
        state: _RunStepState,
        generated_block: LearnGeneratedBlock,
        user_input_param: dict,
    ) -> Generator[RunMarkdownFlowDTO, None, bool]:
        """Validate the interaction input, save variables, advance the cursor.

        Returns True when the step advanced (or the interaction assigns no
        variable); False when validation failed and the error replay must
        fall through to the completion tail.
        """
        run_script_info = state.run_script_info
        validate_result = state.mdflow_context.process(
            block_index=run_script_info.block_position,
            mode=ProcessMode.COMPLETE,
            user_input=user_input_param,
            context=state.message_list,
            variables=state.user_profile,
        )

        if (
            validate_result.metadata is not None
            and validate_result.metadata.get("interaction_type")
            == "non_assignment_button"
        ):
            # No-variable interaction: markdown-flow normalized the answer
            # (button display -> value, free text passed through) into
            # metadata["answer"]. Persist the normalized value so the context
            # rebuild feeds the canonical answer back to the LLM.
            answer_values = validate_result.metadata.get("answer")
            if isinstance(answer_values, list):
                normalized_answer = ",".join(
                    str(value) for value in answer_values if value is not None
                )
            elif answer_values is None:
                normalized_answer = ""
            else:
                normalized_answer = str(answer_values)
            if normalized_answer != (generated_block.generated_content or ""):
                generated_block.generated_content = normalized_answer
                self._recorder.save_generated_block(generated_block)
            self._can_continue = True
            self._run_type = RunType.OUTPUT
            self._recorder.update_progress_pointer(
                self._current_attend,
                status=LEARN_STATUS_IN_PROGRESS,
                block_position=run_script_info.block_position + 1,
            )
            return True

        if validate_result.variables is not None and len(validate_result.variables) > 0:
            memory_update = MemoryUpdate()
            for key, value in validate_result.variables.items():
                if is_course_reference(key):
                    continue
                profile_id = state.variable_definition_key_id_map.get(key, "")
                # Convert list to string (markdown-flow 0.2.27+ returns list[str] for multi-select)
                if isinstance(value, list):
                    # Filter out None and convert to string
                    value_str = ",".join(
                        [str(item) for item in value if item is not None]
                    )
                else:
                    value_str = str(value) if value is not None else ""
                memory_update.variables.append(
                    VariableMemoryUpdate(key, value_str, profile_id)
                )

            with unit_of_work():
                stage_memory(
                    app,
                    self._user_info.user_id,
                    self._outline_item_info.shifu_bid,
                    memory_update,
                    expected_generations=getattr(state, "memory_generations", None),
                )
                self._recorder.update_progress_pointer(
                    self._current_attend,
                    status=LEARN_STATUS_IN_PROGRESS,
                    block_position=run_script_info.block_position + 1,
                )
            self._can_continue = True
            for variable in memory_update.variables:
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.VARIABLE_UPDATE,
                    content=VariableUpdateDTO(
                        variable_name=variable.key,
                        variable_value=variable.value,
                    ),
                )
            self._run_type = RunType.OUTPUT
            self.app.logger.warning(
                "passed and position: %s", self._current_attend.block_position
            )
            return True
        else:
            yield from self._phase_emit_validation_error(app, state, validate_result)
            return False

    def _phase_emit_validation_error(
        self, app: Flask, state: _RunStepState, validate_result: object
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Stream the validation-error content and re-emit the interaction."""
        run_script_info = state.run_script_info
        block = state.block
        generated_block: LearnGeneratedBlock = init_generated_block(
            app,
            shifu_bid=run_script_info.attend.shifu_bid,
            outline_item_bid=run_script_info.outline_bid,
            progress_record_bid=run_script_info.attend.progress_record_bid,
            user_bid=self._user_info.user_id,
            block_type=BLOCK_TYPE_MDERRORMESSAGE_VALUE,
            mdflow=block.content,
            block_index=block.index,
        )
        generated_block.type = BLOCK_TYPE_MDERRORMESSAGE_VALUE
        generated_block.block_content_conf = block.content
        generated_block.role = ROLE_TEACHER
        # Stage only (no unit_of_work): the error content below may
        # stream from the LLM, and the row must not become durable
        # until the post-stream save so a disconnect mid-stream still
        # discards it via the producer rollback.
        db.session.add(generated_block)
        db.session.flush()
        content = ""
        error_content = getattr(validate_result, "content", "")
        if isinstance(error_content, str):
            error_chunks = [error_content] if error_content else []
        elif inspect.isgenerator(error_content):
            error_chunks = error_content
        elif isinstance(error_content, (list, tuple)):
            error_chunks = [str(item) for item in error_content if item is not None]
        elif error_content:
            error_chunks = [str(error_content)]
        else:
            error_chunks = []

        for chunk in error_chunks:
            if chunk is None:
                continue
            chunk_str = str(chunk)
            if not chunk_str:
                continue
            content += chunk_str
            self.append_langfuse_output(chunk_str)
            yield RunMarkdownFlowDTO(
                outline_bid=run_script_info.outline_bid,
                generated_block_bid=generated_block.generated_block_bid,
                type=GeneratedType.CONTENT,
                content=chunk_str,
            )
        yield RunMarkdownFlowDTO(
            outline_bid=run_script_info.outline_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.BREAK,
            content="",
        )
        generated_block.generated_content = content
        generated_block.type = BLOCK_TYPE_MDERRORMESSAGE_VALUE
        generated_block.block_content_conf = block.content
        # Post-stream finalize step: commits the staged error block
        # together with its streamed content.
        self._recorder.save_generated_block(generated_block)
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
        generated_block.role = ROLE_TEACHER
        # Stage only (no unit_of_work): the COMPLETE render below can
        # fail; a durable half-initialized interaction row would
        # otherwise survive it. The persist step after the render
        # commits the finished row.
        db.session.add(generated_block)
        db.session.flush()

        # Render interaction content with translation after validation error
        # Note: Do NOT pass variables here - we only want translation, not variable replacement
        state.llm_provider.set_usage_generated_block_bid(
            generated_block.generated_block_bid
        )
        interaction_result = state.mdflow_context.process(
            block_index=run_script_info.block_position,
            mode=ProcessMode.COMPLETE,
            context=state.message_list,
            variables=state.user_profile,
        )
        rendered_content = (
            interaction_result.content if interaction_result else block.content
        )

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
        self._can_continue = False
        self._recorder.update_progress_pointer(
            self._current_attend, status=LEARN_STATUS_IN_PROGRESS
        )
