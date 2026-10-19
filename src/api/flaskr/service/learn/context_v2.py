"""Orchestrate learning-session state and SSE generation."""

import queue
import threading
from collections.abc import Generator, Iterable
from typing import Any, Union

from flask import Flask
from flaskr.api.langfuse import (
    LangfuseTraceHandle,
    MockClient,
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
    get_request_trace_id,
    normalize_langfuse_input_value,
    normalize_langfuse_output_value,
    update_langfuse_trace,
)
from flaskr.api.llm import (
    chat_llm,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.api.llm.model_selection import selection_metadata, selection_model
from flaskr.common.cache_provider import (
    cache as cache_provider,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.common.i18n_utils import (  # noqa: F401  # kept patchable on the pre-split module path
    get_markdownflow_output_language,
    resolve_markdownflow_output_language,
)
from flaskr.common.shifu_context import (  # noqa: F401  # kept patchable on the pre-split module path
    apply_shifu_context_snapshot,
    get_shifu_context_snapshot,
)
from flaskr.dao import (  # noqa: F401  # kept patchable on the pre-split module path
    cleanup_session_after,
    db,
    invalidate_session,
)
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.i18n import (  # noqa: F401  # kept patchable on the pre-split module path
    _,
    get_current_language,
    set_language,
)
from flaskr.service.common import raise_error
from flaskr.service.learn import (
    context_v2_input_phases,
    context_v2_mdflow,
    context_v2_output_phases,
    context_v2_preview,
    context_v2_streaming,
)
from flaskr.service.learn.check_text import (
    check_text_with_llm_response,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.service.learn.const import (  # noqa: F401  # kept patchable on the pre-split module path
    INPUT_TYPE_ASK,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from flaskr.service.learn.context_v2_input_phases import RunInputPhasesMixin
from flaskr.service.learn.context_v2_mdflow import (  # noqa: F401  # kept patchable on the pre-split module path
    MdflowContextV2,
    RUNLLMProvider,
    RunScriptInfo,
    RunType,
    _iter_llm_result_content_parts,
    _normalize_stream_number,
    _resolve_runtime_language_context,
    _resolve_runtime_output_language,
    _RunStepState,
)
from flaskr.service.learn.context_v2_output_phases import RunOutputPhasesMixin
from flaskr.service.learn.context_v2_preview import (  # noqa: F401  # kept patchable on the pre-split module path
    RunScriptPreviewContextV2,
    _PreviewContextStore,
)
from flaskr.service.learn.context_v2_streaming import RunStreamingMixin
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.follow_up_context import resolve_course_system_prompt
from flaskr.service.learn.handle_input_ask import (
    handle_input_ask,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.service.learn.langfuse_naming import (  # noqa: F401  # kept patchable on the pre-split module path
    build_langfuse_generation_name,
    build_langfuse_span_name,
    build_langfuse_trace_name,
)
from flaskr.service.learn.learn_dtos import (  # noqa: F401  # kept patchable on the pre-split module path
    GeneratedType,
    OutlineItemUpdateDTO,
    PlaygroundPreviewRequest,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
    VariableUpdateDTO,
)
from flaskr.service.learn.learner_profile_prompt import (
    build_course_prompt,
    render_course_prompt_identity_variables,
)
from flaskr.service.learn.listen_element_queries import _load_latest_active_element_row
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.memory import (  # noqa: F401  # kept patchable on the pre-split module path
    MemoryUpdate,
    VariableMemoryUpdate,
    load_memory,
    stage_memory,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.learn.preview_elements import (
    PreviewElementRunAdapter,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.service.learn.run.emitter import RunEventEmitter
from flaskr.service.learn.run.recorder import RunRecorder
from flaskr.service.learn.run.state import RunStateResolver
from flaskr.service.learn.split_module_patching import forward_attribute_writes
from flaskr.service.learn.stream_tts_finalize import (
    StreamTTSFinalizeDrainer,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.service.learn.utils_v2 import (
    init_generated_block,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
)
from flaskr.service.profile.api import (  # noqa: F401  # kept patchable on the pre-split module path
    course_memory_deletion_state,
    is_course_reference,
)
from flaskr.service.profile.constants import (
    SYS_USER_LANGUAGE,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.service.profile.profile_manage import (
    ProfileItemDefinition,
    get_profile_item_definition_list,
)
from flaskr.service.shifu.consts import (  # noqa: F401  # kept patchable on the pre-split module path
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.shifu_struct_manager import (  # noqa: F401  # kept patchable on the pre-split module path
    ShifuInfoDto,
    ShifuOutlineItemDto,
    # Kept as a module attribute: run/state.py resolves it through this
    # namespace at call time and tests patch it here.
    get_outline_item_dto_with_mdflow,
    get_shifu_struct,
)
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.user.exceptions import UserNotLoginError
from flaskr.service.user.repository import (  # noqa: F401  # kept patchable on the pre-split module path
    UserAggregate,
    load_user_aggregate,
)
from flaskr.util import generate_id
from markdown_flow import (  # noqa: F401  # kept patchable on the pre-split module path
    USER_ANSWER_CONTEXT_KEY,
    BlockType,
    InteractionParser,
    LLMProvider,
    MarkdownFlow,
    ProcessMode,
    replace_variables_in_text,
)
from markdown_flow.llm import (
    LLMResult,  # noqa: F401  # kept patchable on the pre-split module path
)
from markdown_flow.models import (
    Block,  # noqa: F401  # kept patchable on the pre-split module path
)

context_local = threading.local()


def _find_outline_path_or_raise(
    struct: HistoryItem, outline_bid: str
) -> list[HistoryItem]:
    path = find_node_with_parents(struct, outline_bid)
    if not path:
        raise_error("server.shifu.lessonNotFoundInCourse")
    return path


class RunScriptContextV2(RunStreamingMixin, RunInputPhasesMixin, RunOutputPhasesMixin):
    """Coordinate state and output for a version-two learning run."""

    user_id: str
    attend_id: str
    is_paid: bool

    preview_mode: bool
    _q: queue.Queue
    _outline_item_info: ShifuOutlineItemDto
    _struct: HistoryItem
    _user_info: UserAggregate
    _is_paid: bool
    _preview_mode: bool
    _listen: bool
    _learning_mode: str
    _shifu_ids: list[str]
    _run_type: RunType
    _app: Flask
    _shifu_model: DraftShifu | PublishedShifu
    _outline_model: DraftOutlineItem | PublishedOutlineItem
    _trace_args: dict
    _trace_id: str
    _shifu_info: ShifuInfoDto
    _trace: LangfuseTraceHandle | MockClient
    _trace_root_span: Any
    _input_type: str
    _input: str
    _can_continue: bool
    _last_position: int
    _stop_event: threading.Event | None = None

    def _get_learning_mode(self) -> str:
        """Return the run learning mode, defaulting for test-built contexts."""
        learning_mode = getattr(self, "_learning_mode", None)
        if learning_mode in {"read", "listen", "classroom"}:
            return learning_mode
        return "listen" if getattr(self, "_listen", False) else "read"

    def __init__(
        self,
        app: Flask,
        shifu_info: ShifuInfoDto,
        struct: HistoryItem,
        outline_item_info: ShifuOutlineItemDto,
        user_info: UserAggregate,
        is_paid: bool,
        preview_mode: bool,
        listen: bool = False,
        learning_mode: str = "read",
        stop_event: threading.Event | None = None,
    ) -> None:
        """Select runtime models, locate the outline, and create its root trace."""
        self._last_position = -1
        self.app = app
        self._struct = struct
        self._outline_item_info = outline_item_info
        self._user_info = user_info
        self._is_paid = is_paid
        self._listen = listen
        normalized_learning_mode = str(learning_mode or "").strip().lower()
        if normalized_learning_mode not in {"read", "listen", "classroom"}:
            normalized_learning_mode = "listen" if listen else "read"
        self._learning_mode = normalized_learning_mode
        self._preview_mode = preview_mode
        self._shifu_info = shifu_info
        self.shifu_ids = []
        self.outline_item_ids = []
        self.current_outline_item = None
        # Initialize the private attribute the runtime actually reads: it is only
        # assigned later when a matching outline is found in the struct, so
        # without this default it stays undefined (AttributeError) whenever the
        # requested outline is missing from the struct.
        self._current_outline_item = None
        self._run_type = RunType.INPUT
        self._can_continue = True
        self._stop_event = stop_event
        self._element_index_cursor = 0
        self._langfuse_output_chunks: list[str] = []

        if preview_mode:
            self._outline_model = DraftOutlineItem
            self._shifu_model = DraftShifu
        else:
            self._outline_model = PublishedOutlineItem
            self._shifu_model = PublishedShifu
        # get current attend
        self._q = queue.Queue()
        self._q.put(struct)
        while not self._q.empty():
            item = self._q.get()
            if item.bid == outline_item_info.bid:
                self._current_outline_item = item
                break
            if item.children:
                for child in item.children:
                    self._q.put(child)
        self._current_attend = None
        self._trace_args = {}
        chapter_title = self._outline_item_info.title
        trace_scene = "lesson_preview_runtime" if preview_mode else "lesson_runtime"
        self._trace_id = get_request_trace_id()
        self._trace_args["user_id"] = user_info.user_id
        self._trace_args["name"] = build_langfuse_trace_name(chapter_title, trace_scene)
        self._trace_args["metadata"] = {
            "scene": trace_scene,
            "chapter_title": chapter_title,
            "outline_item_bid": self._outline_item_info.bid,
            "shifu_bid": self._outline_item_info.shifu_bid,
            "preview_mode": int(bool(preview_mode)),
        }
        self._trace, self._trace_root_span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={"id": self._trace_id, **self._trace_args},
            root_span_payload={
                "name": build_langfuse_span_name(
                    chapter_title,
                    trace_scene,
                    "root",
                ),
            },
        )
        self.app.logger.info(
            "langfuse runtime trace created | request_id=%s trace_id=%s scene=%s user_id=%s shifu_bid=%s outline_item_bid=%s session_id=%s",
            self._trace_id,
            self._trace_id,
            trace_scene,
            user_info.user_id,
            self._outline_item_info.shifu_bid,
            self._outline_item_info.bid,
            "",
        )
        context_local.current_context = self

    def _stop_requested(self) -> bool:
        return bool(self._stop_event is not None and self._stop_event.is_set())

    def _stop_if_requested(self) -> None:
        if self._stop_requested():
            self.app.logger.info("run_script context cancelled")
            raise GeneratorExit

    def _iter_until_active(self, items: Iterable[Any]) -> Generator[Any, None, None]:
        for item in items:
            self._stop_if_requested()
            yield item

    @staticmethod
    def get_current_context(_app: Flask) -> Union["RunScriptContextV2", None]:
        """Return the current RunScript context, if one is active."""
        if not hasattr(context_local, "current_context"):
            return None
        return context_local.current_context

    def append_langfuse_output(self, value: object) -> None:
        """Buffer output content for active Langfuse trace finalization."""
        if not hasattr(self, "_langfuse_output_chunks"):
            self._langfuse_output_chunks = []
        text = normalize_langfuse_output_value(value)
        if not text:
            return
        self._langfuse_output_chunks.append(text)

    def _finalize_langfuse_trace(self) -> None:
        output_chunks = getattr(self, "_langfuse_output_chunks", [])
        finalize_langfuse_trace(
            trace=self._trace,
            root_span=getattr(self, "_trace_root_span", None),
            trace_payload={
                **self._trace_args,
                "output": "".join(output_chunks) or None,
            },
            root_span_payload={
                "input": self._trace_args.get("input"),
                "output": "".join(output_chunks) or None,
            },
        )

    def _get_current_attend(self, outline_bid: str) -> LearnProgressRecord:
        # Order so that a record which has started learning wins over a
        # fresh NOT_STARTED placeholder. A parallel ask SSE running before
        # the main run committed cannot see the main row under MVCC and
        # falls through to creating a sibling at block_position=0; without
        # this ordering the next main-flow SSE would pick that fresh row
        # by id.desc() and restart the lesson from the first block.
        attend_info: LearnProgressRecord = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.outline_item_bid == outline_bid,
                LearnProgressRecord.user_bid == self._user_info.user_id,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            )
            .order_by(
                (LearnProgressRecord.status == LEARN_STATUS_NOT_STARTED).asc(),
                LearnProgressRecord.id.desc(),
            )
            .first()
        )
        if not attend_info:
            outline_filters = [self._outline_model.outline_item_bid == outline_bid]
            if self._preview_mode:
                outline_filters.append(self._outline_model.deleted == 0)
            else:
                if not self._shifu_model.query.filter(
                    self._shifu_model.shifu_bid == self._struct.bid,
                    self._shifu_model.deleted == 0,
                ).first():
                    raise_error("server.shifu.shifuNotFound")
                outline_filters.extend(
                    [
                        self._outline_model.id == self._get_outline_row_id(outline_bid),
                        self._outline_model.shifu_bid == self._struct.bid,
                    ]
                )
            outline_item_info_db: DraftOutlineItem | PublishedOutlineItem = (
                self._outline_model.query.filter(*outline_filters)
                .order_by(self._outline_model.id.desc())
                .first()
            )
            if not outline_item_info_db:
                raise_error("server.shifu.lessonNotFoundInCourse")
            if outline_item_info_db.type == UNIT_TYPE_VALUE_NORMAL:
                if (not self._is_paid) and (not self._preview_mode):
                    raise PaidError
            elif outline_item_info_db.type == UNIT_TYPE_VALUE_TRIAL and (
                not self._preview_mode
                and not self._user_info.mobile
                and not self._user_info.email
            ):
                raise UserNotLoginError
            parent_path = _find_outline_path_or_raise(self._struct, outline_bid)
            attend_info = None
            new_records: list[LearnProgressRecord] = []
            for item in parent_path:
                if item.type == "outline":
                    attend_info = LearnProgressRecord.query.filter(
                        LearnProgressRecord.outline_item_bid == item.bid,
                        LearnProgressRecord.user_bid == self._user_info.user_id,
                        LearnProgressRecord.status != LEARN_STATUS_RESET,
                    ).first()
                    if attend_info:
                        continue
                    # Rows staged earlier in this loop are not in the session
                    # yet, so the query above cannot see them; keep the
                    # pre-PR2 dedupe by checking the staged list too.
                    staged = next(
                        (
                            record
                            for record in new_records
                            if record.outline_item_bid == item.bid
                        ),
                        None,
                    )
                    if staged is not None:
                        attend_info = staged
                        continue
                    attend_info = LearnProgressRecord()
                    # Each placeholder carries its own node's bid: `item` walks
                    # the ancestor path, so ancestors must not inherit the
                    # leaf's bid (outline_item_info_db is the leaf row).
                    attend_info.outline_item_bid = item.bid
                    attend_info.shifu_bid = outline_item_info_db.shifu_bid
                    attend_info.user_bid = self._user_info.user_id
                    attend_info.status = LEARN_STATUS_NOT_STARTED
                    attend_info.progress_record_bid = generate_id(self.app)
                    attend_info.block_position = 0
                    new_records.append(attend_info)
            # One recorder step for the whole placeholder batch: a failure
            # rolls all placeholders back instead of leaving flushed rows.
            self._recorder.save_new_progress_records(new_records)
        return attend_info

    # The state-read methods below are thin delegation seams kept on the
    # context so run_inner call sites and test overrides keep working
    # unchanged; the resolution logic lives in
    # flaskr/service/learn/run/state.py.

    def _is_leaf_outline_item(self, outline_item_info: ShifuOutlineItemDto) -> bool:
        return self._state_resolver.is_leaf_outline_item(outline_item_info)

    def _get_current_outline_block_count(self) -> int:
        return self._state_resolver.get_current_outline_block_count()

    def _get_next_outline_item(self) -> list[OutlineItemUpdateDTO]:
        return self._state_resolver.get_next_outline_item()

    def _has_next_outline_item(
        self, outline_updates: list[OutlineItemUpdateDTO]
    ) -> bool:
        return self._state_resolver.has_next_outline_item(outline_updates)

    def _is_current_outline_completed(
        self, outline_updates: list[OutlineItemUpdateDTO]
    ) -> bool:
        return self._state_resolver.is_current_outline_completed(outline_updates)

    def _get_current_outline_item(self) -> ShifuOutlineItemDto:
        return self._current_outline_item

    @property
    def _event_emitter(self) -> RunEventEmitter:
        # Lazy so contexts built via __new__ (tests) get an emitter too.
        emitter = self.__dict__.get("_run_event_emitter")
        if emitter is None:
            emitter = RunEventEmitter(self)
            self.__dict__["_run_event_emitter"] = emitter
        return emitter

    @property
    def _recorder(self) -> RunRecorder:
        # Lazy so contexts built via __new__ (tests) get a recorder too.
        recorder = self.__dict__.get("_run_recorder")
        if recorder is None:
            recorder = RunRecorder(self.app)
            self.__dict__["_run_recorder"] = recorder
        return recorder

    @property
    def _state_resolver(self) -> RunStateResolver:
        # Lazy so contexts built via __new__ (tests) get a resolver too.
        resolver = self.__dict__.get("_run_state_resolver")
        if resolver is None:
            resolver = RunStateResolver(self)
            self.__dict__["_run_state_resolver"] = resolver
        return resolver

    # The methods below are thin delegation seams kept on the context so
    # run_inner call sites and test overrides keep working unchanged; the
    # event construction lives in flaskr/service/learn/run/emitter.py.

    def _render_outline_updates(
        self,
        outline_updates: list[OutlineItemUpdateDTO],
        new_chapter: bool = False,
    ) -> Generator[str, None, None]:
        yield from self._event_emitter.render_outline_updates(
            outline_updates, new_chapter=new_chapter
        )

    def _emit_next_chapter_interaction(
        self,
        progress_record: LearnProgressRecord,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        yield from self._event_emitter.emit_next_chapter_interaction(progress_record)

    def _emit_lesson_feedback_interaction(
        self,
        progress_record: LearnProgressRecord,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        yield from self._event_emitter.emit_lesson_feedback_interaction(progress_record)

    def _is_access_gate_blocking_interaction(self, parsed_interaction: dict) -> bool:
        return self._event_emitter.is_access_gate_blocking_interaction(
            parsed_interaction
        )

    def _maybe_emit_feedback_after_access_gate(
        self,
        *,
        parsed_interaction: dict,
        progress_record: LearnProgressRecord,
        is_tail_gate: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        yield from self._event_emitter.maybe_emit_feedback_after_access_gate(
            parsed_interaction=parsed_interaction,
            progress_record=progress_record,
            is_tail_gate=is_tail_gate,
        )

    def _emit_feedback_after_exception_gate(
        self,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        yield from self._event_emitter.emit_feedback_after_exception_gate()

    def _ensure_current_attend_for_gate_interaction(
        self,
    ) -> LearnProgressRecord | None:
        return self._event_emitter.ensure_current_attend_for_gate_interaction()

    def _emit_current_progress_gate_interaction(
        self,
        content: str,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        yield from self._event_emitter.emit_current_progress_gate_interaction(content)

    def _emit_completion_tail_interactions(
        self,
        *,
        progress_record: LearnProgressRecord,
        current_outline_completed: bool,
        has_next_outline_item: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        yield from self._event_emitter.emit_completion_tail_interactions(
            progress_record=progress_record,
            current_outline_completed=current_outline_completed,
            has_next_outline_item=has_next_outline_item,
        )

    def _has_effective_input(self) -> bool:
        input_value = self._input
        if input_value is None:
            return False
        if isinstance(input_value, dict):
            for raw in input_value.values():
                values = raw if isinstance(raw, list) else [raw]
                for value in values:
                    if value is None:
                        continue
                    if str(value).strip():
                        return True
            return False
        if isinstance(input_value, list):
            for value in input_value:
                if value is None:
                    continue
                if str(value).strip():
                    return True
            return False
        return bool(str(input_value).strip())

    def set_input(self, user_input: str | dict, input_type: str) -> None:
        """Set user input.

        Args:
            user_input: User input, can be:
                   - str: legacy format (e.g., "Python")
                   - dict: new format from markdown-flow 0.2.27+ (e.g., {"lang": ["Python"]})
            input_type: Input type

        """
        self._trace_args["input"] = normalize_langfuse_input_value(user_input)
        self._trace_args["input_type"] = input_type
        self._input_type = input_type
        self._input = user_input
        self._anchor_element_bid = ""

    def _get_outline_struct(self, outline_item_id: str) -> HistoryItem:
        return self._state_resolver.get_outline_struct(outline_item_id)

    def _get_outline_row_id(self, outline_item_bid: str) -> int | None:
        return self._state_resolver.get_outline_row_id(outline_item_bid)

    def _get_run_script_info(
        self, attend: LearnProgressRecord, is_ask: bool = False
    ) -> RunScriptInfo:
        return self._state_resolver.get_run_script_info(attend, is_ask=is_ask)

    def _get_run_script_info_by_block_id(self, block_id: str) -> RunScriptInfo:
        return self._state_resolver.get_run_script_info_by_block_id(block_id)

    def run_inner(self, app: Flask) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Orchestrate one /run step (B6 PR3).

        Thin phase sequencer: every region of the historical ~1,000-line
        body now lives in a named ``_phase_*`` method below, extracted
        verbatim. Phases that emit SSE events are generators driven via
        ``yield from``; their boolean return value tells the orchestrator
        whether the step finished before the completion tail.
        """
        self._stop_if_requested()
        self._current_attend = self._get_current_attend(self._outline_item_info.bid)
        app.logger.info(
            "run_context.run %s %s",
            self._current_attend.block_position,
            self._current_attend.status,
        )
        self._bind_trace_session()
        proceed = yield from self._phase_sync_outline_progress(app)
        if not proceed:
            return

        run_script_info: RunScriptInfo = self._get_run_script_info(
            self._current_attend, is_ask=self._input_type == "ask"
        )
        if run_script_info is None:
            yield from self._phase_completion_when_script_missing()
            return
        llm_settings = self.get_llm_settings(run_script_info.outline_bid)
        system_prompt = self.get_system_prompt(run_script_info.outline_bid)

        if self._input_type == "ask":
            yield from self._phase_handle_ask_input(app, run_script_info)
            return

        state = self._prepare_step_state(
            app, run_script_info, llm_settings, system_prompt
        )

        if run_script_info.block_position >= len(state.block_list):
            outline_updates = self._get_next_outline_item()
            if len(outline_updates) > 0:
                # Flips inside are committed per recorder step.
                yield from self._render_outline_updates(
                    outline_updates, new_chapter=True
                )
                self._can_continue = False
            return
        state.block = state.block_list[run_script_info.block_position]
        app.logger.info("block: %s", state.block)
        app.logger.info("self._run_type: %s", self._run_type)
        state.has_effective_input = self._has_effective_input()
        if self._run_type == RunType.INPUT:
            handled = yield from self._phase_process_input(app, state)
            if handled:
                return
        elif self._run_type == RunType.OUTPUT:
            handled = yield from self._phase_render_output(app, state)
            if handled:
                return

        yield from self._phase_completion_tail()

    def _bind_trace_session(self) -> None:
        """Bind the langfuse runtime trace to the resolved progress record."""
        if not getattr(self, "_trace_id", ""):
            self._trace_id = get_request_trace_id()
        if not isinstance(getattr(self, "_trace_args", None), dict):
            self._trace_args = {}
        if not hasattr(self, "_trace_root_span"):
            self._trace_root_span = None
        self._trace_args.setdefault("metadata", {})
        self._trace_args["session_id"] = self._current_attend.progress_record_bid
        # The SDK replicates trace attributes onto every observation instead of
        # keeping a mutable trace record, and only observations started after an
        # attribute is bound carry it. Push the session id now so the spans and
        # generations of this step are attributed to the session; leaving it to
        # the finalize update would reach the root observation only.
        trace = getattr(self, "_trace", None)
        if trace is not None:
            update_langfuse_trace(trace, session_id=self._trace_args["session_id"])
        self.app.logger.info(
            "langfuse runtime trace session bound | request_id=%s trace_id=%s scene=%s user_id=%s shifu_bid=%s outline_item_bid=%s session_id=%s",
            self._trace_id,
            self._trace_id,
            self._trace_args["metadata"].get("scene", ""),
            self._trace_args.get("user_id", ""),
            self._outline_item_info.shifu_bid,
            self._outline_item_info.bid,
            self._trace_args["session_id"],
        )

    def _phase_sync_outline_progress(
        self, app: Flask
    ) -> Generator[RunMarkdownFlowDTO, None, bool]:
        """Emit entry outline updates and re-read the attend row.

        Returns False when the refreshed progress status means the step must
        stop (the historical early return in run_inner).
        """
        outline_updates = self._get_next_outline_item()
        if len(outline_updates) > 0 and self._input_type != "ask":
            # PR2: the progress flips inside render_outline_updates are now
            # committed per-step by the recorder; no pending writes remain to
            # flush before re-reading the attend row.
            yield from self._render_outline_updates(outline_updates, new_chapter=False)
            self._current_attend = self._get_current_attend(self._outline_item_info.bid)
            if self._current_attend.status not in [
                LEARN_STATUS_IN_PROGRESS,
                LEARN_STATUS_NOT_STARTED,
            ]:
                app.logger.info(
                    "current_attend.status != LEARN_STATUS_IN_PROGRESS To False,current_attend.status: %s",
                    self._current_attend.status,
                )
                self._can_continue = False
                return False
        return True

    def _phase_completion_when_script_missing(
        self,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Completion tail for a step whose run-script info resolved to None."""
        self.app.logger.warning("run script is none")
        outline_updates = self._get_next_outline_item()
        has_next_outline_item = self._has_next_outline_item(outline_updates)
        current_outline_completed = self._is_current_outline_completed(outline_updates)
        yield from self._emit_completion_tail_interactions(
            progress_record=self._current_attend,
            current_outline_completed=current_outline_completed,
            has_next_outline_item=has_next_outline_item,
        )
        self._can_continue = False
        if len(outline_updates) > 0:
            # Flips/inserts inside are committed per recorder step.
            yield from self._render_outline_updates(outline_updates, new_chapter=True)
            self._can_continue = False

    def _persist_generated_block_for_events(
        self, generated_block: LearnGeneratedBlock | None
    ) -> None:
        # One recorder step per interaction-block persist. Only called
        # after any LLM COMPLETE call for the block has returned; never
        # while a stream is in flight.
        if generated_block is None:
            return
        self._recorder.save_generated_block(generated_block)

    def _prepare_step_state(
        self,
        app: Flask,
        run_script_info: RunScriptInfo,
        llm_settings: LLMSettings,
        system_prompt: str | None,
    ) -> _RunStepState:
        """Build the per-step collaborators (LLM provider, MDF context, ...)."""
        generated_blocks: list[LearnGeneratedBlock] = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.user_bid == self._user_info.user_id,
                LearnGeneratedBlock.shifu_bid == run_script_info.attend.shifu_bid,
                LearnGeneratedBlock.progress_record_bid
                == self._current_attend.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid == run_script_info.outline_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type.in_(
                    [BLOCK_TYPE_MDCONTENT_VALUE, BLOCK_TYPE_MDINTERACTION_VALUE]
                ),
            )
            .order_by(LearnGeneratedBlock.position.asc(), LearnGeneratedBlock.id.asc())
            .all()
        )

        usage_scene = (
            BILL_USAGE_SCENE_PREVIEW if self._preview_mode else BILL_USAGE_SCENE_PROD
        )
        usage_context = UsageContext(
            user_bid=self._user_info.user_id,
            shifu_bid=self._outline_item_info.shifu_bid,
            outline_item_bid=run_script_info.outline_bid,
            progress_record_bid=self._current_attend.progress_record_bid,
            usage_scene=usage_scene,
            learning_mode=self._get_learning_mode(),
        )
        llm_provider = RUNLLMProvider(
            app,
            llm_settings,
            self._trace,
            self._trace_root_span,
            self._trace_args,
            usage_context,
            usage_scene,
        )
        memory_generations, _ = course_memory_deletion_state(
            self._user_info.user_id, self._outline_item_info.shifu_bid
        )
        memory = load_memory(
            app,
            self._user_info.user_id,
            self._outline_item_info.shifu_bid,
            reference_text=(run_script_info.mdflow, system_prompt or ""),
        )
        user_profile, runtime_output_language = _resolve_runtime_language_context(
            memory.as_variables(),
            use_learner_language=bool(self._shifu_info.use_learner_language),
        )
        system_prompt = build_course_prompt(
            system_prompt,
            variables=user_profile,
            nickname_identifiers=(
                getattr(self._user_info, "user_bid", self._user_info.user_id),
                getattr(self._user_info, "identify", ""),
            ),
        )
        system_prompt = render_course_prompt_identity_variables(
            system_prompt,
            user_profile,
        )
        mdflow_context = MdflowContextV2(
            document=run_script_info.mdflow,
            document_prompt=system_prompt,
            llm_provider=llm_provider,
            use_learner_language=self._shifu_info.use_learner_language,
            visual_mode=True,
            output_language=runtime_output_language,
        )
        block_list = mdflow_context.get_all_blocks()
        message_list = MdflowContextV2.build_context_from_blocks(
            generated_blocks, run_script_info.mdflow, user_profile
        )

        variable_definition: list[ProfileItemDefinition] = (
            get_profile_item_definition_list(app, self._outline_item_info.shifu_bid)
        )
        variable_definition_key_id_map: dict[str, str] = {
            p.profile_key: p.profile_id for p in variable_definition
        }
        return _RunStepState(
            run_script_info=run_script_info,
            llm_settings=llm_settings,
            system_prompt=system_prompt,
            usage_context=usage_context,
            llm_provider=llm_provider,
            mdflow_context=mdflow_context,
            block_list=block_list,
            user_profile=user_profile,
            message_list=message_list,
            variable_definition_key_id_map=variable_definition_key_id_map,
            memory_generations=memory_generations,
        )

    def _phase_completion_tail(
        self,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Post-step outline completion: outline flips + tail interactions."""
        progress_record = self._current_attend
        outline_updates = self._get_next_outline_item()
        if len(outline_updates) > 0:
            has_next_outline_item = self._has_next_outline_item(outline_updates)
            current_outline_completed = self._is_current_outline_completed(
                outline_updates
            )
            # Flips/inserts inside are committed per recorder step.
            yield from self._render_outline_updates(outline_updates, new_chapter=True)
            yield from self._emit_completion_tail_interactions(
                progress_record=progress_record,
                current_outline_completed=current_outline_completed,
                has_next_outline_item=has_next_outline_item,
            )
            self._can_continue = False

    def run(self, app: Flask) -> Generator[RunMarkdownFlowDTO, None, None]:
        """Execute the current lesson run."""
        try:
            yield from self.run_inner(app)
        except PaidError:
            app.logger.info("PaidError")
            self._can_continue = False
            yield from self._emit_current_progress_gate_interaction(
                f"?[{_('server.order.checkout')}//_sys_pay]"
            )
            yield from self._emit_feedback_after_exception_gate()
        except UserNotLoginError:
            app.logger.info("UserNotLoginError")
            self._can_continue = False
            yield from self._emit_current_progress_gate_interaction(
                f"?[{_('server.user.login')}//_sys_login]"
            )
            yield from self._emit_feedback_after_exception_gate()

    def has_next(self) -> bool:
        """Return whether the lesson run can execute another step."""
        return self._can_continue

    def get_system_prompt(self, outline_item_bid: str) -> str | None:
        """Build the system prompt for the current lesson run."""
        outline_path = _find_outline_path_or_raise(self._struct, outline_item_bid)
        return resolve_course_system_prompt(
            self.app,
            shifu_bid=str(
                getattr(getattr(self, "_outline_item_info", None), "shifu_bid", "")
                or ""
            ),
            outline_item_bid=outline_item_bid,
            preview_mode=bool(getattr(self, "_preview_mode", False)),
            outline_path=outline_path,
            outline_model=self._outline_model,
            shifu_model=self._shifu_model,
        )

    def get_llm_settings(self, outline_bid: str) -> LLMSettings:
        """Return the effective LLM settings for this run."""
        path = _find_outline_path_or_raise(self._struct, outline_bid)
        shifu_nodes = [item for item in path if item.type == "shifu"]
        if len(shifu_nodes) != 1:
            raise_error("server.shifu.shifuNotFound")
        shifu_node = shifu_nodes[0]
        filters = [
            self._shifu_model.id == shifu_node.id,
            self._shifu_model.shifu_bid == shifu_node.bid,
        ]
        if self._preview_mode:
            filters.append(self._shifu_model.deleted == 0)
        elif not self._shifu_model.query.filter(
            self._shifu_model.shifu_bid == shifu_node.bid,
            self._shifu_model.deleted == 0,
        ).first():
            # Republishing retires a revision, but deleting the course must
            # still prevent a run from reading its historical publication.
            raise_error("server.shifu.shifuNotFound")
        shifu_info_db: DraftShifu | PublishedShifu = self._shifu_model.query.filter(
            *filters,
        ).first()
        if shifu_info_db is None:
            raise_error("server.shifu.shifuNotFound")
        return LLMSettings(
            model=selection_model(shifu_info_db),
            temperature=shifu_info_db.llm_temperature,
            usage_metadata=selection_metadata(shifu_info_db),
        )

    def _deactivate_superseded_generated_rows(
        self,
        generated_block: LearnGeneratedBlock,
        *,
        include_current_block: bool,
    ) -> None:
        """Deactivate generated blocks and elements superseded by a reload anchor."""
        affected_blocks = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid
                == generated_block.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid
                == generated_block.outline_item_bid,
                LearnGeneratedBlock.user_bid == self._user_info.user_id,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type.notin_(
                    [
                        BLOCK_TYPE_MDASK_VALUE,
                        BLOCK_TYPE_MDANSWER_VALUE,
                    ]
                ),
                LearnGeneratedBlock.id
                >= (
                    generated_block.id
                    if include_current_block
                    else generated_block.id + 1
                ),
                LearnGeneratedBlock.position
                >= (
                    generated_block.position
                    if include_current_block
                    else generated_block.position + 1
                ),
            )
            .order_by(LearnGeneratedBlock.id.asc())
            .all()
        )
        affected_block_bids = [
            block.generated_block_bid
            for block in affected_blocks
            if block.generated_block_bid
        ]
        if not affected_block_bids:
            return
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid.in_(affected_block_bids),
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.type.notin_(
                [
                    BLOCK_TYPE_MDASK_VALUE,
                    BLOCK_TYPE_MDANSWER_VALUE,
                ]
            ),
        ).update(
            {LearnGeneratedBlock.status: 0},
            synchronize_session=False,
        )
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.progress_record_bid
            == generated_block.progress_record_bid,
            LearnGeneratedElement.outline_item_bid == generated_block.outline_item_bid,
            LearnGeneratedElement.user_bid == self._user_info.user_id,
            LearnGeneratedElement.generated_block_bid.in_(affected_block_bids),
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ).update(
            {LearnGeneratedElement.status: 0},
            synchronize_session=False,
        )

    def reload(
        self,
        app: Flask,
        reload_generated_block_bid: str,
        *,
        reload_element_bid: str | None = None,
    ) -> Generator[object, None, None]:
        """Regenerate from an anchor by rewinding progress and deactivating superseded persisted state."""
        # Join the producer's session: a nested ``app.app_context()`` would
        # hand this rewind a *different* session from the run it precedes.
        with app_context_scope(app):
            anchor_element = None
            anchor_generated_block_bid = ""
            if reload_element_bid:
                anchor_element = _load_latest_active_element_row(reload_element_bid)
                if anchor_element:
                    anchor_generated_block_bid = (
                        anchor_element.generated_block_bid or ""
                    )
                # Trust the frontend-supplied element_bid for ask runs even if
                # the row is not yet visible in this session: the main run
                # holds the element in an uncommitted transaction, so MVCC
                # isolation hides it from the parallel ask session. Recording
                # it here ensures handle_input_ask receives the real
                # element_bid instead of an empty anchor that would force a
                # synthetic fallback in listen_element_run_sidecar.
                if self._input_type == "ask":
                    self._anchor_element_bid = reload_element_bid

            # Frontend element-protocol flows may still pass element_bid through
            # reload_generated_block_bid. Always prefer the persisted source block
            # resolved from reload_element_bid when it is available.
            if anchor_generated_block_bid:
                reload_generated_block_bid = anchor_generated_block_bid

            generated_block: LearnGeneratedBlock = None
            if reload_generated_block_bid:
                generated_block = LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.generated_block_bid
                    == reload_generated_block_bid,
                ).first()

            if generated_block:
                current_attend = self._get_current_attend(
                    generated_block.outline_item_bid
                )
                self._can_continue = False
                if self._input_type != "ask":
                    app.logger.info(
                        "reload generated_block: %s,block_position: %s",
                        generated_block.id,
                        generated_block.position,
                    )

                    with unit_of_work():
                        if generated_block.type == BLOCK_TYPE_MDCONTENT_VALUE:
                            self._deactivate_superseded_generated_rows(
                                generated_block, include_current_block=True
                            )
                        if generated_block.type == BLOCK_TYPE_MDINTERACTION_VALUE:
                            self._deactivate_superseded_generated_rows(
                                generated_block, include_current_block=False
                            )
                        current_attend.block_position = generated_block.position
                        current_attend.status = LEARN_STATUS_IN_PROGRESS
                else:
                    self._last_position = generated_block.position
            elif anchor_element:
                # Element-only reload for ask: set position from element
                self._can_continue = False
                self._last_position = int(
                    getattr(anchor_element, "element_index", 0) or 0
                )
        # The caller (``run_script_inner``) checkpoints the session once the
        # regenerated stream completes; no commit belongs after the yield.
        with app_context_scope(app):
            yield from self.run(app)


# Code split out of this module still resolves its dependencies in its own
# namespace; forward patches applied here (tests and plugins patch names on
# ``flaskr.service.learn.context_v2``) to the sibling modules.
forward_attribute_writes(
    __name__,
    (
        context_v2_mdflow,
        context_v2_preview,
        context_v2_streaming,
        context_v2_input_phases,
        context_v2_output_phases,
    ),
)
