"""SSE event emitter for the learn /run chain (PR1 of the B6 decomposition).

``RunEventEmitter`` owns the construction and yield-sequencing of the
``RunMarkdownFlowDTO`` events that ``RunScriptContextV2`` streams for
outline updates, completion tails, and access/exception gate interactions.

PR1 scope notes:

- The emitter keeps a back-reference to the context and reads/writes the
  same attributes the original methods used (``_current_attend``,
  ``_current_outline_item``, ...). PR3 narrows this to explicit
  dependencies once the state object exists.
- Cross-method calls are dispatched back through the context wrappers
  (``ctx._emit_lesson_feedback_interaction`` etc.) so instance-level test
  seams and monkey-patches on the context keep working unchanged.
- Several methods still carry DB writes (generated-block persistence,
  progress-record status flips). They moved here intact because they are
  part of the emit flow; PR2 pulls the writes into the recorder.

Event names, payload shapes, and sequencing are FROZEN per
``flaskr/service/learn/AGENTS.md``; the golden suite is the contract gate.
"""

from typing import TYPE_CHECKING, Generator, Union

from flaskr.dao import db
from flaskr.i18n import _
from flaskr.service.learn.const import (
    CONTEXT_INTERACTION_LESSON_FEEDBACK_SCORE,
    CONTEXT_INTERACTION_NEXT,
    ROLE_TEACHER,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    LearnStatus,
    OutlineItemUpdateDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.lesson_feedback import build_lesson_feedback_interaction_md
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.learn.utils_v2 import init_generated_block
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.shifu.models import DraftOutlineItem, PublishedOutlineItem
from flaskr.util import generate_id

if TYPE_CHECKING:  # pragma: no cover - import cycle guard, typing only
    from flaskr.service.learn.context_v2 import RunScriptContextV2


class RunEventEmitter:
    """Constructs and sequences SSE events for the /run chain.

    PR1: holds a back-reference to ``RunScriptContextV2`` and mutates the
    same runtime state the original methods did. PR3 replaces the back
    reference with explicit state/recorder dependencies.
    """

    def __init__(self, context: "RunScriptContextV2") -> None:
        self._context = context

    def render_outline_updates(
        self, outline_updates: list[OutlineItemUpdateDTO], new_chapter: bool = False
    ) -> Generator[str, None, None]:
        ctx = self._context
        shifu_bids = [o.outline_bid for o in outline_updates]
        outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
            ctx._outline_model.query.filter(
                ctx._outline_model.outline_item_bid.in_(shifu_bids),
                ctx._outline_model.deleted == 0,
            ).all()
        )
        outline_item_info_map: dict[
            str, Union[DraftOutlineItem, PublishedOutlineItem]
        ] = {o.outline_item_bid: o for o in outline_item_info_db}
        for update in outline_updates:
            outline_item_info = outline_item_info_map.get(update.outline_bid, None)
            if not outline_item_info:
                continue
            if outline_item_info.hidden:
                continue
            if (not update.has_children) and update.status == LearnStatus.IN_PROGRESS:
                ctx._current_outline_item = ctx._get_outline_struct(update.outline_bid)
                if ctx._current_attend.outline_item_bid == update.outline_bid:
                    ctx._current_attend.status = LEARN_STATUS_IN_PROGRESS
                    ctx._current_attend.outline_item_updated = 0
                    ctx._current_attend.block_position = 0
                    yield RunMarkdownFlowDTO(
                        outline_bid=update.outline_bid,
                        generated_block_bid="",
                        type=GeneratedType.OUTLINE_ITEM_UPDATE,
                        content=update,
                    )
                    db.session.flush()
                    continue
                ctx._current_attend = ctx._get_current_attend(update.outline_bid)
                if (
                    ctx._current_attend.status == LEARN_STATUS_NOT_STARTED
                    or ctx._current_attend.status == LEARN_STATUS_LOCKED
                ):
                    ctx._current_attend.status = LEARN_STATUS_IN_PROGRESS
                    ctx._current_attend.block_position = 0
                    db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )
            elif (not update.has_children) and update.status == LearnStatus.COMPLETED:
                current_attend = ctx._get_current_attend(update.outline_bid)
                current_attend.status = LEARN_STATUS_COMPLETED
                ctx._current_attend = current_attend
                db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )
            elif update.has_children and update.status == LearnStatus.IN_PROGRESS:
                if new_chapter:
                    status = LEARN_STATUS_NOT_STARTED
                else:
                    status = LEARN_STATUS_IN_PROGRESS
                current_attend = ctx._get_current_attend(update.outline_bid)
                current_attend.status = status
                current_attend.block_position = 0

                db.session.flush()

                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )
            elif update.has_children and update.status == LearnStatus.COMPLETED:
                current_attend = ctx._get_current_attend(update.outline_bid)
                current_attend.status = LEARN_STATUS_COMPLETED
                db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )

    def emit_next_chapter_interaction(
        self,
        progress_record: LearnProgressRecord,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Persist and emit the standardized `_sys_next_chapter` interaction when a lesson
        completes so the frontend can advance automatically.
        """
        ctx = self._context
        if not progress_record or not ctx._outline_item_info:
            return

        button_label = _("server.learn.nextChapterButton")
        button_md = f"?[{button_label}//{CONTEXT_INTERACTION_NEXT}]"
        existing_block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid
                == progress_record.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid
                == progress_record.outline_item_bid,
                LearnGeneratedBlock.user_bid == ctx._user_info.user_id,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.block_content_conf == button_md,
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        if existing_block:
            return
        generated_block: LearnGeneratedBlock = init_generated_block(
            ctx.app,
            shifu_bid=progress_record.shifu_bid,
            outline_item_bid=progress_record.outline_item_bid,
            progress_record_bid=progress_record.progress_record_bid,
            user_bid=ctx._user_info.user_id,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            mdflow=button_md,
            block_index=progress_record.block_position,
        )
        generated_block.role = ROLE_TEACHER
        generated_block.block_content_conf = button_md
        db.session.add(generated_block)
        db.session.flush()
        ctx.append_langfuse_output(button_md)
        yield RunMarkdownFlowDTO(
            outline_bid=progress_record.outline_item_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=button_md,
        )

    def emit_lesson_feedback_interaction(
        self,
        progress_record: LearnProgressRecord,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Persist and emit the lesson-end feedback interaction before next chapter.
        """
        ctx = self._context
        if not progress_record or not ctx._outline_item_info:
            return

        feedback_md = build_lesson_feedback_interaction_md()
        marker = f"%{{{{{CONTEXT_INTERACTION_LESSON_FEEDBACK_SCORE}}}}}"
        existing_block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid
                == progress_record.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid
                == progress_record.outline_item_bid,
                LearnGeneratedBlock.user_bid == ctx._user_info.user_id,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.block_content_conf.contains(
                    marker, autoescape=True
                ),
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        if existing_block:
            return
        generated_block: LearnGeneratedBlock = init_generated_block(
            ctx.app,
            shifu_bid=progress_record.shifu_bid,
            outline_item_bid=progress_record.outline_item_bid,
            progress_record_bid=progress_record.progress_record_bid,
            user_bid=ctx._user_info.user_id,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            mdflow=feedback_md,
            block_index=progress_record.block_position,
        )
        generated_block.role = ROLE_TEACHER
        generated_block.block_content_conf = feedback_md
        db.session.add(generated_block)
        db.session.flush()
        ctx.append_langfuse_output(feedback_md)
        yield RunMarkdownFlowDTO(
            outline_bid=progress_record.outline_item_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=feedback_md,
        )

    def is_access_gate_blocking_interaction(self, parsed_interaction: dict) -> bool:
        ctx = self._context
        is_logged_in = bool(
            getattr(ctx._user_info, "mobile", None)
            or getattr(ctx._user_info, "email", None)
        )
        buttons = parsed_interaction.get("buttons") or []
        for button in buttons:
            value = button.get("value")
            if value == "_sys_pay" and not ctx._is_paid:
                return True
            if value == "_sys_login" and not is_logged_in:
                return True
        return False

    def maybe_emit_feedback_after_access_gate(
        self,
        *,
        parsed_interaction: dict,
        progress_record: LearnProgressRecord,
        is_tail_gate: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        # Dispatch through the context wrappers so instance-level overrides
        # (tests patch these seams) keep taking effect.
        ctx = self._context
        if not ctx._is_access_gate_blocking_interaction(parsed_interaction):
            return
        if not is_tail_gate:
            return
        yield from ctx._emit_lesson_feedback_interaction(progress_record)

    def emit_feedback_after_exception_gate(
        self,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        ctx = self._context
        if not ctx._outline_item_info:
            return
        generated_block_exists = (
            db.session.query(LearnGeneratedBlock.id)
            .filter(
                LearnGeneratedBlock.progress_record_bid
                == LearnProgressRecord.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid
                == LearnProgressRecord.outline_item_bid,
                LearnGeneratedBlock.user_bid == ctx._user_info.user_id,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.type.in_(
                    [BLOCK_TYPE_MDCONTENT_VALUE, BLOCK_TYPE_MDINTERACTION_VALUE]
                ),
            )
            .exists()
        )
        latest_completed_progress = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.user_bid == ctx._user_info.user_id,
                LearnProgressRecord.shifu_bid == ctx._outline_item_info.shifu_bid,
                LearnProgressRecord.outline_item_bid == ctx._outline_item_info.bid,
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status == LEARN_STATUS_COMPLETED,
                generated_block_exists,
            )
            .order_by(
                LearnProgressRecord.updated_at.desc(), LearnProgressRecord.id.desc()
            )
            .first()
        )
        if not latest_completed_progress:
            return
        yield from ctx._emit_lesson_feedback_interaction(latest_completed_progress)

    def ensure_current_attend_for_gate_interaction(
        self,
    ) -> LearnProgressRecord | None:
        ctx = self._context
        if ctx._current_attend:
            return ctx._current_attend
        if not ctx._outline_item_info:
            return None

        outline_bid = getattr(ctx._outline_item_info, "bid", "")
        shifu_bid = getattr(ctx._outline_item_info, "shifu_bid", "")
        user_bid = getattr(ctx._user_info, "user_id", "")
        if not outline_bid or not shifu_bid or not user_bid:
            return None

        current_attend = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.outline_item_bid == outline_bid,
                LearnProgressRecord.user_bid == user_bid,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            )
            .order_by(LearnProgressRecord.id.desc())
            .first()
        )
        if current_attend is None:
            current_attend = LearnProgressRecord(
                progress_record_bid=generate_id(ctx.app),
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                user_bid=user_bid,
                status=LEARN_STATUS_NOT_STARTED,
                block_position=0,
            )
            db.session.add(current_attend)
            db.session.flush()

        ctx._current_attend = current_attend
        return current_attend

    def emit_current_progress_gate_interaction(
        self,
        content: str,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        ctx = self._context
        current_attend = ctx._ensure_current_attend_for_gate_interaction()
        if not current_attend:
            return
        outline_bid = current_attend.outline_item_bid or getattr(
            ctx._outline_item_info, "bid", ""
        )
        if not outline_bid:
            return
        generated_block: LearnGeneratedBlock = init_generated_block(
            ctx.app,
            shifu_bid=current_attend.shifu_bid,
            outline_item_bid=outline_bid,
            progress_record_bid=current_attend.progress_record_bid,
            user_bid=ctx._user_info.user_id,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            mdflow=content,
            block_index=current_attend.block_position,
        )
        generated_block.role = ROLE_TEACHER
        generated_block.block_content_conf = content
        generated_block.generated_content = ""
        db.session.add(generated_block)
        db.session.flush()
        ctx.append_langfuse_output(content)
        yield RunMarkdownFlowDTO(
            outline_bid=outline_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=content,
        )

    def emit_completion_tail_interactions(
        self,
        *,
        progress_record: LearnProgressRecord,
        current_outline_completed: bool,
        has_next_outline_item: bool,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        # Dispatch through the context wrappers so instance-level overrides
        # (tests patch these seams) keep taking effect.
        ctx = self._context
        if has_next_outline_item:
            yield from ctx._emit_next_chapter_interaction(progress_record)
        if current_outline_completed:
            yield from ctx._emit_lesson_feedback_interaction(progress_record)
