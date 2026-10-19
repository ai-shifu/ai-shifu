"""Run editor previews of a MarkdownFlow block without persisting progress."""

import hashlib
import inspect
import json
from collections.abc import Generator
from decimal import Decimal

from flask import Flask
from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
    get_request_trace_id,
    normalize_langfuse_input_value,
    normalize_langfuse_output_value,
)
from flaskr.api.llm.model_selection import selection_metadata, selection_model
from flaskr.common.cache_provider import cache as cache_provider
from flaskr.dao import cleanup_session_after, db
from flaskr.i18n import get_current_language, set_language
from flaskr.service.learn.context_v2_mdflow import (
    MdflowContextV2,
    RUNLLMProvider,
    _iter_llm_result_content_parts,
)
from flaskr.service.learn.langfuse_naming import (
    build_langfuse_span_name,
    build_langfuse_trace_name,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    PlaygroundPreviewRequest,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learner_profile_prompt import (
    build_course_prompt,
    render_course_prompt_identity_variables,
)
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.memory import (
    load_memory,
)
from flaskr.service.learn.preview_elements import PreviewElementRunAdapter
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
)
from flaskr.service.profile.constants import SYS_USER_LANGUAGE
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_struct_manager import (
    get_shifu_struct,
)
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.user.repository import UserAggregate, load_user_aggregate
from markdown_flow import (
    BlockType,
    ProcessMode,
    replace_variables_in_text,
)
from markdown_flow.llm import LLMResult


class _PreviewContextStore:
    _DEFAULT_TTL_SECONDS = 30 * 60
    # Sentinel block_index for entries supplied via replace_context without
    # block_index metadata. Negative values are kept by any real-block
    # truncation (which discards entries with block_index >= request index).
    _REPLACE_SENTINEL_BLOCK_INDEX = -1

    def __init__(
        self,
        app: Flask,
        user_bid: str,
        shifu_bid: str,
        outline_bid: str,
        ttl_seconds: int | None = None,
        language: str | None = None,
    ) -> None:
        self._cache = cache_provider
        self._ttl_seconds = ttl_seconds or self._DEFAULT_TTL_SECONDS
        prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
        language_suffix = f":{language}" if language else ""
        self._key = (
            f"{prefix}:preview_context:{user_bid}:{shifu_bid}:{outline_bid}"
            f"{language_suffix}"
        )

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

    @staticmethod
    def _entries_to_messages(entries: list[dict]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for entry in entries:
            user_text = entry.get("user")
            if user_text:
                messages.append({"role": "user", "content": user_text})
            assistant_text = entry.get("assistant")
            if assistant_text:
                messages.append({"role": "assistant", "content": assistant_text})
        return messages

    def _load_entries(self, document: str) -> list[dict] | None:
        payload = self.load()
        if not payload:
            return None
        doc_hash = payload.get("document_hash")
        if document and doc_hash != self._hash_document(document):
            self.clear()
            return None
        entries = payload.get("entries")
        if not isinstance(entries, list):
            self.clear()
            return None
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(
                entry.get("block_index"), int
            ):
                self.clear()
                return None
        return entries

    def get_context(self, document: str, block_index: int) -> list[dict[str, str]]:
        if block_index == 0:
            self.clear()
            return []
        entries = self._load_entries(document)
        if not entries:
            return []
        kept = [entry for entry in entries if entry["block_index"] < block_index]
        if len(kept) != len(entries):
            self.save(
                {
                    "document_hash": self._hash_document(document),
                    "entries": kept,
                }
            )
        return self._entries_to_messages(kept)

    def replace_context(self, document: str, context: list[dict[str, str]]) -> None:
        """Replace cached context from a raw role/content message list.

        Used when callers pass a full context payload without per-block
        metadata. Entries get a sentinel block_index so subsequent
        block-based truncation in get_context() preserves them.
        """
        entries: list[dict] = []
        pending_user: str | None = None
        for item in context or []:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if not content:
                continue
            if role == "user":
                if pending_user is not None:
                    entries.append(
                        {
                            "block_index": self._REPLACE_SENTINEL_BLOCK_INDEX,
                            "user": pending_user,
                            "assistant": None,
                        }
                    )
                pending_user = content
            elif role == "assistant":
                entries.append(
                    {
                        "block_index": self._REPLACE_SENTINEL_BLOCK_INDEX,
                        "user": pending_user,
                        "assistant": content,
                    }
                )
                pending_user = None
        if pending_user is not None:
            entries.append(
                {
                    "block_index": self._REPLACE_SENTINEL_BLOCK_INDEX,
                    "user": pending_user,
                    "assistant": None,
                }
            )
        self.save(
            {
                "document_hash": self._hash_document(document),
                "entries": entries,
            }
        )

    def append_context(
        self,
        document: str,
        block_index: int,
        user_message: str | None,
        assistant_message: str | None,
    ) -> None:
        if not user_message and not assistant_message:
            return
        doc_hash = self._hash_document(document)
        payload = self.load()
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or payload.get("document_hash") != doc_hash:
            entries = []
        entries.append(
            {
                "block_index": block_index,
                "user": user_message or None,
                "assistant": assistant_message or None,
            }
        )
        self.save(
            {
                "document_hash": doc_hash,
                "entries": entries,
            }
        )


class RunScriptPreviewContextV2:
    """MarkdownFlow preview using context v2 logic with optional Redis caching."""

    def __init__(self, app: Flask) -> None:
        """Bind the preview execution context to the Flask app."""
        self.app = app

    def stream_preview(
        self,
        *,
        preview_request: PlaygroundPreviewRequest,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
        session_id: str,
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        """Stream a preview run without persisting learner progress."""
        outline = self._get_outline_record(shifu_bid, outline_bid)
        shifu = self._get_shifu_record(shifu_bid, has_draft_outline=True)
        resolved_variables = self._resolve_preview_variables(
            preview_request=preview_request,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
        )
        document_prompt = self._resolve_document_prompt(
            preview_request,
            outline,
            shifu,
            shifu_bid,
            outline_bid,
            user_bid,
            resolved_variables,
        )
        self.app.logger.info(
            "preview document prompt | shifu_bid=%s | outline_bid=%s | prompt=%s",
            shifu_bid,
            outline_bid,
            (document_prompt or "").strip(),
        )
        model, temperature = self._resolve_llm_settings(shifu)
        document = preview_request.get_document() or (
            outline.content if outline else ""
        )
        if not document:
            message = "Markdown-Flow content is empty"
            raise ValueError(message)

        trace, root_span, trace_args = self._create_preview_trace(
            outline=outline,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            session_id=session_id,
        )
        provider = self._build_preview_provider(
            model=model,
            temperature=temperature,
            trace=trace,
            root_span=root_span,
            trace_args=trace_args,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
        )

        preview_language = resolved_variables.get("language") or resolved_variables.get(
            SYS_USER_LANGUAGE
        )
        original_language = get_current_language()
        restore_language = (
            bool(preview_language) and preview_language != original_language
        )
        if restore_language:
            set_language(preview_language)

        content_chunks: list[str] = []
        langfuse_output_chunks: list[str] = []
        # Holder for the exact user message markdown-flow sent to the LLM
        # (LLMResult.prompt); the preview context stores it verbatim so the
        # rebuilt history stays byte-identical to the sent request.
        sent_prompt_chunks: list[str] = []
        # The trace input resolves mid-run; the holder keeps it visible to the
        # finally below even when the run raises after resolving it.
        trace_input_holder: list[str | None] = [None]
        try:
            yield from self._run_preview_block(
                preview_request=preview_request,
                shifu=shifu,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                user_bid=user_bid,
                session_id=session_id,
                document=document,
                document_prompt=document_prompt,
                model=model,
                temperature=temperature,
                resolved_variables=resolved_variables,
                provider=provider,
                content_chunks=content_chunks,
                langfuse_output_chunks=langfuse_output_chunks,
                sent_prompt_chunks=sent_prompt_chunks,
                trace_input_holder=trace_input_holder,
            )
        finally:
            preview_trace_input = trace_input_holder[0]
            finalize_langfuse_trace(
                trace=trace,
                root_span=root_span,
                trace_payload={
                    **trace_args,
                    "input": preview_trace_input,
                    "output": "".join(langfuse_output_chunks).strip() or None,
                },
                root_span_payload={
                    "input": preview_trace_input,
                    "output": "".join(langfuse_output_chunks).strip() or None,
                },
            )
            if restore_language:
                set_language(original_language)

    def _create_preview_trace(
        self,
        *,
        outline: DraftOutlineItem | PublishedOutlineItem | None,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
        session_id: str,
    ) -> tuple[object, object, dict]:
        """Create the Langfuse trace and root span for one preview request."""
        chapter_title = getattr(outline, "title", "") or outline_bid
        trace_scene = "lesson_preview"
        request_trace_id = get_request_trace_id()
        trace_args = {
            "user_id": user_bid,
            "session_id": session_id,
            "name": build_langfuse_trace_name(chapter_title, trace_scene),
            "metadata": {
                "shifu_bid": shifu_bid,
                "outline_bid": outline_bid,
                "session_id": session_id,
                "scene": trace_scene,
                "chapter_title": chapter_title,
            },
        }
        trace, root_span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={"id": request_trace_id, **trace_args},
            root_span_payload={
                "name": build_langfuse_span_name(
                    chapter_title,
                    trace_scene,
                    "root",
                ),
            },
        )
        self.app.logger.info(
            "langfuse preview trace created | request_id=%s trace_id=%s scene=%s user_id=%s shifu_bid=%s outline_item_bid=%s session_id=%s",
            request_trace_id,
            request_trace_id,
            trace_scene,
            user_bid,
            shifu_bid,
            outline_bid,
            session_id,
        )
        return trace, root_span, trace_args

    def _build_preview_provider(
        self,
        *,
        model: str,
        temperature: float,
        trace: object,
        root_span: object,
        trace_args: dict,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
    ) -> RUNLLMProvider:
        """Build the preview-scene LLM provider bound to the preview trace."""
        usage_context = UsageContext(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            usage_scene=BILL_USAGE_SCENE_PREVIEW,
        )
        return RUNLLMProvider(
            self.app,
            LLMSettings(
                model=model,
                temperature=temperature,
                usage_metadata=getattr(self, "_preview_model_selection_metadata", {}),
            ),
            trace,
            root_span,
            trace_args,
            usage_context,
            BILL_USAGE_SCENE_PREVIEW,
        )

    def _run_preview_block(
        self,
        *,
        preview_request: PlaygroundPreviewRequest,
        shifu: DraftShifu | PublishedShifu | None,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
        session_id: str,
        document: str,
        document_prompt: str | None,
        model: str,
        temperature: float,
        resolved_variables: dict,
        provider: RUNLLMProvider,
        content_chunks: list[str],
        langfuse_output_chunks: list[str],
        sent_prompt_chunks: list[str],
        trace_input_holder: list[str | None],
    ) -> Generator[RunElementSSEMessageDTO, None, None]:
        """Process the requested block and stream its preview elements.

        Publishes the Langfuse trace input through ``trace_input_holder`` as
        soon as it resolves so the caller's ``finally`` sees it on failure
        paths too.
        """
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
            self.app,
            user_bid,
            shifu_bid,
            outline_bid,
            language=str(
                resolved_variables.get("language")
                or resolved_variables.get(SYS_USER_LANGUAGE)
                or ""
            ),
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

        preview_output_language = str(
            resolved_variables.get("language")
            or resolved_variables.get(SYS_USER_LANGUAGE)
            or ""
        )
        context_messages = MdflowContextV2.filter_context_by_output_language(
            context_messages,
            preview_output_language,
        )

        mdflow_context = MdflowContextV2(
            document=document,
            llm_provider=provider,
            document_prompt=document_prompt,
            interaction_prompt=preview_request.interaction_prompt,
            interaction_error_prompt=preview_request.interaction_error_prompt,
            use_learner_language=bool(getattr(shifu, "use_learner_language", 0)),
            visual_mode=bool(preview_request.visual_mode),
            output_language=preview_output_language,
        )

        block_index = preview_request.block_index
        current_block = mdflow_context.get_block(block_index)
        current_block_content = ""
        if current_block:
            current_block_content = (
                replace_variables_in_text(
                    current_block.content or "", resolved_variables
                )
                or ""
            )
        preview_trace_input = normalize_langfuse_input_value(
            preview_request.user_input
        ) or normalize_langfuse_input_value(current_block_content)
        trace_input_holder[0] = preview_trace_input
        is_user_input_validation = bool(preview_request.user_input)

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

        preview_adapter = PreviewElementRunAdapter(
            self.app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_bid=user_bid,
            run_session_bid=session_id,
        )
        yield from preview_adapter.process(
            self._iter_preview_generated_events(
                result=result,
                outline_bid=outline_bid,
                block_index=block_index,
                current_block=current_block,
                is_user_input_validation=is_user_input_validation,
                content_chunks=content_chunks,
                langfuse_output_chunks=langfuse_output_chunks,
                sent_prompt_chunks=sent_prompt_chunks,
            )
        )
        self._update_preview_context(
            context_store,
            document,
            preview_request,
            content_chunks,
            current_block_content,
            sent_prompt=(sent_prompt_chunks[0] if sent_prompt_chunks else ""),
        )

    def _update_preview_context(
        self,
        context_store: _PreviewContextStore,
        document: str,
        preview_request: PlaygroundPreviewRequest,
        content_chunks: list[str],
        current_block_content: str,
        *,
        sent_prompt: str = "",
    ) -> None:
        user_input_text = MdflowContextV2.flatten_user_input_map(
            preview_request.user_input
        )
        content_text = "".join(content_chunks).strip()
        if content_text:
            # Prefer the exact prompt sent to the LLM over the locally
            # re-rendered block content so the stored history replays the
            # sent bytes verbatim (prefix-cache stable).
            user_message = user_input_text or sent_prompt or current_block_content
        else:
            user_message = user_input_text
        assistant_message = content_text or None
        if not user_message and not assistant_message:
            return
        context_store.append_context(
            document,
            preview_request.block_index,
            user_message or None,
            assistant_message,
        )

    def _resolve_preview_variables(
        self,
        *,
        preview_request: PlaygroundPreviewRequest,
        user_bid: str,
        shifu_bid: str,
    ) -> dict | None:
        request_variables = (
            dict(preview_request.variables)
            if isinstance(preview_request.variables, dict)
            else {}
        )
        variables = load_memory(self.app, user_bid, shifu_bid).as_variables()
        variables.update(request_variables)

        request_language = str(
            request_variables.get("language")
            or request_variables.get(SYS_USER_LANGUAGE)
            or ""
        ).strip()
        if request_language:
            variables[SYS_USER_LANGUAGE] = request_language
            variables["language"] = request_language

        # The editor preview may submit an empty sys_user_language placeholder.
        # Runtime language should follow the current request, not an empty variable.
        if not str(variables.get(SYS_USER_LANGUAGE) or "").strip():
            variables[SYS_USER_LANGUAGE] = get_current_language()
        if not str(variables.get("language") or "").strip():
            variables["language"] = variables[SYS_USER_LANGUAGE]
        elif variables.get("language") != variables.get(SYS_USER_LANGUAGE):
            variables[SYS_USER_LANGUAGE] = variables["language"]
        return variables

    def _iter_preview_generated_events(
        self,
        *,
        result: LLMResult | Generator[LLMResult, None, None] | None,
        outline_bid: str,
        block_index: int,
        current_block: object,
        is_user_input_validation: bool,
        content_chunks: list[str],
        langfuse_output_chunks: list[str],
        sent_prompt_chunks: list[str] | None = None,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        generated_block_bid = str(block_index)
        emitted_interaction = False
        raw_items = result if inspect.isgenerator(result) else [result]
        for llm_result in raw_items:
            if sent_prompt_chunks is not None and not sent_prompt_chunks:
                prompt_value = getattr(llm_result, "prompt", None)
                if prompt_value:
                    sent_prompt_chunks.append(str(prompt_value))
            for event in self._preview_events_from_result(
                llm_result=llm_result,
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                current_block=current_block,
                is_user_input_validation=is_user_input_validation,
            ):
                if event.type in (GeneratedType.CONTENT, GeneratedType.INTERACTION):
                    event_content = normalize_langfuse_output_value(event.content)
                    if event_content:
                        langfuse_output_chunks.append(event_content)
                if event.type == GeneratedType.CONTENT:
                    content_chunks.append(str(event.content or ""))
                yield event
                if event.type == GeneratedType.INTERACTION:
                    emitted_interaction = True
            if emitted_interaction:
                break

        yield RunMarkdownFlowDTO(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            type=GeneratedType.BREAK,
            content="",
        )
        yield RunMarkdownFlowDTO(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            type=GeneratedType.DONE,
            content="",
        )

    def _preview_events_from_result(
        self,
        *,
        llm_result: LLMResult | None,
        outline_bid: str,
        generated_block_bid: str,
        current_block: object,
        is_user_input_validation: bool,
    ) -> list[RunMarkdownFlowDTO]:
        content = ""
        if llm_result is not None:
            if hasattr(llm_result, "content"):
                content = str(llm_result.content or "")
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
                return [
                    self._make_preview_content_event(
                        outline_bid=outline_bid,
                        generated_block_bid=generated_block_bid,
                        content=item_content,
                        stream_type=stream_type,
                        stream_number=stream_number,
                    )
                    for item_content, stream_type, stream_number in (
                        _iter_llm_result_content_parts(llm_result)
                    )
                ]

            rendered_content = content or getattr(current_block, "content", "")
            return [
                RunMarkdownFlowDTO(
                    outline_bid=outline_bid,
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=rendered_content,
                )
            ]

        return [
            self._make_preview_content_event(
                outline_bid=outline_bid,
                generated_block_bid=generated_block_bid,
                content=item_content,
                stream_type=stream_type,
                stream_number=stream_number,
            )
            for item_content, stream_type, stream_number in (
                _iter_llm_result_content_parts(llm_result)
            )
        ]

    def _make_preview_content_event(
        self,
        *,
        outline_bid: str,
        generated_block_bid: str,
        content: str,
        stream_type: str,
        stream_number: object,
    ) -> RunMarkdownFlowDTO:
        event = RunMarkdownFlowDTO(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            type=GeneratedType.CONTENT,
            content=content,
        )
        normalized_stream_type = str(stream_type or "").strip().lower()
        if not normalized_stream_type or stream_number is None:
            return event
        try:
            normalized_stream_number = int(stream_number)
        except (TypeError, ValueError):
            return event
        return event.set_mdflow_stream_parts(
            [(content, normalized_stream_type, normalized_stream_number)]
        )

    def _resolve_document_prompt(
        self,
        preview_request: PlaygroundPreviewRequest,
        outline: DraftOutlineItem | PublishedOutlineItem | None,
        shifu: DraftShifu | PublishedShifu | None,
        shifu_bid: str,
        outline_bid: str,
        user_bid: str,
        variables: dict | None,
    ) -> str | None:
        course_prompt: str | None = None
        if preview_request.document_prompt:
            prompt = preview_request.document_prompt.strip()
            if prompt:
                course_prompt = prompt

        if not course_prompt:
            course_prompt = self._resolve_prompt_from_outline_chain(
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                outline_record=outline,
            )

        if not course_prompt and shifu:
            prompt = (getattr(shifu, "llm_system_prompt", None) or "").strip()
            if prompt:
                course_prompt = prompt

        if not course_prompt:
            return course_prompt

        learner = self._load_learner_for_course_prompt(user_bid)
        variable_prompt = build_course_prompt(
            course_prompt,
            variables=variables,
            nickname_identifiers=(
                user_bid,
                getattr(learner, "identify", ""),
            ),
        )
        return render_course_prompt_identity_variables(variable_prompt, variables)

    def _load_learner_for_course_prompt(
        self,
        user_bid: str,
    ) -> UserAggregate | None:
        try:
            return load_user_aggregate(user_bid, with_credentials=False)
        except Exception as exc:  # preview must survive lookup failures
            cleanup_session_after(
                exc,
                source="preview learner identity lookup",
                session=db.session,
            )
            self.app.logger.warning(
                "learner identity lookup failed for preview course prompt | "
                "user_bid=%s | error_class=%s",
                user_bid,
                type(exc).__name__,
            )
            return None

    def _resolve_prompt_from_outline_chain(
        self,
        shifu_bid: str,
        outline_bid: str,
        outline_record: DraftOutlineItem | PublishedOutlineItem | None,
    ) -> str | None:
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
                self.app.logger.debug(
                    "outline hierarchy lookup skipped a struct: "
                    "shifu_bid=%s is_preview=%s",
                    shifu_bid,
                    is_preview,
                    exc_info=True,
                )
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
        shifu: DraftShifu | PublishedShifu | None,
    ) -> tuple[str, float]:
        """Prepare preview settings without routing models for static content."""
        model = selection_model(shifu)
        self._preview_model_selection_metadata = selection_metadata(shifu)
        temperature = self._decimal_to_float(getattr(shifu, "llm_temperature", None))
        if temperature is None:
            temperature = float(self.app.config.get("DEFAULT_LLM_TEMPERATURE"))
        return model, float(temperature)

    def _get_outline_record(
        self, shifu_bid: str, outline_bid: str
    ) -> DraftOutlineItem | PublishedOutlineItem | None:
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
    ) -> DraftShifu | PublishedShifu | None:
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

    def _decimal_to_float(self, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
