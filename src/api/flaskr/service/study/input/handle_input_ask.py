from typing import Generator
from flask import Flask
from flaskr.api.llm import chat_llm
from flaskr.service.study.const import ROLE_STUDENT, ROLE_TEACHER

from flaskr.service.study.models import LearnGeneratedBlock
from flaskr.service.study.plugin import register_shifu_input_handler
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.study.utils import (
    get_follow_up_info,
    make_script_dto,
    get_fmt_prompt,
)
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.llm.funcs import format_script_prompt
from flaskr.dao import db
from flaskr.service.study.input_funcs import (
    BreakException,
    check_text_with_llm_response,
    generation_attend,
)
from flaskr.service.user.models import User
from flaskr.service.lesson.const import UI_TYPE_ASK
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.study.context import RunScriptContext


@register_shifu_input_handler("ask")
@extensible_generic
def _handle_input_ask(
    app: Flask,
    user_info: User,
    attend_id: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> Generator[str, None, None]:
    """
    Main function to handle user Q&A input
    Responsible for processing user questions in the shifu and returning AI tutor responses
    """

    # Get follow-up information (including Q&A prompts and model configuration)
    follow_up_info = get_follow_up_info(
        app, outline_item_info.shifu_bid, block_dto, attend_id, is_preview
    )

    context = RunScriptContext.get_current_context(app)
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
    system_prompt_template = context.get_system_prompt(outline_item_info)
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

    # Obtain user configuration information to replace system variables
    user_profiles = get_user_profiles(
        app, user_info.user_id, outline_item_info.shifu_bid
    )

    # Format the system prompt and replace the variables within it
    system_message = (
        format_script_prompt(system_prompt, user_profiles) if system_prompt else ""
    )

    # Format shifu Q&A prompt, insert system prompt
    system_message = follow_up_info.ask_prompt.replace(
        "{shifu_system_message}", system_message
    )
    messages.append({"role": "system", "content": system_message})  # Add system message

    # Add historical conversation records to system messages
    for script in history_scripts:
        if script.role == ROLE_STUDENT:
            messages.append(
                {"role": "user", "content": script.script_content}
            )  # Add user message
        elif script.role == ROLE_TEACHER:
            messages.append(
                {"role": "assistant", "content": script.script_content}
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
    log_script: LearnGeneratedBlock = generation_attend(
        app, user_info, attend_id, outline_item_info, block_dto
    )
    log_script.generated_content = input
    log_script.role = ROLE_STUDENT  # Mark as student role
    log_script.type = UI_TYPE_ASK  # Mark as Q&A type
    db.session.add(log_script)

    # Create trace span
    span = trace.span(name="user_follow_up", input=input)

    # Format prompt for content checking
    prompt = get_fmt_prompt(
        app,
        user_info.user_id,
        outline_item_info.shifu_bid,
        follow_up_info.ask_prompt,
        input,
        follow_up_info.ask_prompt,
    )

    # Check if user input needs special processing (such as sensitive word filtering, etc.)
    res = check_text_with_llm_response(
        app,
        user_info,
        log_script,
        input,
        span,
        outline_item_info,
        block_dto,
        attend_id,
        prompt,
    )

    try:
        # If check result is not empty, return check result directly
        first_value = next(res)
        app.logger.info("check_text_by_edun is not None")
        yield first_value
        yield from res
        db.session.flush()
        raise BreakException  # Throw break exception to end processing
    except StopIteration:
        app.logger.info("check_text_by_edun is None ,invoke_llm")

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
        + outline_item_info.position
        + "_"
        + str(block_dto.bid)
        + "_"
        + str(outline_item_info.bid),
        messages=messages,  # Pass complete conversation history
    )

    response_text = ""  # Store complete response text
    # Stream process LLM response
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content
            # Return each text fragment in real-time
            yield make_script_dto(
                "text",
                i.result,
                log_script.block_bid,
                log_script.outline_item_bid,
                log_script.generated_block_bid,
            )

    # Log AI response to database
    log_script = generation_attend(
        app, user_info, attend_id, outline_item_info, block_dto
    )
    log_script.generated_content = response_text
    log_script.role = ROLE_TEACHER  # Mark as teacher role
    log_script.type = UI_TYPE_ASK  # Mark as Q&A type
    db.session.add(log_script)

    # End trace span
    span.end(output=response_text)
    trace_args["output"] = trace_args["output"] + "\r\n" + response_text
    trace.update(**trace_args)
    db.session.flush()

    # Return end marker
    yield make_script_dto(
        "text_end",
        "",
        log_script.block_bid,
        log_script.outline_item_bid,
        log_script.generated_block_bid,
    )
