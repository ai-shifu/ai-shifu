from __future__ import annotations

import uuid
from typing import Any, Generator

from flask import Flask

from flaskr.service.learn.learn_dtos import (
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_elements import (
    BlockMeta,
    ListenElementRunAdapter,
    _change_type_for_element,
    _default_is_marker,
    _element_type_code,
    _mdflow_new_stream_is_new,
)
from flaskr.service.learn.type_state_machine import TypeInput


class PreviewElementRunAdapter(ListenElementRunAdapter):
    """Preview-only element adapter that keeps element snapshots in memory."""

    def __init__(
        self,
        app: Flask,
        *,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
        run_session_bid: str | None = None,
    ):
        super().__init__(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            run_session_bid=run_session_bid,
        )
        self._latest_element_snapshots: dict[str, ElementDTO] = {}

    def _load_block_meta(self, generated_block_bid: str) -> BlockMeta:
        if generated_block_bid not in self._block_meta_cache:
            self._block_meta_cache[generated_block_bid] = BlockMeta()
        return self._block_meta_cache[generated_block_bid]

    def _persist_element(self, element: ElementDTO) -> None:
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

        base_element_bid = (
            element.target_element_bid
            if not element.is_new and element.target_element_bid
            else element.element_bid
        )
        self._latest_element_snapshots[base_element_bid] = element.model_copy(deep=True)

    def _non_element_message(
        self,
        *,
        event_type: str,
        content: Any,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq()
        return RunElementSSEMessageDTO(
            type=event_type,
            event_type=event_type,
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            is_terminal=is_terminal,
            content=content,
        )

    def _stream_non_element_message(
        self,
        *,
        stored_event_type: str,
        emitted_event_type: str,
        content: Any,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        del stored_event_type
        seq = self._next_seq()
        return RunElementSSEMessageDTO(
            type=emitted_event_type,
            event_type=emitted_event_type,
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            is_terminal=is_terminal,
            content=content,
        )

    def _load_latest_element_snapshot(self, element_bid: str) -> ElementDTO | None:
        snapshot = self._latest_element_snapshots.get(element_bid)
        if snapshot is None:
            return None
        return snapshot.model_copy(deep=True)

    def _backfill_audio_url(self, element_bid: str, audio_url: str) -> None:
        snapshot = self._latest_element_snapshots.get(element_bid)
        if snapshot is None:
            return
        snapshot.audio_url = audio_url or ""
        self._latest_element_snapshots[element_bid] = snapshot

    def _retire_fallback_element(
        self, state, *, emit_notification: bool = True
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not state.fallback_element_bid:
            return
        self._latest_element_snapshots.pop(state.fallback_element_bid, None)
        if not emit_notification:
            return
        meta = self._load_block_meta(state.generated_block_bid)
        seq = self._next_seq()
        retire_element = ElementDTO(
            event_type="element",
            element_bid=state.fallback_element_bid,
            generated_block_bid=state.generated_block_bid,
            element_index=max(self._max_element_index, 0),
            role=meta.role,
            element_type=ElementType.TEXT,
            element_type_code=_element_type_code(ElementType.TEXT),
            change_type=_change_type_for_element(ElementType.TEXT),
            target_element_bid=None,
            is_new=True,
            is_marker=False,
            is_renderable=False,
            is_navigable=0,
            is_final=True,
            content_text="",
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
        )
        yield RunElementSSEMessageDTO(
            type="element",
            event_type="element",
            generated_block_bid=state.generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            content=retire_element,
        )

    def _retire_stream_elements(
        self, state, *, emit_notification: bool = True
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not state.stream_elements:
            return
        meta = self._load_block_meta(state.generated_block_bid)
        for stream_state in state.stream_elements.values():
            self._latest_element_snapshots.pop(stream_state.element_bid, None)
            if not emit_notification:
                continue
            seq = self._next_seq()
            fixed_is_new = _mdflow_new_stream_is_new(stream_state.element_type)
            retire_element = ElementDTO(
                event_type="element",
                element_bid=stream_state.element_bid,
                generated_block_bid=state.generated_block_bid,
                element_index=stream_state.element_index,
                role=meta.role,
                element_type=stream_state.element_type,
                element_type_code=_element_type_code(stream_state.element_type),
                change_type=_change_type_for_element(stream_state.element_type),
                target_element_bid=None if fixed_is_new else stream_state.element_bid,
                is_new=fixed_is_new,
                is_marker=_default_is_marker(stream_state.element_type),
                is_renderable=False,
                is_navigable=0,
                is_final=True,
                content_text="",
                run_session_bid=self.run_session_bid,
                run_event_seq=seq,
            )
            yield RunElementSSEMessageDTO(
                type="element",
                event_type="element",
                generated_block_bid=state.generated_block_bid or None,
                run_session_bid=self.run_session_bid,
                run_event_seq=seq,
                content=retire_element,
            )

    def _handle_interaction(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        payload = (
            event.content
            if isinstance(event.content, str)
            else str(event.content or "")
        )
        element = ElementDTO(
            event_type="element",
            element_bid=self._new_interaction_bid(),
            generated_block_bid=generated_block_bid,
            element_index=max(self._max_element_index + 1, 0),
            role="ui",
            element_type=ElementType.INTERACTION,
            element_type_code=_element_type_code(ElementType.INTERACTION),
            change_type=_change_type_for_element(ElementType.INTERACTION),
            is_renderable=False,
            is_marker=True,
            is_navigable=0,
            is_final=True,
            content_text=payload,
            payload=ElementPayloadDTO(audio=None, previous_visuals=[]),
        )
        self._max_element_index = max(self._max_element_index, element.element_index)
        yield self._element_message(element)

    def _new_interaction_bid(self) -> str:
        return f"preview-interaction-{uuid.uuid4().hex[:8]}"
