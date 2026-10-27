"""Answer one follow-up question without building the 1.0 script run context.

A follow-up runs beside the lesson under its own semaphore. It never advanced the
script, so all it took from ``RunScriptContextV2`` was the lesson lookup, the
learner's progress record, the course prompt and a Langfuse trace. This module
supplies exactly those, so asking a question no longer depends on the 1.0 engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
    get_request_trace_id,
    normalize_langfuse_input_value,
    normalize_langfuse_output_value,
    update_langfuse_trace,
)
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common import raise_error
from flaskr.service.learn.agent.routing import uses_agent_engine
from flaskr.service.learn.const import INPUT_TYPE_ASK
from flaskr.service.learn.exceptions import PaidError
from flaskr.service.learn.follow_up_context import resolve_course_system_prompt
from flaskr.service.learn.follow_up_memory_writer import (
    FollowUpMemoryPatch,
    stage_follow_up_memory,
)
from flaskr.service.learn.handle_input_ask import handle_input_ask
from flaskr.service.learn.langfuse_naming import (
    build_langfuse_span_name,
    build_langfuse_trace_name,
)
from flaskr.service.learn.listen_element_queries import _load_latest_active_element_row
from flaskr.service.learn.memory import load_memory
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import Order
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_NORMAL, UNIT_TYPE_VALUE_TRIAL
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_struct_manager import (
    ShifuInfoDto,
    ShifuOutlineItemDto,
    get_outline_item_dto,
    get_shifu_dto,
    get_shifu_struct,
)
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.user.exceptions import UserNotLoginError
from flaskr.service.user.repository import UserAggregate, load_user_aggregate
from flaskr.util import generate_id

if TYPE_CHECKING:
    import threading
    from collections.abc import Generator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO
    from flaskr.service.shifu.shifu_history_manager import HistoryItem


class FollowUpCancelledError(Exception):
    """The learner closed the stream; nothing more is written for this question."""


@dataclass
class AskContext:
    """The lesson state ``handle_input_ask`` reads.

    Attribute names match what ``handle_input_ask`` reads from the context it is given.
    """

    app: Flask
    _struct: HistoryItem
    _shifu_info: ShifuInfoDto
    _preview_mode: bool
    _listen: bool
    _learning_mode: str
    _stop_event: threading.Event | None
    _langfuse_output_chunks: list[str] = field(default_factory=list)
    _system_prompts: dict[str, str | None] = field(default_factory=dict)

    @property
    def _outline_model(self) -> type[DraftOutlineItem | PublishedOutlineItem]:
        return DraftOutlineItem if self._preview_mode else PublishedOutlineItem

    @property
    def _shifu_model(self) -> type[DraftShifu | PublishedShifu]:
        return DraftShifu if self._preview_mode else PublishedShifu

    def outline_path(self, outline_item_bid: str) -> list[HistoryItem]:
        """Return the course path down to a lesson, or refuse an unknown lesson."""
        path = find_node_with_parents(self._struct, outline_item_bid)
        if not path:
            raise_error("server.shifu.lessonNotFoundInCourse")
        return path

    def get_system_prompt(self, outline_item_bid: str) -> str | None:
        """Return the nearest inherited Course Prompt for a lesson."""
        if outline_item_bid not in self._system_prompts:
            self._system_prompts[outline_item_bid] = resolve_course_system_prompt(
                self.app,
                shifu_bid=self._shifu_info.bid,
                outline_item_bid=outline_item_bid,
                preview_mode=self._preview_mode,
                outline_path=self.outline_path(outline_item_bid),
                outline_model=self._outline_model,
                shifu_model=self._shifu_model,
            )
        return self._system_prompts[outline_item_bid]

    def _get_outline_row_id(self, outline_item_bid: str) -> int | None:
        node = find_node_with_parents(self._struct, outline_item_bid)
        if node and getattr(node[-1], "id", None):
            return int(node[-1].id)
        return None

    def append_langfuse_output(self, value: object) -> None:
        """Buffer answer text for the trace finalized when the question ends."""
        text = normalize_langfuse_output_value(value)
        if text:
            self._langfuse_output_chunks.append(text)


def follow_up_events(
    app: Flask,
    *,
    user_bid: str,
    outline_bid: str,
    user_input: str | dict | list | None,
    reload_generated_block_bid: str | None,
    reload_element_bid: str | None,
    listen: bool,
    learning_mode: str,
    preview_mode: bool,
    stop_event: threading.Event | None,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """Stream the answer to one follow-up question and save its history rows.

    The caller owns the database session: it commits after this generator is
    exhausted and discards the connection on ``FollowUpCancelledError``.
    """
    user_info = load_user_aggregate(user_bid)
    if not user_info:
        raise_error("USER.USER_NOT_FOUND")
    if not outline_bid:
        raise_error("server.shifu.lessonNotFoundInCourse")
    outline_item_info = get_outline_item_dto(app, outline_bid, preview_mode)
    shifu_info = get_shifu_dto(app, outline_item_info.shifu_bid, preview_mode)
    struct = get_shifu_struct(app, shifu_info.bid, preview_mode)
    if not struct:
        raise_error("server.shifu.shifuNotFound")

    normalized_mode = str(learning_mode or "").strip().lower()
    if normalized_mode not in {"read", "listen", "classroom"}:
        normalized_mode = "listen" if listen else "read"
    context = AskContext(
        app=app,
        _struct=struct,
        _shifu_info=shifu_info,
        _preview_mode=preview_mode,
        _listen=listen,
        _learning_mode=normalized_mode,
        _stop_event=stop_event,
    )
    trace_args, trace, root_span = _open_trace(
        app, user_info, outline_item_info, user_input, preview_mode
    )
    try:
        anchor_element_bid, anchor_position = _resolve_anchor(
            reload_generated_block_bid, reload_element_bid
        )
        attend = _current_attend(
            app,
            context,
            user_info,
            outline_bid=outline_item_info.bid,
            is_paid=_is_paid(user_bid, shifu_info),
        )
        _bind_trace_session(trace, trace_args, attend)
        _require_live_course(context, outline_item_info.bid)
        yield from _answer(
            app,
            context,
            user_info=user_info,
            outline_item_info=outline_item_info,
            attend=attend,
            user_input=user_input,
            last_position=(
                attend.block_position if anchor_position is None else anchor_position
            ),
            anchor_element_bid=anchor_element_bid,
            trace_args=trace_args,
            trace=trace,
            root_span=root_span,
        )
    except (FollowUpCancelledError, GeneratorExit):
        # The learner walked away; the trace is left as it stands.
        raise
    except BaseException:
        _finalize_trace(context, trace_args, trace, root_span)
        raise
    _finalize_trace(context, trace_args, trace, root_span)


def _open_trace(
    app: Flask,
    user_info: UserAggregate,
    outline_item_info: ShifuOutlineItemDto,
    user_input: object,
    preview_mode: bool,
) -> tuple[dict, object, object]:
    chapter_title = outline_item_info.title
    trace_scene = "lesson_preview_runtime" if preview_mode else "lesson_runtime"
    trace_id = get_request_trace_id()
    trace_args: dict = {
        "user_id": user_info.user_id,
        "name": build_langfuse_trace_name(chapter_title, trace_scene),
        "metadata": {
            "scene": trace_scene,
            "chapter_title": chapter_title,
            "outline_item_bid": outline_item_info.bid,
            "shifu_bid": outline_item_info.shifu_bid,
            "preview_mode": int(bool(preview_mode)),
        },
    }
    trace, root_span = create_trace_with_root_span(
        client=get_langfuse_client(),
        trace_payload={"id": trace_id, **trace_args},
        root_span_payload={
            "name": build_langfuse_span_name(chapter_title, trace_scene, "root")
        },
    )
    trace_args["input"] = normalize_langfuse_input_value(user_input)
    trace_args["input_type"] = INPUT_TYPE_ASK
    app.logger.info(
        "langfuse ask trace created | trace_id=%s scene=%s user_id=%s shifu_bid=%s "
        "outline_item_bid=%s",
        trace_id,
        trace_scene,
        user_info.user_id,
        outline_item_info.shifu_bid,
        outline_item_info.bid,
    )
    return trace_args, trace, root_span


def _bind_trace_session(
    trace: object, trace_args: dict, attend: LearnProgressRecord
) -> None:
    # Observations started after this carry the session id; the root span already exists.
    trace_args["session_id"] = attend.progress_record_bid
    if trace is not None:
        update_langfuse_trace(trace, session_id=attend.progress_record_bid)


def _finalize_trace(
    context: AskContext, trace_args: dict, trace: object, root_span: object
) -> None:
    output = "".join(context._langfuse_output_chunks) or None
    finalize_langfuse_trace(
        trace=trace,
        root_span=root_span,
        trace_payload={**trace_args, "output": output},
        root_span_payload={"input": trace_args.get("input"), "output": output},
    )


def _resolve_anchor(
    reload_generated_block_bid: str | None, reload_element_bid: str | None
) -> tuple[str, int | None]:
    """Return the anchor element and the position the question is asked at, if anchored.

    The element id from the client is trusted even when its row is not visible yet: the
    lesson stream may still hold it in an uncommitted transaction.
    """
    anchor_element = None
    if reload_element_bid:
        anchor_element = _load_latest_active_element_row(reload_element_bid)
        if anchor_element and anchor_element.generated_block_bid:
            reload_generated_block_bid = anchor_element.generated_block_bid
    if reload_generated_block_bid:
        block = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == reload_generated_block_bid
        ).first()
        if block:
            return reload_element_bid or "", block.position
    if anchor_element:
        return reload_element_bid or "", int(
            getattr(anchor_element, "element_index", 0) or 0
        )
    return reload_element_bid or "", None


def _is_paid(user_bid: str, shifu_info: ShifuInfoDto) -> bool:
    if not shifu_info.price or shifu_info.price <= 0:
        return True
    return (
        Order.query.filter(
            Order.user_bid == user_bid,
            Order.shifu_bid == shifu_info.bid,
            Order.status == ORDER_STATUS_SUCCESS,
            Order.deleted == 0,
        ).first()
        is not None
    )


def _current_attend(
    app: Flask,
    context: AskContext,
    user_info: UserAggregate,
    *,
    outline_bid: str,
    is_paid: bool,
) -> LearnProgressRecord:
    """Return the learner's progress record for the lesson, creating placeholders if missing.

    A record that has started learning wins over a fresh NOT_STARTED placeholder: a
    question asked before the lesson stream committed cannot see the lesson's row and
    would otherwise make the next lesson request restart from the first block.
    """
    attend = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.user_bid == user_info.user_id,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .order_by(
            (LearnProgressRecord.status == LEARN_STATUS_NOT_STARTED).asc(),
            LearnProgressRecord.id.desc(),
        )
        .first()
    )
    if attend:
        return attend

    outline_model = context._outline_model
    shifu_model = context._shifu_model
    filters = [outline_model.outline_item_bid == outline_bid]
    if context._preview_mode:
        filters.append(outline_model.deleted == 0)
    else:
        if not shifu_model.query.filter(
            shifu_model.shifu_bid == context._struct.bid,
            shifu_model.deleted == 0,
        ).first():
            raise_error("server.shifu.shifuNotFound")
        filters.extend(
            [
                outline_model.id == context._get_outline_row_id(outline_bid),
                outline_model.shifu_bid == context._struct.bid,
            ]
        )
    outline_row = (
        outline_model.query.filter(*filters).order_by(outline_model.id.desc()).first()
    )
    if not outline_row:
        raise_error("server.shifu.lessonNotFoundInCourse")
    if outline_row.type == UNIT_TYPE_VALUE_NORMAL:
        if not is_paid and not context._preview_mode:
            raise PaidError
    elif outline_row.type == UNIT_TYPE_VALUE_TRIAL and (
        not context._preview_mode and not user_info.mobile and not user_info.email
    ):
        raise UserNotLoginError

    new_records: list[LearnProgressRecord] = []
    for item in context.outline_path(outline_bid):
        if item.type != "outline":
            continue
        existing = LearnProgressRecord.query.filter(
            LearnProgressRecord.outline_item_bid == item.bid,
            LearnProgressRecord.user_bid == user_info.user_id,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).first()
        staged = next((r for r in new_records if r.outline_item_bid == item.bid), None)
        attend = existing or staged
        if attend is not None:
            continue
        attend = LearnProgressRecord()
        # Each placeholder carries its own node's bid, not the leaf's.
        attend.outline_item_bid = item.bid
        attend.shifu_bid = outline_row.shifu_bid
        attend.user_bid = user_info.user_id
        attend.status = LEARN_STATUS_NOT_STARTED
        attend.progress_record_bid = generate_id(app)
        attend.block_position = 0
        new_records.append(attend)
    if new_records:
        with unit_of_work():
            for record in new_records:
                db.session.add(record)
            db.session.flush()
    return attend


def _require_live_course(context: AskContext, outline_bid: str) -> None:
    """Refuse a question about a course that was deleted or whose revision is gone."""
    shifu_nodes = [
        item for item in context.outline_path(outline_bid) if item.type == "shifu"
    ]
    if len(shifu_nodes) != 1:
        raise_error("server.shifu.shifuNotFound")
    node = shifu_nodes[0]
    model = context._shifu_model
    filters = [model.id == node.id, model.shifu_bid == node.bid]
    if context._preview_mode:
        filters.append(model.deleted == 0)
    elif not model.query.filter(
        model.shifu_bid == node.bid, model.deleted == 0
    ).first():
        # Republishing retires a revision, but deleting the course must still
        # prevent a question from reading its historical publication.
        raise_error("server.shifu.shifuNotFound")
    if model.query.filter(*filters).first() is None:
        raise_error("server.shifu.shifuNotFound")


def _answer(
    app: Flask,
    context: AskContext,
    *,
    user_info: UserAggregate,
    outline_item_info: ShifuOutlineItemDto,
    attend: LearnProgressRecord,
    user_input: str | dict | list | None,
    last_position: int,
    anchor_element_bid: str,
    trace_args: dict,
    trace: object,
    root_span: object,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    question = user_input
    if isinstance(question, dict):
        question = question.get("input", "")
    if isinstance(question, list):
        question = ",".join(question)
    question = question or ""
    _stop_if_requested(app, context)
    app.logger.info("Ask input normalized: input_chars=%s", len(question))

    agent_course = uses_agent_engine(outline_item_info.shifu_bid)
    runtime_profiles = load_memory(
        app,
        user_info.user_id,
        outline_item_info.shifu_bid,
        reference_text=context.get_system_prompt(outline_item_info.bid) or "",
        **({"include_course_variables": True} if agent_course else {}),
    ).as_variables()
    memory_patch = FollowUpMemoryPatch() if agent_course else None

    events = handle_input_ask(
        app,
        context,
        user_info,
        attend.progress_record_bid,
        question,
        outline_item_info,
        trace_args,
        trace,
        context._preview_mode,
        last_position,
        anchor_element_bid=anchor_element_bid,
        parent_observation=root_span,
        runtime_profiles=runtime_profiles,
        memory_patch=memory_patch,
    )
    for event in events:
        _stop_if_requested(app, context)
        yield event

    # handle_input_ask stages its history rows with plain flushes; the caller
    # commits them once the stream has completed.
    if (
        memory_patch is not None
        and memory_patch.variables
        and not context._preview_mode
    ):
        with unit_of_work():
            stage_follow_up_memory(
                app,
                user_bid=user_info.user_id,
                shifu_bid=outline_item_info.shifu_bid,
                outline_bid=outline_item_info.bid,
                progress_record_bid=attend.progress_record_bid,
                patch=memory_patch,
            )
            db.session.flush()


def _stop_if_requested(app: Flask, context: AskContext) -> None:
    if context._stop_event is not None and context._stop_event.is_set():
        app.logger.info("follow-up cancelled by stop_event")
        raise FollowUpCancelledError
