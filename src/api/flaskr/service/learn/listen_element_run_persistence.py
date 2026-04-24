from __future__ import annotations

import json

from flaskr.dao import db
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    GeneratedType,
    OutlineItemUpdateDTO,
    RunElementSSEMessageDTO,
    VariableUpdateDTO,
)
from flaskr.service.learn.listen_element_payloads import (
    _sanitize_audio_segments_for_storage,
    _serialize_payload,
)
from flaskr.service.learn.listen_element_rows import _element_from_row
from flaskr.service.learn.listen_element_run_state import (
    BlockMeta,
    BlockState,
)
from flaskr.service.learn.listen_element_types import (
    _element_type_code,
    _role_value_to_name,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
)
from flaskr.service.learn.type_state_machine import TypeInput


class ListenElementRunPersistenceMixin:
    def _next_seq(self) -> int:
        self._run_event_seq += 1
        return self._run_event_seq

    def _next_sequence_number(self) -> int:
        self._sequence_number += 1
        return self._sequence_number

    def _resolve_persisted_is_new(self, element: ElementDTO) -> bool:
        if element.target_element_bid:
            return False
        return bool(element.is_new)

    def _remember_latest_element_snapshot(
        self, base_element_bid: str, element: ElementDTO
    ) -> None:
        if not base_element_bid:
            return
        snapshots = getattr(self, "_latest_element_snapshots", None)
        if snapshots is None:
            snapshots = {}
            self._latest_element_snapshots = snapshots
        snapshots[base_element_bid] = element.model_copy(deep=True)

    def _forget_latest_element_snapshot(self, base_element_bid: str) -> None:
        if not base_element_bid:
            return
        snapshots = getattr(self, "_latest_element_snapshots", None)
        if snapshots is None:
            return
        snapshots.pop(base_element_bid, None)

    def _load_block_meta(self, generated_block_bid: str) -> BlockMeta:
        if generated_block_bid in self._block_meta_cache:
            return self._block_meta_cache[generated_block_bid]
        meta = BlockMeta()
        if generated_block_bid:
            block = (
                LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.generated_block_bid == generated_block_bid,
                    LearnGeneratedBlock.deleted == 0,
                )
                .order_by(LearnGeneratedBlock.id.desc())
                .first()
            )
            if block:
                meta = BlockMeta(
                    progress_record_bid=block.progress_record_bid or "",
                    role=_role_value_to_name(block.role),
                )
        self._block_meta_cache[generated_block_bid] = meta
        return meta

    def _ensure_block_state(self, generated_block_bid: str) -> BlockState:
        state = self._block_states.get(generated_block_bid)
        if state is None:
            state = BlockState(generated_block_bid=generated_block_bid)
            self._block_states[generated_block_bid] = state
        return state

    def _find_active_element_row_ids(
        self,
        *,
        generated_block_bid: str,
        element_bids: list[str],
    ) -> list[int]:
        normalized_bids = sorted({str(bid) for bid in element_bids if bid})
        if not normalized_bids:
            return []

        base_filters = [
            LearnGeneratedElement.run_session_bid == self.run_session_bid,
            LearnGeneratedElement.generated_block_bid == (generated_block_bid or ""),
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ]
        row_ids: set[int] = set()
        lookup_columns = (
            LearnGeneratedElement.element_bid,
            LearnGeneratedElement.target_element_bid,
        )

        for lookup_column in lookup_columns:
            lookup_filter = (
                lookup_column == normalized_bids[0]
                if len(normalized_bids) == 1
                else lookup_column.in_(normalized_bids)
            )
            matched_rows = (
                LearnGeneratedElement.query.with_entities(LearnGeneratedElement.id)
                .filter(*base_filters, lookup_filter)
                .order_by(LearnGeneratedElement.id.asc())
                .all()
            )
            row_ids.update(
                int(row_id) for (row_id,) in matched_rows if row_id is not None
            )

        return sorted(row_ids)

    def _deactivate_active_element_rows(
        self,
        *,
        generated_block_bid: str,
        element_bids: list[str],
    ) -> None:
        row_ids = self._find_active_element_row_ids(
            generated_block_bid=generated_block_bid,
            element_bids=element_bids,
        )
        if not row_ids:
            return

        # Update rows in primary-key order so concurrent transactions retire the
        # same historical rows in a deterministic sequence.
        for row_id in row_ids:
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.id == row_id,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            ).update(
                {
                    "status": 0,
                },
                synchronize_session=False,
            )
        db.session.flush()

    def _insert_row(
        self,
        *,
        generated_block_bid: str,
        element_index: int,
        event_type: str,
        role: str,
        element_bid: str = "",
        element_type: ElementType | None = None,
        change_type: ElementChangeType | None = None,
        target_element_bid: str | None = None,
        is_renderable: bool = True,
        is_new: bool = True,
        is_marker: bool = False,
        sequence_number: int = 0,
        is_speakable: bool = False,
        audio_url: str = "",
        audio_segments: list | None = None,
        is_navigable: int = 1,
        is_final: int = 0,
        content_text: str = "",
        payload: ElementPayloadDTO | None = None,
        run_event_seq: int,
    ) -> None:
        meta = self._load_block_meta(generated_block_bid)
        row = LearnGeneratedElement(
            element_bid=element_bid or "",
            progress_record_bid=meta.progress_record_bid,
            user_bid=self.user_bid,
            generated_block_bid=generated_block_bid or "",
            outline_item_bid=self.outline_bid,
            shifu_bid=self.shifu_bid,
            run_session_bid=self.run_session_bid,
            run_event_seq=int(run_event_seq or 0),
            event_type=event_type,
            role=role or meta.role,
            element_index=int(element_index or 0),
            element_type=element_type.value if element_type is not None else "",
            element_type_code=(
                _element_type_code(element_type) if element_type is not None else 0
            ),
            change_type=change_type.value if change_type is not None else "",
            target_element_bid=target_element_bid or "",
            is_renderable=1 if is_renderable else 0,
            is_new=1 if is_new else 0,
            is_marker=1 if is_marker else 0,
            sequence_number=int(sequence_number or 0),
            is_speakable=1 if is_speakable else 0,
            audio_url=audio_url or "",
            audio_segments=json.dumps(
                _sanitize_audio_segments_for_storage(
                    audio_segments,
                    is_final=bool(is_final),
                ),
                ensure_ascii=False,
            ),
            is_navigable=int(is_navigable or 0),
            is_final=int(is_final or 0),
            content_text=content_text or "",
            payload=_serialize_payload(payload),
            deleted=0,
            status=1,
        )
        db.session.add(row)
        db.session.flush()

    def _element_message(self, element: ElementDTO) -> RunElementSSEMessageDTO:
        self._persist_element(element)
        return RunElementSSEMessageDTO(
            type="element",
            event_type="element",
            generated_block_bid=element.generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=element.run_event_seq,
            content=element,
        )

    def _stream_only_element_message(
        self, element: ElementDTO
    ) -> RunElementSSEMessageDTO:
        base_element_bid = self._prepare_runtime_element(element)
        self._remember_latest_element_snapshot(base_element_bid, element)
        return RunElementSSEMessageDTO(
            type="element",
            event_type="element",
            generated_block_bid=element.generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=element.run_event_seq,
            content=element,
        )

    def _prepare_runtime_element(self, element: ElementDTO) -> str:
        seq = self._next_seq()
        if element.element_type in {ElementType.ASK, ElementType.ANSWER}:
            element.is_new = bool(element.is_new)
        else:
            element.is_new = self._resolve_persisted_is_new(element)
        if not element.is_new and not element.target_element_bid:
            element.target_element_bid = element.element_bid
        element.sequence_number = self._next_sequence_number()
        element.run_session_bid = self.run_session_bid
        element.run_event_seq = seq
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.CONTENT_START, is_new=element.is_new)
        self._current_element_bid = (
            element.target_element_bid
            if not element.is_new and element.target_element_bid
            else element.element_bid
        )
        return (
            element.target_element_bid
            if not element.is_new and element.target_element_bid
            else element.element_bid
        )

    def _persist_element(self, element: ElementDTO) -> None:
        base_element_bid = self._prepare_runtime_element(element)
        replace_same_element_bid = bool(element.is_new and element.element_bid)
        if (not element.is_new) or replace_same_element_bid:
            self._deactivate_active_element_rows(
                generated_block_bid=element.generated_block_bid,
                element_bids=[base_element_bid],
            )
        self._insert_row(
            generated_block_bid=element.generated_block_bid,
            element_index=element.element_index,
            event_type="element",
            role=element.role,
            element_bid=element.element_bid,
            element_type=element.element_type,
            change_type=element.change_type,
            target_element_bid=element.target_element_bid,
            is_renderable=element.is_renderable,
            is_new=element.is_new,
            is_marker=element.is_marker,
            sequence_number=element.sequence_number,
            is_speakable=element.is_speakable,
            audio_url=element.audio_url,
            audio_segments=element.audio_segments,
            is_navigable=element.is_navigable,
            is_final=element.is_final,
            content_text=element.content_text,
            payload=element.payload,
            run_event_seq=element.run_event_seq,
        )
        self._remember_latest_element_snapshot(base_element_bid, element)

    def _build_non_element_message(
        self,
        *,
        emitted_event_type: str,
        content: str
        | VariableUpdateDTO
        | OutlineItemUpdateDTO
        | AudioSegmentDTO
        | AudioCompleteDTO,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
        run_event_seq: int | None = None,
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq() if run_event_seq is None else run_event_seq
        return RunElementSSEMessageDTO(
            type=emitted_event_type,
            event_type=emitted_event_type,
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            is_terminal=is_terminal,
            content=content,
        )

    def _persisted_non_element_message(
        self,
        *,
        stored_event_type: str,
        emitted_event_type: str,
        content: str
        | VariableUpdateDTO
        | OutlineItemUpdateDTO
        | AudioSegmentDTO
        | AudioCompleteDTO,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq()
        serialized_text = (
            content
            if isinstance(content, str)
            else json.dumps(content.__json__(), ensure_ascii=False)
        )
        meta = self._load_block_meta(generated_block_bid)
        self._insert_row(
            generated_block_bid=generated_block_bid,
            element_index=max(self._max_element_index, 0),
            event_type=stored_event_type,
            role=meta.role,
            is_navigable=0,
            is_final=1,
            content_text=serialized_text,
            payload=None,
            run_event_seq=seq,
        )
        return self._build_non_element_message(
            emitted_event_type=emitted_event_type,
            content=content,
            generated_block_bid=generated_block_bid,
            is_terminal=is_terminal,
            run_event_seq=seq,
        )

    def _non_element_message(
        self,
        *,
        event_type: str,
        content: str
        | VariableUpdateDTO
        | OutlineItemUpdateDTO
        | AudioSegmentDTO
        | AudioCompleteDTO,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        return self._persisted_non_element_message(
            stored_event_type=event_type,
            emitted_event_type=event_type,
            content=content,
            generated_block_bid=generated_block_bid,
            is_terminal=is_terminal,
        )

    def _stream_non_element_message(
        self,
        *,
        stored_event_type: str,
        emitted_event_type: str,
        content: str
        | VariableUpdateDTO
        | OutlineItemUpdateDTO
        | AudioSegmentDTO
        | AudioCompleteDTO,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        return self._persisted_non_element_message(
            stored_event_type=stored_event_type,
            emitted_event_type=emitted_event_type,
            content=content,
            generated_block_bid=generated_block_bid,
            is_terminal=is_terminal,
        )

    def make_ephemeral_message(
        self,
        *,
        event_type: str,
        content: str = "",
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq()
        emitted_event_type = (
            GeneratedType.DONE.value
            if event_type == GeneratedType.BREAK.value
            else event_type
        )
        if is_terminal is None and emitted_event_type == GeneratedType.DONE.value:
            is_terminal = event_type == GeneratedType.DONE.value
        return RunElementSSEMessageDTO(
            type=emitted_event_type,
            event_type=emitted_event_type,
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            is_terminal=is_terminal,
            content=content,
        )

    def _make_inter_element_done_message(
        self, generated_block_bid: str
    ) -> RunElementSSEMessageDTO:
        return self.make_ephemeral_message(
            event_type=GeneratedType.DONE.value,
            content="",
            generated_block_bid=generated_block_bid,
            is_terminal=False,
        )

    def _load_latest_element_snapshot(self, element_bid: str) -> ElementDTO | None:
        in_memory_snapshot = getattr(self, "_latest_element_snapshots", {}).get(
            element_bid
        )
        if in_memory_snapshot is not None:
            return in_memory_snapshot.model_copy(deep=True)
        row = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == self.run_session_bid,
                LearnGeneratedElement.event_type == "element",
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
                (LearnGeneratedElement.element_bid == element_bid)
                | (LearnGeneratedElement.target_element_bid == element_bid),
            )
            .order_by(
                LearnGeneratedElement.sequence_number.desc(),
                LearnGeneratedElement.run_event_seq.desc(),
                LearnGeneratedElement.id.desc(),
            )
            .first()
        )
        if row is None:
            return None
        return _element_from_row(row)
