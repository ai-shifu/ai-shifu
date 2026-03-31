from __future__ import annotations

import uuid
from typing import Generator

from flask import Flask

from flaskr.service.learn.learn_dtos import (
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_elements import ListenElementRunAdapter
from flaskr.service.learn.listen_element_run_state import BlockMeta


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
        base_element_bid = self._prepare_runtime_element(element)
        self._latest_element_snapshots[base_element_bid] = element.model_copy(deep=True)

    def _persisted_non_element_message(
        self,
        *,
        stored_event_type: str,
        emitted_event_type: str,
        content: str | object,
        generated_block_bid: str = "",
        is_terminal: bool | None = None,
    ) -> RunElementSSEMessageDTO:
        del stored_event_type
        return self._build_non_element_message(
            emitted_event_type=emitted_event_type,
            content=content,
            generated_block_bid=generated_block_bid,
            is_terminal=is_terminal,
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
        yield self._make_retire_element_message(
            generated_block_bid=state.generated_block_bid,
            element_bid=state.fallback_element_bid,
            element_index=max(self._max_element_index, 0),
            role=meta.role,
            element_type=ElementType.TEXT,
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
            yield self._make_retire_element_message(
                generated_block_bid=state.generated_block_bid,
                element_bid=stream_state.element_bid,
                element_index=stream_state.element_index,
                role=meta.role,
                element_type=stream_state.element_type,
            )

    def _interaction_content_and_payload(
        self, event: RunMarkdownFlowDTO, generated_block_bid: str
    ) -> tuple[str, ElementPayloadDTO]:
        del generated_block_bid
        payload = ElementPayloadDTO(audio=None, previous_visuals=[])
        content_text = (
            event.content
            if isinstance(event.content, str)
            else str(event.content or "")
        )
        return content_text, payload

    def _new_interaction_element_bid(self) -> str:
        return f"preview-interaction-{uuid.uuid4().hex[:8]}"
