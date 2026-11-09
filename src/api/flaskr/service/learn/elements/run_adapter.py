"""Adapt learning events into listen-mode elements."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from flaskr.service.common.models import AppError
from flaskr.service.learn.agent.session_store import (
    LessonAttemptSource,
    load_lesson_attempt_source,
)
from flaskr.service.learn.elements.history import (
    get_listen_element_record as _get_listen_element_record,
)
from flaskr.service.learn.elements.legacy import (
    build_listen_elements_from_legacy_record,
)
from flaskr.service.learn.elements.legacy_record_builder import (
    build_legacy_record_for_progress,
)
from flaskr.service.learn.elements.run_persistence import (
    ListenElementRunPersistenceMixin,
)
from flaskr.service.learn.elements.run_sidecar import (
    ListenElementRunSidecarMixin,
)
from flaskr.service.learn.elements.run_stream import (
    ListenElementRunStreamMixin,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    LearnElementRecordDTO,
    OutlineItemUpdateDTO,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learn_funcs import (
    available_follow_up_mode,
    get_current_lesson_outline,
    get_learn_record,
    resolve_outline_reconciliation,
)
from flaskr.service.learn.lesson_content_updates import load_lesson_content_states
from flaskr.service.learn.preview_permissions import (
    has_shifu_staff_permission,
    require_shifu_preview_permission,
)
from flaskr.service.learn.type_state_machine import (
    TypeInput,
    TypeStateMachine,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Literal

    from flask import Flask
    from flaskr.service.learn.elements.run_state import (
        BlockMeta,
        BlockState,
    )

__all__ = [
    "ListenElementRunAdapter",
    "build_legacy_record_for_progress",
    "get_listen_element_record",
]


class ListenElementRunAdapter(
    ListenElementRunPersistenceMixin,
    ListenElementRunSidecarMixin,
    ListenElementRunStreamMixin,
):
    """Transform legacy listen-mode SSE into scheme-B element events."""

    def __init__(
        self,
        app: Flask,
        *,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
        run_session_bid: str | None = None,
        persist_only_final: bool = False,
    ) -> None:
        """Initialize a legacy listen-mode adaptation run and ordering state.

        Uses the supplied run session ID or generates one, resets event and element
        sequence counters, and initializes the type state machine and element
        tracking caches used by persisted and streamed events.
        """
        self.app = app
        self.shifu_bid = shifu_bid
        self.outline_bid = outline_bid
        self.user_bid = user_bid
        self.run_session_bid = run_session_bid or uuid.uuid4().hex
        # Whether a streaming element is written on every update or only once it is final.
        #
        # 1.0 writes each update as a new row holding the whole text so far, retiring the previous
        # one -- a snapshot trail nothing ever reads back, since every read path filters on
        # status == 1. It is affordable there because a script block is small. A 2.0 turn is a
        # whole lesson segment: one measured turn of 13KB produced 6394 rows and 35MB of retired
        # snapshots, against 4 rows and 21KB that the learner can actually see.
        #
        # Deferring costs the mid-stream snapshot, which only a learner refreshing during
        # generation would have seen, and which the session restores anyway.
        self.persist_only_final = persist_only_final
        self._run_event_seq = 0
        self._sequence_number = 0
        self._state_machine = TypeStateMachine()
        self._block_meta_cache: dict[str, BlockMeta] = {}
        self._block_states: dict[str, BlockState] = {}
        self._max_element_index = -1
        self._current_element_bid: str | None = None
        self._current_ask_anchor_bid: str | None = None
        self._current_ask_element_bid: str | None = None
        self._current_answer_element_bid: str | None = None
        self._ask_element_bid_by_block_bid: dict[str, str] = {}
        self._answer_element_bid_by_block_bid: dict[str, str] = {}
        self._latest_element_snapshots: dict[str, object] = {}

    def finalize_pending_blocks(self) -> Iterable[RunElementSSEMessageDTO]:
        """Save already shown content without emitting a successful run boundary."""
        for block_id in list(self._block_states):
            yield from self._finalize_block(block_id)

    def process(
        self, events: Iterable[RunMarkdownFlowDTO]
    ) -> Iterable[RunElementSSEMessageDTO]:
        """Adapt lesson run events into element SSE messages while advancing element state."""
        for event in events:
            if event.type == GeneratedType.CONTENT:
                yield from self._handle_content(event)
                continue
            if event.type == GeneratedType.AUDIO_SEGMENT:
                yield from self._handle_audio_segment(event)
                continue
            if event.type == GeneratedType.AUDIO_COMPLETE:
                yield from self._handle_audio_complete(event)
                continue
            if event.type == GeneratedType.ASK:
                for _ in self._handle_ask(event):
                    pass
                continue
            if event.type == GeneratedType.INTERACTION:
                yield from self._handle_interaction(event)
                continue
            if event.type == GeneratedType.BREAK:
                generated_block_bid = event.generated_block_bid or ""
                ask_element_bid = self._resolve_ask_element_bid_for_block(
                    generated_block_bid
                )
                if ask_element_bid:
                    answer_patch = self._finalize_answer_element(
                        generated_block_bid,
                    )
                    if answer_patch is not None:
                        yield answer_patch
                    self._block_states.pop(generated_block_bid, None)
                else:
                    yield from self._finalize_block(generated_block_bid)
                if not self._state_machine.is_terminated:
                    self._state_machine.feed(TypeInput.BLOCK_BREAK)
                self._current_element_bid = None
                self._current_ask_anchor_bid = None
                self._current_ask_element_bid = None
                self._current_answer_element_bid = None
                yield self._stream_non_element_message(
                    stored_event_type=GeneratedType.BREAK.value,
                    emitted_event_type=GeneratedType.DONE.value,
                    content="",
                    generated_block_bid=generated_block_bid,
                    is_terminal=False,
                )
                continue
            if event.type == GeneratedType.DONE:
                for block_id in list(self._block_states.keys()):
                    yield from self._finalize_block(block_id)
                if not self._state_machine.is_terminated:
                    self._state_machine.feed(TypeInput.DONE)
                self._current_element_bid = None
                yield self._non_element_message(
                    event_type=GeneratedType.DONE.value,
                    content="",
                    generated_block_bid=event.generated_block_bid or "",
                    is_terminal=True,
                )
                continue
            if event.type == GeneratedType.VARIABLE_UPDATE:
                yield self._non_element_message(
                    event_type=GeneratedType.VARIABLE_UPDATE.value,
                    content=event.content,
                    generated_block_bid=event.generated_block_bid or "",
                )
                continue
            if event.type == GeneratedType.OUTLINE_ITEM_UPDATE:
                yield self._non_element_message(
                    event_type=GeneratedType.OUTLINE_ITEM_UPDATE.value,
                    content=event.content,
                    generated_block_bid=event.generated_block_bid or "",
                )
                continue


def _require_draft_history_access(
    app: Flask, *, shifu_bid: str, outline_bid: str, user_bid: str, preview_mode: bool
) -> None:
    from flaskr.service.learn.agent.lesson_entry import require_requested_lesson_access

    require_shifu_preview_permission(app, user_bid, shifu_bid)
    if not preview_mode:
        require_requested_lesson_access(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=False,
        )


def _retained_follow_up_mode(
    app: Flask, shifu_bid: str, outline_bid: str, source: LessonAttemptSource
) -> Literal["text", "live_voice", "disabled"]:
    from flaskr.service.learn.agent.lesson_source import resolve_requested_lesson_source
    from flaskr.service.learn.utils_v2 import get_follow_up_info_v2
    from flaskr.service.shifu.api import HistoryItem, get_shifu_struct

    try:
        if source.structure_row_id is None:
            # The pre-sharing canonical key belongs to published learning.
            current = resolve_requested_lesson_source(
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                preview_mode=source.preview_mode,
            )
            structure = current.structure or get_shifu_struct(
                app, shifu_bid, source.preview_mode
            )
        else:
            model = LogDraftStruct if source.preview_mode else LogPublishedStruct
            row = model.query.filter_by(
                id=source.structure_row_id, shifu_bid=shifu_bid
            ).first()
            if row is None:
                return "disabled"
            structure = HistoryItem.from_json(row.struct)
        info = get_follow_up_info_v2(
            app,
            shifu_bid,
            outline_bid,
            "",
            is_preview=source.preview_mode,
            struct=structure,
            allow_retired_draft=source.preview_mode,
        )
    except AppError:
        # Missing historical configuration must not hide saved teaching.
        return "disabled"
    return available_follow_up_mode(info.ask_mode, info.ask_model)


def _reconcile_completed_outline(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    progress_record_bid: str,
    preview_mode: bool,
) -> list[OutlineItemUpdateDTO]:
    """Apply the selected catalog's hand-off and return its durable progress."""
    from flaskr.service.learn.agent.lesson_entry import require_requested_lesson_access
    from flaskr.service.learn.agent.lesson_record import reconcile_outline_progression

    scope = {"user_bid": user_bid, "shifu_bid": shifu_bid, "outline_bid": outline_bid}
    try:
        if preview_mode:
            require_shifu_preview_permission(app, user_bid, shifu_bid)
        require_requested_lesson_access(app, **scope, preview_mode=preview_mode)
    except AppError:
        # Saved history can remain readable even when the selected lesson cannot be run.
        return []
    try:
        updates, chapter_lessons = resolve_outline_reconciliation(
            app, shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=preview_mode
        )
        if updates:
            return reconcile_outline_progression(
                app,
                **scope,
                progress_record_bid=progress_record_bid,
                updates=updates,
                chapter_lessons=chapter_lessons,
            )
    except Exception:
        app.logger.warning(
            "could not reconcile completed lesson progression: user_bid=%s outline_bid=%s",
            user_bid,
            outline_bid,
            exc_info=True,
        )
    return []


def get_listen_element_record(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    preview_mode: bool,
    include_non_navigable: bool = False,
) -> LearnElementRecordDTO:
    """Read the active learning attempt, comparing it to the requested version."""
    source = load_lesson_attempt_source(
        user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )
    if source is not None and source.preview_mode:
        _require_draft_history_access(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=preview_mode,
        )

    from flaskr.service.learn.agent.lesson_record import find_active_progress_record

    progress = find_active_progress_record(
        user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )
    started = progress is not None and progress.status in (
        LEARN_STATUS_IN_PROGRESS,
        LEARN_STATUS_COMPLETED,
    )
    if (
        source is None
        and not started
        and (preview_mode or has_shifu_staff_permission(app, user_bid, shifu_bid))
    ):
        from flaskr.service.learn.agent.preview_history import (
            get_preview_record,
            legacy_preview_can_resume,
        )

        if legacy_preview_can_resume(
            app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
        ):
            legacy = get_preview_record(
                app,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                include_non_navigable=include_non_navigable,
            )
            if legacy.elements:
                _require_draft_history_access(
                    app,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    user_bid=user_bid,
                    preview_mode=preview_mode,
                )
                legacy.follow_up_mode = _retained_follow_up_mode(
                    app, shifu_bid, outline_bid, LessonAttemptSource(preview_mode=True)
                )
                return legacy
    record = _get_listen_element_record(
        app=app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        include_non_navigable=include_non_navigable,
        build_legacy_record_for_progress_fn=build_legacy_record_for_progress,
        build_record_from_legacy=lambda legacy_record: (
            build_listen_elements_from_legacy_record(app, legacy_record)
        ),
        load_fallback_record=lambda progress_record_bid: get_learn_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=preview_mode,
            progress_record_bid=progress_record_bid,
        ),
    )
    if source is not None:
        record.follow_up_mode = _retained_follow_up_mode(
            app, shifu_bid, outline_bid, source
        )
    if started:
        current = get_current_lesson_outline(
            shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=preview_mode
        )
        model = DraftOutlineItem if preview_mode else PublishedOutlineItem
        visible = (
            model.query.with_entities(model.id)
            .filter_by(
                id=current.id,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                deleted=0,
                hidden=0,
            )
            .first()
            if current
            else None
        )
        if visible and current is not None:
            if source is not None and progress.status == LEARN_STATUS_COMPLETED:
                record.outline_progress_updates = _reconcile_completed_outline(
                    app,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    progress_record_bid=progress.progress_record_bid,
                    preview_mode=preview_mode,
                )
            states = load_lesson_content_states(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                preview_mode=False,
                outline_revisions={outline_bid: current.content_revision},
            )
            state = states.get(outline_bid)
            record.has_content_update_for_current_user = bool(
                state and state.has_content_update
            )
    return record
