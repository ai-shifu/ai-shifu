"""Handle learner follow-up questions and streamed answers."""

from collections.abc import Generator
from typing import Any

from flask import Flask
from flaskr.api.langfuse import (
    LangfuseTraceHandle,
    normalize_langfuse_input_value,
    update_langfuse_observation,
    update_langfuse_trace,
)
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.i18n import _, get_current_language
from flaskr.service.common.models import raise_param_error
from flaskr.service.learn.ask_provider_adapters.consts import (
    ASK_PROVIDER_LLM,
    ASK_PROVIDER_MODE_PROVIDER_ONLY,
    ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
)
from flaskr.service.learn.ask_provider_langfuse import stream_provider_with_langfuse
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.follow_up_context import (
    build_follow_up_conversation_context,
    build_follow_up_element_history,
    build_legacy_follow_up_history,
    is_complete_follow_up_asks,
)
from flaskr.service.learn.langfuse_naming import (
    build_langfuse_generation_name,
    build_langfuse_span_name,
)
from flaskr.service.learn.learn_dtos import (
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.listen_element_queries import (
    _load_latest_active_element_row,
    find_follow_up_element_rows,
)
from flaskr.service.learn.live_follow_up_config import is_live_follow_up_model
from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.service.learn.utils_v2 import (
    get_fmt_prompt,
    get_follow_up_info_v2,
    init_generated_block,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.shifu.ask_provider_registry import get_effective_ask_provider_config
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
)
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.user.repository import UserAggregate

check_text_with_llm_response = None
LLMSettings = None
AskProviderError = None
AskProviderRuntime = None
AskProviderTimeoutError = None
stream_ask_provider_response = None
chat_llm = None


def _is_valid_asks(asks: object) -> bool:
    """Compatibility wrapper for legacy follow-up history tests and callers."""
    return is_complete_follow_up_asks(asks)


def _load_legacy_ask_context(
    anchor_element: object,
    ask_element: object,
    ask_max_history_len: int,
) -> list[dict[str, str]] | None:
    """Compatibility wrapper around the shared legacy-history builder."""
    if anchor_element is None or ask_element is None:
        return None
    return build_legacy_follow_up_history(
        anchor_element,
        ask_element,
        max(0, int(ask_max_history_len)),
    )


def _load_ask_context(
    anchor_element: object,
    follow_up_elements: object,
    ask_max_history_len: int,
) -> list[dict[str, str]] | None:
    """Compatibility wrapper around the shared sidecar-history builder."""
    return build_follow_up_element_history(
        anchor_element,
        follow_up_elements,
        max(0, int(ask_max_history_len)),
    )


def _create_ask_block(
    app: object,
    outline_item_info: object,
    attend_id: object,
    user_bid: object,
    input_text: object,
    last_position: object,
) -> LearnGeneratedBlock:
    ask_block = init_generated_block(
        app,
        shifu_bid=outline_item_info.shifu_bid,
        outline_item_bid=outline_item_info.bid,
        progress_record_bid=attend_id,
        user_bid=user_bid,
        block_type=BLOCK_TYPE_MDASK_VALUE,
        mdflow=input_text,
        block_index=outline_item_info.position,
    )
    ask_block.generated_content = input_text
    ask_block.role = ROLE_STUDENT
    ask_block.type = BLOCK_TYPE_MDASK_VALUE
    ask_block.position = last_position
    db.session.add(ask_block)
    return ask_block


def _create_answer_block(
    app: object,
    outline_item_info: object,
    attend_id: object,
    user_bid: object,
    response_text: object,
    last_position: object,
) -> LearnGeneratedBlock:
    answer_block = init_generated_block(
        app,
        shifu_bid=outline_item_info.shifu_bid,
        outline_item_bid=outline_item_info.bid,
        progress_record_bid=attend_id,
        user_bid=user_bid,
        block_type=BLOCK_TYPE_MDANSWER_VALUE,
        mdflow=response_text,
        block_index=last_position,
    )
    answer_block.generated_content = response_text
    answer_block.role = ROLE_TEACHER
    answer_block.position = last_position
    db.session.add(answer_block)
    return answer_block


def _run_guardrail(
    app: object,
    user_info: object,
    ask_block: object,
    input_text: object,
    span: object,
    outline_item_info: object,
    last_position: object,
    follow_up_model: object,
    follow_up_info: object,
    attend_id: object,
    usage_context: object,
    chapter_title: object,
    ask_scene: object,
) -> list[str]:
    check_text_func = globals().get("check_text_with_llm_response")
    llm_settings_cls = globals().get("LLMSettings")
    if check_text_func is None or llm_settings_cls is None:
        # Lowercase aliases keep the lazily imported names consistent with the
        # module-level lookups above.
        from flaskr.service.learn.check_text import (
            check_text_with_llm_response as check_text_func,
        )
        from flaskr.service.learn.llmsetting import (  # noqa: N813
            LLMSettings as llm_settings_cls,
        )

    res = check_text_func(
        app,
        user_info=user_info,
        log_script=ask_block,
        user_input=input_text,
        span=span,
        outline_item_bid=outline_item_info.bid,
        shifu_bid=outline_item_info.shifu_bid,
        block_position=last_position,
        llm_settings=llm_settings_cls(
            model=follow_up_model,
            temperature=follow_up_info.model_args["temperature"],
        ),
        attend_id=attend_id,
        fmt_prompt=follow_up_info.ask_prompt,
        usage_context=usage_context,
        chapter_title=chapter_title,
        scene=ask_scene,
    )
    chunks = []
    for i in res:
        if i is not None and i != "":
            app.logger.info("check_text_with_llm_response: %s", i)
            chunks.append(i)
    return chunks


def _append_context_langfuse_output(context: object, value: str) -> None:
    append_output = getattr(context, "append_langfuse_output", None)
    if callable(append_output) and value:
        append_output(value)


def _finalize_ask_trace(
    *,
    context: object,
    trace: LangfuseTraceHandle,
    parent_observation: object | None,
    span: object,
    trace_args: dict,
    response_text: str,
) -> None:
    output = response_text or None
    _append_context_langfuse_output(context, response_text)
    span.end(output=output)
    if parent_observation is not None and parent_observation is not trace:
        update_langfuse_observation(parent_observation, output=output)
    update_langfuse_trace(
        trace,
        payload={
            **trace_args,
            "output": output,
        },
    )


@extensible_generic
def handle_input_ask(
    app: Flask,
    context: object,
    user_info: UserAggregate,
    attend_id: str,
    user_input: str,
    outline_item_info: ShifuOutlineItemDto,
    trace_args: dict,
    trace: LangfuseTraceHandle,
    is_preview: bool = False,
    last_position: int = -1,
    anchor_element_bid: str = "",
    parent_observation: object | None = None,
    runtime_profiles: dict | None = None,
) -> Generator[str, None, None]:
    """Handle user Q&A input.

    Process user questions in the shifu and return AI tutor responses.
    """
    # Get follow-up information (including Q&A prompts and model configuration)
    follow_up_info = get_follow_up_info_v2(
        app, outline_item_info.shifu_bid, outline_item_info.bid, attend_id, is_preview
    )
    if is_live_follow_up_model(follow_up_info.ask_model):
        # Live voice has a dedicated authenticated WebSocket transport. The
        # legacy text/SSE path must never invoke it through LiteLLM or create a
        # text fallback history turn.
        raise_param_error("follow_up_model")

    usage_scene = BILL_USAGE_SCENE_PREVIEW if is_preview else BILL_USAGE_SCENE_PROD
    usage_context = UsageContext(
        user_bid=user_info.user_id,
        shifu_bid=outline_item_info.shifu_bid,
        outline_item_bid=outline_item_info.bid,
        progress_record_bid=attend_id,
        usage_scene=usage_scene,
    )

    app.logger.info("follow_up_info:%s", follow_up_info.__json__())
    chapter_title = outline_item_info.title
    ask_scene = "lesson_preview_ask" if is_preview else "lesson_ask"

    raw_ask_max_history_len = app.config.get("ASK_MAX_HISTORY_LEN", 10)
    try:
        ask_max_history_len = int(raw_ask_max_history_len)
    except ValueError:
        ask_max_history_len = 10

    raw_input = user_input
    normalized_trace_input = normalize_langfuse_input_value(raw_input)
    if normalized_trace_input and not trace_args.get("input"):
        trace_args["input"] = normalized_trace_input
    escaped_input = raw_input.replace("{", "{{").replace(
        "}", "}}"
    )  # Escape braces to avoid formatting conflicts
    use_learner_language = bool(getattr(context._shifu_info, "use_learner_language", 0))
    runtime_language = str(get_current_language() or "").strip()
    conversation_context = build_follow_up_conversation_context(
        app,
        user_info=user_info,
        shifu_bid=outline_item_info.shifu_bid,
        outline_item_bid=outline_item_info.bid,
        progress_record_bid=attend_id,
        follow_up_info=follow_up_info,
        course_system_prompt=context.get_system_prompt(outline_item_info.bid),
        use_learner_language=use_learner_language,
        runtime_language=runtime_language,
        runtime_profiles=dict(runtime_profiles or {}),
        anchor_element_bid=anchor_element_bid,
        max_history_messages=ask_max_history_len,
        latest_element_loader=_load_latest_active_element_row,
        element_rows_loader=find_follow_up_element_rows,
        generated_block_model=LearnGeneratedBlock,
        format_prompt=get_fmt_prompt,
        output_language=(
            get_markdownflow_output_language() if use_learner_language else None
        ),
    )
    llm_messages = list(conversation_context.llm_messages)
    provider_messages = list(conversation_context.provider_messages)

    # RAG retrieval has been removed from this system

    # Prepend a format constraint so the model replies in plain text / Markdown
    # and does not mimic HTML or MarkdownFlow interactive syntax that appears
    # in earlier lesson content / conversation history.
    format_constraint = (
        "IMPORTANT — Reply ONLY in plain text or standard Markdown. "
        "Do NOT emit HTML tags (<button>, <input>, <select>, <form>, <div>, etc.). "
        "Do NOT emit MarkdownFlow interactive syntax such as `?[%... | ...]`, "
        "`?[%... || ...]`, `===...===` or `!===...!===` fences. "
        "Do NOT emit double-brace template placeholders. "
        "Earlier lesson content in this conversation may contain such syntax — "
        "DO NOT mimic its format.\n\n"
        "User question:\n"
    )
    # Append language instruction to user input if use_learner_language is enabled
    user_content = format_constraint + escaped_input
    if use_learner_language:
        output_language = conversation_context.output_language
        user_content += f"\n\n(IMPORTANT: You MUST respond in {output_language}.)"
    user_message = {
        "role": "user",
        "content": user_content,
    }
    llm_messages.append(user_message)
    provider_messages.append(user_message)
    app.logger.info("llm_messages: %s", llm_messages)
    app.logger.info("provider_messages: %s", provider_messages)

    # Get model for follow-up Q&A
    follow_up_model = follow_up_info.ask_model
    if not follow_up_model:
        follow_up_model = app.config.get("DEFAULT_LLM_MODEL", "")

    # Create ask block
    ask_block = _create_ask_block(
        app,
        outline_item_info,
        attend_id,
        user_info.user_id,
        escaped_input,
        last_position,
    )

    # Create answer block early (empty placeholder) so all teacher-side
    # events can reference the answer block's generated_block_bid.
    answer_block = _create_answer_block(
        app, outline_item_info, attend_id, user_info.user_id, "", last_position
    )
    db.session.flush()

    # Emit internal ASK event for listen adapter
    yield RunMarkdownFlowDTO(
        outline_bid=outline_item_info.bid,
        generated_block_bid=answer_block.generated_block_bid,
        type=GeneratedType.ASK,
        content=escaped_input,
        anchor_element_bid=anchor_element_bid,
    )

    # Create trace span
    span_parent = parent_observation or trace
    span = span_parent.span(
        name=build_langfuse_span_name(chapter_title, ask_scene, "user_follow_up"),
        input=escaped_input,
    )

    # Run guardrail check
    guardrail_chunks = _run_guardrail(
        app,
        user_info,
        ask_block,
        escaped_input,
        span,
        outline_item_info,
        last_position,
        follow_up_model,
        follow_up_info,
        attend_id,
        usage_context,
        chapter_title,
        ask_scene,
    )

    if guardrail_chunks:
        guardrail_text = "".join(guardrail_chunks)
        for chunk in guardrail_chunks:
            yield RunMarkdownFlowDTO(
                outline_bid=outline_item_info.bid,
                generated_block_bid=answer_block.generated_block_bid,
                type=GeneratedType.CONTENT,
                content=chunk,
            )
        yield RunMarkdownFlowDTO(
            outline_bid=outline_item_info.bid,
            generated_block_bid=answer_block.generated_block_bid,
            type=GeneratedType.BREAK,
            content="",
        )
        yield RunMarkdownFlowDTO(
            outline_bid=outline_item_info.bid,
            generated_block_bid=answer_block.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=escaped_input,
        )
        answer_block.generated_content = guardrail_text
        _finalize_ask_trace(
            context=context,
            trace=trace,
            parent_observation=parent_observation,
            span=span,
            trace_args=trace_args,
            response_text=guardrail_text,
        )
        db.session.flush()
        return

    # Call LLM to generate response
    generation_name = build_langfuse_generation_name(
        chapter_title,
        ask_scene,
        "user_follow_ask",
    )
    ask_provider_config = get_effective_ask_provider_config(
        getattr(follow_up_info, "ask_provider_config", {})
    )
    ask_provider = ask_provider_config.get("provider", ASK_PROVIDER_LLM)
    ask_provider_mode = ask_provider_config.get(
        "mode",
        ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
    )
    app.logger.info(
        "ask provider routing: provider=%s mode=%s",
        ask_provider,
        ask_provider_mode,
    )

    response_text = ""  # Store complete response text
    provider_error: Exception | None = None
    stream_provider_response_func = globals().get("stream_ask_provider_response")
    ask_provider_runtime_cls = globals().get("AskProviderRuntime")
    ask_provider_error_cls = globals().get("AskProviderError")
    ask_provider_timeout_error_cls = globals().get("AskProviderTimeoutError")
    if (
        stream_provider_response_func is None
        or ask_provider_runtime_cls is None
        or ask_provider_error_cls is None
        or ask_provider_timeout_error_cls is None
    ):
        # Lowercase aliases keep the lazily imported names consistent with the
        # module-level lookups above.
        from flaskr.service.learn.ask_provider_adapters import (  # noqa: N813
            AskProviderError as ask_provider_error_cls,
        )
        from flaskr.service.learn.ask_provider_adapters import (  # noqa: N813
            AskProviderRuntime as ask_provider_runtime_cls,
        )
        from flaskr.service.learn.ask_provider_adapters import (  # noqa: N813
            AskProviderTimeoutError as ask_provider_timeout_error_cls,
        )
        from flaskr.service.learn.ask_provider_adapters import (
            stream_ask_provider_response as stream_provider_response_func,
        )

    chat_llm_func = globals().get("chat_llm")
    if chat_llm_func is None:
        chat_llm_func = __import__(
            "flaskr.api.llm",
            fromlist=["chat_llm"],
        ).chat_llm

    from flaskr.service.learn.ask_provider_adapters.common import (
        apply_knowledge_to_messages,
    )

    def _chat_llm_stream(
        stream_messages: list[dict[str, Any]],
    ) -> Generator[Any, None, None]:
        return chat_llm_func(
            app,
            user_info.user_id,
            span,
            model=follow_up_model,  # Use configured model
            json=True,
            stream=True,  # Enable streaming output
            temperature=follow_up_info.model_args[
                "temperature"
            ],  # Use configured temperature parameter
            generation_name=generation_name,
            messages=stream_messages,
            usage_context=usage_context,
            usage_scene=usage_scene,
        )

    llm_runtime = ask_provider_runtime_cls(
        # Pass complete conversation history; an empty knowledge context
        # clears the ask-template {knowledge} placeholder.
        llm_stream_factory=lambda: _chat_llm_stream(
            apply_knowledge_to_messages(llm_messages, "")
        ),
        # Fill the ask-template knowledge section with retrieval output.
        llm_context_stream_factory=lambda knowledge_context: _chat_llm_stream(
            apply_knowledge_to_messages(llm_messages, knowledge_context)
        ),
    )

    def _emit_provider_stream(
        provider_name: str,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        nonlocal response_text
        provider_input_messages = (
            llm_messages if provider_name == ASK_PROVIDER_LLM else provider_messages
        )
        provider_resp = stream_provider_response_func(
            app=app,
            provider=provider_name,
            user_id=user_info.user_id,
            user_query=user_content,
            messages=provider_input_messages,
            provider_config=ask_provider_config,
            runtime=llm_runtime,
        )
        if provider_name != ASK_PROVIDER_LLM:
            provider_resp = stream_provider_with_langfuse(
                provider_stream=provider_resp,
                span=span,
                app=app,
                provider_name=provider_name,
                generation_name=build_langfuse_generation_name(
                    chapter_title,
                    ask_scene,
                    f"user_follow_ask_{provider_name}",
                ),
                user_query=user_content,
                messages=provider_input_messages,
                provider_config=ask_provider_config,
            )
        for chunk in provider_resp:
            current_content = chunk.content
            if isinstance(current_content, str) and current_content:
                response_text += current_content
                yield RunMarkdownFlowDTO(
                    outline_bid=outline_item_info.bid,
                    generated_block_bid=answer_block.generated_block_bid,
                    type=GeneratedType.CONTENT,
                    content=current_content,
                )

    if ask_provider == ASK_PROVIDER_LLM:
        yield from _emit_provider_stream(ASK_PROVIDER_LLM)
    else:
        try:
            yield from _emit_provider_stream(ask_provider)
        except ask_provider_timeout_error_cls as exc:
            provider_error = exc
            app.logger.warning(
                "ask provider timeout, provider=%s, mode=%s, shifu_bid=%s, outline_bid=%s",
                ask_provider,
                ask_provider_mode,
                outline_item_info.shifu_bid,
                outline_item_info.bid,
            )
        except ask_provider_error_cls as exc:
            provider_error = exc
            app.logger.warning(
                "ask provider failed, provider=%s, mode=%s, shifu_bid=%s, outline_bid=%s, error=%s",
                ask_provider,
                ask_provider_mode,
                outline_item_info.shifu_bid,
                outline_item_info.bid,
                exc,
            )

    use_llm_fallback = False
    if ask_provider != ASK_PROVIDER_LLM and not response_text:
        if ask_provider_mode == ASK_PROVIDER_MODE_PROVIDER_ONLY:
            if isinstance(provider_error, ask_provider_timeout_error_cls):
                response_text = str(_("server.learn.askProviderTimeout"))
            else:
                response_text = str(_("server.learn.askProviderUnavailable"))
            yield RunMarkdownFlowDTO(
                outline_bid=outline_item_info.bid,
                generated_block_bid=answer_block.generated_block_bid,
                type=GeneratedType.CONTENT,
                content=response_text,
            )
        else:
            use_llm_fallback = True
            app.logger.info(
                "ask provider fallback to llm, provider=%s, mode=%s, shifu_bid=%s, outline_bid=%s",
                ask_provider,
                ask_provider_mode,
                outline_item_info.shifu_bid,
                outline_item_info.bid,
            )

    if use_llm_fallback:
        yield from _emit_provider_stream(ASK_PROVIDER_LLM)

    # Backfill answer block content
    answer_block.generated_content = response_text

    # End trace span
    _finalize_ask_trace(
        context=context,
        trace=trace,
        parent_observation=parent_observation,
        span=span,
        trace_args=trace_args,
        response_text=response_text,
    )
    db.session.flush()

    # Return end marker
    yield RunMarkdownFlowDTO(
        outline_bid=outline_item_info.bid,
        generated_block_bid=answer_block.generated_block_bid,
        type=GeneratedType.BREAK,
        content="",
    )
