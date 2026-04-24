from __future__ import annotations

from typing import Any, Generator

from flaskr.dao import db
from flaskr.service.learn.learn_dtos import (
    AudioCompleteDTO,
    AudioSegmentDTO,
    ElementAudioDTO,
    ElementChangeType,
    ElementDTO,
    ElementPayloadDTO,
    ElementType,
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_element_audio_binding import (
    _resolve_audio_target_element_bid_for_stream_number,
    _resolve_audio_target_element_bid,
    _resolve_pending_audio_for_stream_element,
    _resolve_stream_audio_for_element_bid,
)
from flaskr.service.learn.listen_element_factory import (
    _build_final_elements_for_av_contract,
)
from flaskr.service.learn.listen_element_payloads import (
    _audio_segment_payload,
    _make_audio_payload,
    _mark_last_audio_segment_final,
    _payload_from_stream_element,
    _pick_default_audio_position,
    _prepare_audio_segments_for_element,
    _upsert_audio_segment_payload,
)
from flaskr.service.learn.listen_element_run_state import (
    BlockState,
    StreamElementState,
    _mdflow_new_stream_is_new,
)
from flaskr.service.learn.listen_element_types import (
    _change_type_for_element,
    _default_is_marker,
    _default_is_renderable,
    _default_is_speakable,
    _element_type_code,
    _new_element_bid,
    _normalized_is_speakable,
)
from flaskr.service.learn.listen_slide_builder import (
    VisualSegment,
    build_visual_segments_for_block,
)
from flaskr.service.learn.listen_source_span_utils import (
    normalize_source_span,
    slice_source_by_span,
)
from flaskr.service.learn.models import LearnGeneratedElement
from flaskr.service.learn.type_state_machine import TypeInput


class ListenElementRunStreamMixin:
    def _make_retire_element_message(
        self,
        *,
        generated_block_bid: str,
        element_bid: str,
        element_index: int,
        role: str,
        element_type: ElementType,
    ) -> RunElementSSEMessageDTO:
        seq = self._next_seq()
        fixed_is_new = _mdflow_new_stream_is_new(element_type)
        retire_element = ElementDTO(
            event_type="element",
            element_bid=element_bid,
            generated_block_bid=generated_block_bid,
            element_index=element_index,
            role=role,
            element_type=element_type,
            element_type_code=_element_type_code(element_type),
            change_type=_change_type_for_element(element_type),
            target_element_bid=None if fixed_is_new else element_bid,
            is_new=fixed_is_new,
            is_marker=_default_is_marker(element_type),
            is_renderable=False,
            is_navigable=0,
            is_final=True,
            content_text="",
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
        )
        return RunElementSSEMessageDTO(
            type="element",
            event_type="element",
            generated_block_bid=generated_block_bid or None,
            run_session_bid=self.run_session_bid,
            run_event_seq=seq,
            content=retire_element,
        )

    def _formatted_parts_from_event(
        self, event: RunMarkdownFlowDTO
    ) -> list[tuple[str, str, int]]:
        return event.get_mdflow_stream_parts()

    def _build_fallback_element(self, state: BlockState, role: str) -> ElementDTO:
        if not state.fallback_element_bid:
            state.fallback_element_bid = _new_element_bid(self.app)
            self._max_element_index += 1
        audio, audio_segments = _resolve_stream_audio_for_element_bid(
            state,
            state.fallback_element_bid,
        )
        return ElementDTO(
            event_type="element",
            element_bid=state.fallback_element_bid,
            generated_block_bid=state.generated_block_bid,
            element_index=max(self._max_element_index, 0),
            role=role,
            element_type=ElementType.TEXT,
            element_type_code=_element_type_code(ElementType.TEXT),
            change_type=ElementChangeType.RENDER,
            is_renderable=False,
            is_marker=False,
            is_navigable=1,
            is_final=False,
            is_speakable=_default_is_speakable(ElementType.TEXT, state.raw_content),
            audio_url=audio.audio_url if audio is not None else "",
            audio_segments=_prepare_audio_segments_for_element(
                audio_segments,
                is_final=False,
            ),
            content_text=state.raw_content,
            payload=ElementPayloadDTO(audio=audio, previous_visuals=[]),
        )

    def _retire_fallback_element(
        self, state: BlockState, *, emit_notification: bool = True
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not state.fallback_element_bid:
            return
        self._deactivate_active_element_rows(
            generated_block_bid=state.generated_block_bid,
            element_bids=[state.fallback_element_bid],
        )
        self._forget_latest_element_snapshot(state.fallback_element_bid)
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

    def _build_audio_patch_element(
        self,
        element_bid: str,
        audio_segments: list[dict[str, Any]] | None = None,
        *,
        audio: ElementAudioDTO | None = None,
        is_final: bool | None = None,
    ) -> ElementDTO | None:
        snapshot = self._load_latest_element_snapshot(element_bid)
        if snapshot is None:
            return None
        element_is_final = snapshot.is_final if is_final is None else bool(is_final)
        fixed_is_new = bool(snapshot.is_new)
        payload = (
            snapshot.payload.model_copy(deep=True)
            if snapshot.payload is not None
            else ElementPayloadDTO()
        )
        if audio is not None:
            payload.audio = audio
        return ElementDTO(
            event_type="element",
            element_bid=element_bid,
            generated_block_bid=snapshot.generated_block_bid,
            element_index=snapshot.element_index,
            role=snapshot.role,
            element_type=snapshot.element_type,
            element_type_code=snapshot.element_type_code,
            change_type=_change_type_for_element(snapshot.element_type),
            target_element_bid=None if fixed_is_new else element_bid,
            is_new=fixed_is_new,
            is_renderable=snapshot.is_renderable,
            is_marker=snapshot.is_marker,
            is_speakable=_normalized_is_speakable(
                snapshot.element_type,
                snapshot.content_text,
                stored_is_speakable=snapshot.is_speakable,
            ),
            audio_url=snapshot.audio_url,
            audio_segments=_prepare_audio_segments_for_element(
                audio_segments or snapshot.audio_segments or [],
                is_final=element_is_final,
            ),
            is_navigable=snapshot.is_navigable,
            is_final=element_is_final,
            content_text=snapshot.content_text,
            payload=payload,
        )

    def _build_audio_segment_patch_message(
        self,
        element_bid: str,
        audio_segments: list[dict[str, Any]] | None = None,
        *,
        audio: ElementAudioDTO | None = None,
    ) -> RunElementSSEMessageDTO | None:
        patch_element = self._build_audio_patch_element(
            element_bid,
            audio_segments=audio_segments,
            audio=audio,
        )
        if patch_element is None:
            return None
        return self._element_message(patch_element)

    def _backfill_audio_url(self, element_bid: str, audio_url: str) -> None:
        LearnGeneratedElement.query.filter(
            LearnGeneratedElement.run_session_bid == self.run_session_bid,
            LearnGeneratedElement.element_bid == element_bid,
            LearnGeneratedElement.event_type == "element",
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ).update({"audio_url": audio_url}, synchronize_session=False)
        db.session.flush()

    def _build_stream_element_message(
        self,
        *,
        state: BlockState,
        role: str,
        stream_state: StreamElementState,
        is_new: bool,
        is_final: bool,
        audio: ElementAudioDTO | None = None,
        audio_segments: list[dict[str, Any]] | None = None,
    ) -> RunElementSSEMessageDTO:
        return self._element_message(
            self._build_stream_element(
                state=state,
                role=role,
                stream_state=stream_state,
                is_new=is_new,
                is_final=is_final,
                audio=audio,
                audio_segments=audio_segments,
            )
        )

    def _build_stream_element(
        self,
        *,
        state: BlockState,
        role: str,
        stream_state: StreamElementState,
        is_new: bool,
        is_final: bool,
        audio: ElementAudioDTO | None = None,
        audio_segments: list[dict[str, Any]] | None = None,
    ) -> ElementDTO:
        payload = _payload_from_stream_element(
            stream_state.element_type,
            stream_state.content_text,
            audio=audio,
        )
        return ElementDTO(
            event_type="element",
            element_bid=stream_state.element_bid,
            generated_block_bid=state.generated_block_bid,
            element_index=stream_state.element_index,
            role=role,
            element_type=stream_state.element_type,
            element_type_code=_element_type_code(stream_state.element_type),
            change_type=_change_type_for_element(stream_state.element_type),
            target_element_bid=None if is_new else stream_state.element_bid,
            is_new=is_new,
            is_renderable=_default_is_renderable(stream_state.element_type),
            is_marker=_default_is_marker(stream_state.element_type),
            is_speakable=_normalized_is_speakable(
                stream_state.element_type,
                stream_state.content_text,
                stored_is_speakable=bool(audio is not None or audio_segments),
            ),
            audio_url=audio.audio_url if audio is not None else "",
            audio_segments=_prepare_audio_segments_for_element(
                audio_segments,
                is_final=is_final,
            ),
            is_navigable=1,
            is_final=is_final,
            content_text=stream_state.content_text,
            payload=payload,
        )

    def _handle_formatted_content(
        self, event: RunMarkdownFlowDTO, parts: list[tuple[str, str, int]]
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        state = self._ensure_block_state(generated_block_bid)
        meta = self._load_block_meta(generated_block_bid)
        for chunk_content, stream_type, stream_number in parts:
            if not chunk_content:
                continue
            state.raw_content += chunk_content
            previous_active_key = state.last_stream_element_key
            normalized_stream_type = (stream_type or "").strip().lower()
            active_key = state.active_stream_element_key_by_number.get(stream_number)
            stream_state = (
                state.stream_elements.get(active_key)
                if active_key is not None
                else None
            )
            slot_was_interrupted = stream_state is not None and active_key not in (
                None,
                state.last_stream_element_key,
            )
            same_mdflow_stream = (
                stream_state is not None
                and not slot_was_interrupted
                and stream_state.stream_type == normalized_stream_type
            )
            try:
                incoming_element_type = ElementType(normalized_stream_type)
            except ValueError:
                incoming_element_type = ElementType.TEXT
            stream_element_type = (
                stream_state.element_type
                if same_mdflow_stream
                else incoming_element_type
            )
            if stream_state is None or slot_was_interrupted or not same_mdflow_stream:
                if slot_was_interrupted:
                    stream_state = None
                    active_key = None
                self._max_element_index += 1
                stream_state = StreamElementState(
                    number=stream_number,
                    element_bid=_new_element_bid(self.app),
                    element_index=max(self._max_element_index, 0),
                    element_type=stream_element_type,
                    stream_type=normalized_stream_type,
                )
                stream_key = f"{stream_number}:{len(state.stream_elements)}"
                state.stream_elements[stream_key] = stream_state
                state.active_stream_element_key_by_number[stream_number] = stream_key
                active_key = stream_key
            is_new = _mdflow_new_stream_is_new(stream_element_type)
            stream_state.content_text += chunk_content
            pending_audio = None
            pending_audio_segments = None
            if is_new:
                pending_audio, pending_audio_segments = (
                    _resolve_pending_audio_for_stream_element(
                        state,
                        stream_state,
                    )
                )
                if (
                    previous_active_key is not None
                    and previous_active_key != active_key
                ):
                    yield self._make_inter_element_done_message(generated_block_bid)
            if pending_audio is None and pending_audio_segments is None:
                pending_audio, pending_audio_segments = (
                    _resolve_stream_audio_for_element_bid(
                        state,
                        stream_state.element_bid,
                    )
                )
            state.last_stream_element_key = active_key
            yield self._build_stream_element_message(
                state=state,
                role=meta.role,
                stream_state=stream_state,
                is_new=is_new,
                is_final=False,
                audio=pending_audio,
                audio_segments=pending_audio_segments,
            )

    def _retire_stream_elements(
        self, state: BlockState, *, emit_notification: bool = True
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not state.stream_elements:
            return
        target_bids = [item.element_bid for item in state.stream_elements.values()]
        self._deactivate_active_element_rows(
            generated_block_bid=state.generated_block_bid,
            element_bids=target_bids,
        )
        for target_bid in target_bids:
            self._forget_latest_element_snapshot(target_bid)
        if not emit_notification:
            return
        meta = self._load_block_meta(state.generated_block_bid)
        for stream_state in state.stream_elements.values():
            yield self._make_retire_element_message(
                generated_block_bid=state.generated_block_bid,
                element_bid=stream_state.element_bid,
                element_index=stream_state.element_index,
                role=meta.role,
                element_type=stream_state.element_type,
            )

    def _finalize_stream_elements(
        self, state: BlockState, *, emit: bool = True
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not state.stream_elements:
            return
        meta = self._load_block_meta(state.generated_block_bid)
        for stream_state in state.stream_elements.values():
            audio, audio_segments = _resolve_stream_audio_for_element_bid(
                state,
                stream_state.element_bid,
            )
            element = self._build_stream_element(
                state=state,
                role=meta.role,
                stream_state=stream_state,
                is_new=_mdflow_new_stream_is_new(stream_state.element_type),
                is_final=True,
                audio=audio,
                audio_segments=audio_segments,
            )
            if emit:
                yield self._element_message(element)
            else:
                self._persist_element(element)

    def _handle_content(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        ask_element_bid = self._resolve_ask_element_bid_for_block(
            generated_block_bid,
            bind_current=True,
        )
        if ask_element_bid:
            state = self._ensure_block_state(generated_block_bid)
            state.raw_content += str(event.content or "")
            answer_element = self._build_answer_element_from_state(
                generated_block_bid,
                is_final=False,
            )
            if answer_element is not None:
                yield self._stream_only_element_message(answer_element)
            return

        formatted_parts = self._formatted_parts_from_event(event)
        if formatted_parts:
            yield from self._handle_formatted_content(event, formatted_parts)
            return
        state = self._ensure_block_state(generated_block_bid)
        state.raw_content += str(event.content or "")
        meta = self._load_block_meta(generated_block_bid)
        yield self._element_message(self._build_fallback_element(state, meta.role))

    def _handle_audio_complete(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        content = event.content
        if not isinstance(content, AudioCompleteDTO):
            yield self._non_element_message(
                event_type=GeneratedType.AUDIO_COMPLETE.value,
                content=event.content,
                generated_block_bid=generated_block_bid,
            )
            return
        state = self._ensure_block_state(generated_block_bid)
        if isinstance(content.av_contract, dict):
            state.latest_av_contract = content.av_contract
        position = int(getattr(content, "position", 0) or 0)
        state.audio_by_position[position] = _make_audio_payload(content)
        finalized_audio_segments = _mark_last_audio_segment_final(
            state.audio_segments_by_position,
            position,
        )
        ask_element_bid = self._resolve_ask_element_bid_for_block(
            generated_block_bid,
            bind_current=True,
        )
        if ask_element_bid:
            if not self._state_machine.is_terminated:
                self._state_machine.feed(TypeInput.AUDIO_COMPLETE)
            return
        target_element_bid = None
        stream_element_number = getattr(content, "stream_element_number", None)
        if stream_element_number is not None:
            target_element_bid = _resolve_audio_target_element_bid_for_stream_number(
                state,
                stream_element_number,
                getattr(content, "stream_element_type", None),
            )
        if target_element_bid is None:
            target_element_bid = _resolve_audio_target_element_bid(state, position)
        if target_element_bid:
            state.audio_target_element_bid_by_position[position] = target_element_bid
        if target_element_bid and content.audio_url:
            self._backfill_audio_url(target_element_bid, content.audio_url)
            audio_payload = _make_audio_payload(content)
            patch_element = self._build_audio_patch_element(
                target_element_bid,
                audio_segments=finalized_audio_segments,
                is_final=True,
            )
            if patch_element is not None:
                patch_element.audio_url = content.audio_url
                payload = patch_element.payload or ElementPayloadDTO()
                payload.audio = audio_payload
                patch_element.payload = payload
                yield self._element_message(patch_element)
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.AUDIO_COMPLETE)

    def _handle_audio_segment(
        self, event: RunMarkdownFlowDTO
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        generated_block_bid = event.generated_block_bid or ""
        content = event.content
        if isinstance(content, AudioSegmentDTO):
            state = self._ensure_block_state(generated_block_bid)
            if isinstance(content.av_contract, dict):
                state.latest_av_contract = content.av_contract
            position = int(getattr(content, "position", 0) or 0)
            current_audio = state.audio_by_position.get(position)
            progressive_subtitle_cues = list(
                getattr(content, "subtitle_cues", []) or []
            )
            progressive_duration_ms = int(getattr(content, "duration_ms", 0) or 0)
            if progressive_subtitle_cues:
                progressive_duration_ms = int(
                    getattr(progressive_subtitle_cues[-1], "end_ms", 0)
                    or progressive_duration_ms
                )
            elif current_audio is not None:
                progressive_duration_ms = int(
                    getattr(current_audio, "duration_ms", 0) or progressive_duration_ms
                )
            state.audio_by_position[position] = ElementAudioDTO(
                audio_url=current_audio.audio_url if current_audio is not None else "",
                audio_bid=current_audio.audio_bid if current_audio is not None else "",
                duration_ms=progressive_duration_ms,
                position=position,
                subtitle_cues=(
                    progressive_subtitle_cues
                    if progressive_subtitle_cues
                    else list(getattr(current_audio, "subtitle_cues", []) or [])
                ),
            )
            segment_data = _audio_segment_payload(content)
            state.audio_segments_by_position[position] = _upsert_audio_segment_payload(
                state.audio_segments_by_position.get(position, []),
                segment_data,
            )
            ask_element_bid = self._resolve_ask_element_bid_for_block(
                generated_block_bid,
                bind_current=True,
            )
            if ask_element_bid:
                if not self._state_machine.is_terminated:
                    self._state_machine.feed(TypeInput.AUDIO_SEGMENT)
                return
            target_element_bid = None
            stream_element_number = getattr(content, "stream_element_number", None)
            if stream_element_number is not None:
                target_element_bid = (
                    _resolve_audio_target_element_bid_for_stream_number(
                        state,
                        stream_element_number,
                        getattr(content, "stream_element_type", None),
                    )
                )
            if target_element_bid is None:
                target_element_bid = _resolve_audio_target_element_bid(state, position)
            if target_element_bid:
                state.audio_target_element_bid_by_position[position] = (
                    target_element_bid
                )
                patch_message = self._build_audio_segment_patch_message(
                    target_element_bid,
                    audio_segments=[segment_data],
                    audio=state.audio_by_position.get(position),
                )
                if patch_message is not None:
                    yield patch_message
        if not self._state_machine.is_terminated:
            self._state_machine.feed(TypeInput.AUDIO_SEGMENT)

    def _finalize_block(
        self, generated_block_bid: str
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        if not generated_block_bid:
            return
        state = self._block_states.get(generated_block_bid)
        if state is None:
            return
        meta = self._load_block_meta(generated_block_bid)
        if state.stream_elements:
            yield from self._retire_fallback_element(state, emit_notification=False)
            yield from self._finalize_stream_elements(state, emit=True)
        else:
            visual_segments: list[VisualSegment] = []
            pos_to_seg_id: dict[int, str] = {}
            if (
                isinstance(state.latest_av_contract, dict)
                and (state.raw_content or "").strip()
            ):
                visual_segments, pos_to_seg_id = build_visual_segments_for_block(
                    app=self.app,
                    raw_content=state.raw_content or "",
                    generated_block_bid=generated_block_bid,
                    av_contract=state.latest_av_contract,
                    element_index_offset=max(self._max_element_index + 1, 0),
                )
                if not visual_segments:
                    visual_boundaries = (
                        state.latest_av_contract.get("visual_boundaries") or []
                    )
                    next_index = max(self._max_element_index + 1, 0)
                    for boundary in visual_boundaries:
                        if not isinstance(boundary, dict):
                            continue
                        source_span = normalize_source_span(boundary.get("source_span"))
                        if not source_span:
                            continue
                        visual_kind = str(boundary.get("kind", "") or "")
                        if not visual_kind:
                            continue
                        visual_segments.append(
                            VisualSegment(
                                segment_id=_new_element_bid(self.app),
                                generated_block_bid=generated_block_bid,
                                element_index=next_index,
                                audio_position=int(boundary.get("position", 0) or 0),
                                visual_kind=visual_kind,
                                segment_type="sandbox"
                                if visual_kind in {"iframe", "sandbox", "html_table"}
                                else "markdown",
                                segment_content=slice_source_by_span(
                                    state.raw_content, source_span
                                ),
                                source_span=source_span,
                                is_placeholder=False,
                            )
                        )
                        next_index += 1

            if visual_segments:
                yield from self._retire_fallback_element(
                    state,
                    emit_notification=True,
                )
                final_elements = _build_final_elements_for_av_contract(
                    app=self.app,
                    generated_block_bid=generated_block_bid,
                    role=meta.role,
                    raw_content=state.raw_content,
                    av_contract=state.latest_av_contract,
                    visual_segments=visual_segments,
                    audio_by_position=state.audio_by_position,
                    audio_segments_by_position=state.audio_segments_by_position,
                    position_to_segment_id=pos_to_seg_id,
                    element_index_offset=max(self._max_element_index + 1, 0),
                )
                for element in final_elements:
                    self._max_element_index = max(
                        self._max_element_index, element.element_index
                    )
                    yield self._element_message(element)
            elif state.fallback_element_bid:
                default_audio_position = _pick_default_audio_position(
                    state.audio_by_position,
                    state.audio_segments_by_position,
                )
                default_audio = (
                    state.audio_by_position.get(default_audio_position)
                    if default_audio_position is not None
                    else None
                )
                element = ElementDTO(
                    event_type="element",
                    element_bid=state.fallback_element_bid,
                    generated_block_bid=generated_block_bid,
                    element_index=max(self._max_element_index, 0),
                    role=meta.role,
                    element_type=ElementType.TEXT,
                    element_type_code=_element_type_code(ElementType.TEXT),
                    change_type=_change_type_for_element(ElementType.TEXT),
                    target_element_bid=None,
                    is_new=True,
                    is_renderable=False,
                    is_marker=False,
                    is_navigable=1,
                    is_final=True,
                    is_speakable=_default_is_speakable(
                        ElementType.TEXT,
                        state.raw_content,
                    ),
                    audio_url=default_audio.audio_url
                    if default_audio is not None
                    else "",
                    audio_segments=(
                        state.audio_segments_by_position.get(default_audio_position, [])
                        if default_audio_position is not None
                        else []
                    ),
                    content_text=state.raw_content,
                    payload=ElementPayloadDTO(audio=default_audio, previous_visuals=[]),
                )
                self._persist_element(element)
        self._block_states.pop(generated_block_bid, None)
