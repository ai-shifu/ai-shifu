from typing import Generator
from flask import Flask
from flaskr.api.llm import chat_llm
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER

from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.dao import db
from flaskr.service.learn.check_text import check_text_with_llm_response
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
from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO, GeneratedType
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
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

    raw_ask_max_history_len = app.config.get("ASK_MAX_HISTORY_LEN", 10)
    try:
        ask_max_history_len = int(raw_ask_max_history_len)
    except ValueError:
        ask_max_history_len = 10

    # Query historical conversation records, ordered by time
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

    messages = []  # List to store conversation messages
    input = input.replace("{", "{{").replace(
        "}", "}}"
    )  # Escape braces to avoid formatting conflicts
    system_prompt_template = context.get_system_prompt(outline_item_info.bid)
    system_prompt = (
        None
        if system_prompt_template is None or system_prompt_template == ""
        else get_fmt_prompt(
            app,
            user_info.user_id,
            outline_item_info.shifu_bid,
            system_prompt_template,
        )
    )
    system_prompt = follow_up_info.ask_prompt.replace(
        "{shifu_system_message}", system_prompt if system_prompt else ""
    )
    messages.append({"role": "system", "content": system_prompt})
    # Add historical conversation records to system messages
    for script in history_scripts:
        if script.type in [BLOCK_TYPE_MDASK_VALUE, BLOCK_TYPE_MDINTERACTION_VALUE]:
            messages.append(
                {"role": "user", "content": script.generated_content}
            )  # Add user message
        elif script.type in [BLOCK_TYPE_MDANSWER_VALUE, BLOCK_TYPE_MDCONTENT_VALUE]:
            messages.append(
                {"role": "assistant", "content": script.generated_content}
            )  # Add assistant message

    # RAG retrieval has been removed from this system

    messages.append(
        {
            "role": "user",
            "content": input,
        }
    )
    app.logger.info(f"messages: {messages}")

    # Get model for follow-up Q&A
    follow_up_model = follow_up_info.ask_model
    if not follow_up_model:
        follow_up_model = app.config.get("DEFAULT_LLM_MODEL", "")

    # Log user input to database
    log_script: LearnGeneratedBlock = init_generated_block(
        app,
        shifu_bid=outline_item_info.shifu_bid,
        outline_item_bid=outline_item_info.bid,
        progress_record_bid=attend_id,
        user_bid=user_info.user_id,
        block_type=BLOCK_TYPE_MDASK_VALUE,
        mdflow=input,
        block_index=outline_item_info.position,
    )
    log_script.generated_content = input
    log_script.role = ROLE_STUDENT  # Mark as student role
    log_script.type = BLOCK_TYPE_MDASK_VALUE  # Mark as Q&A type
    log_script.position = last_position
    db.session.add(log_script)

    # Create trace span
    span = trace.span(name="user_follow_up", input=input)

    # Check if user input needs special processing (such as sensitive word filtering, etc.)
    res = check_text_with_llm_response(
        app,
        user_info=user_info,
        log_script=log_script,
        input=input,
        span=span,
        outline_item_bid=outline_item_info.bid,
        shifu_bid=outline_item_info.shifu_bid,
        block_position=last_position,
        llm_settings=LLMSettings(
            model=follow_up_model,
            temperature=follow_up_info.model_args["temperature"],
        ),
        attend_id=attend_id,
        fmt_prompt=follow_up_info.ask_prompt,
        usage_context=usage_context,
    )
    has_content = False
    for i in res:
        if i is not None and i != "":
            app.logger.info(f"check_text_with_llm_response: {i}")
            has_content = True
            yield RunMarkdownFlowDTO(
                outline_bid=outline_item_info.bid,
                generated_block_bid=log_script.generated_block_bid,
                type=GeneratedType.CONTENT,
                content=i,
            )

    if has_content:
        yield RunMarkdownFlowDTO(
            outline_bid=outline_item_info.bid,
            generated_block_bid=log_script.generated_block_bid,
            type=GeneratedType.BREAK,
            content="",
        )
        yield RunMarkdownFlowDTO(
            outline_bid=outline_item_info.bid,
            generated_block_bid=log_script.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=input,
        )
        db.session.flush()
        return

    # Call LLM to generate response
    resp = chat_llm(
        app,
        user_info.user_id,
        span,
        model=follow_up_model,  # Use configured model
        json=True,
        stream=True,  # Enable streaming output
        temperature=follow_up_info.model_args[
            "temperature"
        ],  # Use configured temperature parameter
        generation_name="user_follow_ask_"  # Generation task name
        + str(outline_item_info.bid)
        + "_"
        + str(outline_item_info.position),
        messages=messages,  # Pass complete conversation history
        usage_context=usage_context,
        usage_scene=usage_scene,
    )

    response_text = ""  # Store complete response text
    # Stream process LLM response
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content
            # Return each text fragment in real-time
            yield RunMarkdownFlowDTO(
                outline_bid=outline_item_info.bid,
                generated_block_bid=log_script.generated_block_bid,
                type=GeneratedType.CONTENT,
                content=i.result,
            )

    # Log AI response to database
    log_script: LearnGeneratedBlock = init_generated_block(
        app,
        shifu_bid=outline_item_info.shifu_bid,
        outline_item_bid=outline_item_info.bid,
        progress_record_bid=attend_id,
        user_bid=user_info.user_id,
        block_type=BLOCK_TYPE_MDANSWER_VALUE,
        mdflow=response_text,
        block_index=last_position,
    )
    log_script.generated_content = response_text
    log_script.role = ROLE_TEACHER  # Mark as teacher role
    log_script.position = last_position
    db.session.add(log_script)

    # End trace span
    span.end(output=response_text)
    trace_args["output"] = trace_args["output"] + "\r\n" + response_text
    trace.update(**trace_args)
    db.session.flush()

    # Return end marker
    yield RunMarkdownFlowDTO(
        outline_bid=outline_item_info.bid,
        generated_block_bid=log_script.generated_block_bid,
        type=GeneratedType.BREAK,
        content="",
    )
