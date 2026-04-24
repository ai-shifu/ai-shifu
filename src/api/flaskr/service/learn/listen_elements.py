from __future__ import annotations

import uuid
from typing import Iterable

from flask import Flask

from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    LearnElementRecordDTO,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learn_funcs import get_learn_record
from flaskr.service.learn.listen_element_history import (
    get_listen_element_record as _get_listen_element_record,
)
from flaskr.service.learn.listen_element_mdflow_backfill import (
    backfill_learn_generated_elements_batch,
)
from flaskr.service.learn.legacy_record_builder import build_legacy_record_for_progress
from flaskr.service.learn.listen_element_legacy import (
    build_listen_elements_from_legacy_record,
)
from flaskr.service.learn.listen_element_run_persistence import (
    ListenElementRunPersistenceMixin,
)
from flaskr.service.learn.listen_element_run_sidecar import (
    ListenElementRunSidecarMixin,
)
from flaskr.service.learn.listen_element_run_state import (
    BlockMeta,
    BlockState,
)
from flaskr.service.learn.listen_element_run_stream import (
    ListenElementRunStreamMixin,
)
from flaskr.service.learn.type_state_machine import (
    TypeInput,
    TypeStateMachine,
)

__all__ = [
    "ListenElementRunAdapter",
    "backfill_learn_generated_elements_batch",
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
    ):
        self.app = app
        self.shifu_bid = shifu_bid
        self.outline_bid = outline_bid
        self.user_bid = user_bid
        self.run_session_bid = run_session_bid or uuid.uuid4().hex
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

    def process(
        self, events: Iterable[RunMarkdownFlowDTO]
    ) -> Iterable[RunElementSSEMessageDTO]:
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


def get_listen_element_record(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    preview_mode: bool,
    include_non_navigable: bool = False,
) -> LearnElementRecordDTO:
    return _get_listen_element_record(
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        include_non_navigable=include_non_navigable,
        build_legacy_record_for_progress_fn=build_legacy_record_for_progress,
        build_record_from_legacy=lambda legacy_record: (
            build_listen_elements_from_legacy_record(app, legacy_record)
        ),
        load_fallback_record=lambda: get_learn_record(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            preview_mode=preview_mode,
        ),
    )
