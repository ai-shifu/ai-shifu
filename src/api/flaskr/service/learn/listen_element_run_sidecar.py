from __future__ import annotations

from typing import Generator

from flaskr.service.learn.learn_dtos import (
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_element_queries import (
    _load_interaction_user_input,
    _load_latest_active_element_row,
)
from flaskr.service.learn.listen_element_rows import _element_from_row
from flaskr.service.learn.listen_element_types import (
    _change_type_for_element,
    _element_type_code,
    _new_element_bid,
)


class ListenElementRunSidecarMixin:
    def _new_interaction_element_bid(self) -> str:
        return _new_element_bid(self.app)

    def _resolve_ask_element_bid_for_block(
        self,
        generated_block_bid: str,
        *,
        bind_current: bool = False,
    ) -> str:
        ask_element_bid = self._ask_element_bid_by_block_bid.get(
            generated_block_bid, ""
        )
        if ask_element_bid:
            return ask_element_bid
        if bind_current and self._current_ask_element_bid:
            self._ask_element_bid_by_block_bid[generated_block_bid] = (
                self._current_ask_element_bid
            )
            return self._current_ask_element_bid
        return ""

    def _resolve_answer_element_bid_for_block(self, generated_block_bid: str) -> str:
        return self._answer_element_bid_by_block_bid.get(generated_block_bid, "")

    def _build_follow_up_payload(
        self,
        *,
        anchor_element_bid: str,
        ask_element_bid: str | None = None,
        base_payload: ElementPayloadDTO | None = None,
    ) -> ElementPayloadDTO:
        payload = base_payload or ElementPayloadDTO()
        payload.audio = None
        payload.previous_visuals = []
        payload.anchor_element_bid = anchor_element_bid
        payload.ask_element_bid = ask_element_bid
        payload.asks = None
        return payload

    def _build_ask_element(
        self,
        *,
        generated_block_bid: str,
        ask_element_bid: str,
        anchor_element_bid: str,
        content_text: str,
        element_index: int,
        is_new: bool,
        is_final: bool,
        base_payload: ElementPayloadDTO | None = None,
    ) -> ElementDTO:
        return ElementDTO(
            event_type="element",
            element_bid=ask_element_bid,
            generated_block_bid=generated_block_bid,
            element_index=element_index,
            role="student",
            element_type=ElementType.ASK,
            element_type_code=_element_type_code(ElementType.ASK),
            change_type=_change_type_for_element(ElementType.ASK),
            target_element_bid=ask_element_bid if not is_new else None,
            is_new=is_new,
            is_renderable=False,
            is_marker=False,
            is_speakable=False,
            audio_url="",
            audio_segments=[],
            is_navigable=0,
            is_final=is_final,
            content_text=content_text,
            payload=self._build_follow_up_payload(
                anchor_element_bid=anchor_element_bid,
                base_payload=base_payload,
            ),
        )

    def _build_answer_element(
        self,
        *,
        generated_block_bid: str,
        answer_element_bid: str,
        anchor_element_bid: str,
        ask_element_bid: str,
        content_text: str,
        element_index: int,
        is_new: bool,
        is_final: bool,
        base_payload: ElementPayloadDTO | None = None,
    ) -> ElementDTO:
        return ElementDTO(
            event_type="element",
            element_bid=answer_element_bid,
            generated_block_bid=generated_block_bid,
            element_index=element_index,
            role="teacher",
            element_type=ElementType.ANSWER,
            element_type_code=_element_type_code(ElementType.ANSWER),
            change_type=_change_type_for_element(ElementType.ANSWER),
            target_element_bid=answer_element_bid if not is_new else None,
            is_new=is_new,
            is_renderable=False,
            is_marker=False,
            is_speakable=False,
            audio_url="",
            audio_segments=[],
            is_navigable=0,
            is_final=is_final,
            content_text=content_text,
            payload=self._build_follow_up_payload(
                anchor_element_bid=anchor_element_bid,
                ask_element_bid=ask_element_bid,
                base_payload=base_payload,
            ),
        )

    def _build_answer_element_patch(
        self,
        *,
        generated_block_bid: str,
        answer_element_bid: str,
        anchor_element_bid: str,
        ask_element_bid: str,
        content_text: str,
        is_final: bool,
    ) -> ElementDTO | None:
        snapshot = self._load_latest_element_snapshot(answer_element_bid)
        if snapshot is None:
            snapshot_row = _load_latest_active_element_row(answer_element_bid)
            if snapshot_row is None:
                return None
            snapshot = _element_from_row(snapshot_row)
        return self._build_answer_element(
            generated_block_bid=generated_block_bid,
            answer_element_bid=answer_element_bid,
            anchor_element_bid=anchor_element_bid,
            ask_element_bid=ask_element_bid,
            content_text=content_text,
            element_index=snapshot.element_index,
            is_new=False,
            is_final=is_final,
            base_payload=snapshot.payload,
        )

    def _load_follow_up_snapshot(self, element_bid: str) -> ElementDTO | None:
        snapshot = self._load_latest_element_snapshot(element_bid)
        if snapshot is not None:
            return snapshot
        snapshot_row = _load_latest_active_element_row(element_bid)
        if snapshot_row is None:
            return None
        return _element_from_row(snapshot_row)

    def _build_answer_element_from_state(
        self,
        generated_block_bid: str,
        *,
        is_final: bool,
    ) -> ElementDTO | None:
        ask_element_bid = self._resolve_ask_element_bid_for_block(
            generated_block_bid,
            bind_current=True,
        )
        if not ask_element_bid:
            return None
        ask_snapshot = self._load_follow_up_snapshot(ask_element_bid)
        if ask_snapshot is None:
            return None
        ask_payload = ask_snapshot.payload or ElementPayloadDTO()
        anchor_element_bid = (
            ask_payload.anchor_element_bid or self._current_ask_anchor_bid
        )
        if not anchor_element_bid:
            return None

        state = self._block_states.get(generated_block_bid)
        answer_element_bid = self._resolve_answer_element_bid_for_block(
            generated_block_bid
        )
        has_answer_signal = bool((state and state.raw_content) or answer_element_bid)
        if not has_answer_signal:
            return None

        if not answer_element_bid:
            answer_element_bid = _new_element_bid(self.app)
            self._answer_element_bid_by_block_bid[generated_block_bid] = (
                answer_element_bid
            )
            self._current_answer_element_bid = answer_element_bid
            return self._build_answer_element(
                generated_block_bid=generated_block_bid,
                answer_element_bid=answer_element_bid,
                anchor_element_bid=anchor_element_bid,
                ask_element_bid=ask_element_bid,
                content_text=state.raw_content if state is not None else "",
                element_index=ask_snapshot.element_index,
                is_new=True,
                is_final=is_final,
                base_payload=None,
            )

        self._current_answer_element_bid = answer_element_bid
        return self._build_answer_element_patch(
            generated_block_bid=generated_block_bid,
            answer_element_bid=answer_element_bid,
            anchor_element_bid=anchor_element_bid,
            ask_element_bid=ask_element_bid,
            content_text=state.raw_content if state is not None else "",
            is_final=is_final,
        )

    def _interaction_content_and_payload(
        self, event: RunMarkdownFlowDTO, generated_block_bid: str
    ) -> tuple[str, ElementPayloadDTO]:
        interaction_user_input = _load_interaction_user_input(generated_block_bid)
        payload = ElementPayloadDTO(audio=None, previous_visuals=[])
        if interaction_user_input:
            payload.user_input = interaction_user_input
        return str(event.content or ""), payload

    def _handle_interaction(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        content_text, payload = self._interaction_content_and_payload(
            event,
            generated_block_bid,
        )
        self._max_element_index += 1
        element = ElementDTO(
            event_type="element",
            element_bid=self._new_interaction_element_bid(),
            generated_block_bid=generated_block_bid,
            element_index=max(self._max_element_index, 0),
            role="ui",
            element_type=ElementType.INTERACTION,
            element_type_code=_element_type_code(ElementType.INTERACTION),
            change_type=ElementChangeType.RENDER,
            is_renderable=False,
            is_marker=True,
            is_navigable=0,
            is_final=True,
            content_text=content_text,
            payload=payload,
        )
        yield self._element_message(element)

    def _handle_ask(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        anchor_bid = getattr(event, "anchor_element_bid", "") or ""
        ask_content = str(event.content or "")
        generated_block_bid = event.generated_block_bid or ""
        meta = self._load_block_meta(generated_block_bid)

        # Under concurrency, the main stream may have just marked the anchor
        # element as status=0 in the instant between the client picking an
        # element and the ask request being served. Previously we dropped the
        # ASK event here, which left the MDASK/MDANSWER blocks orphaned on
        # reload. Fall back to a synthetic anchor derived from the ask's own
        # generated_block_bid so the follow-up chain still persists with the
        # correct element_type and can be recovered by the legacy builder.
        synthetic_anchor = False
        anchor_row = _load_latest_active_element_row(anchor_bid) if anchor_bid else None
        if anchor_row is None:
            synthetic_anchor = True
            self.app.logger.warning(
                "ASK anchor element unavailable, falling back to synthetic anchor: "
                "anchor_bid=%s generated_block_bid=%s",
                anchor_bid,
                generated_block_bid,
            )
            anchor_bid = anchor_bid or generated_block_bid
            element_index = 0
        else:
            element_index = int(anchor_row.element_index or 0)
            if not meta.progress_record_bid:
                meta.progress_record_bid = anchor_row.progress_record_bid or ""
                self._block_meta_cache[generated_block_bid] = meta

        if not anchor_bid:
            # No real anchor and no block bid either. Nothing sensible we can do.
            self.app.logger.warning(
                "ASK event without anchor_element_bid or generated_block_bid, skipping"
            )
            return

        self._current_ask_anchor_bid = anchor_bid

        ask_element_bid = _new_element_bid(self.app)
        self._current_ask_element_bid = ask_element_bid
        self._current_answer_element_bid = None
        self._ask_element_bid_by_block_bid[generated_block_bid] = ask_element_bid

        ask_element = self._build_ask_element(
            generated_block_bid=generated_block_bid,
            ask_element_bid=ask_element_bid,
            anchor_element_bid=anchor_bid,
            content_text=ask_content,
            element_index=element_index,
            is_new=True,
            is_final=True,
            base_payload=ElementPayloadDTO(anchor_element_bid=anchor_bid),
        )
        if synthetic_anchor:
            # Mark the synthesis so downstream consumers (logs, backfill) know
            # this anchor didn't come from a real LearnGeneratedElement row.
            if ask_element.payload is not None:
                ask_element.payload.anchor_element_bid = anchor_bid
        yield self._element_message(ask_element)

    def _finalize_answer_element(
        self, generated_block_bid: str
    ) -> RunElementSSEMessageDTO | None:
        answer_element = self._build_answer_element_from_state(
            generated_block_bid,
            is_final=True,
        )
        if answer_element is None:
            return None
        return self._element_message(answer_element)
