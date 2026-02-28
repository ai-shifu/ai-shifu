import hashlib
import inspect
import json
import queue
import threading
from decimal import Decimal
from enum import Enum
from typing import Generator, Iterable, Optional, Union
from flaskr.service.learn.const import (
    ROLE_STUDENT,
    ROLE_TEACHER,
    CONTEXT_INTERACTION_NEXT,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
)
from markdown_flow import (
    MarkdownFlow,
    ProcessMode,
    LLMProvider,
    BlockType,
    InteractionParser,
    replace_variables_in_text,
)
from markdown_flow.llm import LLMResult
from flask import Flask
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.dao import db
from flaskr.service.shifu.shifu_struct_manager import (
    ShifuOutlineItemDto,
    ShifuInfoDto,
    OutlineItemDtoWithMdflow,
    get_shifu_struct,
    get_outline_item_dto_with_mdflow,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    PublishedOutlineItem,
    DraftShifu,
    PublishedShifu,
)
from flaskr.service.learn.models import LearnProgressRecord, LearnGeneratedBlock
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from langfuse.client import StatefulTraceClient
from ...api.langfuse import langfuse_client as langfuse, MockClient
from flaskr.service.common import raise_error, raise_error_with_args
from flaskr.service.order.consts import (
    LEARN_STATUS_RESET,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_LOCKED,
)
from flaskr.service.shifu.consts import (
    UNIT_TYPE_VALUE_TRIAL,
    UNIT_TYPE_VALUE_NORMAL,
)

from flaskr.service.user.repository import UserAggregate
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.util import generate_id
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.profile.constants import SYS_USER_LANGUAGE
from flaskr.service.learn.learn_dtos import (
    PlaygroundPreviewRequest,
    PreviewContentSSEData,
    PreviewInteractionSSEData,
    PreviewSSEMessage,
    PreviewSSEMessageType,
    PreviewTextEndSSEData,
    RunMarkdownFlowDTO,
    GeneratedType,
    OutlineItemUpdateDTO,
    LearnStatus,
)
from flaskr.api.llm import chat_llm, get_allowed_models, get_current_models
from flaskr.service.learn.handle_input_ask import handle_input_ask
from flaskr.service.profile.funcs import save_user_profiles, ProfileToSave
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
    ProfileItemDefinition,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.learn.learn_dtos import VariableUpdateDTO
from flaskr.service.learn.check_text import check_text_with_llm_response
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.langfuse_naming import (
    build_langfuse_generation_name,
    build_langfuse_trace_name,
)
from flaskr.service.learn.utils_v2 import init_generated_block
from flaskr.service.learn.exceptions import PaidException
from flaskr.i18n import _, get_current_language, set_language
from flaskr.service.user.exceptions import UserNotLoginException

context_local = threading.local()


class RunType(Enum):
    INPUT = "input"
    OUTPUT = "output"


class RunScriptInfo:
    attend: LearnProgressRecord
    outline_bid: str
    block_position: int
    mdflow: str

    def __init__(
        self,
        attend: LearnProgressRecord,
        outline_bid: str,
        block_position: int,
        mdflow: str,
    ):
        self.attend = attend
        self.outline_bid = outline_bid
        self.block_position = block_position
        self.mdflow = mdflow


class RUNLLMProvider(LLMProvider):
    app: Flask
    llm_settings: LLMSettings
    trace: StatefulTraceClient
    trace_args: dict
    usage_context: UsageContext
    usage_scene: int

    def __init__(
        self,
        app: Flask,
        llm_settings: LLMSettings,
        trace: StatefulTraceClient,
        trace_args: dict,
        usage_context: UsageContext,
        usage_scene: int,
    ):
        self.app = app
        self.llm_settings = llm_settings
        self.trace = trace
        self.trace_args = trace_args
        self.usage_context = usage_context
        self.usage_scene = usage_scene

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        # Extract the last message content as the main prompt
        if not messages:
            raise ValueError("No messages provided")
        # Use provided model/temperature or fall back to settings
        actual_model = model or self.llm_settings.model
        actual_temperature = (
            temperature if temperature is not None else self.llm_settings.temperature
        )
        metadata = self.trace_args.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        chapter_title = metadata.get("chapter_title", "")
        scene = metadata.get("scene", "lesson_runtime")
        generation_name = build_langfuse_generation_name(
            chapter_title,
            scene,
            "run_llm",
        )

        res = chat_llm(
            self.app,
            self.trace_args.get("user_id", ""),
            self.trace,
            messages=messages,
            model=actual_model,
            stream=False,
            generation_name=generation_name,
            temperature=actual_temperature,
            usage_context=self.usage_context,
            usage_scene=self.usage_scene,
        )
        # Collect all stream responses and concatenate the results
        content_parts = []
        for response in res:
            if response.result:
                content_parts.append(response.result)
        return "".join(content_parts)

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Generator[str, None, None]:
        # Extract the last message content as the main prompt
        if not messages:
            raise ValueError("No messages provided")

        # system_prompt = messages[0].get("content", "")
        # Get the last message content
        # last_message = messages[-1]
        # prompt = last_message.get("content", "")

        # Use provided model/temperature or fall back to settings
        actual_model = model or self.llm_settings.model
        actual_temperature = (
            temperature if temperature is not None else self.llm_settings.temperature
        )
        metadata = self.trace_args.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        chapter_title = metadata.get("chapter_title", "")
        scene = metadata.get("scene", "lesson_runtime")
        generation_name = build_langfuse_generation_name(
            chapter_title,
            scene,
            "run_llm",
        )

        # Check if there's a system message
        self.app.logger.info("stream invoke_llm begin")
        res = chat_llm(
            self.app,
            self.trace_args["user_id"],
            self.trace,
            model=actual_model,
            messages=messages,
            stream=True,
            generation_name=generation_name,
            temperature=actual_temperature,
            usage_context=self.usage_context,
            usage_scene=self.usage_scene,
        )
        self.app.logger.info(f"stream invoke_llm res: {res}")
        first_result = False
        for i in res:
            if i.result:
                if not first_result:
                    first_result = True
                    self.app.logger.info(f"stream first result: {i.result}")
                yield i.result
        self.app.logger.info("stream invoke_llm end")


class MdflowContextV2:
    def __init__(
        self,
        *,
        document: str,
        document_prompt: Optional[str] = None,
        llm_provider: Optional[LLMProvider] = None,
        interaction_prompt: Optional[str] = None,
        interaction_error_prompt: Optional[str] = None,
        use_learner_language: bool = False,
        visual_mode: bool = True,
    ):
        self._mdflow = MarkdownFlow(
            document=document,
            llm_provider=llm_provider,
            document_prompt=document_prompt,
            interaction_prompt=interaction_prompt,
            interaction_error_prompt=interaction_error_prompt,
        )
        self._mdflow.set_visual_mode(visual_mode)
        # Only set output language if use_learner_language is enabled
        if use_learner_language:
            self._mdflow = self._mdflow.set_output_language(
                get_markdownflow_output_language()
            )

    def get_block(self, block_index: int):
        return self._mdflow.get_block(block_index)

    def get_all_blocks(self):
        return self._mdflow.get_all_blocks()

    def process(
        self,
        *,
        block_index: int,
        mode: ProcessMode,
        context: Optional[list[dict[str, str]]] = None,
        variables: Optional[dict] = None,
        user_input: Optional[dict[str, list[str]]] = None,
    ):
        return self._mdflow.process(
            block_index=block_index,
            mode=mode,
            context=context,
            variables=variables,
            user_input=user_input,
        )

    @staticmethod
    def normalize_context_messages(
        context: Optional[Iterable[dict[str, str]]],
    ) -> Optional[list[dict[str, str]]]:
        if not context:
            return None
        filtered: list[dict[str, str]] = []
        for msg in context:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = msg.get("content", "")
            if not role or not content or not str(content).strip():
                continue
            filtered.append({"role": role, "content": str(content)})
        return filtered or None

    @staticmethod
    def normalize_user_input_map(
        input_value: str | dict | list | None,
        default_key: str = "input",
    ) -> dict[str, list[str]]:
        if input_value is None:
            return {}
        if isinstance(input_value, dict):
            normalized = {}
            for key, raw in input_value.items():
                if raw is None:
                    continue
                if isinstance(raw, list):
                    cleaned = [str(item) for item in raw if item is not None]
                else:
                    cleaned = [str(raw)]
                if cleaned:
                    normalized[str(key)] = cleaned
            return normalized
        if isinstance(input_value, list):
            cleaned = [str(item) for item in input_value if item is not None]
            return {default_key: cleaned} if cleaned else {}
        return {default_key: [str(input_value)]}

    @staticmethod
    def flatten_user_input_map(
        user_input: Optional[dict[str, list[str]]],
    ) -> str:
        if not user_input:
            return ""
        values: list[str] = []
        for value in user_input.values():
            if isinstance(value, list):
                values.extend([str(item) for item in value if item is not None])
            elif value is not None:
                values.append(str(value))
        return ",".join(values)

    @staticmethod
    def build_context_from_blocks(
        blocks: Iterable["LearnGeneratedBlock"],
        document: str,
        variables: Optional[dict] = None,
    ) -> list[dict[str, str]]:
        message_list: list[dict[str, str]] = []
        mdflow_context = MdflowContextV2(document=document)
        block_list = mdflow_context.get_all_blocks()

        from flask import current_app

        current_app.logger.info(f"build_context_from_blocks variables: {variables}")

        for generated_block in blocks:
            if (
                generated_block.type == BLOCK_TYPE_MDCONTENT_VALUE
                and generated_block.position < len(block_list)
            ):
                block = block_list[generated_block.position]
                message_list.append(
                    {
                        "role": "user",
                        "content": replace_variables_in_text(
                            block.content or "", variables
                        )
                        or "",
                    }
                )
                message_list.append(
                    {
                        "role": "assistant",
                        "content": generated_block.generated_content or "",
                    }
                )
        return message_list


class _PreviewContextStore:
    _DEFAULT_TTL_SECONDS = 30 * 60

    def __init__(
        self,
        app: Flask,
        user_bid: str,
        shifu_bid: str,
        outline_bid: str,
        ttl_seconds: Optional[int] = None,
    ):
        self._cache = cache_provider
        self._ttl_seconds = ttl_seconds or self._DEFAULT_TTL_SECONDS
        prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
        self._key = f"{prefix}:preview_context:{user_bid}:{shifu_bid}:{outline_bid}"

    def _hash_document(self, document: str) -> str:
        if not document:
            return ""
        return hashlib.sha256(document.encode("utf-8")).hexdigest()

    def load(self) -> dict:
        try:
            raw = self._cache.get(self._key)
            if raw is None:
                return {}
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def save(self, payload: dict) -> None:
        try:
            value = json.dumps(payload, ensure_ascii=False)
            self._cache.setex(self._key, self._ttl_seconds, value)
        except Exception:
            return

    def clear(self) -> None:
        try:
            self._cache.delete(self._key)
        except Exception:
            return

    def get_context(self, document: str, block_index: int) -> list[dict[str, str]]:
        payload = self.load()
        if not payload:
            return []
        if block_index == 0:
            self.clear()
            return []
        doc_hash = payload.get("document_hash")
        if document and doc_hash and doc_hash != self._hash_document(document):
            self.clear()
            return []
        context = payload.get("context")
        if not isinstance(context, list):
            return []
        return [item for item in context if isinstance(item, dict)]

    def replace_context(self, document: str, context: list[dict[str, str]]) -> None:
        payload = {
            "context": context,
            "document_hash": self._hash_document(document),
        }
        self.save(payload)

    def append_context(self, document: str, messages: list[dict[str, str]]) -> None:
        if not messages:
            return
        payload = self.load()
        context = payload.get("context")
        if not isinstance(context, list):
            context = []
        context.extend(messages)
        self.save(
            {
                "context": context,
                "document_hash": self._hash_document(document),
            }
        )


class RunScriptPreviewContextV2:
    """MarkdownFlow preview using context v2 logic with optional Redis caching."""

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

        chapter_title = getattr(outline, "title", "") or outline_bid
        trace_scene = "lesson_preview"
        trace_args = {
            "user_id": user_bid,
            "name": build_langfuse_trace_name(chapter_title, trace_scene),
            "metadata": {
                "shifu_bid": shifu_bid,
                "outline_bid": outline_bid,
                "session_id": session_id,
                "scene": trace_scene,
                "chapter_title": chapter_title,
            },
        }
        trace = langfuse.trace(**trace_args)
        usage_context = UsageContext(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )
        provider = RUNLLMProvider(
            self.app,
            LLMSettings(model=model, temperature=temperature),
            trace,
            trace_args,
            usage_context,
            BILL_USAGE_SCENE_PREVIEW,
        )

        resolved_variables = self._resolve_preview_variables(
            preview_request=preview_request,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
        )
        preview_language = resolved_variables.get(SYS_USER_LANGUAGE)
        original_language = get_current_language()
        restore_language = (
            bool(preview_language) and preview_language != original_language
        )
        if restore_language:
            set_language(preview_language)

        try:
            final_payload = preview_request.model_dump()
            final_payload["content"] = document
            final_payload["document_prompt"] = document_prompt
            final_payload["model"] = model
            final_payload["temperature"] = temperature
            final_payload["variables"] = resolved_variables
            self.app.logger.info(
                "preview final payload | shifu_bid=%s | outline_bid=%s | user_bid=%s | payload=%s",
                shifu_bid,
                outline_bid,
                user_bid,
                json.dumps(final_payload, ensure_ascii=False),
            )

            context_store = _PreviewContextStore(
                self.app, user_bid, shifu_bid, outline_bid
            )
            request_context = MdflowContextV2.normalize_context_messages(
                preview_request.context
            )
            if request_context is None:
                context_messages = context_store.get_context(
                    document, preview_request.block_index
                )
            else:
                context_messages = request_context
                context_store.replace_context(document, request_context)

            mdflow_context = MdflowContextV2(
                document=document,
                llm_provider=provider,
                document_prompt=document_prompt,
                interaction_prompt=preview_request.interaction_prompt,
                interaction_error_prompt=preview_request.interaction_error_prompt,
                use_learner_language=bool(getattr(shifu, "use_learner_language", 0)),
            )

            block_index = preview_request.block_index
            current_block = mdflow_context.get_block(block_index)
            is_user_input_validation = bool(preview_request.user_input)
            content_chunks: list[str] = []

            mode = ProcessMode.STREAM
            user_input = preview_request.user_input
            if (
                current_block
                and current_block.block_type == BlockType.INTERACTION
                and not is_user_input_validation
            ):
                mode = ProcessMode.COMPLETE
                user_input = None

            result = mdflow_context.process(
                block_index=block_index,
                mode=mode,
                context=context_messages or None,
                variables=resolved_variables,
                user_input=user_input,
            )

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
                            content_chunks.append(message.data.mdflow)
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
                        content_chunks.append(message.data.mdflow)
                    yield message

                yield self._convert_to_sse_message(
                    LLMResult(content=""),
                    True,
                    current_block,
                    is_user_input_validation,
                    block_index,
                )

            current_block_content = ""
            if current_block:
                current_block_content = (
                    replace_variables_in_text(
                        current_block.content or "", resolved_variables
                    )
                    or ""
                )
            self._update_preview_context(
                context_store,
                document,
                preview_request,
                content_chunks,
                current_block_content,
            )
            trace.update(**trace_args)
        finally:
            if restore_language:
                set_language(original_language)

    def _update_preview_context(
        self,
        context_store: _PreviewContextStore,
        document: str,
        preview_request: PlaygroundPreviewRequest,
        content_chunks: list[str],
        current_block_content: str,
    ) -> None:
        new_messages: list[dict[str, str]] = []
        user_input_text = MdflowContextV2.flatten_user_input_map(
            preview_request.user_input
        )
        content_text = "".join(content_chunks).strip()
        if content_text:
            user_message = user_input_text or current_block_content
            if user_message:
                new_messages.append({"role": "user", "content": user_message})
            new_messages.append({"role": "assistant", "content": content_text})
        elif user_input_text:
            new_messages.append({"role": "user", "content": user_input_text})
        if not new_messages:
            return
        context_store.append_context(document, new_messages)

    def _resolve_preview_variables(
        self,
        *,
        preview_request: PlaygroundPreviewRequest,
        user_bid: str,
        shifu_bid: str,
    ) -> Optional[dict]:
        variables = (
            dict(preview_request.variables)
            if isinstance(preview_request.variables, dict)
            else {}
        )
        return variables

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
                current_block.block_type == BlockType.INTERACTION
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
    ) -> tuple[str, float]:
        def _normalize_model(value: object | None) -> str | None:
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        allowed_models = get_allowed_models()
        allowlist_enabled = bool(allowed_models)
        allowed_available_models: list[str] = []
        if allowlist_enabled:
            allowed_available_models = [
                option.get("model", "")
                for option in get_current_models(self.app)
                if option.get("model")
            ]

        model_candidates: list[tuple[str, str | None]] = [
            ("request", _normalize_model(preview_request.model)),
            (
                "outline",
                _normalize_model(getattr(outline, "llm", None)) if outline else None,
            ),
            ("shifu", _normalize_model(getattr(shifu, "llm", None)) if shifu else None),
            ("default", _normalize_model(self.app.config.get("DEFAULT_LLM_MODEL"))),
        ]
        temperature_candidates = [
            preview_request.temperature,
            self._decimal_to_float(getattr(outline, "llm_temperature", None))
            if outline
            else None,
            self._decimal_to_float(getattr(shifu, "llm_temperature", None))
            if shifu
            else None,
            float(self.app.config.get("DEFAULT_LLM_TEMPERATURE")),
        ]

        model_source = "unset"
        model = None
        for source, candidate in model_candidates:
            if not candidate:
                continue
            if allowlist_enabled and candidate not in allowed_models:
                if source == "request":
                    raise_error_with_args(
                        "server.llm.modelNotSupported", model=candidate
                    )
                continue
            model = candidate
            model_source = source
            break

        if allowlist_enabled and not model:
            if allowed_available_models:
                model = allowed_available_models[0]
                model_source = "allowlist"
            else:
                raise ValueError("No allowed LLM models are available")

        temperature = next(
            (t for t in temperature_candidates if t is not None),
            float(self.app.config.get("DEFAULT_LLM_TEMPERATURE")),
        )

        if not model:
            raise ValueError("LLM model is not configured")

        self.app.logger.info(
            "preview resolved llm settings | model=%s | temperature=%s | source=%s",
            model,
            temperature,
            model_source,
        )
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
                .order_by(DraftShifu.id.desc())
                .first()
            )
            if shifu:
                return shifu
        return (
            PublishedShifu.query.filter(
                PublishedShifu.shifu_bid == shifu_bid,
                PublishedShifu.deleted == 0,
            )
            .order_by(PublishedShifu.id.desc())
            .first()
        )

    def _decimal_to_float(self, value) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


class RunScriptContextV2:
    user_id: str
    attend_id: str
    is_paid: bool

    preview_mode: bool
    _q: queue.Queue
    _outline_item_info: ShifuOutlineItemDto
    _struct: HistoryItem
    _user_info: UserAggregate
    _is_paid: bool
    _preview_mode: bool
    _listen: bool
    _shifu_ids: list[str]
    _run_type: RunType
    _app: Flask
    _shifu_model: Union[DraftShifu, PublishedShifu]
    _outline_model: Union[DraftOutlineItem, PublishedOutlineItem]
    _trace_args: dict
    _shifu_info: ShifuInfoDto
    _trace: Union[StatefulTraceClient, MockClient]
    _input_type: str
    _input: str
    _can_continue: bool
    _last_position: int

    def __init__(
        self,
        app: Flask,
        shifu_info: ShifuInfoDto,
        struct: HistoryItem,
        outline_item_info: ShifuOutlineItemDto,
        user_info: UserAggregate,
        is_paid: bool,
        preview_mode: bool,
        listen: bool = False,
    ):
        self._last_position = -1
        self.app = app
        self._struct = struct
        self._outline_item_info = outline_item_info
        self._user_info = user_info
        self._is_paid = is_paid
        self._listen = listen
        self._preview_mode = preview_mode
        self._shifu_info = shifu_info
        self.shifu_ids = []
        self.outline_item_ids = []
        self.current_outline_item = None
        self._run_type = RunType.INPUT
        self._can_continue = True
        self._listen_slide_index_cursor = 0

        if preview_mode:
            self._outline_model = DraftOutlineItem
            self._shifu_model = DraftShifu
        else:
            self._outline_model = PublishedOutlineItem
            self._shifu_model = PublishedShifu
        # get current attend
        self._q = queue.Queue()
        self._q.put(struct)
        while not self._q.empty():
            item = self._q.get()
            if item.bid == outline_item_info.bid:
                self._current_outline_item = item
                break
            if item.children:
                for child in item.children:
                    self._q.put(child)
        self._current_attend = None
        self._trace_args = {}
        chapter_title = self._outline_item_info.title
        trace_scene = "lesson_preview_runtime" if preview_mode else "lesson_runtime"
        self._trace_args["user_id"] = user_info.user_id
        self._trace_args["input"] = ""
        self._trace_args["name"] = build_langfuse_trace_name(chapter_title, trace_scene)
        self._trace_args["metadata"] = {
            "scene": trace_scene,
            "chapter_title": chapter_title,
            "outline_item_bid": self._outline_item_info.bid,
            "shifu_bid": self._outline_item_info.shifu_bid,
            "preview_mode": int(bool(preview_mode)),
        }
        self._trace = langfuse.trace(**self._trace_args)
        self._trace_args["output"] = ""
        context_local.current_context = self

    @staticmethod
    def get_current_context(app: Flask) -> Union["RunScriptContextV2", None]:
        if not hasattr(context_local, "current_context"):
            return None
        return context_local.current_context

    def _should_stream_tts(self) -> bool:
        return (not self._preview_mode) and bool(getattr(self, "_listen", False))

    def _get_current_attend(self, outline_bid: str) -> LearnProgressRecord:
        attend_info: LearnProgressRecord = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.outline_item_bid == outline_bid,
                LearnProgressRecord.user_bid == self._user_info.user_id,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            )
            .order_by(LearnProgressRecord.id.desc())
            .first()
        )
        if not attend_info:
            outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
                self._outline_model.query.filter(
                    self._outline_model.outline_item_bid == outline_bid,
                    self._outline_model.deleted == 0,
                )
                .order_by(self._outline_model.id.desc())
                .first()
            )
            if not outline_item_info_db:
                raise_error("server.shifu.lessonNotFoundInCourse")
            if outline_item_info_db.type == UNIT_TYPE_VALUE_NORMAL:
                if (not self._is_paid) and (not self._preview_mode):
                    raise PaidException()
            elif outline_item_info_db.type == UNIT_TYPE_VALUE_TRIAL:
                if (
                    not self._preview_mode
                    and not self._user_info.mobile
                    and not self._user_info.email
                ):
                    raise UserNotLoginException()
            parent_path = find_node_with_parents(self._struct, outline_bid)
            attend_info = None
            for item in parent_path:
                if item.type == "outline":
                    attend_info = LearnProgressRecord.query.filter(
                        LearnProgressRecord.outline_item_bid == item.bid,
                        LearnProgressRecord.user_bid == self._user_info.user_id,
                        LearnProgressRecord.status != LEARN_STATUS_RESET,
                    ).first()
                    if attend_info:
                        continue
                    attend_info = LearnProgressRecord()
                    attend_info.outline_item_bid = outline_item_info_db.outline_item_bid
                    attend_info.shifu_bid = outline_item_info_db.shifu_bid
                    attend_info.user_bid = self._user_info.user_id
                    attend_info.status = LEARN_STATUS_NOT_STARTED
                    attend_info.progress_record_bid = generate_id(self.app)
                    attend_info.block_position = 0
                    db.session.add(attend_info)
                    db.session.flush()
        return attend_info

    # outline is a leaf when has block item as children
    # outline is a node when has outline item as children
    # outline is a leaf when has no children
    def _is_leaf_outline_item(self, outline_item_info: ShifuOutlineItemDto) -> bool:
        if outline_item_info.children:
            if outline_item_info.children[0].type == "block":
                return True
            if outline_item_info.children[0].type == "outline":
                return False
        if outline_item_info.type == "outline":
            return True
        return False

    # get the outline items to start or complete
    def _get_next_outline_item(self) -> list[OutlineItemUpdateDTO]:
        res = []
        q = queue.Queue()
        q.put(self._struct)
        outline_ids = []
        while not q.empty():
            item: HistoryItem = q.get()
            if item.type == "outline":
                outline_ids.append(item.bid)
            if item.children:
                for child in item.children:
                    q.put(child)
        outline_item_info_db: list[tuple[str, bool, str]] = (
            db.session.query(
                self._outline_model.outline_item_bid,
                self._outline_model.hidden,
                self._outline_model.title,
            )
            .filter(
                self._outline_model.outline_item_bid.in_(outline_ids),
                self._outline_model.deleted == 0,
            )
            .all()
        )
        outline_item_hidden_map: dict[str, bool] = {
            bid: hidden for bid, hidden, _title in outline_item_info_db
        }
        outline_item_title_map: dict[str, str] = {
            bid: title for bid, _hidden, title in outline_item_info_db
        }

        def _mark_sub_node_completed(
            outline_item_info: HistoryItem, res: list[OutlineItemUpdateDTO]
        ):
            q = queue.Queue()
            q.put(self._struct)
            if self._is_leaf_outline_item(outline_item_info):
                res.append(
                    OutlineItemUpdateDTO(
                        outline_bid=outline_item_info.bid,
                        title=outline_item_title_map.get(outline_item_info.bid, ""),
                        status=LearnStatus.COMPLETED,
                        has_children=False,
                    )
                )
            else:
                res.append(
                    OutlineItemUpdateDTO(
                        outline_bid=outline_item_info.bid,
                        title=outline_item_title_map.get(outline_item_info.bid, ""),
                        status=LearnStatus.COMPLETED,
                        has_children=True,
                    )
                )
            while not q.empty():
                item: HistoryItem = q.get()
                if item.children and outline_item_info.bid in [
                    child.bid for child in item.children
                ]:
                    index = [child.bid for child in item.children].index(
                        outline_item_info.bid
                    )
                    while index < len(item.children) - 1:
                        # not sub node
                        current_node = item.children[index + 1]
                        if outline_item_hidden_map.get(current_node.bid, True):
                            index += 1
                            continue
                        while (
                            current_node.children
                            and current_node.children[0].type == "outline"
                        ):
                            res.append(
                                OutlineItemUpdateDTO(
                                    outline_bid=current_node.bid,
                                    title=outline_item_title_map.get(
                                        current_node.bid, ""
                                    ),
                                    status=LearnStatus.IN_PROGRESS,
                                    has_children=True,
                                )
                            )
                            current_node = current_node.children[0]
                        res.append(
                            OutlineItemUpdateDTO(
                                outline_bid=current_node.bid,
                                title=outline_item_title_map.get(current_node.bid, ""),
                                status=LearnStatus.IN_PROGRESS,
                                has_children=False,
                            )
                        )
                        return
                    if index == len(item.children) - 1 and item.type == "outline":
                        _mark_sub_node_completed(item, res)
                if item.children and item.children[0].type == "outline":
                    for child in item.children:
                        q.put(child)

        def _mark_sub_node_start(
            outline_item_info: HistoryItem, res: list[OutlineItemUpdateDTO]
        ):
            path = find_node_with_parents(self._struct, outline_item_info.bid)
            for item in path:
                if item.type == "outline":
                    if item.children and item.children[0].type == "outline":
                        res.append(
                            OutlineItemUpdateDTO(
                                outline_bid=item.bid,
                                title=outline_item_title_map.get(item.bid, ""),
                                status=LearnStatus.IN_PROGRESS,
                                has_children=True,
                            )
                        )
                    else:
                        res.append(
                            OutlineItemUpdateDTO(
                                outline_bid=item.bid,
                                title=outline_item_title_map.get(item.bid, ""),
                                status=LearnStatus.IN_PROGRESS,
                                has_children=False,
                            )
                        )

        if self._current_attend.block_position >= max(
            len(self._current_outline_item.children),
            self._current_outline_item.child_count,
        ):
            _mark_sub_node_completed(self._current_outline_item, res)
        if self._current_attend.status == LEARN_STATUS_NOT_STARTED:
            _mark_sub_node_start(self._current_outline_item, res)
        return res

    def _has_next_outline_item(
        self, outline_updates: list[OutlineItemUpdateDTO]
    ) -> bool:
        if not outline_updates:
            return False
        current_bid = (
            self._current_outline_item.bid if self._current_outline_item else ""
        )
        return any(
            update.status == LearnStatus.IN_PROGRESS
            and update.outline_bid != current_bid
            for update in outline_updates
        )

    def _get_current_outline_item(self) -> ShifuOutlineItemDto:
        return self._current_outline_item

    def _render_outline_updates(
        self, outline_updates: list[OutlineItemUpdateDTO], new_chapter: bool = False
    ) -> Generator[str, None, None]:
        shifu_bids = [o.outline_bid for o in outline_updates]
        outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
            self._outline_model.query.filter(
                self._outline_model.outline_item_bid.in_(shifu_bids),
                self._outline_model.deleted == 0,
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
                self._current_outline_item = self._get_outline_struct(
                    update.outline_bid
                )
                if self._current_attend.outline_item_bid == update.outline_bid:
                    self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                    self._current_attend.outline_item_updated = 0
                    self._current_attend.block_position = 0
                    yield RunMarkdownFlowDTO(
                        outline_bid=update.outline_bid,
                        generated_block_bid="",
                        type=GeneratedType.OUTLINE_ITEM_UPDATE,
                        content=update,
                    )
                    db.session.flush()
                    continue
                self._current_attend = self._get_current_attend(update.outline_bid)
                if (
                    self._current_attend.status == LEARN_STATUS_NOT_STARTED
                    or self._current_attend.status == LEARN_STATUS_LOCKED
                ):
                    self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                    self._current_attend.block_position = 0
                    db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )
            elif (not update.has_children) and update.status == LearnStatus.COMPLETED:
                current_attend = self._get_current_attend(update.outline_bid)
                current_attend.status = LEARN_STATUS_COMPLETED
                self._current_attend = current_attend
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
                current_attend = self._get_current_attend(update.outline_bid)
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
                current_attend = self._get_current_attend(update.outline_bid)
                current_attend.status = LEARN_STATUS_COMPLETED
                db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )

    def _emit_next_chapter_interaction(
        self,
        progress_record: LearnProgressRecord,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Persist and emit the standardized `_sys_next_chapter` interaction when a lesson
        completes so the frontend can advance automatically.
        """
        if not progress_record or not self._outline_item_info:
            return

        button_label = _("server.learn.nextChapterButton")
        button_md = f"?[{button_label}//{CONTEXT_INTERACTION_NEXT}]"
        existing_block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid
                == progress_record.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid
                == progress_record.outline_item_bid,
                LearnGeneratedBlock.user_bid == self._user_info.user_id,
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
            self.app,
            shifu_bid=progress_record.shifu_bid,
            outline_item_bid=progress_record.outline_item_bid,
            progress_record_bid=progress_record.progress_record_bid,
            user_bid=self._user_info.user_id,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            mdflow=button_md,
            block_index=progress_record.block_position,
        )
        generated_block.role = ROLE_TEACHER
        generated_block.block_content_conf = button_md
        db.session.add(generated_block)
        db.session.flush()
        yield RunMarkdownFlowDTO(
            outline_bid=progress_record.outline_item_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=button_md,
        )

    def _get_default_llm_settings(self) -> LLMSettings:
        return LLMSettings(
            model=self.app.config.get("DEFAULT_LLM_MODEL"),
            temperature=float(self.app.config.get("DEFAULT_LLM_TEMPERATURE")),
        )

    def _has_effective_input(self) -> bool:
        input_value = self._input
        if input_value is None:
            return False
        if isinstance(input_value, dict):
            for raw in input_value.values():
                values = raw if isinstance(raw, list) else [raw]
                for value in values:
                    if value is None:
                        continue
                    if str(value).strip():
                        return True
            return False
        if isinstance(input_value, list):
            for value in input_value:
                if value is None:
                    continue
                if str(value).strip():
                    return True
            return False
        return bool(str(input_value).strip())

    def set_input(self, input: str | dict, input_type: str):
        """
        Set user input.

        Args:
            input: User input, can be:
                   - str: legacy format (e.g., "Python")
                   - dict: new format from markdown-flow 0.2.27+ (e.g., {"lang": ["Python"]})
            input_type: Input type
        """
        self._trace_args["input"] = input
        self._trace_args["input_type"] = input_type
        self._input_type = input_type
        self._input = input

    def _get_outline_struct(self, outline_item_id: str) -> HistoryItem:
        q = queue.Queue()
        q.put(self._struct)
        outline_struct = None
        while not q.empty():
            item = q.get()
            if item.bid == outline_item_id:
                outline_struct = item
                break
            if item.children:
                for child in item.children:
                    q.put(child)
        return outline_struct

    def _get_run_script_info(
        self, attend: LearnProgressRecord, is_ask: bool = False
    ) -> RunScriptInfo:
        outline_item_id = attend.outline_item_bid
        outline_item_info: OutlineItemDtoWithMdflow = get_outline_item_dto_with_mdflow(
            self.app, outline_item_id, self._preview_mode
        )

        mdflow_context = MdflowContextV2(document=outline_item_info.mdflow)
        block_list = mdflow_context.get_all_blocks()
        self.app.logger.info(
            f"attend position: {attend.block_position} blocks:{len(block_list)}"
        )
        if attend.block_position >= len(block_list) and not is_ask:
            return None
        return RunScriptInfo(
            attend=attend,
            outline_bid=outline_item_info.outline_bid,
            block_position=attend.block_position,
            mdflow=outline_item_info.mdflow,
        )

    def _get_run_script_info_by_block_id(self, block_id: str) -> RunScriptInfo:
        generate_block: LearnGeneratedBlock = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == block_id,
            LearnGeneratedBlock.deleted == 0,
        ).first()
        if not generate_block:
            raise_error("server.shifu.lessonNotFoundInCourse")
        outline_item_info: OutlineItemDtoWithMdflow = get_outline_item_dto_with_mdflow(
            self.app, generate_block.outline_item_bid, self._preview_mode
        )
        attend: LearnProgressRecord = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == self._user_info.user_id,
            LearnProgressRecord.shifu_bid == outline_item_info.shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_item_info.bid,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).first()
        return RunScriptInfo(
            attend=attend,
            outline_bid=outline_item_info.outline_bid,
            block_position=generate_block.position,
            mdflow=outline_item_info.mdflow,
        )

    def run_inner(self, app: Flask) -> Generator[RunMarkdownFlowDTO, None, None]:
        self._current_attend = self._get_current_attend(self._outline_item_info.bid)
        app.logger.info(
            f"run_context.run {self._current_attend.block_position} {self._current_attend.status}"
        )
        self._trace_args["session_id"] = self._current_attend.progress_record_bid
        outline_updates = self._get_next_outline_item()
        if len(outline_updates) > 0 and self._input_type != "ask":
            yield from self._render_outline_updates(outline_updates, new_chapter=False)
            db.session.flush()
            self._current_attend = self._get_current_attend(self._outline_item_info.bid)
            if self._current_attend.status not in [
                LEARN_STATUS_IN_PROGRESS,
                LEARN_STATUS_NOT_STARTED,
            ]:
                app.logger.info(
                    f"current_attend.status != LEARN_STATUS_IN_PROGRESS To False,current_attend.status: {self._current_attend.status}"
                )
                self._can_continue = False
                return

        run_script_info: RunScriptInfo = self._get_run_script_info(
            self._current_attend, is_ask=self._input_type == "ask"
        )
        if run_script_info is None:
            self.app.logger.warning("run script is none")
            outline_updates = self._get_next_outline_item()
            if self._has_next_outline_item(outline_updates):
                yield from self._emit_next_chapter_interaction(self._current_attend)
            self._can_continue = False
            if len(outline_updates) > 0:
                yield from self._render_outline_updates(
                    outline_updates, new_chapter=True
                )
                self._can_continue = False
                db.session.flush()
            return
        llm_settings = self.get_llm_settings(run_script_info.outline_bid)
        system_prompt = self.get_system_prompt(run_script_info.outline_bid)

        if self._input_type == "ask":
            if self._last_position == -1:
                self._last_position = run_script_info.block_position
            ask_input = self._input
            app.logger.info(f"ask_input: {ask_input}")
            if isinstance(ask_input, dict):
                ask_input = ask_input.get("input", "")
            else:
                ask_input = ask_input
            if isinstance(ask_input, list):
                ask_input = ",".join(ask_input)
            app.logger.info(f"ask_input: {ask_input}")
            res = handle_input_ask(
                app,
                self,
                self._user_info,
                self._current_attend.progress_record_bid,
                ask_input,
                self._outline_item_info,
                self._trace_args,
                self._trace,
                self._preview_mode,
                self._last_position,
            )
            yield from res
            self._can_continue = False
            db.session.flush()
            return
        generated_blocks: list[LearnGeneratedBlock] = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.user_bid == self._user_info.user_id,
                LearnGeneratedBlock.shifu_bid == run_script_info.attend.shifu_bid,
                LearnGeneratedBlock.progress_record_bid
                == self._current_attend.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid == run_script_info.outline_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.type.in_(
                    [BLOCK_TYPE_MDCONTENT_VALUE, BLOCK_TYPE_MDINTERACTION_VALUE]
                ),
            )
            .order_by(LearnGeneratedBlock.position.asc(), LearnGeneratedBlock.id.asc())
            .all()
        )

        usage_scene = (
            BILL_USAGE_SCENE_PREVIEW if self._preview_mode else BILL_USAGE_SCENE_PROD
        )
        usage_context = UsageContext(
            user_bid=self._user_info.user_id,
            shifu_bid=self._outline_item_info.shifu_bid,
            outline_item_bid=run_script_info.outline_bid,
            progress_record_bid=self._current_attend.progress_record_bid,
            usage_scene=usage_scene,
        )
        mdflow_context = MdflowContextV2(
            document=run_script_info.mdflow,
            document_prompt=system_prompt,
            llm_provider=RUNLLMProvider(
                app,
                llm_settings,
                self._trace,
                self._trace_args,
                usage_context,
                usage_scene,
            ),
            use_learner_language=self._shifu_info.use_learner_language,
            visual_mode=self._listen,
        )
        block_list = mdflow_context.get_all_blocks()
        user_profile = get_user_profiles(
            app, self._user_info.user_id, self._outline_item_info.shifu_bid
        )
        message_list = MdflowContextV2.build_context_from_blocks(
            generated_blocks, run_script_info.mdflow, user_profile
        )

        variable_definition: list[ProfileItemDefinition] = (
            get_profile_item_definition_list(app, self._outline_item_info.shifu_bid)
        )
        variable_definition_key_id_map: dict[str, str] = {
            p.profile_key: p.profile_id for p in variable_definition
        }

        if run_script_info.block_position >= len(block_list):
            outline_updates = self._get_next_outline_item()
            if len(outline_updates) > 0:
                yield from self._render_outline_updates(
                    outline_updates, new_chapter=True
                )
                self._can_continue = False
                db.session.flush()
            return
        block = block_list[run_script_info.block_position]
        app.logger.info(f"block: {block}")
        app.logger.info(f"self._run_type: {self._run_type}")
        has_effective_input = self._has_effective_input()
        if self._run_type == RunType.INPUT:
            if block.block_type != BlockType.INTERACTION:
                if has_effective_input:
                    pending_interaction_block: LearnGeneratedBlock | None = (
                        LearnGeneratedBlock.query.filter(
                            LearnGeneratedBlock.progress_record_bid
                            == run_script_info.attend.progress_record_bid,
                            LearnGeneratedBlock.outline_item_bid
                            == run_script_info.outline_bid,
                            LearnGeneratedBlock.user_bid == self._user_info.user_id,
                            LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
                            LearnGeneratedBlock.status == 1,
                            LearnGeneratedBlock.deleted == 0,
                            LearnGeneratedBlock.position
                            >= run_script_info.block_position,
                            LearnGeneratedBlock.generated_content == "",
                        )
                        .order_by(
                            LearnGeneratedBlock.position.asc(),
                            LearnGeneratedBlock.id.asc(),
                        )
                        .first()
                    )
                    if pending_interaction_block:
                        app.logger.warning(
                            "Input received on non-interaction block. Realign index to pending interaction: progress=%s outline=%s from=%s to=%s generated_block=%s",
                            run_script_info.attend.progress_record_bid,
                            run_script_info.outline_bid,
                            run_script_info.block_position,
                            pending_interaction_block.position,
                            pending_interaction_block.generated_block_bid,
                        )
                        self._current_attend.block_position = (
                            pending_interaction_block.position
                        )
                        self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                        self._run_type = RunType.INPUT
                        self._can_continue = True
                        db.session.flush()
                        return
                self._can_continue = True
                self._run_type = RunType.OUTPUT
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                db.session.flush()
                return
            interaction_parser: InteractionParser = InteractionParser()
            parsed_interaction = interaction_parser.parse(block.content)
            generated_block: LearnGeneratedBlock = (
                LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.progress_record_bid
                    == run_script_info.attend.progress_record_bid,
                    LearnGeneratedBlock.outline_item_bid == run_script_info.outline_bid,
                    LearnGeneratedBlock.user_bid == self._user_info.user_id,
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
                    LearnGeneratedBlock.position == run_script_info.block_position,
                    LearnGeneratedBlock.status == 1,
                )
                .order_by(LearnGeneratedBlock.id.desc())
                .first()
            )
            if (
                parsed_interaction.get("buttons")
                and len(parsed_interaction.get("buttons")) > 0
            ):
                for button in parsed_interaction.get("buttons"):
                    if button.get("value") == "_sys_pay":
                        if not self._is_paid:
                            # Use translated content from database if available
                            interaction_content = (
                                generated_block.block_content_conf
                                if generated_block
                                and generated_block.block_content_conf
                                else block.content
                            )
                            yield RunMarkdownFlowDTO(
                                outline_bid=run_script_info.outline_bid,
                                generated_block_bid=generated_block.generated_block_bid
                                if generated_block
                                else generate_id(app),
                                type=GeneratedType.INTERACTION,
                                content=interaction_content,
                            )
                            self._can_continue = False
                            db.session.flush()
                            return
                        else:
                            self._can_continue = True
                            self._current_attend.block_position += 1
                            self._run_type = RunType.OUTPUT
                            db.session.flush()
                            return
                    if button.get("value") == "_sys_login":
                        if bool(self._user_info.mobile):
                            self._can_continue = True
                            self._current_attend.block_position += 1
                            self._run_type = RunType.OUTPUT
                            db.session.flush()
                            return
                        else:
                            # Use translated content from database if available
                            interaction_content = (
                                generated_block.block_content_conf
                                if generated_block
                                and generated_block.block_content_conf
                                else block.content
                            )
                            yield RunMarkdownFlowDTO(
                                outline_bid=run_script_info.outline_bid,
                                generated_block_bid=generated_block.generated_block_bid
                                if generated_block
                                else generate_id(app),
                                type=GeneratedType.INTERACTION,
                                content=interaction_content,
                            )
                            self._can_continue = False
                            db.session.flush()
                            return
            if not generated_block:
                generated_block = init_generated_block(
                    app,
                    shifu_bid=run_script_info.attend.shifu_bid,
                    outline_item_bid=run_script_info.outline_bid,
                    progress_record_bid=run_script_info.attend.progress_record_bid,
                    user_bid=self._user_info.user_id,
                    block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
                    mdflow=block.content,
                    block_index=run_script_info.block_position,
                )
                app.logger.info(
                    f"generated_block not found, init new one: {generated_block.generated_block_bid}"
                )

                # Render interaction content with translation (INPUT mode, no cached block)
                # Note: Do NOT pass variables here - we only want translation, not variable replacement
                interaction_result = mdflow_context.process(
                    block_index=run_script_info.block_position,
                    mode=ProcessMode.COMPLETE,
                    context=message_list,
                    variables=user_profile,
                )
                rendered_content = (
                    interaction_result.content if interaction_result else block.content
                )

                # Store translated interaction block for future retrieval
                generated_block.block_content_conf = rendered_content
                # Keep generated_content empty, will be filled with user input later
                generated_block.generated_content = ""
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=rendered_content,
                )
                self._can_continue = False
                db.session.add(generated_block)
                db.session.flush()
                return
            expected_variable = (parsed_interaction.get("variable") or "input").strip()
            if not expected_variable:
                expected_variable = "input"

            user_input_param = MdflowContextV2.normalize_user_input_map(
                self._input, expected_variable
            )
            # Backward compatible: some clients may still send `{input: [...]}` or a single
            # unnamed key even when the interaction expects a specific variable.
            if expected_variable and expected_variable not in user_input_param:
                if "input" in user_input_param and len(user_input_param) == 1:
                    app.logger.warning(
                        "Remap interaction input key 'input' -> '%s'", expected_variable
                    )
                    user_input_param = {expected_variable: user_input_param["input"]}
                elif len(user_input_param) == 1:
                    only_key, only_values = next(iter(user_input_param.items()))
                    if only_values:
                        app.logger.warning(
                            "Remap interaction input key '%s' -> '%s'",
                            only_key,
                            expected_variable,
                        )
                        user_input_param = {expected_variable: only_values}

            generated_block.generated_content = MdflowContextV2.flatten_user_input_map(
                user_input_param
            )
            generated_block.role = ROLE_STUDENT
            generated_block.position = run_script_info.block_position
            # For STUDENT records, also store translated interaction block
            # (in case this record is returned instead of TEACHER record)
            interaction_result = mdflow_context.process(
                block_index=run_script_info.block_position,
                mode=ProcessMode.COMPLETE,
                context=message_list,
                variables=user_profile,
            )
            generated_block.block_content_conf = (
                interaction_result.content if interaction_result else block.content
            )
            generated_block.status = 1
            db.session.flush()
            trace_metadata = self._trace_args.get("metadata") or {}
            if not isinstance(trace_metadata, dict):
                trace_metadata = {}
            chapter_title = trace_metadata.get(
                "chapter_title",
                self._outline_item_info.title,
            )
            trace_scene = trace_metadata.get("scene", "lesson_runtime")
            res = check_text_with_llm_response(
                app,
                user_info=self._user_info,
                log_script=generated_block,
                input=generated_block.generated_content,  # Use converted string value
                span=self._trace,
                outline_item_bid=self._outline_item_info.bid,
                shifu_bid=self._outline_item_info.shifu_bid,
                block_position=run_script_info.block_position,
                llm_settings=llm_settings,
                attend_id=self._current_attend.progress_record_bid,
                fmt_prompt="",
                usage_context=usage_context,
                chapter_title=chapter_title,
                scene=f"{trace_scene}_interaction",
            )
            # Check if the generator yields any content (not None)
            has_content = False
            for i in res:
                if i is not None and i != "":
                    self.app.logger.info(f"check_text_with_llm_response: {i}")
                    has_content = True
                    yield RunMarkdownFlowDTO(
                        outline_bid=run_script_info.outline_bid,
                        generated_block_bid=generated_block.generated_block_bid,
                        type=GeneratedType.CONTENT,
                        content=i,
                    )

            if has_content:
                self._can_continue = False
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.BREAK,
                    content="",
                )

                # Render interaction content with translation after risk check
                # Note: Do NOT pass variables here - we only want translation, not variable replacement
                interaction_result = mdflow_context.process(
                    block_index=run_script_info.block_position,
                    mode=ProcessMode.COMPLETE,
                    context=message_list,
                    variables=user_profile,
                )
                rendered_content = (
                    interaction_result.content if interaction_result else block.content
                )

                # Store translated interaction block for future retrieval
                generated_block.block_content_conf = rendered_content
                # Keep generated_content empty, will be filled with user input later
                generated_block.generated_content = ""
                generated_block.generated_block_bid = generate_id(app)
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=rendered_content,
                )

                db.session.flush()
                return
            if not parsed_interaction.get("variable"):
                self._can_continue = True
                self._run_type = RunType.OUTPUT
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                self._current_attend.block_position = run_script_info.block_position + 1
                db.session.flush()
                return
            validate_result = mdflow_context.process(
                block_index=run_script_info.block_position,
                mode=ProcessMode.COMPLETE,
                user_input=user_input_param,
                context=message_list,
                variables=user_profile,
            )

            if (
                validate_result.variables is not None
                and len(validate_result.variables) > 0
            ):
                profile_to_save: list[ProfileToSave] = []
                for key, value in validate_result.variables.items():
                    profile_id = variable_definition_key_id_map.get(key, "")
                    # Convert list to string (markdown-flow 0.2.27+ returns list[str] for multi-select)
                    if isinstance(value, list):
                        # Filter out None and convert to string
                        value_str = ",".join(
                            [str(item) for item in value if item is not None]
                        )
                    else:
                        value_str = str(value) if value is not None else ""
                    profile_to_save.append(ProfileToSave(key, value_str, profile_id))

                save_user_profiles(
                    app,
                    self._user_info.user_id,
                    self._outline_item_info.shifu_bid,
                    profile_to_save,
                )
                # Commit profile changes before sending VARIABLE_UPDATE events,
                # so frontend updates always reflect persisted data.
                db.session.commit()
                for profile in profile_to_save:
                    yield RunMarkdownFlowDTO(
                        outline_bid=run_script_info.outline_bid,
                        generated_block_bid=generated_block.generated_block_bid,
                        type=GeneratedType.VARIABLE_UPDATE,
                        content=VariableUpdateDTO(
                            variable_name=profile.key,
                            variable_value=profile.value,
                        ),
                    )
                self._can_continue = True
                self._current_attend.block_position = run_script_info.block_position + 1
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                self._run_type = RunType.OUTPUT
                self.app.logger.warning(
                    f"passed and position: {self._current_attend.block_position}"
                )
                db.session.flush()
                return
            else:
                generated_block: LearnGeneratedBlock = init_generated_block(
                    app,
                    shifu_bid=run_script_info.attend.shifu_bid,
                    outline_item_bid=run_script_info.outline_bid,
                    progress_record_bid=run_script_info.attend.progress_record_bid,
                    user_bid=self._user_info.user_id,
                    block_type=BLOCK_TYPE_MDERRORMESSAGE_VALUE,
                    mdflow=block.content,
                    block_index=block.index,
                )
                generated_block.type = BLOCK_TYPE_MDERRORMESSAGE_VALUE
                generated_block.block_content_conf = block.content
                generated_block.role = ROLE_TEACHER
                db.session.add(generated_block)
                db.session.flush()
                content = ""
                error_content = getattr(validate_result, "content", "")
                if isinstance(error_content, str):
                    error_chunks = [error_content] if error_content else []
                elif inspect.isgenerator(error_content):
                    error_chunks = error_content
                elif isinstance(error_content, (list, tuple)):
                    error_chunks = [
                        str(item) for item in error_content if item is not None
                    ]
                elif error_content:
                    error_chunks = [str(error_content)]
                else:
                    error_chunks = []

                for chunk in error_chunks:
                    if chunk is None:
                        continue
                    chunk_str = str(chunk)
                    if not chunk_str:
                        continue
                    content += chunk_str
                    yield RunMarkdownFlowDTO(
                        outline_bid=run_script_info.outline_bid,
                        generated_block_bid=generated_block.generated_block_bid,
                        type=GeneratedType.CONTENT,
                        content=chunk_str,
                    )
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.BREAK,
                    content="",
                )
                generated_block.generated_content = content
                generated_block.type = BLOCK_TYPE_MDERRORMESSAGE_VALUE
                generated_block.block_content_conf = block.content
                db.session.add(generated_block)
                db.session.flush()
                generated_block: LearnGeneratedBlock = init_generated_block(
                    app,
                    shifu_bid=run_script_info.attend.shifu_bid,
                    outline_item_bid=run_script_info.outline_bid,
                    progress_record_bid=run_script_info.attend.progress_record_bid,
                    user_bid=self._user_info.user_id,
                    block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
                    mdflow=block.content,
                    block_index=block.index,
                )
                generated_block.role = ROLE_TEACHER
                db.session.add(generated_block)
                db.session.flush()

                # Render interaction content with translation after validation error
                # Note: Do NOT pass variables here - we only want translation, not variable replacement
                interaction_result = mdflow_context.process(
                    block_index=run_script_info.block_position,
                    mode=ProcessMode.COMPLETE,
                    context=message_list,
                    variables=user_profile,
                )
                rendered_content = (
                    interaction_result.content if interaction_result else block.content
                )

                # Store translated interaction block for future retrieval
                generated_block.block_content_conf = rendered_content
                # Keep generated_content empty, will be filled with user input later
                generated_block.generated_content = ""
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=rendered_content,
                )
                self._can_continue = False
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                db.session.add(generated_block)
                db.session.flush()
        elif self._run_type == RunType.OUTPUT:
            generated_block: LearnGeneratedBlock = init_generated_block(
                app,
                shifu_bid=run_script_info.attend.shifu_bid,
                outline_item_bid=run_script_info.outline_bid,
                progress_record_bid=run_script_info.attend.progress_record_bid,
                user_bid=self._user_info.user_id,
                block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
                mdflow=block.content,
                block_index=block.index,
            )
            if block.block_type == BlockType.INTERACTION:
                interaction_parser: InteractionParser = InteractionParser()
                parsed_interaction = interaction_parser.parse(block.content)
                if (
                    parsed_interaction.get("buttons")
                    and len(parsed_interaction.get("buttons")) > 0
                ):
                    for button in parsed_interaction.get("buttons"):
                        if button.get("value") == "_sys_pay":
                            if self._is_paid:
                                self._can_continue = True
                                self._current_attend.block_position += 1
                                self._run_type = RunType.OUTPUT
                                db.session.flush()
                                return
                        if button.get("value") == "_sys_login":
                            self.app.logger.warning(
                                f"_sys_login :{self._user_info.mobile}"
                            )
                            if bool(self._user_info.mobile):
                                self._can_continue = True
                                self._current_attend.block_position += 1
                                self._run_type = RunType.OUTPUT
                                db.session.flush()
                                return

                # Render interaction content with translation (markdown-flow 0.2.34+)
                # Call process() without user_input to trigger interaction rendering
                # Note: Do NOT pass variables here - we only want translation, not variable replacement
                app.logger.info(f"render_interaction: {run_script_info.block_position}")

                interaction_result = mdflow_context.process(
                    block_index=run_script_info.block_position,
                    mode=ProcessMode.COMPLETE,
                    context=message_list,
                    variables=user_profile,
                )

                # Get rendered interaction content
                rendered_content = (
                    interaction_result.content if interaction_result else block.content
                )

                generated_block.type = BLOCK_TYPE_MDINTERACTION_VALUE
                # Store translated interaction block for future retrieval
                generated_block.block_content_conf = rendered_content
                # Keep generated_content empty, will be filled with user input later
                generated_block.generated_content = ""
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=rendered_content,
                )
                self._can_continue = False
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                db.session.add(generated_block)
                db.session.flush()
            else:
                # Guard against replaying the same fixed-output block right after
                # processing an interaction input in the same request.
                if has_effective_input:
                    existing_content_block: LearnGeneratedBlock | None = (
                        LearnGeneratedBlock.query.filter(
                            LearnGeneratedBlock.progress_record_bid
                            == run_script_info.attend.progress_record_bid,
                            LearnGeneratedBlock.outline_item_bid
                            == run_script_info.outline_bid,
                            LearnGeneratedBlock.user_bid == self._user_info.user_id,
                            LearnGeneratedBlock.type == BLOCK_TYPE_MDCONTENT_VALUE,
                            LearnGeneratedBlock.position
                            == run_script_info.block_position,
                            LearnGeneratedBlock.status == 1,
                            LearnGeneratedBlock.deleted == 0,
                        )
                        .order_by(LearnGeneratedBlock.id.desc())
                        .first()
                    )
                    if existing_content_block:
                        app.logger.warning(
                            "Skip duplicated fixed output block: progress=%s outline=%s position=%s generated_block=%s",
                            run_script_info.attend.progress_record_bid,
                            run_script_info.outline_bid,
                            run_script_info.block_position,
                            existing_content_block.generated_block_bid,
                        )
                        self._can_continue = True
                        self._run_type = RunType.OUTPUT
                        self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                        self._current_attend.block_position += 1
                        db.session.flush()
                        return
                generated_block.type = BLOCK_TYPE_MDCONTENT_VALUE
                generated_content = ""
                tts_processor = None
                content_cache = ""

                # Direct synchronous stream processing (markdown-flow 0.2.27+)
                app.logger.info(f"process_stream: {run_script_info.block_position}")
                app.logger.info(f"variables: {user_profile}")

                if self._should_stream_tts():
                    try:
                        from flaskr.common.config import get_config
                        from flaskr.service.tts.streaming_tts import (
                            AVStreamingTTSProcessor,
                        )
                        from flaskr.service.tts.validation import (
                            validate_tts_settings_strict,
                        )

                        shifu_record = (
                            self._shifu_model.query.filter(
                                self._shifu_model.shifu_bid
                                == run_script_info.attend.shifu_bid,
                                self._shifu_model.deleted == 0,
                            )
                            .order_by(self._shifu_model.id.desc())
                            .first()
                        )

                        if shifu_record and getattr(shifu_record, "tts_enabled", False):
                            provider_raw = (
                                getattr(shifu_record, "tts_provider", "") or ""
                            )
                            provider_name = provider_raw.strip().lower()
                            if provider_name == "default":
                                provider_name = ""

                            try:
                                validated = validate_tts_settings_strict(
                                    provider=provider_name,
                                    model=(
                                        getattr(shifu_record, "tts_model", "") or ""
                                    ).strip(),
                                    voice_id=(
                                        getattr(shifu_record, "tts_voice_id", "") or ""
                                    ).strip(),
                                    speed=getattr(shifu_record, "tts_speed", None),
                                    pitch=getattr(shifu_record, "tts_pitch", None),
                                    emotion=(
                                        getattr(shifu_record, "tts_emotion", "") or ""
                                    ).strip(),
                                )
                            except Exception as exc:
                                app.logger.warning(
                                    "TTS settings invalid; skip streaming TTS: %s",
                                    exc,
                                )
                                validated = None

                            if validated:
                                max_segment_chars = get_config("TTS_MAX_SEGMENT_CHARS")
                                if not max_segment_chars:
                                    max_segment_chars = 300
                                tts_processor = AVStreamingTTSProcessor(
                                    app=app,
                                    generated_block_bid=generated_block.generated_block_bid,
                                    outline_bid=run_script_info.outline_bid,
                                    progress_record_bid=run_script_info.attend.progress_record_bid,
                                    user_bid=self._user_info.user_id,
                                    shifu_bid=run_script_info.attend.shifu_bid,
                                    voice_id=validated.voice_id,
                                    speed=validated.speed,
                                    pitch=validated.pitch,
                                    emotion=validated.emotion,
                                    max_segment_chars=int(max_segment_chars),
                                    tts_provider=validated.provider,
                                    tts_model=validated.model,
                                    slide_index_offset=self._listen_slide_index_cursor,
                                )
                                yield from tts_processor.emit_run_start_slide()
                    except Exception as exc:
                        app.logger.warning(
                            "Initialize streaming TTS failed: %s", exc, exc_info=True
                        )

                def _flush_content_cache(*, keep_tail: int = 0):
                    nonlocal content_cache
                    if not content_cache:
                        return
                    if keep_tail > 0 and len(content_cache) > keep_tail:
                        cached = content_cache[:-keep_tail]
                        content_cache = content_cache[-keep_tail:]
                    elif keep_tail > 0:
                        # Keep the whole cache for next chunk to avoid breaking
                        # partial visual markers like `<svg` / `<div`.
                        return
                    else:
                        cached = content_cache
                        content_cache = ""
                    if not cached:
                        return
                    yield RunMarkdownFlowDTO(
                        outline_bid=run_script_info.outline_bid,
                        generated_block_bid=generated_block.generated_block_bid,
                        type=GeneratedType.CONTENT,
                        content=cached,
                    )

                def _process_stream_chunk(chunk_content: str):
                    nonlocal generated_content, tts_processor, content_cache
                    if not chunk_content:
                        return
                    generated_content += chunk_content
                    if not tts_processor:
                        yield RunMarkdownFlowDTO(
                            outline_bid=run_script_info.outline_bid,
                            generated_block_bid=generated_block.generated_block_bid,
                            type=GeneratedType.CONTENT,
                            content=chunk_content,
                        )
                        return

                    # Cache content until AV validation confirms slide boundaries,
                    # then emit NEW_SLIDE before the cached content.
                    content_cache += chunk_content
                    try:
                        new_slide_events = []
                        other_events = []
                        for event in tts_processor.process_chunk(chunk_content):
                            if event.type == GeneratedType.NEW_SLIDE:
                                new_slide_events.append(event)
                            else:
                                other_events.append(event)
                    except Exception as exc:
                        app.logger.warning(
                            "Streaming TTS failed; disable for this block: %s",
                            exc,
                            exc_info=True,
                        )
                        tts_processor = None
                        yield from _flush_content_cache()
                        return

                    if new_slide_events:
                        yield from new_slide_events
                    has_pending_visual_boundary = bool(
                        getattr(tts_processor, "has_pending_visual_boundary", False)
                    )
                    # Stream-through policy:
                    # 1) any NEW_SLIDE -> flush immediately (after NEW_SLIDE),
                    # 2) boundary pending -> keep streaming immediately,
                    # 3) otherwise keep only a tiny guard tail to avoid emitting
                    #    split visual markers (e.g. `<sv`, `<di`) too early.
                    if new_slide_events or has_pending_visual_boundary:
                        yield from _flush_content_cache()
                    else:
                        yield from _flush_content_cache(keep_tail=12)

                    yield from other_events

                stream_result = mdflow_context.process(
                    block_index=run_script_info.block_position,
                    mode=ProcessMode.STREAM,
                    variables=user_profile,
                    context=message_list,
                )

                # Handle both Generator and single LLMResult (markdown-flow 0.2.27+)
                # In some edge cases (e.g., no LLM provider), returns a single LLMResult instead of Generator
                if inspect.isgenerator(stream_result):
                    # It's a generator, iterate normally
                    for llm_result in stream_result:
                        chunk_content = (
                            llm_result.content
                            if hasattr(llm_result, "content")
                            else str(llm_result)
                        )
                        if chunk_content:
                            yield from _process_stream_chunk(chunk_content)
                else:
                    # It's a single LLMResult object (edge case)
                    chunk_content = (
                        stream_result.content
                        if hasattr(stream_result, "content")
                        else str(stream_result)
                    )
                    if chunk_content:
                        yield from _process_stream_chunk(chunk_content)

                if content_cache:
                    yield from _flush_content_cache()

                if tts_processor:
                    try:
                        yield from tts_processor.finalize(commit=False)
                        self._listen_slide_index_cursor = max(
                            self._listen_slide_index_cursor,
                            int(getattr(tts_processor, "next_slide_index", 0) or 0),
                        )
                    except Exception as exc:
                        app.logger.warning(
                            "Finalize streaming TTS failed: %s", exc, exc_info=True
                        )

                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.BREAK,
                    content="",
                )
                generated_block.generated_content = generated_content
                db.session.add(generated_block)
                self._can_continue = False
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                self._current_attend.block_position += 1
                db.session.flush()

        progress_record = self._current_attend
        outline_updates = self._get_next_outline_item()
        if len(outline_updates) > 0:
            has_next_outline_item = self._has_next_outline_item(outline_updates)
            yield from self._render_outline_updates(outline_updates, new_chapter=True)
            if has_next_outline_item:
                yield from self._emit_next_chapter_interaction(progress_record)
            self._can_continue = False
            db.session.flush()
        self._trace.update(**self._trace_args)

    def run(self, app: Flask) -> Generator[RunMarkdownFlowDTO, None, None]:
        try:
            yield from self.run_inner(app)
        except PaidException:
            app.logger.info("PaidException")
            self._can_continue = False
            yield RunMarkdownFlowDTO(
                outline_bid=self._outline_item_info.bid,
                generated_block_bid=generate_id(self.app),
                type=GeneratedType.INTERACTION,
                content=f"?[{_('server.order.checkout')}//_sys_pay]",
            )
        except UserNotLoginException:
            app.logger.info("UserNotLoginException")
            self._can_continue = False
            yield RunMarkdownFlowDTO(
                outline_bid=self._outline_item_info.bid,
                generated_block_bid=generate_id(self.app),
                type=GeneratedType.INTERACTION,
                content=f"?[{_('server.user.login')}//_sys_login]",
            )

    def has_next(self) -> bool:
        return self._can_continue

    def get_system_prompt(self, outline_item_bid: str) -> str:
        path = find_node_with_parents(self._struct, outline_item_bid)
        path = list(reversed(path))
        outline_ids = [item.id for item in path if item.type == "outline"]
        shifu_ids = [item.id for item in path if item.type == "shifu"]
        outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
            self._outline_model.query.filter(
                self._outline_model.id.in_(outline_ids),
                self._outline_model.deleted == 0,
            ).all()
        )
        outline_item_info_map: dict[
            str, Union[DraftOutlineItem, PublishedOutlineItem]
        ] = {o.id: o for o in outline_item_info_db}
        for id in outline_ids:
            outline_item_info = outline_item_info_map.get(id, None)
            if (
                outline_item_info
                and outline_item_info.llm_system_prompt
                and outline_item_info.llm_system_prompt != ""
            ):
                self.app.logger.info(
                    f"outline_item_info.llm_system_prompt: {outline_item_info.llm_system_prompt}"
                )
                return outline_item_info.llm_system_prompt
        shifu_info_db: Union[DraftShifu, PublishedShifu] = (
            self._shifu_model.query.filter(
                self._shifu_model.id.in_(shifu_ids),
                self._shifu_model.deleted == 0,
            )
            .order_by(self._shifu_model.id.desc())
            .first()
        )
        self.app.logger.info(f"shifu_info_db: {shifu_info_db}")
        if shifu_info_db and shifu_info_db.llm_system_prompt:
            self.app.logger.info(
                f"shifu_info_db.llm_system_prompt: {shifu_info_db.llm_system_prompt}"
            )
            return shifu_info_db.llm_system_prompt
        return None

    def get_llm_settings(self, outline_bid: str) -> LLMSettings:
        path = find_node_with_parents(self._struct, outline_bid)
        path.reverse()
        outline_ids = [item.id for item in path if item.type == "outline"]
        shifu_ids = [item.id for item in path if item.type == "shifu"]
        outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
            self._outline_model.query.filter(
                self._outline_model.id.in_(outline_ids),
                self._outline_model.deleted == 0,
            ).all()
        )
        outline_item_info_map = {o.id: o for o in outline_item_info_db}
        for id in outline_ids:
            outline_item_info = outline_item_info_map.get(id, None)
            if outline_item_info and outline_item_info.llm:
                return LLMSettings(
                    model=outline_item_info.llm,
                    temperature=outline_item_info.llm_temperature,
                )
        shifu_info_db: Union[DraftShifu, PublishedShifu] = (
            self._shifu_model.query.filter(
                self._shifu_model.id.in_(shifu_ids),
                self._shifu_model.deleted == 0,
            ).first()
        )
        if shifu_info_db and shifu_info_db.llm:
            return LLMSettings(
                model=shifu_info_db.llm, temperature=shifu_info_db.llm_temperature
            )
        return self._get_default_llm_settings()

    def reload(self, app: Flask, reload_generated_block_bid: str):
        with app.app_context():
            generated_block: LearnGeneratedBlock = LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid == reload_generated_block_bid,
            ).first()

            current_attend = self._get_current_attend(generated_block.outline_item_bid)
            self._can_continue = False
            if generated_block:
                if self._input_type != "ask":
                    app.logger.info(
                        f"reload generated_block: {generated_block.id},block_position: {generated_block.position}"
                    )
                    if generated_block.type == BLOCK_TYPE_MDCONTENT_VALUE:
                        LearnGeneratedBlock.query.filter(
                            LearnGeneratedBlock.progress_record_bid
                            == generated_block.progress_record_bid,
                            LearnGeneratedBlock.outline_item_bid
                            == generated_block.outline_item_bid,
                            LearnGeneratedBlock.user_bid == self._user_info.user_id,
                            LearnGeneratedBlock.id >= generated_block.id,
                            LearnGeneratedBlock.position >= generated_block.position,
                        ).update({LearnGeneratedBlock.status: 0})
                    if generated_block.type == BLOCK_TYPE_MDINTERACTION_VALUE:
                        LearnGeneratedBlock.query.filter(
                            LearnGeneratedBlock.progress_record_bid
                            == generated_block.progress_record_bid,
                            LearnGeneratedBlock.outline_item_bid
                            == generated_block.outline_item_bid,
                            LearnGeneratedBlock.user_bid == self._user_info.user_id,
                            LearnGeneratedBlock.id > generated_block.id,
                            LearnGeneratedBlock.position > generated_block.position,
                        ).update({LearnGeneratedBlock.status: 0})
                    current_attend.block_position = generated_block.position
                    current_attend.status = LEARN_STATUS_IN_PROGRESS
                    db.session.commit()
                else:
                    self._last_position = generated_block.position
        with app.app_context():
            yield from self.run(app)
            db.session.commit()
        return
