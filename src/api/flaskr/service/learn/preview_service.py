import inspect
import json
from decimal import Decimal
from typing import Dict, Generator, Iterable, Optional, Tuple

from flask import Flask
from markdown_flow import MarkdownFlow, ProcessMode
from markdown_flow.enums import BlockType as MFBlockType
from markdown_flow.llm import LLMResult

from flaskr.api.langfuse import langfuse_client as langfuse
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.dao import redis_client
from flaskr.service.learn.context_v2 import RUNLLMProvider
from flaskr.service.shifu.shifu_struct_manager import get_shifu_struct
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.learn.learn_dtos import (
    PlaygroundPreviewRequest,
    PreviewContentSSEData,
    PreviewInteractionSSEData,
    PreviewSSEMessage,
    PreviewSSEMessageType,
    PreviewTextEndSSEData,
)
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)


class MarkdownFlowPreviewService:
    """Service that renders MarkdownFlow blocks using LLM, emulating playground behavior."""

    def __init__(self, app: Flask):
        self.app = app

    def stream_preview(
        self,
        *,
        preview_request: PlaygroundPreviewRequest,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
        session_id: str,
    ) -> Generator[PreviewSSEMessage, None, None]:
        outline = self._get_outline_record(shifu_bid, outline_bid)
        # Preview is a Draft editing feature, always prioritize DraftShifu configuration
        # Falls back to PublishedShifu if DraftShifu doesn't exist (backward compatible)
        shifu = self._get_shifu_record(shifu_bid, True)
        document_prompt = self._resolve_document_prompt(
            preview_request, outline, shifu, shifu_bid, outline_bid
        )
        self.app.logger.info(
            "preview document prompt | shifu_bid=%s | outline_bid=%s | prompt=%s",
            shifu_bid,
            outline_bid,
            (document_prompt or "").strip(),
        )
        model, temperature = self._resolve_llm_settings(preview_request, outline, shifu)
        document = preview_request.get_document() or (
            outline.content if outline else ""
        )
        if not document:
            raise ValueError("Markdown-Flow content is empty")

        stored_context = (
            []
            if preview_request.block_index == 0
            else self._load_cached_context(user_bid, outline_bid)
        )
        request_context = self._convert_context_to_dict(preview_request.context)
        if preview_request.block_index == 0:
            self._clear_cached_context(user_bid, outline_bid)
        effective_context = self._merge_contexts(list(stored_context), request_context)
        user_message = self._format_user_input(preview_request.user_input)
        assistant_chunks: list[str] = []

        trace_args = {
            "user_id": user_bid,
            "name": "preview_outline_block",
            "metadata": {
                "shifu_bid": shifu_bid,
                "outline_bid": outline_bid,
                "session_id": session_id,
            },
        }
        trace = langfuse.trace(**trace_args)
        provider = RUNLLMProvider(
            self.app,
            LLMSettings(model=model, temperature=temperature),
            trace,
            trace_args,
        )

        final_payload = preview_request.model_dump()
        final_payload["content"] = document
        final_payload["document_prompt"] = document_prompt
        final_payload["model"] = model
        final_payload["temperature"] = temperature
        self.app.logger.info(
            "preview final payload | shifu_bid=%s | outline_bid=%s | user_bid=%s | payload=%s",
            shifu_bid,
            outline_bid,
            user_bid,
            json.dumps(final_payload, ensure_ascii=False),
        )

        mf = MarkdownFlow(
            document=document,
            llm_provider=provider,
            document_prompt=document_prompt,
            interaction_prompt=preview_request.interaction_prompt,
            interaction_error_prompt=preview_request.interaction_error_prompt,
        ).set_output_language(get_markdownflow_output_language())

        block_index = preview_request.block_index
        result = mf.process(
            block_index=block_index,
            mode=ProcessMode.STREAM,
            context=effective_context or None,
            variables=preview_request.variables,
            user_input=preview_request.user_input,
        )
        current_block = mf.get_block(block_index)
        is_user_input_validation = bool(preview_request.user_input)

        if inspect.isgenerator(result):
            for chunk in result:
                message = self._convert_to_sse_message(
                    chunk,
                    False,
                    current_block,
                    is_user_input_validation,
                    block_index,
                )
                if message:
                    if message.type == PreviewSSEMessageType.CONTENT:
                        assistant_chunks.append(message.data.mdflow)
                    yield message
                    if message.type == PreviewSSEMessageType.INTERACTION:
                        break
            yield self._convert_to_sse_message(
                LLMResult(content=""),
                True,
                current_block,
                is_user_input_validation,
                block_index,
            )
        else:
            message = self._convert_to_sse_message(
                result,
                False,
                current_block,
                is_user_input_validation,
                block_index,
            )
            if message:
                if message.type == PreviewSSEMessageType.CONTENT:
                    assistant_chunks.append(message.data.mdflow)
                yield message
            yield self._convert_to_sse_message(
                LLMResult(content=""),
                True,
                current_block,
                is_user_input_validation,
                block_index,
            )
        assistant_response = "".join(assistant_chunks).strip()
        updated_context = list(effective_context or [])
        if user_message:
            self._append_message(updated_context, "user", user_message)
        if assistant_response:
            self._append_message(updated_context, "assistant", assistant_response)
        if updated_context:
            self._save_cached_context(user_bid, outline_bid, updated_context)
        else:
            self._clear_cached_context(user_bid, outline_bid)
        trace.update(**trace_args)

    def _context_cache_key(self, user_bid: str, outline_bid: str) -> str:
        prefix = self.app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
        return f"{prefix}:preview_context:{user_bid}:{outline_bid}"

    def _load_cached_context(
        self, user_bid: str, outline_bid: str
    ) -> list[Dict[str, str]]:
        if not redis_client:
            return []
        try:
            cache_key = self._context_cache_key(user_bid, outline_bid)
            raw = redis_client.get(cache_key)
            if not raw:
                return []
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            merged: list[Dict[str, str]] = []
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    role = item.get("role")
                    content = item.get("content")
                    self._append_message(
                        merged,
                        role if isinstance(role, str) else "",
                        content if isinstance(content, str) else "",
                    )
            return merged
        except Exception:
            self.app.logger.warning("preview context load failed", exc_info=True)
            return []

    def _save_cached_context(
        self, user_bid: str, outline_bid: str, context: list[Dict[str, str]]
    ) -> None:
        if not redis_client:
            return
        try:
            cache_key = self._context_cache_key(user_bid, outline_bid)
            redis_client.setex(
                cache_key,
                3600,
                json.dumps(context, ensure_ascii=False),
            )
        except Exception:
            self.app.logger.warning("preview context save failed", exc_info=True)

    def _clear_cached_context(self, user_bid: str, outline_bid: str) -> None:
        if not redis_client:
            return
        try:
            redis_client.delete(self._context_cache_key(user_bid, outline_bid))
        except Exception:
            self.app.logger.warning("preview context clear failed", exc_info=True)

    def _merge_contexts(
        self,
        stored_context: Optional[list[Dict[str, str]]],
        incoming_context: Optional[list[Dict[str, str]]],
    ) -> list[Dict[str, str]]:
        merged: list[Dict[str, str]] = []
        for msg in stored_context or []:
            self._append_message(
                merged,
                str(msg.get("role", "") or ""),
                str(msg.get("content", "") or ""),
            )
        for msg in incoming_context or []:
            self._append_message(
                merged,
                str(msg.get("role", "") or ""),
                str(msg.get("content", "") or ""),
            )
        return merged

    def _append_message(
        self, messages: list[Dict[str, str]], role: str, content: str
    ) -> None:
        if not role or not content:
            return
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()
        if not content:
            return
        if messages and messages[-1].get("role") == role:
            messages[-1]["content"] = (
                messages[-1].get("content", "") + "\n" + content
            ).strip()
            return
        messages.append({"role": role, "content": content})

    def _format_user_input(self, user_input: Optional[Dict[str, list[str]]]) -> str:
        if not user_input:
            return ""
        if isinstance(user_input, dict):
            parts = []
            for key, values in user_input.items():
                if values is None:
                    continue
                if isinstance(values, list):
                    cleaned = [str(v) for v in values if v is not None]
                    if not cleaned:
                        continue
                    parts.append(f"{key}: {', '.join(cleaned)}")
                else:
                    parts.append(f"{key}: {values}")
            return "\n".join(parts).strip()
        return str(user_input).strip()

    def _convert_to_sse_message(
        self,
        llm_result: Optional[LLMResult],
        finished: bool,
        current_block,
        is_user_input_validation: bool,
        block_index: int,
    ) -> PreviewSSEMessage | None:
        if finished:
            return PreviewSSEMessage(
                generated_block_bid=str(block_index),
                type=PreviewSSEMessageType.TEXT_END,
                data=PreviewTextEndSSEData(),
            )

        content = ""
        if llm_result is None:
            content = ""
        else:
            if hasattr(llm_result, "content"):
                content = llm_result.content or ""
            else:
                content = str(llm_result)

        is_interaction_block = bool(
            current_block
            and hasattr(current_block, "block_type")
            and (
                current_block.block_type == MFBlockType.INTERACTION
                or getattr(llm_result, "transformed_to_interaction", False)
            )
        )

        if is_interaction_block:
            if is_user_input_validation:
                if content.strip():
                    return PreviewSSEMessage(
                        generated_block_bid=str(block_index),
                        type=PreviewSSEMessageType.CONTENT,
                        data=PreviewContentSSEData(mdflow=content),
                    )
                return None

            # Use translated content from LLM if available, otherwise fallback to original
            rendered_content = content or getattr(current_block, "content", "")
            variable_name = (
                current_block.variables[0]
                if getattr(current_block, "variables", None)
                else "user_input"
            )
            return PreviewSSEMessage(
                generated_block_bid=str(block_index),
                type=PreviewSSEMessageType.INTERACTION,
                data=PreviewInteractionSSEData(
                    mdflow=rendered_content,
                    variable=variable_name,
                ),
            )

        if not content:
            return None

        return PreviewSSEMessage(
            generated_block_bid=str(block_index),
            type=PreviewSSEMessageType.CONTENT,
            data=PreviewContentSSEData(mdflow=content),
        )

    def _resolve_document_prompt(
        self,
        preview_request: PlaygroundPreviewRequest,
        outline: Optional[DraftOutlineItem | PublishedOutlineItem],
        shifu: Optional[DraftShifu | PublishedShifu],
        shifu_bid: str,
        outline_bid: str,
    ) -> Optional[str]:
        if preview_request.document_prompt:
            prompt = preview_request.document_prompt.strip()
            if prompt:
                return prompt

        prompt = self._resolve_prompt_from_outline_chain(
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            outline_record=outline,
        )
        if prompt:
            return prompt

        if shifu:
            prompt = (getattr(shifu, "llm_system_prompt", None) or "").strip()
            if prompt:
                return prompt
        return None

    def _resolve_prompt_from_outline_chain(
        self,
        shifu_bid: str,
        outline_bid: str,
        outline_record: Optional[DraftOutlineItem | PublishedOutlineItem],
    ) -> Optional[str]:
        target_bid = outline_record.outline_item_bid if outline_record else outline_bid
        if not target_bid:
            return None

        preferred_is_draft = isinstance(outline_record, DraftOutlineItem)
        visited_bids = set()

        if outline_record:
            prompt = (outline_record.llm_system_prompt or "").strip()
            if prompt:
                return prompt
            visited_bids.add(outline_record.outline_item_bid)

        hierarchy_records = self._load_outline_hierarchy_records(
            shifu_bid=shifu_bid,
            outline_bid=target_bid,
            prefer_draft=preferred_is_draft,
        )
        for record in hierarchy_records:
            if not record or record.outline_item_bid in visited_bids:
                continue
            prompt = (record.llm_system_prompt or "").strip()
            if prompt:
                return prompt
            visited_bids.add(record.outline_item_bid)
        return None

    def _load_outline_hierarchy_records(
        self,
        shifu_bid: str,
        outline_bid: str,
        prefer_draft: bool,
    ) -> list[DraftOutlineItem | PublishedOutlineItem]:
        records: list[DraftOutlineItem | PublishedOutlineItem] = []
        struct_modes = (
            [prefer_draft, not prefer_draft]
            if prefer_draft in (True, False)
            else [True, False]
        )
        # ensure unique boolean list
        struct_modes = list(dict.fromkeys(struct_modes))

        for is_preview in struct_modes:
            try:
                struct = get_shifu_struct(self.app, shifu_bid, is_preview)
            except Exception:
                continue
            path = find_node_with_parents(struct, outline_bid)
            if not path:
                continue
            path = list(reversed(path))
            outline_ids = [item.id for item in path if item.type == "outline"]
            if not outline_ids:
                continue
            outline_model = DraftOutlineItem if is_preview else PublishedOutlineItem
            outline_items = outline_model.query.filter(
                outline_model.id.in_(outline_ids),
                outline_model.deleted == 0,
            ).all()
            outline_map = {item.id: item for item in outline_items}
            for oid in outline_ids:
                record = outline_map.get(oid)
                if record:
                    records.append(record)
            if records:
                break
        return records

    def _resolve_llm_settings(
        self,
        preview_request: PlaygroundPreviewRequest,
        outline: Optional[DraftOutlineItem | PublishedOutlineItem],
        shifu: Optional[DraftShifu | PublishedShifu],
    ) -> Tuple[str, float]:
        model_candidates = [
            preview_request.model,
            getattr(shifu, "llm", None) if shifu else None,
            self.app.config.get("DEFAULT_LLM_MODEL"),
        ]
        temperature_candidates = [
            preview_request.temperature,
            self._decimal_to_float(getattr(shifu, "llm_temperature", None))
            if shifu
            else None,
            float(self.app.config.get("DEFAULT_LLM_TEMPERATURE")),
        ]

        model = next((m for m in model_candidates if m), None)
        temperature = next(
            (t for t in temperature_candidates if t is not None),
            float(self.app.config.get("DEFAULT_LLM_TEMPERATURE")),
        )

        if not model:
            raise ValueError("LLM model is not configured")

        return model, float(temperature)

    def _get_outline_record(
        self, shifu_bid: str, outline_bid: str
    ) -> Optional[DraftOutlineItem | PublishedOutlineItem]:
        outline = (
            DraftOutlineItem.query.filter(
                DraftOutlineItem.shifu_bid == shifu_bid,
                DraftOutlineItem.outline_item_bid == outline_bid,
                DraftOutlineItem.deleted == 0,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if outline:
            return outline
        return (
            PublishedOutlineItem.query.filter(
                PublishedOutlineItem.shifu_bid == shifu_bid,
                PublishedOutlineItem.outline_item_bid == outline_bid,
                PublishedOutlineItem.deleted == 0,
            )
            .order_by(PublishedOutlineItem.id.desc())
            .first()
        )

    def _get_shifu_record(
        self, shifu_bid: str, has_draft_outline: bool
    ) -> Optional[DraftShifu | PublishedShifu]:
        if has_draft_outline:
            shifu = (
                DraftShifu.query.filter(
                    DraftShifu.shifu_bid == shifu_bid, DraftShifu.deleted == 0
                )
                .order_by(DraftShifu.id.desc())  # Always get the latest version
                .first()
            )
            if shifu:
                return shifu
        return (
            PublishedShifu.query.filter(
                PublishedShifu.shifu_bid == shifu_bid,
                PublishedShifu.deleted == 0,
            )
            .order_by(PublishedShifu.id.desc())  # Always get the latest version
            .first()
        )

    def _convert_context_to_dict(
        self, context: Optional[Iterable[Dict[str, str]]]
    ) -> Optional[list[Dict[str, str]]]:
        if not context:
            return None
        filtered: list[Dict[str, str]] = []
        for msg in context:
            role = msg.get("role")
            content = msg.get("content", "")
            if not role or not content or not content.strip():
                continue
            filtered.append({"role": role, "content": content})
        return filtered or None

    def _decimal_to_float(self, value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
