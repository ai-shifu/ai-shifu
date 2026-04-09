from typing import Any, Generator

from flask import Flask
from flaskr.api.langfuse import (
    normalize_langfuse_input_value,
    update_langfuse_observation,
    update_langfuse_trace,
)
from flaskr.i18n import _
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER

from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.dao import db
from flaskr.service.user.repository import UserAggregate
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from langfuse.client import StatefulTraceClient
from flaskr.service.learn.utils_v2 import (
    init_generated_block,
    get_fmt_prompt,
    get_follow_up_info_v2,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)
from flaskr.service.learn.learn_dtos import (
    ElementType,
    GeneratedType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.langfuse_naming import (
    build_langfuse_generation_name,
    build_langfuse_span_name,
)
from flaskr.service.learn.ask_provider_langfuse import stream_provider_with_langfuse
from flaskr.service.shifu.ask_provider_registry import get_effective_ask_provider_config
from flaskr.service.shifu.shifu_draft_funcs import (
    ASK_PROVIDER_LLM,
    ASK_PROVIDER_MODE_PROVIDER_ONLY,
    ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
)
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.common.i18n_utils import get_markdownflow_output_language
from flaskr.service.learn.listen_element_payloads import _deserialize_payload
from flaskr.service.learn.listen_element_queries import (
    _load_latest_active_element_row,
    find_follow_up_element_rows,
)

check_text_with_llm_response = None
LLMSettings = None
AskProviderError = None
AskProviderRuntime = None
AskProviderTimeoutError = None
stream_ask_provider_response = None
chat_llm = None


def _is_valid_asks(asks):
    """Check if asks list has at least one complete student+teacher pair."""
    if not asks or not isinstance(asks, list):
        return False
    has_student = any(a.get("role") == "student" for a in asks if isinstance(a, dict))
    has_teacher = any(a.get("role") == "teacher" for a in asks if isinstance(a, dict))
    return has_student and has_teacher


def _load_legacy_ask_context(anchor_element, ask_element, ask_max_history_len):
    if anchor_element is None or ask_element is None:
        return None

    payload_dto = _deserialize_payload(getattr(ask_element, "payload", "") or "")
    asks = payload_dto.asks

    if not _is_valid_asks(asks):
        return None

    messages = []
    # Anchor element content as first assistant context message
    anchor_content = getattr(anchor_element, "content_text", "") or ""
    if anchor_content:
        messages.append({"role": "assistant", "content": anchor_content})

    # Map asks entries: student -> user, teacher -> assistant
    for entry in asks[-ask_max_history_len:]:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "student":
            messages.append({"role": "user", "content": content})
        elif role == "teacher":
            messages.append({"role": "assistant", "content": content})

    return messages


def _load_ask_context(anchor_element, follow_up_elements, ask_max_history_len):
    """Load ask context from ask/answer sidecar elements first."""
    if anchor_element is None or not follow_up_elements:
        return None

    messages = []
    anchor_content = getattr(anchor_element, "content_text", "") or ""
    if anchor_content:
        messages.append({"role": "assistant", "content": anchor_content})

    row_messages = []
    legacy_ask_element = None
    has_new_follow_up_elements = False

    for row in follow_up_elements:
        element_type = str(getattr(row, "element_type", "") or "")
        payload_dto = _deserialize_payload(getattr(row, "payload", "") or "")
        if element_type == ElementType.ASK.value and _is_valid_asks(payload_dto.asks):
            legacy_ask_element = row
            continue

        content = getattr(row, "content_text", "") or ""
        if not content:
            continue

        if element_type == ElementType.ASK.value:
            has_new_follow_up_elements = True
            row_messages.append({"role": "user", "content": content})
        elif element_type == ElementType.ANSWER.value:
            has_new_follow_up_elements = True
            row_messages.append({"role": "assistant", "content": content})

    if has_new_follow_up_elements and row_messages:
        messages.extend(row_messages[-ask_max_history_len:])
        return messages

    if legacy_ask_element is not None:
        return _load_legacy_ask_context(
            anchor_element,
            legacy_ask_element,
            ask_max_history_len,
        )

    return None


def _create_ask_block(
    app,
    outline_item_info,
    attend_id,
    user_bid,
    input_text,
    last_position,
):
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
    app,
    outline_item_info,
    attend_id,
    user_bid,
    response_text,
    last_position,
):
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
    app,
    user_info,
    ask_block,
    input_text,
    span,
    outline_item_info,
    last_position,
    follow_up_model,
    follow_up_info,
    attend_id,
    usage_context,
    chapter_title,
    ask_scene,
):
    check_text_func = globals().get("check_text_with_llm_response")
    llm_settings_cls = globals().get("LLMSettings")
    if check_text_func is None or llm_settings_cls is None:
        from flaskr.service.learn.check_text import (
            check_text_with_llm_response as check_text_func,
        )
        from flaskr.service.learn.llmsetting import LLMSettings as llm_settings_cls

    res = check_text_func(
        app,
        user_info=user_info,
        log_script=ask_block,
        input=input_text,
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
            app.logger.info(f"check_text_with_llm_response: {i}")
            chunks.append(i)
    return chunks


def _append_context_langfuse_output(context: Any, value: str) -> None:
    append_output = getattr(context, "append_langfuse_output", None)
    if callable(append_output) and value:
        append_output(value)


def _finalize_ask_trace(
    *,
    context: Any,
    trace: StatefulTraceClient,
    parent_observation: Any | None,
    span: Any,
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
    context,
    user_info: UserAggregate,
    attend_id: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
    last_position: int = -1,
    anchor_element_bid: str = "",
    parent_observation: Any | None = None,
) -> Generator[str, None, None]:
    """
    Main function to handle user Q&A input
    Responsible for processing user questions in the shifu and returning AI tutor responses
    """

    # Get follow-up information (including Q&A prompts and model configuration)
    follow_up_info = get_follow_up_info_v2(
        app, outline_item_info.shifu_bid, outline_item_info.bid, attend_id, is_preview
    )

    usage_scene = BILL_USAGE_SCENE_PREVIEW if is_preview else BILL_USAGE_SCENE_PROD
    usage_context = UsageContext(
        user_bid=user_info.user_id,
        shifu_bid=outline_item_info.shifu_bid,
        outline_item_bid=outline_item_info.bid,
        progress_record_bid=attend_id,
        usage_scene=usage_scene,
    )

    app.logger.info("follow_up_info:{}".format(follow_up_info.__json__()))
    chapter_title = outline_item_info.title
    ask_scene = "lesson_preview_ask" if is_preview else "lesson_ask"

    raw_ask_max_history_len = app.config.get("ASK_MAX_HISTORY_LEN", 10)
    try:
        ask_max_history_len = int(raw_ask_max_history_len)
    except ValueError:
        ask_max_history_len = 10

    llm_messages = []  # Conversation messages for built-in LLM ask.
    provider_messages = []  # Conversation messages for external ask providers.
    raw_input = input
    normalized_trace_input = normalize_langfuse_input_value(raw_input)
    if normalized_trace_input and not trace_args.get("input"):
        trace_args["input"] = normalized_trace_input
    input = raw_input.replace("{", "{{").replace(
        "}", "}}"
    )  # Escape braces to avoid formatting conflicts
    system_prompt_template = context.get_system_prompt(outline_item_info.bid)
    base_system_prompt = (
        None
        if system_prompt_template is None or system_prompt_template == ""
        else get_fmt_prompt(
            app,
            user_info.user_id,
            outline_item_info.shifu_bid,
            system_prompt_template,
        )
    )
    llm_system_prompt = follow_up_info.ask_prompt.replace(
        "{shifu_system_message}", base_system_prompt if base_system_prompt else ""
    )
    # Append language instruction if use_learner_language is enabled
    use_learner_language = getattr(context._shifu_info, "use_learner_language", 0)
    if use_learner_language:
        output_language = get_markdownflow_output_language()
        llm_system_prompt += f"\n\nIMPORTANT: You MUST respond in {output_language}."
    llm_messages.append({"role": "system", "content": llm_system_prompt})
    if base_system_prompt:
        provider_messages.append({"role": "system", "content": base_system_prompt})

    # Try loading ask context from ask/answer sidecar elements first
    anchor_element = None
    follow_up_elements = []
    if anchor_element_bid:
        anchor_element = _load_latest_active_element_row(anchor_element_bid)
        if anchor_element is not None:
            follow_up_elements = find_follow_up_element_rows(
                attend_id,
                anchor_element_bid,
            )

    element_context = _load_ask_context(
        anchor_element,
        follow_up_elements,
        ask_max_history_len,
    )
    if element_context is not None:
        for msg in element_context:
            llm_messages.append(msg)
            provider_messages.append(msg)
    else:
        # Fallback: load from LearnGeneratedBlock
        history_scripts: list[LearnGeneratedBlock] = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid == attend_id,
                LearnGeneratedBlock.deleted == 0,
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .limit(ask_max_history_len)
            .all()
        )
        history_scripts = history_scripts[::-1]
        for script in history_scripts:
            if script.type in [BLOCK_TYPE_MDASK_VALUE, BLOCK_TYPE_MDINTERACTION_VALUE]:
                history_message = {
                    "role": "user",
                    "content": script.generated_content,
                }
                llm_messages.append(history_message)
                provider_messages.append(history_message)
            elif script.type in [
                BLOCK_TYPE_MDANSWER_VALUE,
                BLOCK_TYPE_MDCONTENT_VALUE,
            ]:
                history_message = {
                    "role": "assistant",
                    "content": script.generated_content,
                }
                llm_messages.append(history_message)
                provider_messages.append(history_message)

    # RAG retrieval has been removed from this system

    # Append language instruction to user input if use_learner_language is enabled
    use_learner_language = getattr(context._shifu_info, "use_learner_language", 0)
    user_content = input
    if use_learner_language:
        output_language = get_markdownflow_output_language()
        user_content += f"\n\n(IMPORTANT: You MUST respond in {output_language}.)"
    user_message = {
        "role": "user",
        "content": user_content,
    }
    llm_messages.append(user_message)
    provider_messages.append(user_message)
    app.logger.info(f"llm_messages: {llm_messages}")
    app.logger.info(f"provider_messages: {provider_messages}")

    # Get model for follow-up Q&A
    follow_up_model = follow_up_info.ask_model
    if not follow_up_model:
        follow_up_model = app.config.get("DEFAULT_LLM_MODEL", "")

    # Create ask block
    ask_block = _create_ask_block(
        app, outline_item_info, attend_id, user_info.user_id, input, last_position
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
        content=input,
        anchor_element_bid=anchor_element_bid,
    )

    # Create trace span
    span_parent = parent_observation or trace
    span = span_parent.span(
        name=build_langfuse_span_name(chapter_title, ask_scene, "user_follow_up"),
        input=input,
    )

    # Run guardrail check
    guardrail_chunks = _run_guardrail(
        app,
        user_info,
        ask_block,
        input,
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
            content=input,
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
        from flaskr.service.learn.ask_provider_adapters import (
            AskProviderError as ask_provider_error_cls,
            AskProviderRuntime as ask_provider_runtime_cls,
            AskProviderTimeoutError as ask_provider_timeout_error_cls,
            stream_ask_provider_response as stream_provider_response_func,
        )

    chat_llm_func = globals().get("chat_llm")
    if chat_llm_func is None:
        chat_llm_func = __import__(
            "flaskr.api.llm",
            fromlist=["chat_llm"],
        ).chat_llm

    llm_runtime = ask_provider_runtime_cls(
        llm_stream_factory=lambda: chat_llm_func(
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
            messages=llm_messages,  # Pass complete conversation history
            usage_context=usage_context,
            usage_scene=usage_scene,
        )
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
